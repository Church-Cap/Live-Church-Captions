import asyncio
import os
import platform
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import qrcode
from fastapi import Depends, FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import COOKIE_NAME, bootstrap_auth_store, create_session_token, get_auth_config, password_is_valid, require_operator, set_operator_password
from app.broadcast import CaptionHub
from app.glossary import Glossary
from app.models import CaptionSegment
from app.metrics import get_metrics
from app.exporting import segments_to_srt, segments_to_vtt, segments_to_json
from app.hardware import detect_hardware_acceleration, resolve_whisper_runtime
from app.profanity_filter import ProfanityFilter
from app.settings import get_settings
from app.networking import default_base_url, detected_local_hostname, local_ip
from app.runtime_config import load_runtime_config, set_audio_device, set_privacy_config, set_profanity_filter_config, set_translation_config, set_security_config
from app.i18n import SUPPORTED_LANGUAGES, get_client_ui_strings, normalise_language
from app.paths import app_support_dir
from app.transcript_store import TranscriptStore
from app.updater import fetch_remote_version, is_remote_newer, launch_update_process, update_script_for_system, version_label

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - audio package may be unavailable in demo installs
    sd = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]

settings = get_settings()
runtime_config = load_runtime_config()
hub = CaptionHub(
    retention_minutes=int(runtime_config.get("transcript_retention_minutes", settings.transcript_retention_minutes)),
    transcript_saving_enabled=bool(runtime_config.get("transcript_saving_enabled", settings.transcript_saving_enabled)),
)
hub.configure_translation(
    enabled=bool(runtime_config.get("translation_enabled", settings.translation_enabled)),
    provider=settings.translation_provider,
    allowed_languages=runtime_config.get("translation_allowed_languages", (settings.translation_allowed_languages or "en").split(",")),
    max_active_languages=int(runtime_config.get("translation_max_active_languages", settings.translation_max_active_languages)),
)
glossary = Glossary()
profanity_filter = ProfanityFilter()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


DOC_FILES = {
    "privacy": ("Privacy statement", "docs/legal/PRIVACY.md"),
    "disclaimer": ("Disclaimers", "docs/legal/DISCLAIMER.md"),
    "church-notice": ("Church notice wording", "docs/legal/NOTICE_TEMPLATE_FOR_CHURCHES.md"),
    "translation": ("Translation notes", "docs/translation.md"),
}

_transcription_task: asyncio.Task | None = None
_transcriber = None
_update_state = {"status": "idle"}


def base_url(request: Request | None = None) -> str:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    scheme = "https" if request is not None and request.url.scheme == "https" else "http"
    # In dual-port mode, QR codes and audience links must always point to the viewer port.
    port = settings.viewer_port if settings.dual_port_mode else (request.url.port if request is not None and request.url.port else settings.port)
    return default_base_url(port, scheme=scheme).rstrip("/")


def operator_base_url(request: Request | None = None) -> str:
    scheme = "https" if request is not None and request.url.scheme == "https" else "http"
    host = "localhost" if bool(load_runtime_config().get("lock_operator_to_localhost", settings.lock_operator_to_localhost)) else detected_local_hostname()
    port = settings.operator_port if settings.dual_port_mode else (request.url.port if request is not None and request.url.port else settings.port)
    return f"{scheme}://{host}:{port}"


def ip_base_url(request: Request | None = None) -> str:
    scheme = "https" if request is not None and request.url.scheme == "https" else "http"
    port = settings.viewer_port if settings.dual_port_mode else (request.url.port if request is not None and request.url.port else settings.port)
    return f"{scheme}://{local_ip()}:{port}"


def _transcript_storage_paths() -> tuple[Path, Path]:
    store = TranscriptStore()
    folder = store.encrypted_path.parent
    if store.encrypted_path.exists():
        return folder, store.encrypted_path
    if store.plaintext_fallback_path.exists():
        return folder, store.plaintext_fallback_path
    return folder, store.encrypted_path if store.encryption_available else store.plaintext_fallback_path


