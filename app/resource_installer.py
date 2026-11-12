"""Install optional mutable resources without modifying a packaged runtime."""

from __future__ import annotations

import hashlib
import hmac
import os
import runpy
import sys
from pathlib import Path

from app.install_progress import write_install_progress
from app.paths import model_data_dir, resource_root
from app.translation_packages import validate_argos_package_archive


SMALL100_MODEL = "alirezamsh/small100"
SMALL100_REVISION = "8ab680e26a596d2e3d2d2d17ae0f68df1037328c"
SMALL100_TOKENIZER_SHA256 = "73c8d2405e9c588582434c9f91327127faf133b9f915b203ed07ba4cd0ca9c92"
TIGRINYA_MODEL = "Helsinki-NLP/opus-mt-en-ti"
TIGRINYA_REVISION = "72f1e40b4b60ff4863407f90792b4fac517562ec"
COMMON_ARGOS_TARGETS = ("es", "fr", "pt", "pl", "uk", "ar", "fa", "zh", "zt")


def validate_tokenizer_save_paths(tokenizer: object, save_directory: Path) -> None:
    """Reject named chat templates that could escape a tokenizer save directory."""
    templates = getattr(tokenizer, "chat_template", None)
    if not isinstance(templates, dict):
        return
    template_root = (Path(save_directory) / "chat_templates").resolve()
    for name in templates:
        if not isinstance(name, str):
            raise RuntimeError("The pinned tokenizer contains an invalid chat-template name.")
        target = (template_root / f"{name}.jinja").resolve()
        if target.parent != template_root:
            raise RuntimeError("The pinned tokenizer contains an unsafe chat-template path.")


def validate_packaged_installer_runtime() -> None:
    """Fail before a large download if signed installer resources are incomplete."""
    write_install_progress(3, "runtime-check", "Checking the packaged language installer before downloading.", indeterminate=True)
    import ctranslate2  # noqa: F401
    import safetensors  # noqa: F401
    import sherpa_onnx  # noqa: F401
    from ctranslate2.converters import TransformersConverter  # noqa: F401
    from ctranslate2.converters import transformers as ctranslate2_transformers
    from transformers import AutoTokenizer, M2M100ForConditionalGeneration  # noqa: F401

    missing_converter_dependencies = [
        name
        for name in ("huggingface_hub", "torch", "transformers")
        if not hasattr(ctranslate2_transformers, name)
    ]
    if missing_converter_dependencies:
        raise RuntimeError(
            "CTranslate2 model conversion dependencies are incomplete: "
            + ", ".join(missing_converter_dependencies)
        )

    required_resources = (
        resource_root() / "scripts" / "install-tts-voices.py",
        resource_root() / "docs" / "legal" / "SPOKEN_LANGUAGE_MODELS.md",
    )
    missing = [str(path) for path in required_resources if not path.is_file()]
    if missing:
        raise RuntimeError(f"Packaged resource installer file is missing: {missing[0]}")


def _check_small100_tokenizer() -> Path:
    from huggingface_hub import hf_hub_download

    tokenizer = Path(
        hf_hub_download(
            SMALL100_MODEL,
            "tokenization_small100.py",
            revision=SMALL100_REVISION,
        )
    )
    digest = hashlib.sha256(tokenizer.read_bytes()).hexdigest()
    if not hmac.compare_digest(digest, SMALL100_TOKENIZER_SHA256):
        raise RuntimeError("Pinned SMaLL-100 tokenizer failed its integrity check.")
    return tokenizer


def install_argos(*, all_languages: bool = False) -> None:
    from argostranslate import package

    write_install_progress(10, "package-index", "Loading the Base language package index.")
    package.update_package_index()
    available = package.get_available_packages()
    targets = (
        sorted({item.to_code for item in available if item.from_code == "en" and item.to_code != "en"})
        if all_languages
        else list(COMMON_ARGOS_TARGETS)
    )
    items = [{"id": code, "label": code.upper(), "state": "pending", "percent": 0} for code in targets]
    write_install_progress(14, "package-index", f"Found {len(targets)} Base language packages to check.", item_count=len(targets), items=items)
    for index, target in enumerate(targets, start=1):
        start = 14 + round(80 * ((index - 1) / max(1, len(targets))))
        items[index - 1].update(state="downloading", percent=20)
        write_install_progress(start, "downloading-package", f"Downloading and installing English to {target.upper()}.", item_index=index, item_count=len(targets), items=items, indeterminate=True)
        candidates = [item for item in available if item.from_code == "en" and item.to_code == target]
        if not candidates:
            items[index - 1].update(state="error", percent=100)
            write_install_progress(start, "package-missing", f"No English to {target.upper()} package was available.", item_index=index, item_count=len(targets), items=items)
            continue
        archive = candidates[0].download()
        validate_argos_package_archive(archive)
        package.install_from_path(archive)
        items[index - 1].update(state="complete", percent=100)
        write_install_progress(14 + round(80 * (index / max(1, len(targets)))), "package-complete", f"English to {target.upper()} is installed.", item_index=index, item_count=len(targets), items=items)
    write_install_progress(100, "complete", "Base translation packages are ready.")


