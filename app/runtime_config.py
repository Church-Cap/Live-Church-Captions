"""Runtime configuration that can be changed from the operator page.

This deliberately stores only small, non-secret settings locally. It lets a church
choose an audio device and privacy defaults from the web UI without editing .env.
"""
from __future__ import annotations

import json
from threading import Lock
from typing import Any

from app.i18n import MAX_TRANSLATION_LANGUAGES
from app.paths import data_path, migrate_project_data

CONFIG_PATH = data_path("runtime_config.json")
_lock = Lock()

DEFAULTS: dict[str, Any] = {
    "audio_device": None,
    "performance_preset": "balanced",
    "performance_platform": "auto",
    "transcriber_mode": None,
    "whisper_model": None,
    "whisper_device": None,
    "whisper_compute_type": None,
    "whisper_beam_size": None,
    "chunk_seconds": None,
    "stream_window_seconds": None,
    "stream_update_interval_seconds": None,
    "stream_silence_finalise_seconds": None,
    "stream_stability_passes": None,
    "transcript_saving_enabled": True,
    "transcript_retention_minutes": 120,
    "translation_enabled": False,
    "translation_provider": "argos",
    "translation_allowed_languages": ["en"],
    "translation_max_active_languages": 20,
    "translation_language_policy": "automatic",
    "translation_priority_mode": "most_viewers",
    "profanity_filter_enabled": True,
    "security_mode": "secure_operator",
    "lock_operator_to_localhost": True,
}


def load_runtime_config() -> dict[str, Any]:
    migrate_project_data("runtime_config.json", CONFIG_PATH)
    with _lock:
        if not CONFIG_PATH.exists():
            return dict(DEFAULTS)
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return dict(DEFAULTS)
        cfg = dict(DEFAULTS)
        cfg.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        return cfg


def save_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = dict(DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in DEFAULTS})
        try:
            cfg["transcript_retention_minutes"] = max(0, int(cfg["transcript_retention_minutes"]))
        except Exception:
            cfg["transcript_retention_minutes"] = DEFAULTS["transcript_retention_minutes"]
        try:
            cfg["translation_max_active_languages"] = max(1, min(MAX_TRANSLATION_LANGUAGES, int(cfg["translation_max_active_languages"])))
        except Exception:
            cfg["translation_max_active_languages"] = DEFAULTS["translation_max_active_languages"]
        cfg["transcript_saving_enabled"] = bool(cfg["transcript_saving_enabled"])
        cfg["translation_enabled"] = bool(cfg["translation_enabled"])
        if cfg.get("translation_provider") not in {"disabled", "argos", "small100", "both", "demo"}:
            cfg["translation_provider"] = "argos"
        if cfg.get("translation_language_policy") not in {"automatic", "restricted"}:
            cfg["translation_language_policy"] = "automatic"
        if cfg.get("translation_priority_mode") not in {"most_viewers", "pinned_first"}:
            cfg["translation_priority_mode"] = "most_viewers"
        cfg["profanity_filter_enabled"] = bool(cfg["profanity_filter_enabled"])
        cfg["lock_operator_to_localhost"] = bool(cfg.get("lock_operator_to_localhost", True))
        if not isinstance(cfg.get("performance_preset"), str) or cfg.get("performance_preset") not in {"fastest", "fast", "balanced", "accurate", "most_accurate", "custom"}:
            cfg["performance_preset"] = "balanced"
        if not isinstance(cfg.get("performance_platform"), str) or cfg.get("performance_platform") not in {"auto", "macos", "windows"}:
            cfg["performance_platform"] = "auto"
        if cfg.get("transcriber_mode") is not None and (not isinstance(cfg.get("transcriber_mode"), str) or cfg.get("transcriber_mode") not in {"whisper", "faster_whisper"}):
            cfg["transcriber_mode"] = None
        if cfg.get("whisper_model") is not None and (not isinstance(cfg.get("whisper_model"), str) or cfg.get("whisper_model") not in {"tiny.en", "base.en", "small.en", "medium.en"}):
            cfg["whisper_model"] = None
        if cfg.get("whisper_device") is not None and (not isinstance(cfg.get("whisper_device"), str) or cfg.get("whisper_device") not in {"auto", "cpu", "cuda", "mps"}):
            cfg["whisper_device"] = None
        if cfg.get("whisper_compute_type") is not None and (not isinstance(cfg.get("whisper_compute_type"), str) or cfg.get("whisper_compute_type") not in {"auto", "int8", "float16", "float32"}):
            cfg["whisper_compute_type"] = None
        for key, default, lower, upper, cast in (
            ("whisper_beam_size", None, 1, 8, int),
            ("chunk_seconds", None, 0.5, 6.0, float),
            ("stream_window_seconds", None, 2.0, 14.0, float),
            ("stream_update_interval_seconds", None, 0.35, 3.0, float),
            ("stream_silence_finalise_seconds", None, 0.3, 4.0, float),
            ("stream_stability_passes", None, 1, 4, int),
        ):
            value = cfg.get(key)
            if value is None or value == "":
                cfg[key] = default
                continue
            try:
                cfg[key] = max(lower, min(upper, cast(value)))
            except Exception:
                cfg[key] = default
        if cfg.get("security_mode") not in {"easy_offline", "secure_operator", "managed_https"}:
            cfg["security_mode"] = "secure_operator"
        allowed = cfg.get("translation_allowed_languages") or ["en"]
        if not isinstance(allowed, list):
            allowed = ["en"]
        cfg["translation_allowed_languages"] = sorted(set(str(x).lower().strip() for x in allowed if str(x).strip())) or ["en"]
        if "en" not in cfg["translation_allowed_languages"]:
            cfg["translation_allowed_languages"].insert(0, "en")
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg


def set_audio_device(device: str | int | None) -> dict[str, Any]:
    cfg = load_runtime_config()
    if device == "" or device == "default":
        device = None
    cfg["audio_device"] = device
    return save_runtime_config(cfg)


def set_performance_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = load_runtime_config()
    for key in (
        "performance_preset",
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
        if key in config:
            cfg[key] = config[key]
    return save_runtime_config(cfg)


def set_privacy_config(save_transcripts: bool, retention_minutes: int) -> dict[str, Any]:
    cfg = load_runtime_config()
    cfg["transcript_saving_enabled"] = save_transcripts
    cfg["transcript_retention_minutes"] = retention_minutes
    return save_runtime_config(cfg)


def set_translation_config(
    enabled: bool,
    allowed_languages: list[str] | None,
    max_active_languages: int,
    provider: str | None = None,
    language_policy: str | None = None,
    priority_mode: str | None = None,
) -> dict[str, Any]:
    cfg = load_runtime_config()
    cfg["translation_enabled"] = bool(enabled)
    if provider is not None:
        cfg["translation_provider"] = provider
    if language_policy is not None:
        cfg["translation_language_policy"] = language_policy
    if priority_mode is not None:
        cfg["translation_priority_mode"] = priority_mode
    if allowed_languages is not None:
        cfg["translation_allowed_languages"] = allowed_languages
    cfg["translation_max_active_languages"] = max_active_languages
    return save_runtime_config(cfg)


def set_profanity_filter_config(enabled: bool) -> dict[str, Any]:
    cfg = load_runtime_config()
    cfg["profanity_filter_enabled"] = bool(enabled)
    return save_runtime_config(cfg)


def set_security_config(security_mode: str, lock_operator_to_localhost: bool | None = None) -> dict[str, Any]:
    cfg = load_runtime_config()
    if security_mode not in {"easy_offline", "secure_operator", "managed_https"}:
        security_mode = "secure_operator"
    cfg["security_mode"] = security_mode
    if lock_operator_to_localhost is None:
        cfg["lock_operator_to_localhost"] = security_mode in {"secure_operator", "managed_https"}
    else:
        cfg["lock_operator_to_localhost"] = bool(lock_operator_to_localhost)
    return save_runtime_config(cfg)