def _reveal_transcript_path(folder: Path, file_path: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Darwin":
        if file_path.exists():
            subprocess.Popen(["open", "-R", str(file_path)])
        else:
            subprocess.Popen(["open", str(folder)])
        return
    if system == "Windows":
        if file_path.exists():
            subprocess.Popen(["explorer", f"/select,{file_path}"])
        else:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(folder)])


def selected_audio_device():
    runtime = load_runtime_config()
    return runtime.get("audio_device") if runtime.get("audio_device") is not None else settings.audio_device


def auth_config():
    return get_auth_config(
        max_age_seconds=settings.session_max_age_seconds,
        env_password=settings.operator_password,
        env_secret=settings.session_secret,
    )


def base_template_context(request: Request | None = None) -> dict:
    context = {
        "church_name": settings.church_name,
        "app_version": settings.app_version,
        "app_version_label": settings.app_version_label,
        "feedback_email": settings.feedback_email,
    }
    if request is not None:
        context["request"] = request
    return context


def _request_port(request: Request) -> int | None:
    if request.url.port:
        return request.url.port
    host = request.headers.get("host", "")
    if ":" in host:
        try:
            return int(host.rsplit(":", 1)[1])
        except Exception:
            return None
    return None


PUBLIC_PREFIXES = ("/static/",)
PUBLIC_EXACT_PATHS = {"/", "/display", "/obs", "/qr.png", "/qr-ip.png", "/health", "/api/languages"}
PUBLIC_WS_PATHS = {"/ws/captions"}


def is_public_viewer_path(path: str) -> bool:
    return path in PUBLIC_EXACT_PATHS or path in PUBLIC_WS_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def is_local_client(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    return client_host in {"127.0.0.1", "::1", "localhost"}


def security_state(request: Request | None = None) -> dict:
    runtime = load_runtime_config()
    lock_localhost = bool(runtime.get("lock_operator_to_localhost", settings.lock_operator_to_localhost))
    dual = bool(settings.dual_port_mode)
    return {
        "dual_port_mode": dual,
        "viewer_port": settings.viewer_port if dual else settings.port,
        "operator_port": settings.operator_port if dual else settings.port,
        "lock_operator_to_localhost": lock_localhost,
        "security_mode": runtime.get("security_mode", "secure_operator"),
        "viewer_url": base_url(request),
        "viewer_ip_url": ip_base_url(request),
        "operator_url": operator_base_url(request),
        "offline_https_note": "Fully offline trusted HTTPS on visitor phones is not possible unless their device already trusts the certificate.",
        "data_dir": str(app_support_dir()),
    }


def update_capability_state() -> dict:
    system = platform.system()
    script = update_script_for_system(PROJECT_ROOT, system)
    return {
        "system": system,
        "supported": bool(script and script.exists()),
        "script": script.name if script else None,
        "current_version": settings.app_version,
        "current_version_label": settings.app_version_label,
    }




def create_transcriber():
    mode = settings.transcriber_mode.lower().strip()
    common = dict(
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        language=settings.language,
        audio_device=selected_audio_device(),
        sample_rate=settings.sample_rate,
        chunk_seconds=settings.chunk_seconds,
        stream_window_seconds=settings.stream_window_seconds,
        stream_update_interval_seconds=settings.stream_update_interval_seconds,
        stream_silence_finalise_seconds=settings.stream_silence_finalise_seconds,
        stream_min_rms=settings.stream_min_rms,
        stream_stability_passes=settings.stream_stability_passes,
        initial_prompt=settings.whisper_initial_prompt,
    )
    if mode in {"whisper", "openai_whisper", "openai-whisper"}:
        from app.transcription.whisper_live import WhisperLiveTranscriber
        return WhisperLiveTranscriber(**common, beam_size=settings.whisper_beam_size)
    if mode == "faster_whisper":
        from app.transcription.faster_whisper_live import FasterWhisperTranscriber
        return FasterWhisperTranscriber(**common, compute_type=settings.whisper_compute_type)
    raise RuntimeError(
        "Demo/mock captions have been disabled. "
        "Set TRANSCRIBER_MODE=whisper for accuracy-first local Whisper, or faster_whisper for the faster backend."
    )


async def transcription_loop():
    global _transcriber
    _transcriber = create_transcriber()
    hub.set_status("listening")
    try:
        async for segment in _transcriber.stream():
            runtime = load_runtime_config()
            filter_enabled = bool(runtime.get("profanity_filter_enabled", True))
            corrected = profanity_filter.apply(glossary.apply(segment.text), enabled=filter_enabled)
            raw_text = profanity_filter.apply(segment.raw_text or segment.text, enabled=filter_enabled)
            await hub.publish(
                CaptionSegment(
                    text=corrected,
                    raw_text=raw_text,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    is_final=segment.is_final,
                )
            )
    except asyncio.CancelledError:
        hub.set_status("stopped")
        raise
    except Exception as exc:
        hub.set_status("error")
        await hub.publish(CaptionSegment(text=f"Caption system error: {exc}", raw_text=str(exc), is_final=True))
    finally:
        if _transcriber is not None:
            await _transcriber.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_support_dir().mkdir(parents=True, exist_ok=True)
    (app_support_dir() / "data").mkdir(parents=True, exist_ok=True)
    bootstrap_auth_store(env_password=settings.operator_password, env_secret=settings.session_secret)
    yield
    global _transcription_task
    if _transcription_task:
        _transcription_task.cancel()
        try:
            await _transcription_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

@app.middleware("http")
async def security_boundary_middleware(request: Request, call_next):
    if not settings.dual_port_mode:
        return await call_next(request)

    path = request.url.path
    port = _request_port(request)

    # Public viewer port: only read-only viewer/display/OBS/static/health/language endpoints.
    if port == settings.viewer_port and not is_public_viewer_path(path):
        if request.method in {"GET", "HEAD"} and is_local_client(request):
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"{operator_base_url(request)}{path}{query}", status_code=307)
        return JSONResponse(
            {
                "detail": "Operator controls are not available on the public viewer port.",
                "operator_url": operator_base_url(request),
            },
            status_code=403,
        )

    runtime = load_runtime_config()
    lock_localhost = bool(runtime.get("lock_operator_to_localhost", settings.lock_operator_to_localhost))

    # Operator port can optionally be restricted to the local machine only.
    if port == settings.operator_port and lock_localhost and not is_local_client(request):
        return JSONResponse(
            {"detail": "Operator controls are locked to localhost on this installation."},
            status_code=403,
        )

    return await call_next(request)




