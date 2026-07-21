import asyncio
import base64
import io
import inspect
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import COOKIE_NAME, bootstrap_auth_store, create_session_token, get_auth_config, password_is_valid, require_operator, set_operator_password
from app.broadcast import CaptionHub
from app.glossary import Glossary
from app.models import CaptionSegment
from app.metrics import (
    clear_service_metrics,
    finish_service_metrics,
    get_metrics,
    get_service_metrics,
    get_service_metrics_report,
    initialise_service_metrics_storage,
    record_system_sample,
    record_viewer_counts,
    service_report_payload,
    start_service_metrics,
)
from app.exporting import segments_to_srt, segments_to_vtt, segments_to_json
from app.hardware import HardwareAccelerationStatus, detect_hardware_acceleration, resolve_whisper_runtime
from app.deployment import deployment_context
from app.profanity_filter import ProfanityFilter
from app.settings import get_settings
from app.networking import default_base_url, detected_local_hostname, local_ip
from app.runtime_config import load_runtime_config, set_audio_device, set_performance_config, set_privacy_config, set_profanity_filter_config, set_translation_config, set_security_config
from app.i18n import LANGUAGE_BY_CODE, SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, normalise_language
from app.localisation import get_client_ui_language_strings, get_client_ui_sources, get_client_ui_strings, get_runtime_translated_client_ui_strings
from app.paths import app_support_dir
from app.service_leader_auth import SERVICE_LEADER_COOKIE_NAME, ServiceLeaderAccessManager, ServiceLeaderSession
from app.platforms import performance_platform_key
from app.storage import clear_storage_candidates, rotate_log_file, rotate_runtime_logs, storage_snapshot, tail_log_lines
from app.transcript_store import TranscriptStore
from app.updater import fetch_remote_version, is_remote_newer, launch_update_process, poll_update_process_state, update_script_for_system, version_label

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - audio package may be unavailable in demo installs
    sd = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def safe_hardware_acceleration() -> dict:
    try:
        return detect_hardware_acceleration().as_dict()
    except Exception as exc:
        return {
            "platform": platform.system(),
            "cuda_available": False,
            "cuda_device_count": 0,
            "cuda_runtime_ready": False,
            "missing_cuda_libraries": [],
            "nvidia_smi_available": False,
            "message": f"Hardware detection failed; using safe CPU fallback: {exc}",
            "nvidia_driver_status": "unknown",
            "nvidia_gpu_names": [],
            "ctranslate2_cuda_status": "unknown",
            "cuda_runtime_status": "unknown",
            "fallback_mode": "CPU / int8",
        }


def safe_hardware_status_object() -> HardwareAccelerationStatus:
    try:
        return detect_hardware_acceleration()
    except Exception as exc:
        return HardwareAccelerationStatus(
            platform=platform.system(),
            cuda_available=False,
            cuda_device_count=0,
            cuda_runtime_ready=False,
            missing_cuda_libraries=[],
            nvidia_smi_available=False,
            message=f"Hardware detection failed; using safe CPU fallback: {exc}",
            nvidia_driver_status="unknown",
            nvidia_gpu_names=[],
            ctranslate2_cuda_status="unknown",
            cuda_runtime_status="unknown",
            fallback_mode="CPU / int8",
        )


def safe_deployment_context(hardware: dict | None = None) -> dict:
    try:
        return deployment_context(hardware or safe_hardware_acceleration())
    except Exception as exc:
        return {
            "identity": {
                "mode": "desktop",
                "profile": "desktop",
                "appliance_id": None,
                "edition": "desktop",
                "language_mode": "full",
                "source": f"fallback: {exc}",
            },
            "capabilities": {
                "profile": "desktop",
                "is_appliance": False,
                "simple_operator": False,
                "show_model_slider": True,
                "show_performance_advanced": True,
                "show_translation_setup": True,
                "show_translation_install": True,
                "allow_translation": True,
                "language_mode": "full",
                "recommended_max_languages": None,
                "translation_max_limit": None,
                "translation_advanced": False,
                "cpu_translation_warning": False,
                "cpu_translation_available": False,
                "cpu_translation_enabled": False,
                "gpu_required_for_languages": False,
                "gpu_available": False,
                "message": f"Deployment detection failed; using safe desktop fallback: {exc}",
            },
        }


def language_request_items() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for code, request in sorted(_language_requests.items(), key=lambda item: (-int(item[1].get("count", 0)), item[0])):
        language = LANGUAGE_BY_CODE.get(code, {"code": code, "name": code.upper(), "native": code.upper(), "flag": ""})
        items.append({
            "code": code,
            "count": int(request.get("count", 0)),
            "last_requested_at": request.get("last_requested_at"),
            "language": language,
        })
    return items


def language_requests_enabled() -> bool:
    return bool(load_runtime_config().get("translation_language_requests_enabled", True))


def submit_language_request(code: str) -> dict[str, object]:
    if not language_requests_enabled():
        raise HTTPException(status_code=403, detail="Language requests are currently disabled by the operator.")
    code = normalise_language(code)
    if code == SOURCE_LANGUAGE or code not in LANGUAGE_BY_CODE:
        raise HTTPException(status_code=400, detail="Choose a supported translated language.")
    state = safe_translation_state()
    requestable = set(state.get("requestable_languages") or [])
    if code not in requestable:
        raise HTTPException(status_code=409, detail="That language is already available or is not installed for this translation mode.")
    request = _language_requests.setdefault(code, {"code": code, "count": 0})
    request["count"] = int(request.get("count", 0)) + 1
    request["last_requested_at"] = datetime.now(timezone.utc).isoformat()
    return request


def prune_language_requests_for_allowed(allowed_languages: list[str] | set[str]) -> None:
    allowed = {normalise_language(code) for code in allowed_languages}
    for code in list(_language_requests):
        if code in allowed:
            _language_requests.pop(code, None)


def safe_translation_state() -> dict:
    try:
        state = dict(hub.translation_state())
        requests_enabled = language_requests_enabled()
        if not requests_enabled:
            state["requestable_languages"] = []
        prune_language_requests_for_allowed(set(state.get("allowed_languages") or []))
        state["language_requests_enabled"] = requests_enabled
        state["language_requests"] = language_request_items() if requests_enabled else []
        allowed_by_deployment, deployment = translation_allowed_for_current_deployment()
        capabilities = deployment.get("capabilities", {})
        limit = capabilities.get("translation_max_limit")
        if isinstance(limit, int) and limit > 0:
            state["max_active_languages"] = min(int(state.get("max_active_languages") or limit), limit)
        if not allowed_by_deployment:
            message = capabilities.get("message") or "Translated captions are not enabled for this appliance profile."
            state.update({
                "enabled": False,
                "provider_status": {
                    **dict(state.get("provider_status") or {}),
                    "ready": False,
                    "message": message,
                },
                "active_translated_languages": [],
                "available_languages": [SOURCE_LANGUAGE],
                "requestable_languages": [],
                "language_requests_enabled": requests_enabled,
                "language_requests": [],
                "max_active_languages": 1,
            })
        return state
    except Exception as exc:
        return {
            "enabled": False,
            "provider": "disabled",
            "provider_status": {"provider": "disabled", "ready": False, "message": f"Translation status failed: {exc}"},
            "allowed_languages": [SOURCE_LANGUAGE],
            "max_active_languages": 1,
            "language_policy": "automatic",
            "priority_mode": "most_viewers",
            "viewer_languages": {},
            "active_translated_languages": [],
            "scheduler": {
                "scheduler_type": "bounded_fair_per_language",
                "queue_capacity_per_language": settings.translation_queue_capacity_per_language,
                "queue_depths": {},
                "oldest_final_age_seconds": {},
                "degraded_languages": [],
            },
            "resources": {},
            "available_languages": [SOURCE_LANGUAGE],
            "requestable_languages": [],
            "language_requests_enabled": True,
            "language_requests": [],
        }


settings = get_settings()
runtime_config = load_runtime_config()
startup_deployment = safe_deployment_context(safe_hardware_acceleration())
startup_capabilities = startup_deployment.get("capabilities", {})
startup_translation_allowed = bool(startup_capabilities.get("allow_translation", True))
startup_translation_max_active = int(runtime_config.get("translation_max_active_languages", settings.translation_max_active_languages))
startup_translation_limit = startup_capabilities.get("translation_max_limit")
if isinstance(startup_translation_limit, int) and startup_translation_limit > 0:
    startup_translation_max_active = min(startup_translation_max_active, startup_translation_limit)
hub = CaptionHub(
    retention_minutes=int(runtime_config.get("transcript_retention_minutes", settings.transcript_retention_minutes)),
    transcript_saving_enabled=bool(runtime_config.get("transcript_saving_enabled", settings.transcript_saving_enabled)),
    translation_queue_capacity_per_language=settings.translation_queue_capacity_per_language,
)
hub.configure_translation(
    enabled=startup_translation_allowed and bool(runtime_config.get("translation_enabled", settings.translation_enabled)),
    provider=runtime_config.get("translation_provider") or settings.translation_provider,
    allowed_languages=runtime_config.get("translation_allowed_languages", (settings.translation_allowed_languages or "en").split(",")),
    max_active_languages=startup_translation_max_active,
    language_policy=runtime_config.get("translation_language_policy", "automatic"),
    priority_mode=runtime_config.get("translation_priority_mode", "most_viewers"),
    timing_mode=runtime_config.get("translation_timing_mode", "responsive"),
)
glossary = Glossary()
profanity_filter = ProfanityFilter()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
_TEMPLATE_RESPONSE_ACCEPTS_REQUEST = "request" in inspect.signature(templates.TemplateResponse).parameters


def template_response(name: str, context: dict, **kwargs):
    """Render with both legacy and current Starlette TemplateResponse signatures."""
    request = context.get("request")
    if _TEMPLATE_RESPONSE_ACCEPTS_REQUEST:
        if request is None:
            raise ValueError("Template context must include the current request.")
        return templates.TemplateResponse(request=request, name=name, context=context, **kwargs)
    return templates.TemplateResponse(name, context, **kwargs)


DOC_FILES = {
    "privacy": ("Privacy statement", "docs/legal/PRIVACY.md"),
    "disclaimer": ("Disclaimers", "docs/legal/DISCLAIMER.md"),
    "church-notice": ("Church notice wording", "docs/legal/NOTICE_TEMPLATE_FOR_CHURCHES.md"),
    "translation": ("Translation notes", "docs/translation.md"),
}

_transcription_task: asyncio.Task | None = None
_transcriber = None
_update_state = {"status": "idle"}
_update_process: subprocess.Popen | None = None
_client_ui_runtime_translation_cache: dict[tuple[str, str], dict[str, str]] = {}
_cuda_runtime_install_state = {"status": "idle"}
_cuda_runtime_install_process: subprocess.Popen | None = None
_translation_install_state = {"status": "idle"}
_translation_install_process: subprocess.Popen | None = None
_language_requests: dict[str, dict[str, object]] = {}
CUDA_RUNTIME_LOG_LABEL = "logs/cuda-runtime-install.log"
TRANSLATION_INSTALL_LOG_LABEL = "logs/translation-install.log"
UPDATE_LOG_LABEL = "logs/update.log"
service_leader_access = ServiceLeaderAccessManager()

DOWNLOAD_HANDOFF_TTL_SECONDS = 10 * 60
_download_handoff_tokens: dict[str, dict[str, object]] = {}



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


def service_leader_base_url(request: Request | None = None) -> str:
    scheme = "https" if request is not None and request.url.scheme == "https" else "http"
    port = settings.operator_port if settings.dual_port_mode else (request.url.port if request is not None and request.url.port else settings.port)
    return f"{scheme}://{local_ip()}:{port}"


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