def install_tigrinya() -> None:
    import ctranslate2
    from ctranslate2.converters import TransformersConverter
    from transformers import AutoTokenizer

    root = model_data_dir()
    model_dir = root / "opus-mt-en-ti-ct2-int8"
    tokenizer_dir = root / "opus-mt-en-ti-tokenizer"
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    required = ("tokenizer_config.json", "source.spm", "target.spm", "vocab.json")
    if not ctranslate2.contains_model(str(model_dir)) or not all((tokenizer_dir / name).is_file() for name in required):
        write_install_progress(82, "tigrinya-downloading", "Downloading the pinned English-to-Tigrinya model.", indeterminate=True)
        tokenizer = AutoTokenizer.from_pretrained(TIGRINYA_MODEL, revision=TIGRINYA_REVISION)
        validate_tokenizer_save_paths(tokenizer, tokenizer_dir)
        tokenizer.save_pretrained(tokenizer_dir)
        write_install_progress(90, "tigrinya-converting", "Converting the Tigrinya model to INT8.", indeterminate=True)
        TransformersConverter(TIGRINYA_MODEL, revision=TIGRINYA_REVISION, trust_remote_code=False).convert(
            output_dir=str(model_dir), quantization="int8", force=True
        )
    write_install_progress(98, "tigrinya-ready", "The Tigrinya translation model is ready.")


def install_recommended() -> None:
    import ctranslate2
    from ctranslate2.converters import TransformersConverter

    output = model_data_dir() / "small100-ct2-int8"
    output.parent.mkdir(parents=True, exist_ok=True)
    if not ctranslate2.contains_model(str(output)):
        write_install_progress(18, "downloading", "Downloading the pinned SMaLL-100 model.", indeterminate=True)
        _check_small100_tokenizer()
        write_install_progress(34, "converting", "Converting SMaLL-100 to INT8.", indeterminate=True)
        TransformersConverter(SMALL100_MODEL, revision=SMALL100_REVISION, trust_remote_code=False).convert(
            output_dir=str(output), quantization="int8", force=True
        )
    write_install_progress(78, "model-ready", "The SMaLL-100 INT8 model is ready.")
    install_tigrinya()
    write_install_progress(100, "complete", "Recommended language bundle is ready, including Tigrinya.")


def install_compatibility() -> None:
    from transformers import M2M100ForConditionalGeneration

    write_install_progress(15, "downloading", "Downloading the pinned SMaLL-100 Compatibility model.", indeterminate=True)
    _check_small100_tokenizer()
    M2M100ForConditionalGeneration.from_pretrained(
        SMALL100_MODEL,
        revision=SMALL100_REVISION,
        use_safetensors=True,
    )
    write_install_progress(100, "complete", "Compatibility translation package is ready.")


def install_translation(kind: str) -> None:
    write_install_progress(2, "starting", "Starting the selected language resource installer.", indeterminate=True)
    os.environ.setdefault("ARGOS_STANZA_AVAILABLE", "0")
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    os.environ.setdefault("ARGOS_PACKAGES_DIR", str(model_data_dir() / "argos-packages"))
    data_dir = os.environ.get("CHURCH_CAP_DATA_DIR", "").strip()
    if data_dir:
        os.environ.setdefault("HF_HOME", str(Path(data_dir) / "cache" / "huggingface"))
    if kind == "argos":
        install_argos()
    elif kind == "argos_all":
        install_argos(all_languages=True)
    elif kind == "ct2small100":
        validate_packaged_installer_runtime()
        install_recommended()
    elif kind == "small100":
        validate_packaged_installer_runtime()
        install_compatibility()
    else:
        raise ValueError("Unknown translation install kind.")


def install_tts(package_ids: str) -> None:
    write_install_progress(2, "runtime-check", "Checking the packaged spoken-language installer.", indeterminate=True)
    validate_packaged_installer_runtime()
    previous = sys.argv
    try:
        sys.argv = ["install-tts-voices", "--packages", package_ids]
        runpy.run_path(str(resource_root() / "scripts" / "install-tts-voices.py"), run_name="__main__")
    finally:
        sys.argv = previous