@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "captions.html",
        {
            **base_template_context(request),
            "dnd_reminder": settings.dnd_reminder,
            "languages": SUPPORTED_LANGUAGES,
            "ui_strings": get_client_ui_strings(),
            "translation_state": hub.translation_state(),
        },
    )


@app.get("/display", response_class=HTMLResponse)
async def display(request: Request):
    return templates.TemplateResponse(
        "display.html",
        {"request": request, "church_name": settings.church_name},
    )


@app.get("/obs", response_class=HTMLResponse)
async def obs_overlay(request: Request):
    return templates.TemplateResponse(
        "obs.html",
        {"request": request, "church_name": settings.church_name},
    )


@app.get("/obs/help", response_class=HTMLResponse)
async def obs_help(request: Request, _: None = Depends(require_operator)):
    return templates.TemplateResponse(
        "obs_help.html",
        {"request": request, "church_name": settings.church_name, "obs_url": f"{base_url(request)}/obs"},
    )




@app.get("/docs/{doc_key}", response_class=HTMLResponse)
async def operator_doc(doc_key: str, request: Request, _: None = Depends(require_operator)):
    title, rel_path = DOC_FILES.get(doc_key, ("Document", "README.md"))
    path = PROJECT_ROOT / rel_path
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        content = "Document not found."
    return templates.TemplateResponse(
        "doc.html",
        {"request": request, "church_name": settings.church_name, "title": title, "content": content},
    )


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request, _: None = Depends(require_operator)):
    return templates.TemplateResponse("feedback.html", base_template_context(request))