PERFORMANCE_PRESETS = {
    "fastest": {
        "label": "Fastest, less accurate",
        "description": "Lowest delay for older PCs. Best for testing or slower hardware.",
        "transcriber_mode": "faster_whisper",
        "whisper_model": "tiny.en",
        "whisper_compute_type": "auto",
        "whisper_beam_size": 1,
        "chunk_seconds": 1.0,
        "stream_window_seconds": 3.5,
        "stream_update_interval_seconds": 0.6,
        "stream_silence_finalise_seconds": 0.8,
        "stream_stability_passes": 1,
    },
    "fast": {
        "label": "Fast",
        "description": "Quick captions with better wording than tiny on most speech.",
        "transcriber_mode": "faster_whisper",
        "whisper_model": "base.en",
        "whisper_compute_type": "auto",
        "whisper_beam_size": 1,
        "chunk_seconds": 1.25,
        "stream_window_seconds": 4.5,
        "stream_update_interval_seconds": 0.8,
        "stream_silence_finalise_seconds": 1.0,
        "stream_stability_passes": 1,
    },
    "balanced": {
        "label": "Balanced",
        "description": "Recommended starting point for live church services.",
        "transcriber_mode": "faster_whisper",
        "whisper_model": "base.en",
        "whisper_compute_type": "auto",
        "whisper_beam_size": 1,
        "chunk_seconds": 1.5,
        "stream_window_seconds": 6.0,
        "stream_update_interval_seconds": 1.0,
        "stream_silence_finalise_seconds": 1.25,
        "stream_stability_passes": 2,
    },
    "accurate": {
        "label": "Accurate",
        "description": "More context and stability, with a little more delay.",
        "transcriber_mode": "faster_whisper",
        "whisper_model": "small.en",
        "whisper_compute_type": "auto",
        "whisper_beam_size": 1,
        "chunk_seconds": 2.0,
        "stream_window_seconds": 8.0,
        "stream_update_interval_seconds": 1.2,
        "stream_silence_finalise_seconds": 1.45,
        "stream_stability_passes": 2,
    },
    "most_accurate": {
        "label": "Slowest, most accurate",
        "description": "Uses the medium Whisper model. Best for powerful systems; benchmark it before relying on it live.",
        "transcriber_mode": "whisper",
        "whisper_model": "medium.en",
        "whisper_compute_type": "auto",
        "whisper_beam_size": 5,
        "chunk_seconds": 2.0,
        "stream_window_seconds": 10.0,
        "stream_update_interval_seconds": 1.5,
        "stream_silence_finalise_seconds": 1.7,
        "stream_stability_passes": 2,
    },
}


def effective_performance_config(runtime: dict | None = None) -> dict:
    runtime = runtime or load_runtime_config()
    preset_key = runtime.get("performance_preset")
    if preset_key == "custom":
        preset = {**PERFORMANCE_PRESETS["balanced"], "label": "Custom", "description": "Advanced settings chosen by the operator."}
    else:
        preset_key = preset_key if preset_key in PERFORMANCE_PRESETS else "balanced"
        preset = PERFORMANCE_PRESETS[preset_key]
    cfg = {
        "performance_preset": preset_key,
        "performance_platform": runtime.get("performance_platform") if runtime.get("performance_platform") in {"auto", "macos", "windows", "linux"} else "auto",
        "performance_label": preset["label"],
        "performance_description": preset["description"],
        "transcriber_mode": settings.transcriber_mode,
        "whisper_model": settings.whisper_model,
        "whisper_device": settings.whisper_device,
        "whisper_compute_type": settings.whisper_compute_type,
        "whisper_beam_size": settings.whisper_beam_size,
        "chunk_seconds": settings.chunk_seconds,
        "stream_window_seconds": settings.stream_window_seconds,
        "stream_update_interval_seconds": settings.stream_update_interval_seconds,
        "stream_silence_finalise_seconds": settings.stream_silence_finalise_seconds,
        "stream_stability_passes": settings.stream_stability_passes,
    }
    for key, value in preset.items():
        if key not in {"label", "description"}:
            cfg[key] = value
    for key in (
        "performance_platform",
        "transcriber_mode",
        "whisper_model",
        "whisper_device",
        "whisper_compute_type",
        "whisper_beam_size",
        "chunk_seconds",
        "stream_window_seconds",
        "stream_update_interval_seconds",
        "stream_silence_finalise_seconds",
        "stream_stability_passes",
    ):
        if runtime.get(key) is not None:
            cfg[key] = runtime[key]
    effective_platform = performance_platform_key() if cfg["performance_platform"] == "auto" else cfg["performance_platform"]
    if (
        effective_platform == "windows"
        and cfg["performance_preset"] == "most_accurate"
        and cfg["transcriber_mode"] == "whisper"
    ):
        cfg["transcriber_mode"] = "faster_whisper"
        cfg["whisper_beam_size"] = 1
    return cfg



def translation_allowed_for_current_deployment(hardware: dict | None = None) -> tuple[bool, dict]:
    deployment = safe_deployment_context(hardware or safe_hardware_acceleration())
    capabilities = deployment.get("capabilities", {})
    return bool(capabilities.get("allow_translation", True)), deployment


def translation_limit_for_deployment(deployment: dict) -> int | None:
    limit = deployment.get("capabilities", {}).get("translation_max_limit")
    return limit if isinstance(limit, int) and limit > 0 else None


def clamp_translation_max_for_deployment(value: int, deployment: dict) -> int:
    limit = translation_limit_for_deployment(deployment)
    value = max(1, int(value))
    return min(value, limit) if limit else value

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
        "deployment": safe_deployment_context(safe_hardware_acceleration()),
    }
    if request is not None:
        context["request"] = request
    return context


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _qr_data_uri(value: str) -> str:
    image = qrcode.make(value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def require_service_leader(request: Request) -> ServiceLeaderSession:
    touch = request.method != "GET" or request.url.path == "/service-leader"
    session = service_leader_access.verify_session(request.cookies.get(SERVICE_LEADER_COOKIE_NAME), touch=touch)
    if session is None:
        if request.url.path == "/service-leader":
            raise HTTPException(status_code=303, headers={"Location": "/service-leader/pair"})
        raise HTTPException(status_code=401, detail="Service leader pairing required")
    return session


def require_service_leader_mutation(request: Request, session: ServiceLeaderSession) -> None:
    csrf = request.headers.get("x-csrf-token")
    if not service_leader_access.csrf_is_valid(session, csrf):
        raise HTTPException(status_code=403, detail="Invalid service leader request token")
    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(status_code=403, detail="Missing request origin")
    expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if origin.rstrip("/") != expected_origin.rstrip("/"):
        raise HTTPException(status_code=403, detail="Request origin did not match Church Cap")


def service_leader_language_context() -> dict:
    runtime = load_runtime_config()
    _allowed_by_deployment, deployment = translation_allowed_for_current_deployment()
    provider = str(runtime.get("translation_provider") or settings.translation_provider or "disabled")
    provider_codes = set(hub.translator.supported_languages_for_provider(provider))
    selected_codes = {
        code
        for code in runtime.get("translation_allowed_languages", ["en"])
        if code != SOURCE_LANGUAGE and code in provider_codes
    }
    language_policy = str(runtime.get("translation_language_policy") or "automatic")
    requests_enabled = bool(runtime.get("translation_language_requests_enabled", True))
    if language_policy == "restricted":
        visible_codes = selected_codes
        requestable_codes = provider_codes - selected_codes - {SOURCE_LANGUAGE} if requests_enabled else set()
    else:
        visible_codes = provider_codes - {SOURCE_LANGUAGE}
        requestable_codes = set()
    available = [language for language in SUPPORTED_LANGUAGES if language["code"] in visible_codes]
    requestable = [language for language in SUPPORTED_LANGUAGES if language["code"] in requestable_codes]
    return {
        "translation_enabled": bool(runtime.get("translation_enabled")) and provider != "disabled",
        "translation_provider": provider,
        "translation_provider_ready": bool(hub.translator.provider_status(provider).get("ready")),
        "translation_max_active_languages": clamp_translation_max_for_deployment(int(runtime.get("translation_max_active_languages", 2)), deployment),
        "translation_language_policy": language_policy,
        "translation_language_requests_enabled": requests_enabled,
        "available_languages": available,
        "requestable_languages": requestable,
        "language_requests": language_request_items() if requests_enabled else [],
        "selected_languages": sorted(selected_codes),
    }


def service_leader_audio_context() -> dict:
    selected = selected_audio_device()
    if sd is None:
        return {"ok": False, "selected": selected, "devices": [], "error": "Audio support is not available."}
    try:
        devices = [
            _device_to_api(index, device)
            for index, device in enumerate(sd.query_devices())
            if int(device.get("max_input_channels", 0)) > 0
        ]
        return {"ok": True, "selected": selected, "devices": devices}
    except Exception as exc:
        return {"ok": False, "selected": selected, "devices": [], "error": str(exc)}


def caption_health_snapshot() -> dict:
    metrics = get_metrics()
    performance = effective_performance_config()
    system_perf = system_performance_snapshot()
    transcription = metrics.get("last_transcription_seconds")
    transcription = float(transcription) if transcription is not None else None
    update_interval = float(performance.get("stream_update_interval_seconds") or 0)
    live_delay = None if transcription is None else transcription + update_interval
    if live_delay is None:
        level, label = "unknown", "Waiting"
        message = "Start captions and speak normally to build a useful delay estimate."
    elif live_delay < 2.5:
        level, label = "healthy", "Healthy"
        message = "Caption delay is in a healthy range for live use."
    elif live_delay <= 3.5:
        level, label = "attention", "Needs attention"
        message = "Captions are usable, but the operator may be able to reduce the delay."
    else:
        level, label = "poor", "Slow"
        message = "Caption delay is high. Open the improvement guide and ask the operator to tune performance."
    backend = "Faster Whisper" if performance.get("transcriber_mode") == "faster_whisper" else "OpenAI Whisper"
    system_load = system_perf.get("cpu_percent")
    if system_load is None:
        system_load = system_perf.get("load_1m_percent")
    translation_latency = metrics.get("last_translation_seconds")
    try:
        translation_latency = None if translation_latency is None else float(translation_latency)
    except (TypeError, ValueError):
        translation_latency = None
    translation_delay = None
    if live_delay is not None and translation_latency is not None:
        translation_delay = live_delay + translation_latency
    return {
        "level": level,
        "label": label,
        "message": message,
        "live_delay_seconds": live_delay,
        "translation_delay_seconds": translation_delay,
        "transcription_seconds": transcription,
        "system_load_percent": system_load,
        "runtime_label": f"{backend} · {performance.get('whisper_model', 'unknown')}",
    }


def _request_port(request: Request) -> int | None:
    server = request.scope.get("server")
    if isinstance(server, (tuple, list)) and len(server) >= 2:
        try:
            return int(server[1])
        except (TypeError, ValueError):
            pass
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
PUBLIC_EXACT_PATHS = {"/", "/display", "/obs", "/qr.png", "/qr-ip.png", "/health", "/api/languages", "/api/language-requests"}
PUBLIC_WS_PATHS = {"/ws/captions"}
REMOTE_SERVICE_LEADER_PREFIXES = ("/service-leader/", "/download-handoff/", "/download-handoff-qr/", "/static/")


def is_public_viewer_path(path: str) -> bool:
    return path in PUBLIC_EXACT_PATHS or path in PUBLIC_WS_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def is_remote_service_leader_path(path: str) -> bool:
    return (
        path == "/service-leader"
        or path == "/pastor"
        or path.startswith("/pastor/")
        or any(path.startswith(prefix) for prefix in REMOTE_SERVICE_LEADER_PREFIXES)
    )


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
        "service_leader_url": f"{service_leader_base_url(request)}/service-leader",
        "offline_https_note": "Fully offline trusted HTTPS on visitor phones is not possible unless their device already trusts the certificate.",
        "data_dir": str(app_support_dir()),
    }


