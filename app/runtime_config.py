"""Runtime configuration that can be changed from the operator page.

This deliberately stores only small, non-secret settings locally. It lets a church
choose an audio device and privacy defaults from the web UI without editing .env.
"""
from __future__ import annotations

import json
from threading import Lock
from typing import Any

from app.paths import data_path, migrate_project_data

CONFIG_PATH = data_path("runtime_config.json")
_lock = Lock()

DEFAULTS: dict[str, Any] = {
    "audio_device": None,
    "transcript_saving_enabled": True,
    "transcript_retention_minutes": 120,
    "translation_enabled": False,
    "translation_allowed_languages": ["en"],
    "translation_max_active_languages": 1,
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
            cfg["translation_max_active_languages"] = max(1, min(8, int(cfg["translation_max_active_languages"])))
        except Exception:
            cfg["translation_max_active_languages"] = DEFAULTS["translation_max_active_languages"]
        cfg["transcript_saving_enabled"] = bool(cfg["transcript_saving_enabled"])
        cfg["translation_enabled"] = bool(cfg["translation_enabled"])
        cfg["profanity_filter_enabled"] = bool(cfg["profanity_filter_enabled"])
        cfg["lock_operator_to_localhost"] = bool(cfg.get("lock_operator_to_localhost", True))
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


def set_privacy_config(save_transcripts: bool, retention_minutes: int) -> dict[str, Any]:
    cfg = load_runtime_config()
    cfg["transcript_saving_enabled"] = save_transcripts
    cfg["transcript_retention_minutes"] = retention_minutes
    return save_runtime_config(cfg)


def set_translation_config(enabled: bool, allowed_languages: list[str], max_active_languages: int) -> dict[str, Any]:
    cfg = load_runtime_config()
    cfg["translation_enabled"] = bool(enabled)
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