@app.get("/setup/network", response_class=HTMLResponse)
async def setup_network_page(request: Request, _: None = Depends(require_operator)):
    return templates.TemplateResponse(
        "network_setup.html",
        {"request": request, "church_name": settings.church_name, "base_url": base_url(request)},
    )


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    config = auth_config()
    if not config.needs_setup:
        return RedirectResponse("/operator", status_code=303)
    return templates.TemplateResponse("setup.html", {**base_template_context(request), "error": None})


@app.post("/setup")
async def setup_operator(request: Request, password: str = Form(...), confirm_password: str = Form(...), security_mode: str = Form("secure_operator")):
    config = auth_config()
    if not config.needs_setup:
        return RedirectResponse("/operator", status_code=303)
    if password != confirm_password:
        return templates.TemplateResponse("setup.html", {**base_template_context(request), "error": "Passwords do not match."}, status_code=400)
    try:
        set_operator_password(password)
        set_security_config(security_mode)
    except ValueError as exc:
        return templates.TemplateResponse("setup.html", {**base_template_context(request), "error": str(exc)}, status_code=400)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if auth_config().needs_setup:
        return RedirectResponse("/setup", status_code=303)
    # Clear any stale cookie left from a previous server run so operators can
    # sign back in cleanly after Sunday-morning restarts.
    response = templates.TemplateResponse("login.html", {**base_template_context(request), "error": None})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    config = auth_config()
    if not password_is_valid(password, config):
        return templates.TemplateResponse(
            "login.html",
            {**base_template_context(request), "error": "Incorrect password."},
            status_code=401,
        )
    response = RedirectResponse("/operator", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(config),
        httponly=True,
        samesite="lax",
        max_age=config.max_age_seconds,
        secure=request.url.scheme == "https",
    )
    return response


@app.post("/logout")
async def logout(_: None = Depends(require_operator)):
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, _: None = Depends(require_operator)):
    return templates.TemplateResponse("account.html", {"request": request, "church_name": settings.church_name, "error": None, "success": None})


@app.post("/account/password")
async def change_operator_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    _: None = Depends(require_operator),
):
    config = auth_config()
    if not password_is_valid(current_password, config):
        return templates.TemplateResponse("account.html", {"request": request, "church_name": settings.church_name, "error": "Current password is incorrect.", "success": None}, status_code=400)
    if new_password != confirm_password:
        return templates.TemplateResponse("account.html", {"request": request, "church_name": settings.church_name, "error": "New passwords do not match.", "success": None}, status_code=400)
    try:
        set_operator_password(new_password)
    except ValueError as exc:
        return templates.TemplateResponse("account.html", {"request": request, "church_name": settings.church_name, "error": str(exc), "success": None}, status_code=400)
    response = templates.TemplateResponse("account.html", {"request": request, "church_name": settings.church_name, "error": None, "success": "Password changed. Please sign in again."})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/operator", response_class=HTMLResponse)
async def operator(request: Request, _: None = Depends(require_operator)):
    runtime = load_runtime_config()
    return templates.TemplateResponse(
        "operator.html",
        {
            **base_template_context(request),
            "caption_url": f"{base_url(request)}/",
            "caption_ip_url": f"{ip_base_url(request)}/",
            "display_url": f"{base_url(request)}/display",
            "obs_url": f"{base_url(request)}/obs",
            "detected_hostname": detected_local_hostname(),
            "operator_password_is_default": auth_config().needs_setup,
            "session_secret_is_default": False,
            "runtime": runtime,
            "languages": SUPPORTED_LANGUAGES,
            "translation_state": hub.translation_state(),
            "translation_provider": settings.translation_provider,
            "security": security_state(request),
        },
    )


@app.get("/qr.png")
async def qr(request: Request):
    img = qrcode.make(f"{base_url(request)}/")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.get("/qr-ip.png")
async def qr_ip(request: Request):
    """IP-address fallback QR for Android/guest Wi-Fi networks that do not resolve .local/mDNS."""
    img = qrcode.make(f"{ip_base_url(request)}/")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.get("/health")
