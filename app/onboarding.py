"""Privacy-safe first-run recommendations and input validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.i18n import (
    LANGUAGE_BY_CODE,
    SMALL100_LANGUAGE_NAMES,
    SOURCE_LANGUAGE,
    SUPPORTED_LANGUAGES,
    normalise_language,
    translation_model_language,
)
from app.paths import data_path


ONBOARDING_LANGUAGE_SELECTION_LIMIT = 8
ONBOARDING_DESKTOP_ACTIVE_LIMIT = 20
PASSWORD_RECOVERY_MARKER = data_path("operator_password_recovery.flag")
FACTORY_RESET_MARKER = data_path("factory_reset.flag")
ONBOARDING_LANGUAGE_PACKS = {
    "english": {
        "label": "English captions only",
        "short_label": "English only",
        "provider": "ct2small100",
        "installer": None,
    },
    "efficient": {
        "label": "Broad language pack",
        "short_label": "Broad language pack",
        "provider": "ct2small100",
        "installer": "ct2small100",
    },
    "compatibility": {
        "label": "PyTorch SMaLL-100 language pack",
        "short_label": "PyTorch SMaLL-100 pack",
        "provider": "small100",
        "installer": "small100",
    },
}


def password_recovery_requested(marker: Path | None = None) -> bool:
    """Return whether setup was opened by an intentional password reset."""
    candidate = marker or PASSWORD_RECOVERY_MARKER
    try:
        return candidate.is_file()
    except OSError:
        return False


def clear_password_recovery_request(marker: Path | None = None) -> None:
    """Best-effort cleanup after the replacement password has been stored."""
    candidate = marker or PASSWORD_RECOVERY_MARKER
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        # Authentication is already restored. A stale marker is harmless while
        # auth exists and can be replaced by the next intentional reset.
        pass


def factory_reset_requested(marker: Path | None = None) -> bool:
    """Return whether the next visit should use the complete first-run setup."""
    candidate = marker or FACTORY_RESET_MARKER
    try:
        return candidate.is_file()
    except OSError:
        return False


def clear_factory_reset_request(marker: Path | None = None) -> None:
    """Remove the reset marker after the complete setup has been saved."""
    candidate = marker or FACTORY_RESET_MARKER
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        pass


def _positive_int(value: object, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def local_pytorch_cuda_available() -> bool:
    """Check the installed open-source PyTorch runtime without contacting a service."""
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def build_onboarding_recommendation(performance: dict[str, Any], deployment: dict[str, Any]) -> dict[str, Any]:
    """Turn detailed local detection into a small, non-identifying setup summary."""
    hardware = dict(performance.get("hardware_acceleration") or {})
    performance_recommendation = dict(performance.get("recommendation") or {})
    config = dict(performance_recommendation.get("config") or {})
    capabilities = dict(deployment.get("capabilities") or {})
    platform_name = str(hardware.get("platform") or performance.get("detected_platform") or "Computer")
    cpu_count = _positive_int(performance_recommendation.get("cpu_count"), 1)
    cuda_ready = bool(hardware.get("cuda_available"))
    cuda_runtime_requested = bool(performance.get("cuda_runtime_requested"))
    pytorch_cuda_ready = bool(performance.get("pytorch_cuda_available"))
    windows_packaged_cpu_torch = bool(performance.get("windows_packaged_cpu_torch"))
    nvidia_detected = platform_name.lower() in {"windows", "linux"} and bool(
        hardware.get("nvidia_driver_status") == "detected"
        or hardware.get("nvidia_smi_available")
        or hardware.get("cuda_device_count", 0)
        or cuda_ready
        or pytorch_cuda_ready
    )
    try:
        memory_bytes = int(performance.get("total_memory_bytes") or 0)
    except (TypeError, ValueError):
        memory_bytes = 0
    memory_gb = round(memory_bytes / (1024 ** 3)) if memory_bytes > 0 else None

    if cuda_ready:
        hardware_title = "NVIDIA acceleration is ready"
        hardware_detail = "Church Cap can use the NVIDIA GPU for English caption recognition. Translation still adds work, so the initial language limit remains conservative."
        recommended_active = 4
    elif nvidia_detected and pytorch_cuda_ready:
        hardware_title = "NVIDIA translation acceleration is ready"
        hardware_detail = "PyTorch can use this NVIDIA GPU for translated captions. English recognition may still use the CPU, so start with a modest live-language limit."
        recommended_active = 3
    elif platform_name == "Darwin" and cpu_count >= 8:
        hardware_title = "Multi-core Mac detected"
        hardware_detail = "Balanced Faster Whisper is a safe starting point on this Mac. Local translation uses additional processor and memory capacity."
        recommended_active = 3
    elif cpu_count >= 8:
        hardware_title = "Multi-core CPU detected"
        hardware_detail = "Church Cap will favour responsive CPU settings. Start with a small number of simultaneous translated languages and benchmark before increasing it."
        recommended_active = 2
    else:
        hardware_title = "Conservative CPU setup recommended"
        hardware_detail = "This computer should begin with the lowest practical caption delay and one simultaneous translated language."
        recommended_active = 1

    deployment_limit = capabilities.get("translation_max_limit")
    hard_limit = _positive_int(deployment_limit, ONBOARDING_DESKTOP_ACTIVE_LIMIT) if deployment_limit else ONBOARDING_DESKTOP_ACTIVE_LIMIT
    recommended_active = min(recommended_active, hard_limit)
    translation_available = bool(capabilities.get("allow_translation", True))
    if not translation_available:
        recommended_active = 1

    if not translation_available:
        recommended_language_pack = "english"
        language_pack_reason = "This Church Cap profile is configured for English captions, so no translation download is recommended."
    elif (memory_gb is not None and memory_gb < 12) or (not cuda_ready and not pytorch_cuda_ready and cpu_count <= 4):
        recommended_language_pack = "english"
        if memory_gb is not None and memory_gb < 12:
            language_pack_reason = (
                "English-only captions are the safest starting point with the detected memory. "
                "A language pack can still be added later after a successful benchmark."
            )
        else:
            language_pack_reason = (
                "English-only captions are the safest starting point on this lower-power CPU. "
                "A language pack can still be added later after a successful benchmark."
            )
    elif nvidia_detected and pytorch_cuda_ready:
        recommended_language_pack = "compatibility"
        language_pack_reason = (
            "NVIDIA GPU detected and PyTorch confirmed it can use CUDA on this computer. "
            "The PyTorch language pack is recommended for GPU translation; test its delay with your service audio before relying on it."
        )
    else:
        recommended_language_pack = "efficient"
        language_pack_reason = (
            "The broad language pack is the best balance for this computer. "
            "It uses an efficient local translation engine and keeps the live-language limit conservative."
        )

    preset = str(config.get("performance_preset") or "balanced")
    model = str(config.get("whisper_model") or "base.en")
    preset_labels = {
        "fastest": "Fastest",
        "fast": "Fast",
        "balanced": "Balanced",
        "accurate": "Accurate",
        "most_accurate": "Most accurate",
    }
    model_labels = {
        "tiny.en": "Tiny English",
        "base.en": "Base English",
        "small.en": "Small English",
        "medium.en": "Medium English",
    }
    local_check_parts = [f"{cpu_count} logical processor{'s' if cpu_count != 1 else ''}"]
    if memory_gb is not None:
        local_check_parts.append(f"about {memory_gb} GB memory")
    if cuda_ready:
        local_check_parts.append("ready NVIDIA CUDA acceleration")
    elif nvidia_detected and pytorch_cuda_ready:
        local_check_parts.append("PyTorch CUDA translation ready")
    elif platform_name != "Darwin":
        local_check_parts.append("English-caption CUDA acceleration not ready")

    show_pytorch_pack = nvidia_detected or cuda_runtime_requested
    if pytorch_cuda_ready:
        pytorch_pack_badge = "CUDA verified"
        pytorch_pack_detail = (
            "The installed PyTorch runtime reports that NVIDIA CUDA is available. "
            "This original SMaLL-100 path can use the GPU, but it needs more memory and should be benchmarked against the Broad pack."
        )
    elif windows_packaged_cpu_torch:
        pytorch_pack_badge = "CPU fallback"
        pytorch_pack_detail = (
            "This Windows installer includes CPU-only PyTorch. The optional NVIDIA CUDA download "
            "accelerates the Broad/CTranslate2 path where supported, not this PyTorch pack. "
            "Use PyTorch mainly for compatibility testing or comparison."
        )
    elif nvidia_detected:
        pytorch_pack_badge = "CUDA check needed"
        pytorch_pack_detail = (
            "NVIDIA GPU detected, but PyTorch has not confirmed it can use CUDA. "
            "This pack may run on the CPU until PyTorch GPU support is ready, so the Broad pack is the safer starting point."
        )
    elif cuda_runtime_requested:
        pytorch_pack_badge = "CUDA pending"
        pytorch_pack_detail = (
            "NVIDIA CUDA was selected in the Windows installer, but its runtime is not verified yet. "
            "Church Cap will only describe this pack as GPU-ready after both CUDA and PyTorch pass their local checks."
        )
    else:
        pytorch_pack_badge = "Fallback"
        pytorch_pack_detail = (
            "Uses the original SMaLL-100 model through PyTorch. It needs more memory and may add latency, "
            "so use it mainly for compatibility testing or comparison."
        )

    # A verified Windows CUDA runtime lets the Broad/CTranslate2 provider use
    # the GPU. Select both packs for Automatic mode, with CPU-only PyTorch as
    # the fallback in the small Windows installer. A driver or an installer
    # request alone is not enough to claim CUDA is ready.
    default_language_packs = [recommended_language_pack]
    if (
        platform_name.lower() == "windows"
        and cuda_ready
        and translation_available
        and recommended_language_pack != "english"
    ):
        default_language_packs = ["efficient", "compatibility"]

    return {
        "hardware_title": hardware_title,
        "hardware_detail": hardware_detail,
        "performance_label": preset_labels.get(preset, preset.replace("_", " ").title()),
        "model_label": model_labels.get(model, model),
        "performance_reason": str(performance_recommendation.get("reason") or "Church Cap selected a safe local starting point."),
        "performance_config": config,
        "recommended_active_languages": recommended_active,
        "maximum_active_languages": hard_limit,
        "translation_available": translation_available,
        "translation_message": str(capabilities.get("message") or "Local translated captions are available."),
        "language_selection_limit": ONBOARDING_LANGUAGE_SELECTION_LIMIT,
        # Keep the single-pack recommendation for labels while allowing a
        # verified Windows CUDA system to start with both packs in Automatic
        # mode. English-only remains an explicit, lightweight choice.
        "default_language_pack": recommended_language_pack,
        "default_language_packs": default_language_packs,
        "recommended_language_pack": recommended_language_pack,
        "language_pack_reason": language_pack_reason,
        "local_check_summary": f"Checked locally: {', '.join(local_check_parts)}.",
        "cuda_ready": cuda_ready,
        "nvidia_detected": nvidia_detected,
        "cuda_runtime_requested": cuda_runtime_requested,
        "pytorch_cuda_ready": pytorch_cuda_ready,
        "windows_packaged_cpu_torch": windows_packaged_cpu_torch,
        "show_pytorch_pack": show_pytorch_pack,
        "pytorch_pack_badge": pytorch_pack_badge,
        "pytorch_pack_detail": pytorch_pack_detail,
    }


def validate_onboarding_language_pack(value: object, *, translation_available: bool = True) -> str:
    """Return one allow supported first-run pack without probing any remote service."""
    pack = str(value or "english").strip().lower()
    if pack not in ONBOARDING_LANGUAGE_PACKS:
        raise ValueError("Choose one of the language packs shown in setup.")
    if pack != "english" and not translation_available:
        raise ValueError("Translated captions are not available for this Church Cap deployment profile.")
    return pack


def validate_onboarding_language_packs(
    values: Iterable[object] | None,
    *,
    translation_available: bool = True,
) -> list[str]:
    """Return a safe multi-pack selection while keeping English mutually exclusive."""
    selected: list[str] = []
    for value in values or ():
        pack = validate_onboarding_language_pack(value, translation_available=translation_available)
        if pack not in selected:
            selected.append(pack)
    if not selected:
        return ["english"]
    translated = [pack for pack in selected if pack != "english"]
    return translated or ["english"]


def onboarding_language_pack_config(pack: str) -> dict[str, Any]:
    """Build the provider, installer and safe language catalogue for a setup pack."""
    pack = validate_onboarding_language_pack(pack)
    definition = dict(ONBOARDING_LANGUAGE_PACKS[pack])
    if pack == "english":
        languages = [SOURCE_LANGUAGE]
    else:
        languages = [
            language["code"]
            for language in SUPPORTED_LANGUAGES
            if language["code"] != "ti" and translation_model_language(language["code"]) in SMALL100_LANGUAGE_NAMES
        ]
        if pack == "efficient" and "ti" in LANGUAGE_BY_CODE:
            languages.append("ti")
        languages = [SOURCE_LANGUAGE, *[code for code in languages if code != SOURCE_LANGUAGE]]
    return {
        **definition,
        "key": pack,
        "enabled": pack != "english",
        "languages": languages,
    }


def onboarding_language_packs_config(packs: Iterable[object] | None) -> dict[str, Any]:
    """Combine one or more first-run packs into one runtime and installer plan."""
    selected = validate_onboarding_language_packs(packs)
    translated = [pack for pack in selected if pack != "english"]
    if not translated:
        return {**onboarding_language_pack_config("english"), "selected_packs": ["english"], "installers": []}
    configs = [onboarding_language_pack_config(pack) for pack in translated]
    languages = [SOURCE_LANGUAGE]
    for config in configs:
        for language in config["languages"]:
            if language not in languages:
                languages.append(language)
    installers = [str(config["installer"]) for config in configs if config.get("installer")]
    if len(configs) == 1:
        return {**configs[0], "selected_packs": translated, "installers": installers}
    return {
        "key": "all",
        "label": "All language packs · Automatic",
        "short_label": "All packs · Automatic",
        "provider": "both",
        "installer": None,
        "installers": installers,
        "selected_packs": translated,
        "enabled": True,
        "languages": languages,
    }


def onboarding_language_pack_for_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    """Describe the onboarding pack represented by saved runtime settings."""
    if not bool(runtime.get("translation_enabled")):
        return onboarding_language_pack_config("english")
    provider = str(runtime.get("translation_provider") or "ct2small100")
    if provider == "both":
        return onboarding_language_packs_config(("efficient", "compatibility"))
    return onboarding_language_pack_config("compatibility" if provider == "small100" else "efficient")


def onboarding_language_options() -> list[dict[str, str]]:
    return [dict(language) for language in SUPPORTED_LANGUAGES if language["code"] != SOURCE_LANGUAGE]


def validate_onboarding_languages(values: Iterable[object] | None) -> list[str]:
    """Return unique supported target codes while preserving the user's order."""
    result: list[str] = []
    for raw in values or ():
        original = str(raw or "").strip().lower().replace("_", "-")
        code = normalise_language(original)
        if code == SOURCE_LANGUAGE or code not in LANGUAGE_BY_CODE:
            continue
        if code not in result:
            result.append(code)
    if len(result) > ONBOARDING_LANGUAGE_SELECTION_LIMIT:
        raise ValueError(
            f"Choose no more than {ONBOARDING_LANGUAGE_SELECTION_LIMIT} languages during first setup. More can be enabled later from Languages."
        )
    return result


def clamp_onboarding_active_limit(value: object, *, maximum: int, selected_count: int) -> int:
    requested = _positive_int(value, 1)
    useful_maximum = max(1, min(_positive_int(maximum, 1), max(1, selected_count)))
    return min(requested, useful_maximum)