def update_capability_state() -> dict:
    global _update_state
    system = platform.system()
    script = update_script_for_system(PROJECT_ROOT, system)
    state = poll_update_process_state(_update_state, _update_process, UPDATE_LOG_LABEL)
    _update_state = {key: value for key, value in state.items() if key != "log"}
    return {
        "system": system,
        "supported": bool(script and script.exists()),
        "script": script.name if script else None,
        "current_version": settings.app_version,
        "current_version_label": settings.app_version_label,
        "state": state,
    }


def cuda_runtime_capability_state() -> dict:
    global _cuda_runtime_install_state
    system = platform.system()
    script = PROJECT_ROOT / "scripts" / "install-cuda-runtime-windows.ps1"
    if _cuda_runtime_install_state.get("status") == "installing" and _cuda_runtime_install_process is not None:
        return_code = _cuda_runtime_install_process.poll()
        if return_code is not None:
            if return_code == 0:
                _cuda_runtime_install_state = {
                    **_cuda_runtime_install_state,
                    "status": "complete",
                    "message": "CUDA runtime force reinstall finished. Restart Church Cap, then check CUDA again.",
                    "return_code": return_code,
                }
            else:
                _cuda_runtime_install_state = {
                    **_cuda_runtime_install_state,
                    "status": "error",
                    "error": f"CUDA runtime force reinstall exited with code {return_code}. Check logs/cuda-runtime-install.log.",
                    "return_code": return_code,
                }
    state = {**_cuda_runtime_install_state}
    if "log" in state:
        state["log"] = CUDA_RUNTIME_LOG_LABEL
    return {
        "system": system,
        "supported": system == "Windows" and script.exists(),
        "script": script.name if script.exists() else None,
        "log": CUDA_RUNTIME_LOG_LABEL,
        "state": state,
    }


def refreshed_hardware_status() -> dict:
    cache_clear = getattr(detect_hardware_acceleration, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    return safe_hardware_acceleration()


def launch_cuda_runtime_install() -> dict:
    global _cuda_runtime_install_process
    if platform.system() != "Windows":
        raise RuntimeError("CUDA runtime install is only available on Windows.")
    script = PROJECT_ROOT / "scripts" / "install-cuda-runtime-windows.ps1"
    if not script.exists():
        raise RuntimeError("CUDA runtime installer script is missing. Re-download Church Cap and try again.")
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "cuda-runtime-install.log"
    rotate_log_file(log_path)
    with log_path.open("ab") as log:
        log.write(b"\n--- Starting CUDA runtime force reinstall from operator page ---\n")
        creationflags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )
    _cuda_runtime_install_process = process
    return {"pid": process.pid, "log": CUDA_RUNTIME_LOG_LABEL}


def recommended_performance_config(status: dict | None = None) -> dict:
    status = status or performance_status()
    hardware = status["hardware_acceleration"]
    effective_platform = status["effective_platform"]
    cpu_count = os.cpu_count() or 1
    if effective_platform in {"windows", "linux"} and hardware.get("cuda_available"):
        config = {
            "performance_preset": "balanced",
            "performance_platform": "auto",
            "transcriber_mode": "faster_whisper",
            "whisper_model": "base.en",
            "whisper_device": "auto",
            "whisper_compute_type": "auto",
        }
        reason = "NVIDIA CUDA is available, so balanced Faster Whisper is recommended as the safest live-service starting point. Try medium manually only after a successful benchmark."
    elif effective_platform == "macos" and cpu_count >= 8:
        config = {
            "performance_preset": "balanced",
            "performance_platform": "auto",
            "transcriber_mode": "faster_whisper",
            "whisper_model": "base.en",
            "whisper_device": "auto",
            "whisper_compute_type": "auto",
        }
        reason = "This Mac has enough CPU headroom for the balanced Faster Whisper preset, which is safer to auto-apply than the medium model. Try medium manually only after a successful benchmark."
    elif cpu_count <= 4:
        config = {
            "performance_preset": "fastest",
            "performance_platform": "auto",
            "transcriber_mode": "faster_whisper",
            "whisper_model": "tiny.en",
            "whisper_device": "auto",
            "whisper_compute_type": "auto",
        }
        reason = "This looks like a lower-power CPU, so the fastest preset is recommended to reduce delay."
    else:
        config = {
            "performance_preset": "fast",
            "performance_platform": "auto",
            "transcriber_mode": "faster_whisper",
            "whisper_model": "base.en",
            "whisper_device": "auto",
            "whisper_compute_type": "auto",
        }
        reason = "No ready GPU acceleration was detected, so fast Faster Whisper settings are recommended."
    preset_values = {
        key: value
        for key, value in PERFORMANCE_PRESETS[config["performance_preset"]].items()
        if key not in {"label", "description"}
    }
    config = {**preset_values, **config}
    current = status["effective"]
    applied = all(str(current.get(key)) == str(value) for key, value in config.items())
    return {"config": config, "reason": reason, "applied": applied, "cpu_count": cpu_count}


_last_linux_cpu_snapshot: tuple[int, int] | None = None
_last_process_cpu_snapshot: tuple[float, float] | None = None


def _linux_cpu_usage_percent() -> float | None:
    global _last_linux_cpu_snapshot
    if platform.system() != "Linux":
        return None
    try:
        first = Path("/proc/stat").read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        parts = first.split()
        if not parts or parts[0] != "cpu":
            return None
        values = [int(value) for value in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
    except Exception:
        return None
    previous = _last_linux_cpu_snapshot
    _last_linux_cpu_snapshot = (total, idle)
    if previous is None:
        return None
    previous_total, previous_idle = previous
    total_delta = total - previous_total
    idle_delta = idle - previous_idle
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, ((total_delta - idle_delta) / total_delta) * 100.0)), 1)


def _process_performance_snapshot() -> dict[str, float | int | None]:
    """Return cross-platform Church Cap process CPU and resident memory."""
    global _last_process_cpu_snapshot
    now = time.monotonic()
    process_cpu = time.process_time()
    previous = _last_process_cpu_snapshot
    _last_process_cpu_snapshot = (now, process_cpu)
    process_cpu_percent = None
    if previous is not None:
        wall_delta = now - previous[0]
        cpu_delta = process_cpu - previous[1]
        if wall_delta > 0:
            process_cpu_percent = round(max(0.0, (cpu_delta / wall_delta) * 100.0), 1)

    rss_bytes: int | None = None
    try:
        if platform.system() == "Linux":
            for line in Path("/proc/self/status").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("VmRSS:"):
                    rss_bytes = int(line.split()[1]) * 1024
                    break
        elif platform.system() == "Windows":
            import ctypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            ):
                rss_bytes = int(counters.WorkingSetSize)
        else:
            import resource

            raw_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            rss_bytes = raw_rss if platform.system() == "Darwin" else raw_rss * 1024
    except Exception:
        rss_bytes = None
    return {
        "process_cpu_percent": process_cpu_percent,
        "process_rss_bytes": rss_bytes,
        "process_rss_mib": None if rss_bytes is None else round(rss_bytes / (1024 ** 2), 2),
    }


def system_performance_snapshot() -> dict:
    cpu_count = os.cpu_count() or 1
    load_1m = load_5m = load_15m = None
    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except Exception:
        pass
    memory = _memory_usage_snapshot()
    load_percent = None if load_1m is None else round((float(load_1m) / cpu_count) * 100, 1)
    cpu_percent = _linux_cpu_usage_percent()
    if cpu_percent is None:
        cpu_percent = load_percent
    return {
        "platform": platform.system(),
        "cpu_count": cpu_count,
        "load_1m": load_1m,
        "load_5m": load_5m,
        "load_15m": load_15m,
        "load_1m_percent": load_percent,
        "cpu_percent": cpu_percent,
        **memory,
        **_process_performance_snapshot(),
    }


def _bytes_to_gib(value: int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024 ** 3), 2)


def _total_memory_bytes() -> int | None:
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
        if system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return int(page_size * pages)
    except Exception:
        return None


def _memory_usage_snapshot() -> dict:
    total = _total_memory_bytes()
    available: int | None = None
    system = platform.system()
    try:
        if system == "Darwin":
            page_size_result = subprocess.run(["pagesize"], capture_output=True, text=True, timeout=3, check=False)
            vm_result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3, check=False)
            page_size = int(page_size_result.stdout.strip()) if page_size_result.returncode == 0 else 4096
            pages: dict[str, int] = {}
            for line in vm_result.stdout.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                digits = "".join(ch for ch in value if ch.isdigit())
                if digits:
                    pages[key.strip()] = int(digits)
            reclaimable_pages = (
                pages.get("Pages free", 0)
                + pages.get("Pages inactive", 0)
                + pages.get("Pages speculative", 0)
                + pages.get("Pages purgeable", 0)
            )
            active_used_pages = (
                pages.get("Pages active", 0)
                + pages.get("Pages wired down", 0)
                + pages.get("Pages occupied by compressor", 0)
            )
            available = reclaimable_pages * page_size
            if total is not None and active_used_pages:
                available = max(0, min(total, total - (active_used_pages * page_size)))
        elif system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total = int(status.ullTotalPhys)
                available = int(status.ullAvailPhys)
        else:
            meminfo = Path("/proc/meminfo")
            if meminfo.exists():
                values = {}
                for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                    key, raw = line.split(":", 1)
                    amount = raw.strip().split()[0]
                    values[key] = int(amount) * 1024
                total = values.get("MemTotal", total)
                available = values.get("MemAvailable")
    except Exception:
        available = None
    used = None if total is None or available is None else max(0, total - available)
    used_percent = None if total in {None, 0} or used is None else round((used / total) * 100, 1)
    return {
        "memory_total_bytes": total,
        "memory_available_bytes": available,
        "memory_used_bytes": used,
        "memory_total_gib": _bytes_to_gib(total),
        "memory_available_gib": _bytes_to_gib(available),
        "memory_used_gib": _bytes_to_gib(used),
        "memory_used_percent": used_percent,
    }