async def health():
    return {
        "ok": True,
        "status": hub.state().status,
        "app_version": settings.app_version,
        "app_version_label": settings.app_version_label,
        "viewers": hub.viewer_count,
        "mode": settings.transcriber_mode,
        "audio_device": selected_audio_device(),
        "sensitive_mode": hub.sensitive_mode,
        "profanity_filter_enabled": bool(load_runtime_config().get("profanity_filter_enabled", True)),
        "hostname": detected_local_hostname(),
        "base_url": base_url(),
        "ip_base_url": ip_base_url(),
        "translation": hub.translation_state(),
        "security": security_state(),
    }


def _device_to_api(index: int, device: dict):
    name = str(device.get("name", f"Device {index}"))
    max_input_channels = int(device.get("max_input_channels", 0))
    default_sample_rate = int(float(device.get("default_samplerate", 0) or 0))
    return {
        "id": index,
        "name": name,
        "max_input_channels": max_input_channels,
        "default_sample_rate": default_sample_rate,
        "label": f"{index}: {name} ({max_input_channels} input ch)",
    }


@app.get("/api/audio-devices")
async def audio_devices(_: None = Depends(require_operator)):
    if sd is None:
        return {
            "ok": False,
            "error": "The sounddevice package is not available. Install requirements and PortAudio first.",
            "selected": selected_audio_device(),
            "devices": [],
        }
    try:
        devices = sd.query_devices()
        inputs = []
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) > 0:
                inputs.append(_device_to_api(index, device))
        default_input = None
        try:
            default_input = int(sd.default.device[0])
        except Exception:
            pass
        return {
            "ok": True,
            "selected": selected_audio_device(),
            "default_input": default_input,
            "devices": inputs,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "selected": selected_audio_device(), "devices": []}


@app.post("/api/audio-device")
async def set_audio_device_api(request: Request, _: None = Depends(require_operator)):
    body = await request.json()
    device = body.get("audio_device")
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    if device in {"", "default"}:
        device = None
    if sd is not None and device is not None:
        try:
            info = sd.query_devices(device)
            if int(info.get("max_input_channels", 0)) <= 0:
                return JSONResponse(
                    {"status": "error", "error": "That device is not an audio input. Choose a microphone or USB audio interface."},
                    status_code=400,
                )
        except Exception as exc:
            return JSONResponse(
                {"status": "error", "error": f"That audio input is no longer available: {exc}. Click Refresh, choose another input, and save again."},
                status_code=400,
            )
    cfg = set_audio_device(device)
    return {"status": "saved", "audio_device": cfg.get("audio_device")}


def _download_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@app.get("/transcript.txt", response_class=PlainTextResponse)
async def transcript(_: None = Depends(require_operator)):
    lines = [seg.text for seg in hub.final_segments()]
    return PlainTextResponse("\n".join(lines), headers=_download_headers("church-cap-current-session-transcript.txt"))


@app.get("/transcript.srt", response_class=PlainTextResponse)
async def transcript_srt(_: None = Depends(require_operator)):
    return PlainTextResponse(segments_to_srt(hub.final_segments()), media_type="application/x-subrip", headers=_download_headers("church-cap-current-session-transcript.srt"))


@app.get("/transcript.vtt", response_class=PlainTextResponse)
async def transcript_vtt(_: None = Depends(require_operator)):
    return PlainTextResponse(segments_to_vtt(hub.final_segments()), media_type="text/vtt", headers=_download_headers("church-cap-current-session-transcript.vtt"))


@app.get("/transcript.json")
async def transcript_json(_: None = Depends(require_operator)):
    return Response(segments_to_json(hub.final_segments()), media_type="application/json", headers=_download_headers("church-cap-current-session-transcript.json"))


@app.get("/api/status")
async def api_status(_: None = Depends(require_operator)):
    state = hub.state()
    return {
        "status": state.status,
        "viewers": state.viewers,
        "sensitive_mode": state.sensitive_mode,
        "current": state.current.model_dump(mode="json") if state.current else None,
        "transcript_count": len(hub.final_segments()),
        "metrics": get_metrics(),
        "settings": {
            "model": settings.whisper_model,
            "transcriber_mode": settings.transcriber_mode,
            "device": settings.whisper_device,
            "compute_type": settings.whisper_compute_type,
            "beam_size": settings.whisper_beam_size,
            "resolved_whisper_runtime": dict(
                zip(
                    ("device", "compute_type"),
                    resolve_whisper_runtime(settings.whisper_device, settings.whisper_compute_type),
                )
            ),
            "hardware_acceleration": detect_hardware_acceleration().as_dict(),
            "stream_window_seconds": settings.stream_window_seconds,
            "stream_update_interval_seconds": settings.stream_update_interval_seconds,
            "stream_stability_passes": settings.stream_stability_passes,
            "audio_device": selected_audio_device(),
        },
        "translation": hub.translation_state(),
        "security": security_state(),
        "update": {**update_capability_state(), "state": _update_state},
        "profanity_filter_enabled": bool(load_runtime_config().get("profanity_filter_enabled", True)),
    }


