from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from threading import Lock

_lock = Lock()

@dataclass
class RuntimeMetrics:
    audio_rms: float = 0.0
    audio_peak: float = 0.0
    has_recent_voice: bool = False
    last_voice_age_seconds: float | None = None
    model_name: str = ""
    model_device: str = ""
    model_compute_type: str = ""
    model_loaded: bool = False
    model_load_seconds: float | None = None
    last_transcription_seconds: float | None = None
    last_update_at: float | None = None
    transcriptions_completed: int = 0
    audio_device: str | int | None = None
    sample_rate: int = 16000
    error: str | None = None

_metrics = RuntimeMetrics()


def update_metrics(**kwargs) -> None:
    with _lock:
        for key, value in kwargs.items():
            if hasattr(_metrics, key):
                setattr(_metrics, key, value)


def reset_metrics() -> None:
    global _metrics
    with _lock:
        _metrics = RuntimeMetrics()


def get_metrics() -> dict:
    with _lock:
        data = asdict(_metrics)
    if data.get("last_update_at"):
        data["last_update_age_seconds"] = max(0.0, time.monotonic() - float(data["last_update_at"]))
    else:
        data["last_update_age_seconds"] = None
    return data
