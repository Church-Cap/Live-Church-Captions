import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from app.runtime_config import load_runtime_config, set_audio_device, set_performance_config, set_privacy_config, set_profanity_filter_config, set_translation_config, set_security_config
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
_cuda_runtime_install_state = {"status": "idle"}
_cuda_runtime_install_process: subprocess.Popen | None = None
CUDA_RUNTIME_LOG_LABEL = "logs/cuda-runtime-install.log"


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


def performance_platform_key(system_name: str | None = None) -> str:
    system_name = system_name or platform.system()
    if system_name == "Darwin":
        return "macos"
    if system_name == "Windows":
        return "windows"
    return "unsupported"


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
        "performance_platform": runtime.get("performance_platform") if runtime.get("performance_platform") in {"auto", "macos", "windows"} else "auto",
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
    return detect_hardware_acceleration().as_dict()


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
    if effective_platform == "windows" and hardware.get("cuda_available"):
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


def system_performance_snapshot() -> dict:
    cpu_count = os.cpu_count() or 1
    load_1m = load_5m = load_15m = None
    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except Exception:
        pass
    return {
        "platform": platform.system(),
        "cpu_count": cpu_count,
        "load_1m": load_1m,
        "load_5m": load_5m,
        "load_15m": load_15m,
        "load_1m_percent": None if load_1m is None else round((float(load_1m) / cpu_count) * 100, 1),
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
    if not path.exists() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return [f"Could not read log: {exc}"]
    return [_redact_local_paths(line) for line in lines[-max_lines:]]


def diagnostics_payload() -> dict:
    runtime = load_runtime_config()
    performance = performance_status()
    logs_dir = PROJECT_ROOT / "logs"
    safe_runtime = {
        key: value
        for key, value in runtime.items()
        if key not in {"audio_device"}
    }
    return {
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
        "metrics": get_metrics(),
        "cuda_runtime_install": cuda_runtime_capability_state(),
        "logs": {
            "update.log": _tail_log(logs_dir / "update.log"),
            "cuda-runtime-install.log": _tail_log(logs_dir / "cuda-runtime-install.log"),
            "update-restart.log": _tail_log(logs_dir / "update-restart.log"),
        },
        "privacy_note": "Diagnostics are generated only when an operator chooses to download them. They can include OS version, CPU details, memory size, project drive capacity/free space, Python version, performance settings, CUDA/Apple runtime status, runtime metrics, and recent updater/CUDA log lines with local paths redacted. They exclude transcripts, captions, operator passwords, session secrets, and .env contents. Review the file before sharing it for support, and do not post it publicly on GitHub unless you are comfortable with the contents.",
    }


def performance_status() -> dict:
    runtime = load_runtime_config()
    effective = effective_performance_config(runtime)
    hardware = detect_hardware_acceleration()
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
        return FasterWhisperTranscriber(**common, compute_type=performance["whisper_compute_type"])
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
            "performance": performance_status(),
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
    performance = effective_performance_config()
    return {
        "ok": True,
        "status": hub.state().status,
        "app_version": settings.app_version,
        "app_version_label": settings.app_version_label,
        "viewers": hub.viewer_count,
        "mode": performance["transcriber_mode"],
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


@app.post("/api/performance/apply-recommended")
async def apply_recommended_performance(_: None = Depends(require_operator)):
    recommendation = recommended_performance_config()
    cfg = set_performance_config(recommendation["config"])
    status = performance_status()
    return {"status": "saved", "restart_required": True, "recommendation": status["recommendation"], **status, "runtime": cfg}


@app.post("/api/performance")
async def update_performance(request: Request, _: None = Depends(require_operator)):
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


@app.get("/api/status")
async def api_status(_: None = Depends(require_operator)):
    state = hub.state()
    performance = performance_status()
    return {
        "status": state.status,
        "viewers": state.viewers,
        "sensitive_mode": state.sensitive_mode,
        "current": state.current.model_dump(mode="json") if state.current else None,
        "transcript_count": len(hub.final_segments()),
        "metrics": get_metrics(),
        "system_performance": system_performance_snapshot(),
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
            "stream_stability_passes": performance["effective"]["stream_stability_passes"],
            "audio_device": selected_audio_device(),
        },
        "translation": hub.translation_state(),
        "security": security_state(),
        "update": {**update_capability_state(), "state": _update_state},
        "cuda_runtime": cuda_runtime_capability_state(),
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