@app.post("/api/update/check")
async def check_for_update(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {
                "status": "error",
                "error": "Check for updates from the Church Cap computer.",
                **update_capability_state(),
            },
            status_code=403,
        )
    capability = update_capability_state()
    if not capability["supported"]:
        return JSONResponse(
            {"status": "error", "error": f"Updates are not configured for {capability['system']}.", **capability},
            status_code=400,
        )
    try:
        remote_version = await asyncio.to_thread(fetch_remote_version)
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "error": f"Could not check GitHub for updates: {exc}", **capability},
            status_code=502,
        )
    update_available = is_remote_newer(remote_version, settings.app_version)
    status = "update_available" if update_available else "up_to_date"
    return {
        **capability,
        "status": status,
        "update_available": update_available,
        "remote_version": remote_version,
        "remote_version_label": version_label(remote_version),
    }


@app.post("/api/update/start")
async def start_update(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Start updates from the Church Cap computer.", **update_capability_state()},
            status_code=403,
        )
    body = await request.json()
    if not bool(body.get("confirm")):
        return JSONResponse({"status": "error", "error": "Update was not confirmed."}, status_code=400)
    capability = update_capability_state()
    if not capability["supported"]:
        return JSONResponse(
            {"status": "error", "error": f"Updates are not configured for {capability['system']}.", **capability},
            status_code=400,
        )
    try:
        remote_version = await asyncio.to_thread(fetch_remote_version)
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "error": f"Could not check GitHub for updates: {exc}", **capability},
            status_code=502,
        )
    if not is_remote_newer(remote_version, settings.app_version):
        return {
            **capability,
            "status": "up_to_date",
            "update_available": False,
            "remote_version": remote_version,
            "remote_version_label": version_label(remote_version),
        }
    global _update_state
    _update_state = {
        "status": "starting",
        "remote_version": remote_version,
        "remote_version_label": version_label(remote_version),
    }
    try:
        process = await asyncio.to_thread(launch_update_process, PROJECT_ROOT, remote_version)
    except Exception as exc:
        _update_state = {"status": "error", "error": str(exc)}
        return JSONResponse({"status": "error", "error": str(exc), **capability}, status_code=500)
    _update_state = {**_update_state, "status": "updating", **process}
    return {
        **capability,
        "status": "updating",
        "update_available": True,
        "remote_version": remote_version,
        "remote_version_label": version_label(remote_version),
        **process,
    }


@app.post("/api/start")
async def start(_: None = Depends(require_operator)):
    global _transcription_task
    if _transcription_task and not _transcription_task.done():
        return {"status": "already_running"}
    _transcription_task = asyncio.create_task(transcription_loop())
    return {"status": "started"}


@app.post("/api/stop")
async def stop(_: None = Depends(require_operator)):
    global _transcription_task
    if _transcription_task and not _transcription_task.done():
        _transcription_task.cancel()
        try:
            await _transcription_task
        except asyncio.CancelledError:
            pass
    hub.set_status("stopped")
    return {"status": "stopped"}


@app.post("/api/clear")
async def clear(_: None = Depends(require_operator)):
    await hub.clear()
    return {"status": "cleared"}