def gpu_utilisation_snapshot(active_device: str | None = None) -> dict:
    device = (active_device or "").lower()
    if device == "cuda":
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                result = subprocess.run(
                    [
                        nvidia_smi,
                        "--query-gpu=utilization.gpu,memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    first = result.stdout.splitlines()[0]
                    parts = [part.strip() for part in first.split(",")]
                    util = float(parts[0]) if parts and parts[0] else None
                    memory_used = float(parts[1]) if len(parts) > 1 and parts[1] else None
                    memory_total = float(parts[2]) if len(parts) > 2 and parts[2] else None
                    return {
                        "device": "cuda",
                        "active": True,
                        "utilization_percent": util,
                        "memory_used_mib": memory_used,
                        "memory_total_mib": memory_total,
                        "message": "NVIDIA GPU utilisation reported by nvidia-smi.",
                    }
            except Exception:
                pass
        return {"device": "cuda", "active": True, "utilization_percent": None, "message": "NVIDIA GPU active; utilisation unavailable."}
    if platform.system() == "Darwin":
        hardware = safe_hardware_acceleration()
        gpu_names = hardware.get("apple_gpu_names") or []
        chip = hardware.get("apple_chip") or "Apple Silicon"
        label = ", ".join(gpu_names) if gpu_names else "Apple GPU"
        if device == "mps":
            return {"device": "mps", "active": True, "utilization_percent": None, "message": f"Apple Metal/MPS active on {label} ({chip})."}
        return {"device": "apple", "active": False, "utilization_percent": None, "message": f"{label} available on {chip}; current caption runtime is {device or 'cpu'}."}
    if device == "mps":
        return {"device": "mps", "active": True, "utilization_percent": None, "message": "Apple Metal/MPS active; utilisation unavailable without system tools."}
    return {"device": device or "cpu", "active": False, "utilization_percent": None, "message": "GPU is not active for captions."}


def _disk_usage_snapshot() -> dict:
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
    except Exception:
        return {
            "project_drive_total_bytes": None,
            "project_drive_used_bytes": None,
            "project_drive_free_bytes": None,
            "project_drive_total_gib": None,
            "project_drive_used_gib": None,
            "project_drive_free_gib": None,
        }
    return {
        "project_drive_total_bytes": int(usage.total),
        "project_drive_used_bytes": int(usage.used),
        "project_drive_free_bytes": int(usage.free),
        "project_drive_total_gib": _bytes_to_gib(usage.total),
        "project_drive_used_gib": _bytes_to_gib(usage.used),
        "project_drive_free_gib": _bytes_to_gib(usage.free),
    }


def _system_specs_snapshot() -> dict:
    memory_bytes = _total_memory_bytes()
    hardware = safe_hardware_acceleration()
    specs = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "os_label": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "architecture": platform.architecture()[0],
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "cpu_count": os.cpu_count() or 1,
        "cpu_brand": hardware.get("cpu_brand"),
        "physical_cpu_count": hardware.get("physical_cpu_count"),
        "performance_core_count": hardware.get("performance_core_count"),
        "efficiency_core_count": hardware.get("efficiency_core_count"),
        "apple_chip": hardware.get("apple_chip"),
        "apple_gpu_names": hardware.get("apple_gpu_names"),
        "mac_model": hardware.get("mac_model"),
        "total_memory_bytes": memory_bytes,
        "total_memory_gib": _bytes_to_gib(memory_bytes),
    }
    specs.update(_disk_usage_snapshot())
    return specs


def _redact_local_paths(text: str) -> str:
    redacted = str(text)
    replacements = {
        str(PROJECT_ROOT): "<project_root>",
        str(PROJECT_ROOT.parent): "<project_parent>",
        str(app_support_dir()): "<app_support_dir>",
    }
    home = Path.home()
    replacements[str(home)] = "<home>"
    for before, after in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if before:
            redacted = redacted.replace(before, after)
            redacted = redacted.replace(before.replace("/", "\\"), after)
    return redacted


def _tail_log(path: Path, max_lines: int = 160) -> list[str]:
    return [_redact_local_paths(line) for line in tail_log_lines(path, max_lines=max_lines)]


def _storage_runtime_config() -> dict:
    runtime = load_runtime_config()
    effective = effective_performance_config(runtime)
    return {
        **runtime,
        "transcriber_mode": effective.get("transcriber_mode"),
        "whisper_model": effective.get("whisper_model"),
    }


def _redact_diagnostics_value(value):
    if isinstance(value, str):
        return _redact_local_paths(value)
    if isinstance(value, list):
        return [_redact_diagnostics_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_diagnostics_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_diagnostics_value(item) for key, item in value.items()}
    return value


def diagnostics_payload() -> dict:
    runtime = load_runtime_config()
    performance = performance_status()
    logs_dir = PROJECT_ROOT / "logs"
    support_logs_dir = app_support_dir() / "logs"
    safe_runtime = {
        key: value
        for key, value in runtime.items()
        if key not in {"audio_device"}
    }
    translation = safe_translation_state()
    translation_diagnostics = {
        "enabled": translation.get("enabled"),
        "provider": translation.get("provider"),
        "provider_ready": translation.get("provider_status", {}).get("ready"),
        "provider_message": translation.get("provider_status", {}).get("message"),
        "max_active_languages": translation.get("max_active_languages"),
        "language_policy": translation.get("language_policy"),
        "priority_mode": translation.get("priority_mode"),
        "timing_mode": translation.get("timing_mode"),
        "language_requests_enabled": translation.get("language_requests_enabled"),
        "active_translated_languages": translation.get("active_translated_languages", []),
        "viewer_language_counts": translation.get("viewer_languages", {}),
        "scheduler": translation.get("scheduler", {}),
        "argos_installed_language_count": len(translation.get("resources", {}).get("argos", {}).get("installed_languages", [])),
        "argos_installed_pair_count": len(translation.get("resources", {}).get("argos", {}).get("installed_pairs", [])),
        "ct2small100_ready": translation.get("resources", {}).get("ct2small100", {}).get("status", {}).get("ready"),
        "ct2small100_model_dir": translation.get("resources", {}).get("ct2small100", {}).get("status", {}).get("model_dir"),
        "ct2small100_license": translation.get("resources", {}).get("ct2small100", {}).get("license"),
        "small100_ready": translation.get("resources", {}).get("small100", {}).get("status", {}).get("ready"),
        "small100_license": translation.get("resources", {}).get("small100", {}).get("license"),
    }
    safe_metrics = {
        key: value
        for key, value in get_metrics().items()
        if key not in {"audio_device"}
    }
    payload = {
        "diagnostics_schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": settings.app_name,
            "version": settings.app_version,
            "version_label": settings.app_version_label,
        },
        "system": _system_specs_snapshot(),
        "hardware_acceleration": performance["hardware_acceleration"],
        "resolved_runtime": performance["resolved_whisper_runtime"],
        "effective_performance": performance["effective"],
        "system_performance": system_performance_snapshot(),
        "runtime_config_sanitized": safe_runtime,
        "translation": translation_diagnostics,
        "metrics": safe_metrics,
        "last_service_metrics": get_service_metrics(),
        "service_metrics": get_service_metrics_report(),
        "cuda_runtime_install": cuda_runtime_capability_state(),
        "translation_install": _translation_install_state,
        "storage": storage_snapshot(PROJECT_ROOT, app_support_dir(), _storage_runtime_config()),
        "logs": {
            "update.log": _tail_log(logs_dir / "update.log"),
            "cuda-runtime-install.log": _tail_log(logs_dir / "cuda-runtime-install.log"),
            "translation-install.log": _tail_log(support_logs_dir / "translation-install.log"),
            "update-restart.log": _tail_log(logs_dir / "update-restart.log"),
        },
        "privacy_note": "Diagnostics are generated only when an operator chooses to download them. They can include OS version, CPU details, memory size, project drive capacity/free space, Python version, performance settings, CUDA/Apple runtime status, privacy-safe numeric service measurements, storage category sizes and cleanup availability, and recent updater/CUDA log lines with local paths redacted. They exclude audio, transcripts, captions, translations, operator passwords, session secrets, and .env contents. Review the file before sharing it for support, and do not post it publicly on GitHub unless you are comfortable with the contents.",
    }
    return _redact_diagnostics_value(payload)


def performance_status() -> dict:
    runtime = load_runtime_config()
    effective = effective_performance_config(runtime)
    hardware = safe_hardware_status_object()
    detected_platform = performance_platform_key(hardware.platform)
    selected_platform = str(effective.get("performance_platform") or "auto")
    effective_platform = detected_platform if selected_platform == "auto" else selected_platform
    requested_device = str(effective["whisper_device"])
    if effective["transcriber_mode"] == "faster_whisper":
        faster_device = "cpu" if requested_device == "mps" else requested_device
        resolved_device, resolved_compute = resolve_whisper_runtime(
            faster_device,
            str(effective["whisper_compute_type"]),
            hardware,
        )
    else:
        resolved_device = requested_device
        if resolved_device == "auto":
            if effective_platform == "macos":
                resolved_device = "mps"
            elif hardware.cuda_available:
                resolved_device = "cuda"
            else:
                resolved_device = "cpu"
        resolved_compute = "fp16" if resolved_device == "cuda" else "fp32"
    status = {
        "presets": [
            {"key": key, "label": value["label"], "description": value["description"]}
            for key, value in PERFORMANCE_PRESETS.items()
        ],
        "runtime": runtime,
        "effective": effective,
        "detected_platform": detected_platform,
        "effective_platform": effective_platform,
        "resolved_whisper_runtime": {"device": resolved_device, "compute_type": resolved_compute},
        "hardware_acceleration": hardware.as_dict(),
    }
    status["recommendation"] = recommended_performance_config(status)
    return status


def captions_are_running() -> bool:
    task_running = _transcription_task is not None and not _transcription_task.done()
    return task_running or hub.state().status in {"listening", "sensitive"}


def performance_locked_response() -> JSONResponse:
    return JSONResponse(
        {
            "status": "error",
            "error": "Stop captions before changing performance settings.",
            "restart_required": True,
            "performance_locked": True,
        },
        status_code=409,
    )




def create_transcriber():
    performance = effective_performance_config()
    mode = str(performance["transcriber_mode"]).lower().strip()
    transcriber_device = performance["whisper_device"]
    if mode == "faster_whisper" and transcriber_device == "mps":
        transcriber_device = "auto"
    common = dict(
        model_name=performance["whisper_model"],
        device=transcriber_device,
        language=settings.language,
        audio_device=selected_audio_device(),
        sample_rate=settings.sample_rate,
        chunk_seconds=performance["chunk_seconds"],
        stream_window_seconds=performance["stream_window_seconds"],
        stream_update_interval_seconds=performance["stream_update_interval_seconds"],
        stream_silence_finalise_seconds=performance["stream_silence_finalise_seconds"],
        stream_min_rms=settings.stream_min_rms,
        stream_stability_passes=performance["stream_stability_passes"],
        initial_prompt=settings.whisper_initial_prompt,
    )
    if mode in {"whisper", "openai_whisper", "openai-whisper"}:
        from app.transcription.whisper_live import WhisperLiveTranscriber
        return WhisperLiveTranscriber(**common, beam_size=performance["whisper_beam_size"])
    if mode == "faster_whisper":
        from app.transcription.faster_whisper_live import FasterWhisperTranscriber
        return FasterWhisperTranscriber(
            **common,
            compute_type=performance["whisper_compute_type"],
            word_timestamps_enabled=settings.stream_word_timestamps_enabled,
            edge_guard_seconds=settings.stream_edge_guard_seconds,
            edge_confidence_threshold=settings.stream_edge_confidence_threshold,
            committed_audio_overlap_seconds=settings.stream_committed_audio_overlap_seconds,
        )
    raise RuntimeError(
        "Demo/mock captions have been disabled. "
        "Set TRANSCRIBER_MODE=whisper for accuracy-first local Whisper, or faster_whisper for the faster backend."
    )


async def _sample_service_performance() -> None:
    while True:
        record_system_sample(system_performance_snapshot())
        await asyncio.sleep(5)


