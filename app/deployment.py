"""Deployment identity and UI capabilities.

Hardware detection tells Church Cap what a machine can do. It must not decide
whether a normal computer is a Church Cap appliance. Appliance mode is entered
only through an explicit installer-owned identity file or environment variables.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


IDENTITY_PATH = Path(os.environ.get("CHURCHCAP_APPLIANCE_IDENTITY_FILE", "/etc/churchcap-appliance/identity.json"))
VALID_PROFILES = {"desktop", "appliance_cpu", "appliance_gpu"}


@dataclass(frozen=True)
class DeploymentIdentity:
    mode: str = "desktop"
    profile: str = "desktop"
    appliance_id: str | None = None
    edition: str = "desktop"
    language_mode: str = "full"
    source: str = "default"

    @property
    def is_appliance(self) -> bool:
        return self.mode == "appliance"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_profile(value: Any, *, default: str) -> str:
    profile = str(value or "").strip().lower().replace("-", "_")
    return profile if profile in VALID_PROFILES else default


def _identity_from_mapping(data: dict[str, Any], *, source: str) -> DeploymentIdentity | None:
    explicit_appliance = bool(data.get("appliance")) or str(data.get("mode", "")).strip().lower() == "appliance"
    profile = _clean_profile(data.get("profile"), default="appliance_gpu" if data.get("language_mode") == "multilingual" else "appliance_cpu")
    if not explicit_appliance and profile == "desktop":
        return None
    if profile == "desktop":
        profile = "appliance_gpu" if str(data.get("language_mode", "")).lower() == "multilingual" else "appliance_cpu"
    language_mode = str(data.get("language_mode") or ("multilingual" if profile == "appliance_gpu" else "english_only")).strip().lower()
    if language_mode not in {"english_only", "multilingual", "full", "cpu_limited"}:
        language_mode = "multilingual" if profile == "appliance_gpu" else "english_only"
    return DeploymentIdentity(
        mode="appliance",
        profile=profile,
        appliance_id=str(data.get("appliance_id") or data.get("id") or "").strip() or None,
        edition=str(data.get("edition") or "churchcap-box").strip() or "churchcap-box",
        language_mode=language_mode,
        source=source,
    )


@lru_cache(maxsize=1)
def load_deployment_identity() -> DeploymentIdentity:
    env_mode = os.environ.get("CHURCHCAP_DEPLOYMENT", "").strip().lower()
    env_profile = os.environ.get("CHURCHCAP_PROFILE", "").strip().lower().replace("-", "_")
    if env_mode == "appliance" or env_profile.startswith("appliance_"):
        identity = _identity_from_mapping(
            {
                "appliance": True,
                "profile": env_profile or os.environ.get("CHURCHCAP_APPLIANCE_PROFILE"),
                "appliance_id": os.environ.get("CHURCHCAP_APPLIANCE_ID"),
                "edition": os.environ.get("CHURCHCAP_APPLIANCE_EDITION") or "churchcap-box",
                "language_mode": os.environ.get("CHURCHCAP_LANGUAGE_MODE"),
            },
            source="env",
        )
        if identity is not None:
            return identity

    try:
        if IDENTITY_PATH.exists():
            loaded = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                identity = _identity_from_mapping(loaded, source=str(IDENTITY_PATH))
                if identity is not None:
                    return identity
    except Exception:
        pass

    return DeploymentIdentity()


def deployment_capabilities(identity: DeploymentIdentity, hardware: dict[str, Any] | None = None) -> dict[str, Any]:
    hardware = hardware or {}
    cuda_ready = bool(hardware.get("cuda_available"))
    if not identity.is_appliance:
        return {
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
            "gpu_available": cuda_ready,
            "message": "Desktop profile: full operator controls are available.",
        }

    gpu_profile = identity.profile == "appliance_gpu"
    cpu_profile = identity.profile == "appliance_cpu"
    cpu_translation_available = cpu_profile
    cpu_translation_enabled = cpu_profile and identity.language_mode == "cpu_limited"
    allow_translation = cpu_translation_enabled or (gpu_profile and cuda_ready)
    show_translation_setup = gpu_profile or cpu_translation_available
    show_translation_install = (gpu_profile and cuda_ready) or cpu_translation_enabled
    cpu_limit = 3 if cpu_translation_available else None
    if gpu_profile and cuda_ready:
        message = "Appliance GPU profile: multilingual controls are available."
    elif gpu_profile:
        message = "Appliance GPU profile is selected, but CUDA is not ready; multilingual controls should remain limited."
    elif cpu_translation_enabled:
        message = "Appliance CPU profile: translated captions are enabled as an advanced option. Confirm the warning first, then keep the limit to three active languages or fewer."
    else:
        message = "Appliance CPU profile: translated captions are currently off in the System menu. Enable CPU language options there before using translated captions."
    return {
        "profile": identity.profile,
        "is_appliance": True,
        "simple_operator": True,
        "show_model_slider": False,
        "show_performance_advanced": False,
        "show_translation_setup": show_translation_setup,
        "show_translation_install": show_translation_install,
        "allow_translation": allow_translation,
        "language_mode": "multilingual" if gpu_profile else identity.language_mode,
        "recommended_max_languages": 4 if gpu_profile and cuda_ready else (3 if cpu_translation_enabled else 1),
        "translation_max_limit": cpu_limit,
        "translation_advanced": cpu_translation_available,
        "cpu_translation_warning": cpu_translation_available,
        "cpu_translation_requires_confirmation": cpu_translation_available,
        "cpu_translation_available": cpu_translation_available,
        "cpu_translation_enabled": cpu_translation_enabled,
        "gpu_required_for_languages": gpu_profile,
        "gpu_available": cuda_ready,
        "message": message,
    }


def deployment_context(hardware: dict[str, Any] | None = None) -> dict[str, Any]:
    # The appliance shell can change language_mode while the web process is
    # still alive. Refresh the tiny identity file each time so the operator UI
    # does not keep using a stale english_only/cpu_limited state.
    load_deployment_identity.cache_clear()
    identity = load_deployment_identity()
    return {
        "identity": identity.as_dict(),
        "capabilities": deployment_capabilities(identity, hardware),
    }