@app.post("/api/transcript-location")
async def open_transcript_location(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        folder, file_path = _transcript_storage_paths()
        return JSONResponse(
            {
                "status": "error",
                "error": "Open this from the Church Cap computer to reveal the local transcript folder.",
                "path": str(folder),
                "file": str(file_path),
            },
            status_code=403,
        )
    folder, file_path = _transcript_storage_paths()
    try:
        _reveal_transcript_path(folder, file_path)
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "error": str(exc), "path": str(folder), "file": str(file_path)},
            status_code=500,
        )
    return {"status": "opened", "path": str(folder), "file": str(file_path)}


def reset_transcriber_buffer() -> None:
    if _transcriber is not None and hasattr(_transcriber, "reset_buffer"):
        try:
            _transcriber.reset_buffer()
        except Exception:
            pass


@app.post("/api/sensitive-on")
async def sensitive_on(_: None = Depends(require_operator)):
    reset_transcriber_buffer()
    await hub.set_sensitive_mode(True)
    return {"status": "sensitive_on"}


@app.post("/api/sensitive-off")
async def sensitive_off(_: None = Depends(require_operator)):
    reset_transcriber_buffer()
    await hub.set_sensitive_mode(False)
    reset_transcriber_buffer()
    return {"status": "sensitive_off"}


@app.post("/api/security")
async def update_security(request: Request, _: None = Depends(require_operator)):
    body = await request.json()
    mode = str(body.get("security_mode") or "secure_operator")
    lock = body.get("lock_operator_to_localhost")
    cfg = set_security_config(mode, None if lock is None else bool(lock))
    return {"status": "saved", "restart_recommended": True, **security_state(request), "runtime": cfg}


@app.post("/api/privacy")
async def update_privacy(request: Request, _: None = Depends(require_operator)):
    body = await request.json()
    save_transcripts = bool(body.get("transcript_saving_enabled"))
    retention_minutes = int(body.get("transcript_retention_minutes", 120))
    cfg = set_privacy_config(save_transcripts, retention_minutes)
    hub.configure_retention(
        retention_minutes=int(cfg["transcript_retention_minutes"]),
        transcript_saving_enabled=bool(cfg["transcript_saving_enabled"]),
    )
    await hub.broadcast_retention_state()
    return {"status": "saved", **hub.retention_state()}


@app.post("/api/profanity-filter")
async def update_profanity_filter(request: Request, _: None = Depends(require_operator)):
    body = await request.json()
    cfg = set_profanity_filter_config(bool(body.get("profanity_filter_enabled")))
    return {"status": "saved", "profanity_filter_enabled": bool(cfg["profanity_filter_enabled"])}


@app.post("/api/translation")
async def update_translation(request: Request, _: None = Depends(require_operator)):
    body = await request.json()
    enabled = bool(body.get("translation_enabled"))
    allowed = body.get("translation_allowed_languages") or ["en"]
    if not isinstance(allowed, list):
        allowed = ["en"]
    allowed = [normalise_language(x) for x in allowed]
    max_active = int(body.get("translation_max_active_languages", 1))
    cfg = set_translation_config(enabled, allowed, max_active)
    hub.configure_translation(
        enabled=bool(cfg["translation_enabled"]),
        provider=settings.translation_provider,
        allowed_languages=cfg["translation_allowed_languages"],
        max_active_languages=int(cfg["translation_max_active_languages"]),
    )
    return {"status": "saved", **hub.translation_state()}




@app.get("/api/translation/status")
async def translation_status(_: None = Depends(require_operator)):
    return hub.translation_state()

@app.get("/api/languages")
async def languages():
    return {
        "languages": SUPPORTED_LANGUAGES,
        "ui_strings": get_client_ui_strings(),
        "translation": hub.translation_state(),
    }


@app.post("/api/test-caption")
async def test_caption(_: None = Depends(require_operator)):
    filter_enabled = bool(load_runtime_config().get("profanity_filter_enabled", True))
    text = profanity_filter.apply(glossary.apply("Please turn with me to Efficiency chapter two and listen to the Word of God."), enabled=filter_enabled)
    await hub.publish(CaptionSegment(text=text, raw_text=text, is_final=True))
    return {"status": "sent", "text": text}


@app.websocket("/ws/captions")
async def ws_captions(websocket: WebSocket):
    language = normalise_language(websocket.query_params.get("lang"))
    await hub.connect(websocket, language=language)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)