async def transcription_loop():
    global _transcriber
    _transcriber = None
    runtime = load_runtime_config()
    effective = effective_performance_config(runtime)
    start_service_metrics({
        "app_version": settings.app_version,
        "diagnostics_schema_version": 2,
        "transcriber_mode": effective.get("transcriber_mode"),
        "whisper_model": effective.get("whisper_model"),
        "whisper_device_requested": effective.get("whisper_device"),
        "whisper_compute_type_requested": effective.get("whisper_compute_type"),
        "stream_update_interval_seconds": effective.get("stream_update_interval_seconds"),
        "stream_window_seconds": effective.get("stream_window_seconds"),
        "word_timestamps_enabled": bool(
            effective.get("transcriber_mode") == "faster_whisper"
            and settings.stream_word_timestamps_enabled
        ),
        "edge_guard_seconds": settings.stream_edge_guard_seconds,
        "translation_enabled": bool(runtime.get("translation_enabled", settings.translation_enabled)),
        "translation_provider": runtime.get("translation_provider", settings.translation_provider),
        "translation_timing_mode": runtime.get("translation_timing_mode", "responsive"),
        "translation_allowed_languages": sorted(hub.translation_allowed_languages),
        "translation_max_active_languages": hub.translation_max_active_languages,
        "translation_queue_capacity_per_language": hub.translation_queue_capacity_per_language,
    })
    # Audience viewers often join before the operator starts captions. Seed the
    # run immediately so peak counts and viewer-seconds include those viewers.
    record_viewer_counts(hub.language_counts())
    sampler_task = asyncio.create_task(_sample_service_performance())
    service_status = "completed"
    try:
        _transcriber = create_transcriber()
        hub.set_status("listening")
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
                    recognition_spans=segment.recognition_spans,
                    capture_started_monotonic=segment.capture_started_monotonic,
                    source_ready_monotonic=segment.source_ready_monotonic,
                )
            )
            if hasattr(_transcriber, "acknowledge_audio_until"):
                _transcriber.acknowledge_audio_until(hub.sealed_audio_end_monotonic())
    except asyncio.CancelledError:
        hub.set_status("stopped")
        raise
    except Exception as exc:
        service_status = "error"
        hub.set_status("error")
        await hub.publish(CaptionSegment(text=f"Caption system error: {exc}", raw_text=str(exc), is_final=True))
    finally:
        sampler_task.cancel()
        try:
            await sampler_task
        except asyncio.CancelledError:
            pass
        if _transcriber is not None:
            await _transcriber.stop()
        await hub.drain_translation_work(timeout_seconds=2.0)
        finish_service_metrics(
            service_status,
            error=service_status == "error",
            stop_reason="caption_error" if service_status == "error" else "operator_stop",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_support_dir().mkdir(parents=True, exist_ok=True)
    (app_support_dir() / "data").mkdir(parents=True, exist_ok=True)
    rotate_runtime_logs(PROJECT_ROOT, app_support_dir())
    initialise_service_metrics_storage()
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
    if port == settings.operator_port and lock_localhost and not is_local_client(request) and not is_remote_service_leader_path(path):
        return JSONResponse(
            {"detail": "Full operator controls are locked to localhost on this installation."},
            status_code=403,
        )

    return await call_next(request)




@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return template_response(
        "captions.html",
        {
            **base_template_context(request),
            "dnd_reminder": settings.dnd_reminder,
            "languages": SUPPORTED_LANGUAGES,
            "ui_strings": get_client_ui_strings(),
            "ui_string_sources": get_client_ui_sources(language["code"] for language in SUPPORTED_LANGUAGES),
            "translation_state": safe_translation_state(),
        },
    )


@app.get("/display", response_class=HTMLResponse)
async def display(request: Request):
    return template_response(
        "display.html",
        {"request": request, "church_name": settings.church_name},
    )


@app.get("/obs", response_class=HTMLResponse)
async def obs_overlay(request: Request):
    return_to_operator = request.query_params.get("return") in {"1", "true", "operator"}
    return template_response(
        "obs.html",
        {
            **base_template_context(request),
            "return_to_operator": return_to_operator,
        },
    )


@app.get("/obs/help", response_class=HTMLResponse)
async def obs_help(request: Request, _: None = Depends(require_operator)):
    return template_response(
        "obs_help.html",
        {
            **base_template_context(request),
            "obs_url": f"{base_url(request)}/obs",
            "obs_ip_url": f"{ip_base_url(request)}/obs",
            "system_ip": local_ip(),
        },
    )




@app.get("/docs/{doc_key}", response_class=HTMLResponse)
async def operator_doc(doc_key: str, request: Request, _: None = Depends(require_operator)):
    title, rel_path = DOC_FILES.get(doc_key, ("Document", "README.md"))
    path = PROJECT_ROOT / rel_path
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        content = "Document not found."
    return template_response(
        "doc.html",
        {"request": request, "church_name": settings.church_name, "title": title, "content": content},
    )


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request, _: None = Depends(require_operator)):
    return template_response("feedback.html", base_template_context(request))


@app.get("/setup/network", response_class=HTMLResponse)
async def setup_network_page(request: Request, _: None = Depends(require_operator)):
    return template_response(
        "network_setup.html",
        {"request": request, "church_name": settings.church_name, "base_url": base_url(request)},
    )


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    config = auth_config()
    if not config.needs_setup:
        return RedirectResponse("/operator", status_code=303)
    return template_response("setup.html", {**base_template_context(request), "error": None})


@app.post("/setup")
async def setup_operator(request: Request, password: str = Form(...), confirm_password: str = Form(...), security_mode: str = Form("secure_operator")):
    config = auth_config()
    if not config.needs_setup:
        return RedirectResponse("/operator", status_code=303)
    if password != confirm_password:
        return template_response("setup.html", {**base_template_context(request), "error": "Passwords do not match."}, status_code=400)
    try:
        set_operator_password(password)
        set_security_config(security_mode)
    except ValueError as exc:
        return template_response("setup.html", {**base_template_context(request), "error": str(exc)}, status_code=400)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if auth_config().needs_setup:
        return RedirectResponse("/setup", status_code=303)
    # Clear any stale cookie left from a previous server run so operators can
    # sign back in cleanly after Sunday-morning restarts.
    response = template_response("login.html", {**base_template_context(request), "error": None})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.post("/service-leader/pairing/create", response_class=HTMLResponse)
async def create_service_leader_pairing(request: Request, service_leader_password: str = Form(...)):
    if not is_local_client(request):
        return JSONResponse({"detail": "Create service-leader pairing codes on the Church Cap computer."}, status_code=403)
    config = auth_config()
    if not password_is_valid(service_leader_password, config):
        response = template_response(
            "login.html",
            {
                **base_template_context(request),
                "error": None,
                "service_leader_error": "Incorrect operator password.",
            },
            status_code=401,
        )
        response.delete_cookie(COOKIE_NAME)
        return _no_store(response)
    token = service_leader_access.create_pairing()
    pairing_url = f"{service_leader_base_url(request)}/service-leader/pair#{token}"
    response = template_response(
        "service_leader_pairing.html",
        {
            **base_template_context(request),
            "pairing_qr": _qr_data_uri(pairing_url),
            "pairing_seconds": service_leader_access.pairing_ttl_seconds,
            "service_leader_url": f"{service_leader_base_url(request)}/service-leader",
        },
    )
    return _no_store(response)


@app.get("/service-leader/pair", response_class=HTMLResponse)
async def service_leader_pair_page(request: Request):
    return _no_store(template_response("service_leader_pair.html", base_template_context(request)))


@app.post("/service-leader/pair/exchange")
async def service_leader_pair_exchange(request: Request):
    origin = request.headers.get("origin")
    expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if not origin or origin.rstrip("/") != expected_origin.rstrip("/"):
        return JSONResponse({"status": "error", "error": "Invalid pairing origin."}, status_code=403)
    body = await request.json()
    exchanged = service_leader_access.exchange_pairing(str(body.get("token") or ""))
    if exchanged is None:
        return JSONResponse(
            {"status": "error", "error": "This pairing code has expired or has already been used."},
            status_code=401,
        )
    session_token, _session = exchanged
    response = JSONResponse({"status": "paired"})
    response.set_cookie(
        SERVICE_LEADER_COOKIE_NAME,
        session_token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=service_leader_access.session_max_age_seconds,
        path="/service-leader",
    )
    return _no_store(response)


@app.get("/service-leader", response_class=HTMLResponse)
async def service_leader_page(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    response = template_response(
        "service_leader.html",
        {
            **base_template_context(request),
            "csrf_token": session.csrf_token,
            "secure_transport": request.url.scheme == "https",
            "audience_url": f"{base_url(request)}/",
            "audience_ip_url": f"{ip_base_url(request)}/",
            **service_leader_language_context(),
        },
    )
    return _no_store(response)


@app.get("/service-leader/api/status")
async def service_leader_status(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    state = hub.state()
    metrics = get_metrics()
    runtime = load_runtime_config()
    return {
        "status": state.status,
        "sensitive_mode": state.sensitive_mode,
        "current": state.current.text if state.current else "",
        "audio_rms": metrics.get("audio_rms"),
        "audio_peak": metrics.get("audio_peak"),
        "viewers": state.viewers,
        "translation": service_leader_language_context(),
        "audio": service_leader_audio_context(),
        "health": caption_health_snapshot(),
        "session": service_leader_access.session_timing(session),
    }


@app.post("/service-leader/logout")
async def service_leader_logout(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    service_leader_access.revoke_session(request.cookies.get(SERVICE_LEADER_COOKIE_NAME))
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(SERVICE_LEADER_COOKIE_NAME, path="/service-leader")
    return _no_store(response)


@app.get("/pastor")
@app.get("/pastor/{legacy_path:path}")
async def legacy_pastor_redirect(legacy_path: str = ""):
    return RedirectResponse("/service-leader", status_code=308)


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    config = auth_config()
    if not password_is_valid(password, config):
        return template_response(
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
    return template_response("account.html", {"request": request, "church_name": settings.church_name, "error": None, "success": None})


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
        return template_response("account.html", {"request": request, "church_name": settings.church_name, "error": "Current password is incorrect.", "success": None}, status_code=400)
    if new_password != confirm_password:
        return template_response("account.html", {"request": request, "church_name": settings.church_name, "error": "New passwords do not match.", "success": None}, status_code=400)
    try:
        set_operator_password(new_password)
        service_leader_access.revoke_all()
    except ValueError as exc:
        return template_response("account.html", {"request": request, "church_name": settings.church_name, "error": str(exc), "success": None}, status_code=400)
    response = template_response("account.html", {"request": request, "church_name": settings.church_name, "error": None, "success": "Password changed. Please sign in again."})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/operator", response_class=HTMLResponse)
async def operator(request: Request, _: None = Depends(require_operator)):
    runtime = load_runtime_config()
    return template_response(
        "operator.html",
        {
            **base_template_context(request),
            "caption_url": f"{base_url(request)}/",
            "caption_ip_url": f"{ip_base_url(request)}/",
            "display_url": f"{base_url(request)}/display",
            "display_ip_url": f"{ip_base_url(request)}/display",
            "obs_url": f"{base_url(request)}/obs",
            "obs_ip_url": f"{ip_base_url(request)}/obs",
            "system_ip": local_ip(),
            "detected_hostname": detected_local_hostname(),
            "operator_password_is_default": auth_config().needs_setup,
            "session_secret_is_default": False,
            "runtime": runtime,
            "performance": performance_status(),
            "languages": SUPPORTED_LANGUAGES,
            "translation_state": safe_translation_state(),
            "translation_provider": settings.translation_provider,
            "security": security_state(request),
            "service_leader_access": service_leader_access.access_state(),
        },
    )



def _qr_png_response(value: str, filename: str | None = None) -> Response:
    img = qrcode.make(value)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    headers = _download_headers(filename) if filename else None
    return Response(buf.getvalue(), media_type="image/png", headers=headers)


def _cleanup_download_handoffs() -> None:
    now = time.time()
    for token, payload in list(_download_handoff_tokens.items()):
        if float(payload.get("expires_at", 0)) <= now:
            _download_handoff_tokens.pop(token, None)


def _create_download_handoff(target: str) -> str:
    _cleanup_download_handoffs()
    token = secrets.token_urlsafe(24)
    _download_handoff_tokens[token] = {
        "target": target,
        "expires_at": time.time() + DOWNLOAD_HANDOFF_TTL_SECONDS,
    }
    return token


def _download_handoff_urls(request: Request, token: str) -> dict[str, str | int]:
    base = service_leader_base_url(request).rstrip("/")
    return {
        "download_url": f"{base}/download-handoff/{token}",
        "qr_url": f"{base}/download-handoff-qr/{token}.png",
        "expires_seconds": DOWNLOAD_HANDOFF_TTL_SECONDS,
    }


def _download_handoff_target_response(request: Request, target: str) -> Response:
    if target == "audience_qr":
        return _qr_png_response(f"{base_url(request)}/", "church-cap-audience-qr.png")
    if target == "audience_qr_ip":
        return _qr_png_response(f"{ip_base_url(request)}/", "church-cap-audience-ip-qr.png")
    if target == "service_report":
        return Response(
            json.dumps(service_report_payload(), indent=2, sort_keys=True),
            media_type="application/json",
            headers=_download_headers(f"church-cap-service-report-{settings.app_version}.json"),
        )
    if target in {"support_logs", "operator_diagnostics"}:
        filename = "church-cap-support-logs" if target == "support_logs" else "church-cap-diagnostics"
        body = json.dumps(diagnostics_payload(), indent=2, sort_keys=True)
        return Response(
            body,
            media_type="application/json",
            headers=_download_headers(f"{filename}-{settings.app_version}.json"),
        )
    raise HTTPException(status_code=404, detail="Download handoff target expired or unavailable")



@app.get("/qr.png")
async def qr(request: Request):
    return _qr_png_response(f"{base_url(request)}/")


@app.get("/qr-ip.png")
async def qr_ip(request: Request):
    """IP-address fallback QR for Android/guest Wi-Fi networks that do not resolve .local/mDNS."""
    return _qr_png_response(f"{ip_base_url(request)}/")


@app.get("/service-leader/audience-qr.png")
async def service_leader_audience_qr(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    return _qr_png_response(f"{base_url(request)}/", "church-cap-audience-qr.png")


@app.get("/service-leader/audience-qr-ip.png")
async def service_leader_audience_qr_ip(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    return _qr_png_response(f"{ip_base_url(request)}/", "church-cap-audience-ip-qr.png")


@app.post("/service-leader/api/download-handoff")
async def create_service_leader_download_handoff(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    try:
        body = await request.json()
    except Exception:
        body = {}
    target = str(body.get("target", ""))
    if target not in {"audience_qr", "audience_qr_ip", "support_logs"}:
        raise HTTPException(status_code=400, detail="Unsupported Service Leader download handoff")
    return _download_handoff_urls(request, _create_download_handoff(target))


@app.post("/api/diagnostics/download-handoff")
async def create_operator_diagnostics_download_handoff(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Create diagnostics handoff QR codes from the Church Cap computer."},
            status_code=403,
        )
    return _download_handoff_urls(request, _create_download_handoff("operator_diagnostics"))


@app.post("/api/download-handoff")
async def create_operator_download_handoff(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Create download handoff QR codes from the Church Cap computer."},
            status_code=403,
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    target = str(body.get("target", ""))
    if target not in {"audience_qr", "audience_qr_ip", "operator_diagnostics", "service_report"}:
        raise HTTPException(status_code=400, detail="Unsupported operator download handoff")
    return _download_handoff_urls(request, _create_download_handoff(target))


@app.get("/download-handoff-qr/{token}.png")
async def download_handoff_qr(request: Request, token: str):
    _cleanup_download_handoffs()
    payload = _download_handoff_tokens.get(token)
    if payload is None:
        raise HTTPException(status_code=404, detail="Download handoff expired")
    return _qr_png_response(f"{service_leader_base_url(request).rstrip()}/download-handoff/{token}")


@app.get("/download-handoff/{token}")
async def download_handoff(request: Request, token: str):
    _cleanup_download_handoffs()
    payload = _download_handoff_tokens.get(token)
    if payload is None:
        return PlainTextResponse("This Church Cap download link has expired. Create a new QR code from the appliance.", status_code=404)
    return _download_handoff_target_response(request, str(payload.get("target", "")))


@app.get("/health")
async def health():
    performance = effective_performance_config()
    return {
        "ok": True,
        "status": hub.state().status,
        "app_version": settings.app_version,
        "app_version_label": settings.app_version_label,
        "deployment": safe_deployment_context(safe_hardware_acceleration()),
        "viewers": hub.viewer_count,
        "mode": performance["transcriber_mode"],
        "audio_device": selected_audio_device(),
        "sensitive_mode": hub.sensitive_mode,
        "profanity_filter_enabled": bool(load_runtime_config().get("profanity_filter_enabled", True)),
        "hostname": detected_local_hostname(),
        "base_url": base_url(),
        "ip_base_url": ip_base_url(),
        "translation": safe_translation_state(),
        "security": security_state(),
    }


def _device_to_api(index: int, device: dict):
    name = str(device.get("name", f"Device {index}"))
    max_input_channels = int(device.get("max_input_channels", 0))
    default_sample_rate = int(float(device.get("default_samplerate", 0) or 0))
    rate_label = f", {default_sample_rate} Hz" if default_sample_rate else ""
    return {
        "id": index,
        "name": name,
        "max_input_channels": max_input_channels,
        "default_sample_rate": default_sample_rate,
        "label": f"{index}: {name} ({max_input_channels} input ch{rate_label})",
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
    if isinstance(device, str):
        device = device.strip()
        if device.isdigit():
            device = int(device)
        elif device in {"", "default"}:
            device = None
    if isinstance(device, bool) or not isinstance(device, (int, str, type(None))):
        return JSONResponse({"status": "error", "error": "Choose a valid audio input."}, status_code=400)
    if sd is None and device is not None:
        return JSONResponse({"status": "error", "error": "Audio support is not available."}, status_code=503)
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


@app.post("/api/performance/apply-recommended")
async def apply_recommended_performance(_: None = Depends(require_operator)):
    if captions_are_running():
        return performance_locked_response()
    recommendation = recommended_performance_config()
    cfg = set_performance_config(recommendation["config"])
    status = performance_status()
    return {"status": "saved", "restart_required": True, "recommendation": status["recommendation"], **status, "runtime": cfg}


@app.post("/api/performance")
async def update_performance(request: Request, _: None = Depends(require_operator)):
    if captions_are_running():
        return performance_locked_response()
    body = await request.json()
    preset = str(body.get("performance_preset") or "balanced")
    if preset in PERFORMANCE_PRESETS:
        preset_values = {
            key: value
            for key, value in PERFORMANCE_PRESETS[preset].items()
            if key not in {"label", "description"}
        }
    else:
        preset_values = {}
        preset = "custom"

    cfg = set_performance_config(
        {
            **preset_values,
            "performance_preset": preset,
            "performance_platform": body.get("performance_platform", "auto"),
            "transcriber_mode": body.get("transcriber_mode", preset_values.get("transcriber_mode")),
            "whisper_model": body.get("whisper_model", preset_values.get("whisper_model")),
            "whisper_device": body.get("whisper_device", preset_values.get("whisper_device")),
            "whisper_compute_type": body.get("whisper_compute_type", preset_values.get("whisper_compute_type")),
            "whisper_beam_size": body.get("whisper_beam_size", preset_values.get("whisper_beam_size")),
            "chunk_seconds": body.get("chunk_seconds", preset_values.get("chunk_seconds")),
            "stream_window_seconds": body.get("stream_window_seconds", preset_values.get("stream_window_seconds")),
            "stream_update_interval_seconds": body.get("stream_update_interval_seconds", preset_values.get("stream_update_interval_seconds")),
            "stream_silence_finalise_seconds": body.get("stream_silence_finalise_seconds", preset_values.get("stream_silence_finalise_seconds")),
            "stream_stability_passes": body.get("stream_stability_passes", preset_values.get("stream_stability_passes")),
        }
    )
    return {"status": "saved", "restart_required": True, **performance_status(), "runtime": cfg}


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


def _service_leader_export_confirmed(request: Request) -> JSONResponse | None:
    if request.query_params.get("confirmed") == "1":
        return None
    return JSONResponse(
        {
            "status": "confirmation_required",
            "error": "Confirm that you understand this download may contain sensitive service information.",
        },
        status_code=400,
    )


@app.get("/service-leader/transcript.txt", response_class=PlainTextResponse)
async def service_leader_transcript_txt(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    if error := _service_leader_export_confirmed(request):
        return error
    lines = [seg.text for seg in hub.final_segments()]
    return PlainTextResponse("\n".join(lines), headers=_download_headers("church-cap-current-session-transcript.txt"))


@app.get("/service-leader/transcript.vtt", response_class=PlainTextResponse)
async def service_leader_transcript_vtt(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    if error := _service_leader_export_confirmed(request):
        return error
    return PlainTextResponse(segments_to_vtt(hub.final_segments()), media_type="text/vtt", headers=_download_headers("church-cap-current-session-transcript.vtt"))


@app.get("/service-leader/support-logs.json")
async def service_leader_support_logs(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    if error := _service_leader_export_confirmed(request):
        return error
    body = json.dumps(diagnostics_payload(), indent=2, sort_keys=True)
    return Response(
        body,
        media_type="application/json",
        headers=_download_headers(f"church-cap-support-logs-{settings.app_version}.json"),
    )


@app.get("/api/status")
async def api_status(_: None = Depends(require_operator)):
    state = hub.state()
    performance = performance_status()
    system_perf = system_performance_snapshot()
    runtime = performance["resolved_whisper_runtime"]
    metrics = get_metrics()
    runtime_device = str(metrics.get("model_device") or runtime.get("device") or "cpu")
    gpu = gpu_utilisation_snapshot(runtime_device)
    translation_state = safe_translation_state()
    audience_delay = None
    if metrics.get("last_transcription_seconds") is not None:
        audience_delay = float(metrics.get("last_transcription_seconds") or 0) + float(performance["effective"].get("stream_update_interval_seconds") or 0)
    translation_delay = None
    if audience_delay is not None and metrics.get("last_translation_seconds") is not None:
        translation_delay = audience_delay + float(metrics.get("last_translation_seconds") or 0)
    translation_delay_by_language: dict[str, float] = {}
    if audience_delay is not None:
        for language, seconds in (translation_state.get("translation_latency_seconds") or {}).items():
            try:
                translation_delay_by_language[str(language)] = audience_delay + float(seconds)
            except (TypeError, ValueError):
                continue
    translation_state = {**translation_state, "translation_delay_seconds_by_language": translation_delay_by_language}
    strip_cpu_percent = system_perf.get("cpu_percent")
    if strip_cpu_percent is None:
        strip_cpu_percent = system_perf.get("load_1m_percent")
    hardware_info = performance.get("hardware_acceleration") or {}
    gpu_label = f"{runtime.get('device', 'auto')} / {runtime.get('compute_type', 'auto')}"
    if hardware_info.get("platform") == "Darwin":
        apple_names = hardware_info.get("apple_gpu_names") or []
        gpu_label = "Apple GPU" if apple_names else ("Apple Metal" if runtime_device == "mps" else gpu_label)
    return {
        "status": state.status,
        "viewers": state.viewers,
        "deployment": safe_deployment_context(performance["hardware_acceleration"]),
        "sensitive_mode": state.sensitive_mode,
        "current": state.current.model_dump(mode="json") if state.current else None,
        "transcript_count": len(hub.final_segments()),
        "metrics": metrics,
        "last_service_metrics": get_service_metrics(),
        "system_performance": system_perf,
        "settings": {
            "model": performance["effective"]["whisper_model"],
            "transcriber_mode": performance["effective"]["transcriber_mode"],
            "device": performance["effective"]["whisper_device"],
            "compute_type": performance["effective"]["whisper_compute_type"],
            "beam_size": performance["effective"]["whisper_beam_size"],
            "resolved_whisper_runtime": performance["resolved_whisper_runtime"],
            "hardware_acceleration": performance["hardware_acceleration"],
            "performance": performance,
            "stream_window_seconds": performance["effective"]["stream_window_seconds"],
            "stream_update_interval_seconds": performance["effective"]["stream_update_interval_seconds"],
            "stream_silence_finalise_seconds": performance["effective"]["stream_silence_finalise_seconds"],
            "stream_stability_passes": performance["effective"]["stream_stability_passes"],
            "audio_device": selected_audio_device(),
        },
        "translation": translation_state,
        "security": security_state(),
        "service_leader_access": service_leader_access.access_state(),
        "performance_locked": captions_are_running(),
        "update": update_capability_state(),
        "cuda_runtime": cuda_runtime_capability_state(),
        "translation_install": translation_install_state(),
        "operator_strip": {
            "caption_status": state.status,
            "mic_level_percent": max(0, min(100, round((float(metrics.get("audio_rms") or 0) / 0.06) * 100))),
            "processing_delay_seconds": metrics.get("last_transcription_seconds"),
            "audience_delay_seconds": audience_delay,
            "live_delay_seconds": audience_delay,
            "translation_delay_seconds": translation_delay,
            "cpu_percent": strip_cpu_percent,
            "ram_percent": system_perf.get("memory_used_percent"),
            "ram_used_gib": system_perf.get("memory_used_gib"),
            "ram_total_gib": system_perf.get("memory_total_gib"),
            "gpu": gpu_label,
            "gpu_utilization_percent": gpu.get("utilization_percent"),
            "gpu_memory_used_mib": gpu.get("memory_used_mib"),
            "gpu_memory_total_mib": gpu.get("memory_total_mib"),
            "gpu_message": gpu.get("message"),
            "active_languages": translation_state.get("active_translated_languages", []),
            "translation_capacity": translation_state.get("max_active_languages", 1),
            "last_translation_seconds": metrics.get("last_translation_seconds"),
            "translations_completed": metrics.get("translations_completed", 0),
        },
        "profanity_filter_enabled": bool(load_runtime_config().get("profanity_filter_enabled", True)),
    }


@app.get("/api/diagnostics/export")
async def export_diagnostics(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Download diagnostics from the Church Cap computer."},
            status_code=403,
        )
    if request.query_params.get("confirmed") != "1":
        return JSONResponse(
            {
                "status": "confirmation_required",
                "error": "Confirm that you understand the diagnostics file may contain support-sensitive system details before downloading it.",
            },
            status_code=400,
        )
    body = json.dumps(diagnostics_payload(), indent=2, sort_keys=True)
    return Response(
        body,
        media_type="application/json",
        headers=_download_headers(f"church-cap-diagnostics-{settings.app_version}.json"),
    )


@app.get("/api/diagnostics/service-report")
async def export_anonymised_service_report(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Download the anonymised service report from the Church Cap computer."},
            status_code=403,
        )
    body = json.dumps(service_report_payload(), indent=2, sort_keys=True)
    return Response(
        body,
        media_type="application/json",
        headers=_download_headers(f"church-cap-service-report-{settings.app_version}.json"),
    )


@app.post("/api/diagnostics/reset-service-metrics")
async def reset_service_diagnostics(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Reset test measurements from the Church Cap computer."},
            status_code=403,
        )
    if captions_are_running():
        return JSONResponse(
            {"status": "error", "error": "Stop captions before resetting test measurements."},
            status_code=409,
        )
    clear_service_metrics()
    return {"status": "reset"}


@app.get("/api/diagnostics/storage")
async def diagnostics_storage(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "View storage use from the Church Cap computer."},
            status_code=403,
        )
    snapshot = await asyncio.to_thread(
        storage_snapshot,
        PROJECT_ROOT,
        app_support_dir(),
        _storage_runtime_config(),
    )
    return {"status": "ok", "storage": snapshot}


@app.post("/api/diagnostics/storage/cleanup")
async def diagnostics_storage_cleanup(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Clear unused downloads from the Church Cap computer."},
            status_code=403,
        )
    if captions_are_running():
        return JSONResponse(
            {"status": "error", "error": "Stop captions before clearing unused downloads."},
            status_code=409,
        )
    body = await request.json()
    if body.get("confirmed") is not True:
        return JSONResponse(
            {"status": "error", "error": "Confirm the selected cleanup items before continuing."},
            status_code=400,
        )
    candidate_ids = body.get("candidate_ids")
    if not isinstance(candidate_ids, list) or not candidate_ids:
        return JSONResponse(
            {"status": "error", "error": "Select at least one unused download or archived log."},
            status_code=400,
        )
    try:
        result = await asyncio.to_thread(
            clear_storage_candidates,
            candidate_ids,
            PROJECT_ROOT,
            app_support_dir(),
            _storage_runtime_config(),
        )
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)
    snapshot = await asyncio.to_thread(
        storage_snapshot,
        PROJECT_ROOT,
        app_support_dir(),
        _storage_runtime_config(),
    )
    return {"status": "cleared", **result, "storage": snapshot}


@app.post("/api/cuda/check")
async def check_cuda_runtime(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Check CUDA from the Church Cap computer."},
            status_code=403,
        )
    return {"status": "checked", "hardware_acceleration": refreshed_hardware_status(), "cuda_runtime": cuda_runtime_capability_state()}


@app.post("/api/cuda/install")
async def install_cuda_runtime(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Install CUDA from the Church Cap computer."},
            status_code=403,
        )
    capability = cuda_runtime_capability_state()
    if not capability["supported"]:
        return JSONResponse(
            {"status": "error", "error": "CUDA runtime force reinstall is only available on Windows.", "cuda_runtime": capability},
            status_code=400,
        )
    global _cuda_runtime_install_state
    if _cuda_runtime_install_state.get("status") == "installing":
        return {"status": "installing", "cuda_runtime": capability}
    try:
        process = await asyncio.to_thread(launch_cuda_runtime_install)
    except Exception as exc:
        _cuda_runtime_install_state = {"status": "error", "error": str(exc)}
        return JSONResponse({"status": "error", "error": str(exc), "cuda_runtime": cuda_runtime_capability_state()}, status_code=500)
    _cuda_runtime_install_state = {"status": "installing", **process}
    return {
        "status": "installing",
        "message": "CUDA runtime force reinstall started. Restart Church Cap after it finishes, then check CUDA again.",
        "cuda_runtime": cuda_runtime_capability_state(),
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


@app.get("/api/update/status")
async def get_update_status(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Check update progress from the Church Cap computer."},
            status_code=403,
        )
    return update_capability_state()


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
    if capability.get("state", {}).get("status") in {"starting", "updating"}:
        return JSONResponse(
            {**capability, "status": "error", "error": "A Church Cap update is already running."},
            status_code=409,
        )
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
    global _update_state, _update_process
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
    _update_process = process.pop("_process")
    public_process = {"pid": process["pid"], "log": UPDATE_LOG_LABEL}
    _update_state = {**_update_state, "status": "updating", **public_process}
    return {
        **capability,
        "status": "updating",
        "update_available": True,
        "remote_version": remote_version,
        "remote_version_label": version_label(remote_version),
        **public_process,
    }


async def start_captions_action() -> dict:
    global _transcription_task
    if _transcription_task and not _transcription_task.done():
        return {"status": "already_running"}
    _transcription_task = asyncio.create_task(transcription_loop())
    return {"status": "started"}


async def stop_captions_action() -> dict:
    global _transcription_task
    if _transcription_task and not _transcription_task.done():
        _transcription_task.cancel()
        try:
            await _transcription_task
        except asyncio.CancelledError:
            pass
    hub.set_status("stopped")
    return {"status": "stopped"}


async def set_sensitive_action(enabled: bool) -> dict:
    reset_transcriber_buffer()
    await hub.set_sensitive_mode(enabled)
    if not enabled:
        reset_transcriber_buffer()
    return {"status": "sensitive_on" if enabled else "sensitive_off"}


@app.post("/api/start")
async def start(_: None = Depends(require_operator)):
    return await start_captions_action()


@app.post("/api/stop")
async def stop(_: None = Depends(require_operator)):
    return await stop_captions_action()


@app.post("/service-leader/api/start")
async def service_leader_start(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    return await start_captions_action()


@app.post("/service-leader/api/stop")
async def service_leader_stop(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    return await stop_captions_action()


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
    return await set_sensitive_action(True)


@app.post("/api/sensitive-off")
async def sensitive_off(_: None = Depends(require_operator)):
    return await set_sensitive_action(False)


@app.post("/service-leader/api/sensitive-on")
async def service_leader_sensitive_on(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    return await set_sensitive_action(True)


@app.post("/service-leader/api/sensitive-off")
async def service_leader_sensitive_off(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    return await set_sensitive_action(False)


@app.post("/service-leader/api/languages")
async def service_leader_update_languages(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    body = await request.json()
    runtime = load_runtime_config()
    provider = str(runtime.get("translation_provider") or settings.translation_provider or "disabled")
    requested_enabled = bool(body.get("translation_enabled"))
    allowed_by_deployment, deployment = translation_allowed_for_current_deployment()
    if requested_enabled and not allowed_by_deployment:
        return JSONResponse(
            {"status": "error", "error": deployment["capabilities"].get("message") or "Translation is not enabled for this appliance profile."},
            status_code=409,
        )
    language_policy = str(body.get("translation_language_policy") or runtime.get("translation_language_policy") or "automatic")
    if language_policy not in {"automatic", "restricted"}:
        language_policy = "automatic"
    if provider == "disabled" and requested_enabled:
        return JSONResponse(
            {"status": "error", "error": "An operator must configure a translation provider before service leaders can enable languages."},
            status_code=409,
        )
    provider_codes = set(hub.translator.supported_languages_for_provider(provider))
    operator_allowed_codes = {
        code
        for code in runtime.get("translation_allowed_languages", ["en"])
        if code != SOURCE_LANGUAGE and code in provider_codes
    }
    selectable_codes = operator_allowed_codes if str(runtime.get("translation_language_policy") or "automatic") == "restricted" else provider_codes
    submitted = body.get("languages") or []
    if not isinstance(submitted, list):
        submitted = []
    selected = sorted(
        {
            normalise_language(code)
            for code in submitted
            if normalise_language(code) != SOURCE_LANGUAGE and normalise_language(code) in selectable_codes
        }
    )
    max_active = clamp_translation_max_for_deployment(int(runtime.get("translation_max_active_languages", 2)), deployment)
    if language_policy == "restricted" and len(selected) > max_active:
        return JSONResponse(
            {"status": "error", "error": f"Choose no more than {max_active} translated languages on this installation."},
            status_code=400,
        )
    if requested_enabled and language_policy == "restricted" and not selected:
        return JSONResponse(
            {"status": "error", "error": "Choose at least one available translated language or switch to Automatic before enabling translation."},
            status_code=400,
        )
    enabled = requested_enabled and (language_policy == "automatic" or bool(selected))
    cfg = set_translation_config(
        enabled,
        [SOURCE_LANGUAGE, *selected],
        max_active,
        provider,
        language_policy,
        str(runtime.get("translation_priority_mode") or "most_viewers"),
        bool(runtime.get("translation_language_requests_enabled", True)),
        str(runtime.get("translation_timing_mode") or "responsive"),
    )
    hub.configure_translation(
        enabled=bool(cfg["translation_enabled"]),
        provider=cfg["translation_provider"],
        allowed_languages=cfg["translation_allowed_languages"],
        max_active_languages=int(cfg["translation_max_active_languages"]),
        language_policy=cfg["translation_language_policy"],
        priority_mode=cfg["translation_priority_mode"],
        timing_mode=cfg["translation_timing_mode"],
    )
    return {"status": "saved", **service_leader_language_context()}


@app.post("/service-leader/api/audio-device")
async def service_leader_update_audio(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    if captions_are_running():
        return JSONResponse(
            {"status": "error", "error": "Stop captions before changing the audio input."},
            status_code=409,
        )
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
                raise ValueError("That device is not an audio input.")
        except Exception as exc:
            return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)
    cfg = set_audio_device(device)
    return {"status": "saved", "audio_device": cfg.get("audio_device"), "restart_required": True}


@app.post("/service-leader/api/session/extend")
async def extend_service_leader_session(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    extended = service_leader_access.extend_session(request.cookies.get(SERVICE_LEADER_COOKIE_NAME))
    if extended is None:
        return JSONResponse({"status": "error", "error": "This service-leader session has expired."}, status_code=401)
    return {"status": "extended", "session": service_leader_access.session_timing(extended)}


@app.post("/api/service-leader/revoke")
async def revoke_service_leader_access(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse({"status": "error", "error": "Revoke service-leader access from the Church Cap computer."}, status_code=403)
    service_leader_access.revoke_all()
    return {"status": "revoked", **service_leader_access.access_state()}


@app.post("/api/service-leader/pairing")
async def create_operator_service_leader_pairing(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Create service-leader pairing codes from the Church Cap computer."},
            status_code=403,
        )
    token = service_leader_access.create_pairing()
    pairing_url = f"{service_leader_base_url(request)}/service-leader/pair#{token}"
    return {
        "status": "pairing",
        "pairing_qr": _qr_data_uri(pairing_url),
        "pairing_seconds": service_leader_access.pairing_ttl_seconds,
        "service_leader_url": f"{service_leader_base_url(request)}/service-leader",
        **service_leader_access.access_state(),
    }


@app.post("/api/service-leader/pairing/cancel")
async def cancel_operator_service_leader_pairing(request: Request, _: None = Depends(require_operator)):
    if not is_local_client(request):
        return JSONResponse(
            {"status": "error", "error": "Cancel service-leader pairing from the Church Cap computer."},
            status_code=403,
        )
    service_leader_access.cancel_pairings()
    return {"status": "cancelled", **service_leader_access.access_state()}


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
    allowed_by_deployment, deployment = translation_allowed_for_current_deployment()
    if enabled and not allowed_by_deployment:
        return JSONResponse(
            {"status": "error", "error": deployment["capabilities"].get("message") or "Translation is not enabled for this appliance profile."},
            status_code=409,
        )
    allowed = body.get("translation_allowed_languages") or ["en"]
    if not isinstance(allowed, list):
        allowed = ["en"]
    allowed = [normalise_language(x) for x in allowed]
    max_active = clamp_translation_max_for_deployment(int(body.get("translation_max_active_languages", 2)), deployment)
    provider = str(body.get("translation_provider") or "argos")
    if provider == "disabled":
        enabled = False
    language_policy = str(body.get("translation_language_policy") or "automatic")
    priority_mode = str(body.get("translation_priority_mode") or "most_viewers")
    requests_enabled = bool(body.get("translation_language_requests_enabled", True))
    timing_mode = str(body.get("translation_timing_mode") or "responsive")
    cfg = set_translation_config(enabled, allowed, max_active, provider, language_policy, priority_mode, requests_enabled, timing_mode)
    if not requests_enabled:
        _language_requests.clear()
    prune_language_requests_for_allowed(cfg["translation_allowed_languages"])
    hub.configure_translation(
        enabled=bool(cfg["translation_enabled"]),
        provider=cfg["translation_provider"],
        allowed_languages=cfg["translation_allowed_languages"],
        max_active_languages=int(cfg["translation_max_active_languages"]),
        language_policy=cfg["translation_language_policy"],
        priority_mode=cfg["translation_priority_mode"],
        timing_mode=cfg["translation_timing_mode"],
    )
    return {"status": "saved", **safe_translation_state()}




@app.get("/api/translation/status")
async def translation_status(_: None = Depends(require_operator)):
    return {**safe_translation_state(), "install": _translation_install_state}


@app.post("/api/language-requests")
async def request_language(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    submit_language_request(str(body.get("language") or body.get("code") or ""))
    return {"status": "requested", "translation": safe_translation_state()}


@app.post("/service-leader/api/language-requests")
async def service_leader_request_language(request: Request, session: ServiceLeaderSession = Depends(require_service_leader)):
    require_service_leader_mutation(request, session)
    body = await request.json()
    submit_language_request(str(body.get("language") or body.get("code") or ""))
    return {"status": "requested", "translation": service_leader_language_context()}


@app.post("/api/language-requests/{language}/accept")
async def accept_language_request(language: str, _: None = Depends(require_operator)):
    code = normalise_language(language)
    if code == SOURCE_LANGUAGE or code not in LANGUAGE_BY_CODE:
        raise HTTPException(status_code=400, detail="Choose a supported translated language.")
    runtime = load_runtime_config()
    provider = str(runtime.get("translation_provider") or settings.translation_provider or "disabled")
    provider_codes = set(hub.translator.supported_languages_for_provider(provider))
    if code not in provider_codes:
        raise HTTPException(status_code=409, detail="That language is not installed for the current translation provider.")
    allowed = sorted({*(runtime.get("translation_allowed_languages") or [SOURCE_LANGUAGE]), SOURCE_LANGUAGE, code})
    allowed_by_deployment, deployment = translation_allowed_for_current_deployment()
    max_active = clamp_translation_max_for_deployment(int(runtime.get("translation_max_active_languages", 2)), deployment)
    cfg = set_translation_config(
        bool(runtime.get("translation_enabled")) and allowed_by_deployment and provider != "disabled",
        allowed,
        max_active,
        provider,
        "restricted",
        str(runtime.get("translation_priority_mode") or "most_viewers"),
        bool(runtime.get("translation_language_requests_enabled", True)),
        str(runtime.get("translation_timing_mode") or "responsive"),
    )
    hub.configure_translation(
        enabled=bool(cfg["translation_enabled"]),
        provider=cfg["translation_provider"],
        allowed_languages=cfg["translation_allowed_languages"],
        max_active_languages=int(cfg["translation_max_active_languages"]),
        language_policy=cfg["translation_language_policy"],
        priority_mode=cfg["translation_priority_mode"],
        timing_mode=cfg["translation_timing_mode"],
    )
    _language_requests.pop(code, None)
    return {"status": "accepted", "translation": safe_translation_state()}


@app.post("/api/language-requests/{language}/reject")
async def reject_language_request(language: str, _: None = Depends(require_operator)):
    code = normalise_language(language)
    _language_requests.pop(code, None)
    return {"status": "rejected", "translation": safe_translation_state()}


def translation_install_script(kind: str) -> list[str]:
    system = platform.system()
    if kind in {"argos", "argos_all"}:
        if system == "Windows":
            command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "scripts" / "install-translation-models-argos.ps1")]
            if kind == "argos_all":
                command.append("-All")
            return command
        command = ["bash", str(PROJECT_ROOT / "scripts" / "install-translation-models-argos.sh")]
        if kind == "argos_all":
            command.append("--all")
        return command
    if kind == "ct2small100":
        if system == "Windows":
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "scripts" / "install-small100-ct2-int8.ps1")]
        return ["bash", str(PROJECT_ROOT / "scripts" / "install-small100-ct2-int8.sh")]
    if kind == "small100":
        if system == "Windows":
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "scripts" / "install-small100-core.ps1")]
        return ["bash", str(PROJECT_ROOT / "scripts" / "install-small100-core.sh")]
    raise ValueError("Unknown translation install kind.")


def translation_install_state() -> dict:
    global _translation_install_state
    if _translation_install_process is not None and _translation_install_state.get("status") == "installing":
        code = _translation_install_process.poll()
        if code is not None:
            _translation_install_state = {
                **_translation_install_state,
                "status": "complete" if code == 0 else "error",
                "returncode": code,
                "message": "Translation install finished." if code == 0 else "Translation install failed. Check logs/translation-install.log.",
            }
    return _translation_install_state


@app.post("/api/translation/install")
async def install_translation_resources(request: Request, _: None = Depends(require_operator)):
    global _translation_install_process, _translation_install_state
    allowed_by_deployment, deployment = translation_allowed_for_current_deployment()
    if not allowed_by_deployment:
        return JSONResponse(
            {"status": "error", "error": deployment["capabilities"].get("message") or "Translation resource installs are not enabled for this appliance profile."},
            status_code=409,
        )
    body = await request.json()
    kind = str(body.get("kind") or "argos")
    state = translation_install_state()
    if state.get("status") == "installing":
        return {"status": "installing", "message": "Translation install is already running.", "install": state}
    try:
        command = translation_install_script(kind)
    except Exception as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)
    if not (PROJECT_ROOT / ".venv").exists():
        return JSONResponse(
            {
                "status": "error",
                "error": "No local .venv was found. Run setup first, then install translation resources from this page.",
            },
            status_code=400,
        )
    script_paths = [Path(part) for part in command if "install-" in part and part.endswith((".sh", ".ps1"))]
    if script_paths and not script_paths[0].exists():
        return JSONResponse({"status": "error", "error": "Translation installer script was not found."}, status_code=500)
    logs_dir = app_support_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "translation-install.log"
    rotate_log_file(log_path)
    try:
        log_file = log_path.open("a", encoding="utf-8")
        log_file.write(f"\n[{datetime.now(timezone.utc).isoformat()}] Starting {kind} translation install\n")
        log_file.flush()
        _translation_install_process = subprocess.Popen(command, cwd=str(PROJECT_ROOT), stdout=log_file, stderr=subprocess.STDOUT)
    except Exception as exc:
        _translation_install_state = {"status": "error", "error": str(exc), "log": TRANSLATION_INSTALL_LOG_LABEL}
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
    _translation_install_state = {"status": "installing", "kind": kind, "log": TRANSLATION_INSTALL_LOG_LABEL}
    install_messages = {
        "ct2small100": "Installing the Recommended package / CTranslate2 INT8 SMaLL-100. Allow about 2 GB of temporary free space while the roughly 1.2 GB source download is converted.",
        "small100": "Installing the Compatibility package / PyTorch SMaLL-100. Its model download is approximately 1.2 GB.",
        "argos": "Installing common Base package / Argos Translate language packs.",
        "argos_all": "Installing all available Base package / Argos Translate language packs. Total storage varies and can reach several GB.",
    }
    return {"status": "installing", "message": install_messages.get(kind, "Installing translation resources."), "install": _translation_install_state}


@app.get("/api/languages")
async def languages():
    return {
        "languages": SUPPORTED_LANGUAGES,
        "ui_strings": get_client_ui_strings(),
        "ui_string_sources": get_client_ui_sources(language["code"] for language in SUPPORTED_LANGUAGES),
        "translation": safe_translation_state(),
    }


@app.get("/api/client-ui/{language}")
async def client_ui(language: str):
    language = normalise_language(language)
    strings = dict(get_client_ui_language_strings(language))
    source = get_client_ui_sources([language])[language]
    if language != SOURCE_LANGUAGE and source == "fallback":
        strings, source = await get_runtime_translated_client_ui_strings(
            language,
            translator=hub.translator,
            provider="argos",
            cache=_client_ui_runtime_translation_cache,
        )
    return {"language": language, "source": source, "strings": strings}


@app.post("/api/test-caption")
async def test_caption(_: None = Depends(require_operator)):
    filter_enabled = bool(load_runtime_config().get("profanity_filter_enabled", True))
    text = profanity_filter.apply(glossary.apply("Please turn with me to Efficiency chapter two and listen to the Word of God."), enabled=filter_enabled)
    await hub.publish(CaptionSegment(text=text, raw_text=text, is_final=True))
    return {"status": "sent", "text": text}


@app.websocket("/ws/captions")
async def ws_captions(websocket: WebSocket):
    language = normalise_language(websocket.query_params.get("lang"))
    count_viewer = websocket.query_params.get("role") != "service-leader"
    await hub.connect(websocket, language=language, count_viewer=count_viewer)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)
