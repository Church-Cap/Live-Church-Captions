from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import metadata
import importlib.util
import os
from pathlib import Path
import sys
from typing import Any

# Church Cap sends short, bounded cues to Argos and does not need its Stanza
# sentence-boundary pipeline. Keep that pipeline disabled before Argos is lazily
# imported: this avoids service-time model loading/network attempts and prevents
# packaged Stanza model files from entering the translation path.
os.environ["ARGOS_STANZA_AVAILABLE"] = "0"

SOURCE_LANGUAGE = "en"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CT2_SMALL100_PROVIDER = "ct2small100"
CT2_SMALL100_MODEL_NAME = "alirezamsh/small100"
CT2_SMALL100_MODEL_DIR = Path(os.environ.get("CHURCHCAP_CT2_SMALL100_DIR") or PROJECT_ROOT / "data" / "models" / "small100-ct2-int8")
CHINESE_SIMPLIFIED = "zh-hans"
CHINESE_TRADITIONAL = "zh-hant"
CHINESE_VARIANTS = {
    CHINESE_SIMPLIFIED: {"model_language": "zh", "opencc_profile": "t2s", "label": "Simplified Chinese"},
    CHINESE_TRADITIONAL: {"model_language": "zh", "opencc_profile": "s2hk", "label": "Traditional Chinese (Hong Kong)"},
}
LANGUAGE_ALIASES = {
    "zh": CHINESE_SIMPLIFIED,
    "zh-cn": CHINESE_SIMPLIFIED,
    "zh-sg": CHINESE_SIMPLIFIED,
    "zh-hans": CHINESE_SIMPLIFIED,
    "zh-hk": CHINESE_TRADITIONAL,
    "zh-mo": CHINESE_TRADITIONAL,
    "zh-tw": CHINESE_TRADITIONAL,
    "zh-hant": CHINESE_TRADITIONAL,
}

BASE_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native": "English", "flag": "🇬🇧", "dir": "ltr"},
    {"code": "es", "name": "Spanish", "native": "Español", "flag": "🇪🇸", "dir": "ltr"},
    {"code": "fr", "name": "French", "native": "Français", "flag": "🇫🇷", "dir": "ltr"},
    {"code": "pt", "name": "Portuguese", "native": "Português", "flag": "🇵🇹", "dir": "ltr"},
    {"code": "pl", "name": "Polish", "native": "Polski", "flag": "🇵🇱", "dir": "ltr"},
    {"code": "uk", "name": "Ukrainian", "native": "Українська", "flag": "🇺🇦", "dir": "ltr"},
    {"code": "ar", "name": "Arabic", "native": "العربية", "flag": "🇸🇦", "dir": "rtl"},
    {"code": "fa", "name": "Farsi", "native": "فارسی", "flag": "🇮🇷", "dir": "rtl"},
    {"code": CHINESE_SIMPLIFIED, "name": "Chinese (Simplified)", "native": "简体中文", "flag": "🇨🇳", "dir": "ltr"},
    {"code": CHINESE_TRADITIONAL, "name": "Chinese (Traditional, Hong Kong)", "native": "繁體中文（香港）", "flag": "🇭🇰", "dir": "ltr"},
]


SMALL100_LANGUAGE_NAMES: dict[str, str] = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "ast": "Asturian", "az": "Azerbaijani",
    "ba": "Bashkir", "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali", "br": "Breton",
    "bs": "Bosnian", "ca": "Catalan", "ceb": "Cebuano", "cs": "Czech", "cy": "Welsh",
    "da": "Danish", "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "et": "Estonian", "fa": "Persian", "ff": "Fulah", "fi": "Finnish", "fr": "French",
    "fy": "Western Frisian", "ga": "Irish", "gd": "Scottish Gaelic", "gl": "Galician", "gu": "Gujarati",
    "ha": "Hausa", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "ht": "Haitian Creole",
    "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian", "ig": "Igbo", "ilo": "Iloko",
    "is": "Icelandic", "it": "Italian", "ja": "Japanese", "jv": "Javanese", "ka": "Georgian",
    "kk": "Kazakh", "km": "Khmer", "kn": "Kannada", "ko": "Korean", "lb": "Luxembourgish",
    "lg": "Ganda", "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mg": "Malagasy", "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian", "mr": "Marathi",
    "ms": "Malay", "my": "Burmese", "ne": "Nepali", "nl": "Dutch", "no": "Norwegian",
    "ns": "Northern Sotho", "oc": "Occitan", "or": "Oriya", "pa": "Punjabi", "pl": "Polish",
    "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sd": "Sindhi",
    "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian", "so": "Somali", "sq": "Albanian",
    "sr": "Serbian", "ss": "Swati", "su": "Sundanese", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "th": "Thai", "tl": "Tagalog", "tn": "Tswana", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese", "wo": "Wolof",
    "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese", "zu": "Zulu",
}

NATIVE_LANGUAGE_NAMES: dict[str, str] = {
    "de": "Deutsch", "el": "Ελληνικά", "he": "עברית", "hi": "हिन्दी", "id": "Bahasa Indonesia",
    "it": "Italiano", "ja": "日本語", "ko": "한국어", "nl": "Nederlands", "ru": "Русский",
    "sv": "Svenska", "sw": "Kiswahili", "ta": "தமிழ்", "th": "ไทย", "tr": "Türkçe",
    "ur": "اردو", "vi": "Tiếng Việt", "zh": "中文",
}

LANGUAGE_FLAGS: dict[str, str] = {
    "af": "🇿🇦", "am": "🇪🇹", "ar": "🇸🇦", "ast": "🇪🇸", "az": "🇦🇿", "ba": "🇷🇺", "be": "🇧🇾",
    "bg": "🇧🇬", "bn": "🇧🇩", "br": "🇫🇷", "bs": "🇧🇦", "ca": "🇪🇸", "ceb": "🇵🇭", "cs": "🇨🇿",
    "cy": "🇬🇧", "da": "🇩🇰", "de": "🇩🇪", "el": "🇬🇷", "en": "🇬🇧", "es": "🇪🇸", "et": "🇪🇪",
    "fa": "🇮🇷", "ff": "🇸🇳", "fi": "🇫🇮", "fr": "🇫🇷", "fy": "🇳🇱", "ga": "🇮🇪", "gd": "🇬🇧",
    "gl": "🇪🇸", "gu": "🇮🇳", "ha": "🇳🇬", "he": "🇮🇱", "hi": "🇮🇳", "hr": "🇭🇷", "ht": "🇭🇹",
    "hu": "🇭🇺", "hy": "🇦🇲", "id": "🇮🇩", "ig": "🇳🇬", "ilo": "🇵🇭", "is": "🇮🇸", "it": "🇮🇹",
    "ja": "🇯🇵", "jv": "🇮🇩", "ka": "🇬🇪", "kk": "🇰🇿", "km": "🇰🇭", "kn": "🇮🇳", "ko": "🇰🇷",
    "lb": "🇱🇺", "lg": "🇺🇬", "ln": "🇨🇩", "lo": "🇱🇦", "lt": "🇱🇹", "lv": "🇱🇻", "mg": "🇲🇬",
    "mk": "🇲🇰", "ml": "🇮🇳", "mn": "🇲🇳", "mr": "🇮🇳", "ms": "🇲🇾", "my": "🇲🇲", "ne": "🇳🇵",
    "nl": "🇳🇱", "no": "🇳🇴", "ns": "🇿🇦", "oc": "🇫🇷", "or": "🇮🇳", "pa": "🇮🇳", "pl": "🇵🇱",
    "ps": "🇦🇫", "pt": "🇵🇹", "ro": "🇷🇴", "ru": "🇷🇺", "sd": "🇵🇰", "si": "🇱🇰", "sk": "🇸🇰",
    "sl": "🇸🇮", "so": "🇸🇴", "sq": "🇦🇱", "sr": "🇷🇸", "ss": "🇸🇿", "su": "🇮🇩", "sv": "🇸🇪",
    "sw": "🇰🇪", "ta": "🇮🇳", "th": "🇹🇭", "tl": "🇵🇭", "tn": "🇧🇼", "tr": "🇹🇷", "uk": "🇺🇦",
    "ur": "🇵🇰", "uz": "🇺🇿", "vi": "🇻🇳", "wo": "🇸🇳", "xh": "🇿🇦", "yi": "🇮🇱", "yo": "🇳🇬",
    "zh": "🇨🇳", "zu": "🇿🇦",
}


def _language_dir(code: str) -> str:
    return "rtl" if code in {"ar", "fa", "he", "ps", "ur", "yi"} else "ltr"


def _merge_supported_languages() -> list[dict[str, str]]:
    by_code = {item["code"]: dict(item) for item in BASE_LANGUAGES}
    for code, name in SMALL100_LANGUAGE_NAMES.items():
        if code == "zh":
            continue
        if code not in by_code:
            by_code[code] = {
                "code": code,
                "name": name,
                "native": NATIVE_LANGUAGE_NAMES.get(code, name),
                "flag": LANGUAGE_FLAGS.get(code, "🌐"),
                "dir": _language_dir(code),
            }
    return sorted(by_code.values(), key=lambda item: (item["code"] != SOURCE_LANGUAGE, item["name"]))


SUPPORTED_LANGUAGES: list[dict[str, str]] = _merge_supported_languages()
LANGUAGE_BY_CODE = {item["code"]: item for item in SUPPORTED_LANGUAGES}
MAX_TRANSLATION_LANGUAGES = len(SUPPORTED_LANGUAGES)
ARGOS_ENGLISH_TARGET_LANGUAGE_CODES = {
    "ar", "az", "bg", "bn", "ca", "cs", "da", "de", "el", "es", "et", "fa", "fi", "fr", "ga", "gl",
    "he", "hi", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms", "nl", "pl", "pt", "ro", "ru", "sk",
    "sl", "sq", "sv", "th", "tl", "tr", "uk", "ur", "vi", "zh",
    # Church Cap aliases for Argos package codes.
    "no",
}
ARGOS_LANGUAGE_ALIASES = {
    "no": "nb",
    CHINESE_SIMPLIFIED: "zh",
    CHINESE_TRADITIONAL: "zt",
}
ARGOS_TO_CHURCH_LANGUAGE_ALIASES = {
    "nb": "no",
}

def normalise_language(code: str | None) -> str:
    if not code:
        return SOURCE_LANGUAGE
    code = str(code).lower().replace("_", "-").strip()
    if code in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[code]
    if code in LANGUAGE_BY_CODE:
        return code
    base = code.split("-", 1)[0]
    if base in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[base]
    return base if base in LANGUAGE_BY_CODE else SOURCE_LANGUAGE


def translation_model_language(code: str) -> str:
    normalised = normalise_language(code)
    return str(CHINESE_VARIANTS.get(normalised, {}).get("model_language") or normalised)


@dataclass(frozen=True)
class TranslationResult:
    text: str
    applied: bool
    warning: str | None = None
    requested_provider: str | None = None
    actual_provider: str | None = None
    fallback_chain: tuple[str, ...] = ()
    retry_count: int = 0
    outcome: str = "source_shown"
    target_variant: str | None = None
    conversion_profile: str | None = None
    conversion_profile_version: str | None = None


class LocalTranslator:
    """Optional local caption translation bridge.

    Caption translation is available when explicitly enabled by the operator. The live-caption core stays
    local and lightweight. If a church enables translation, the operator should
    also set a small maximum number of active translated languages because every
    additional language increases CPU/RAM use.

    Providers:
    - demo: prefixes text for testing routing; not a real translation.
    - argos: uses optional Argos Translate local models installed on the Mac.
    - disabled: no translation, source captions only.
    """

    def __init__(self, source_language: str = SOURCE_LANGUAGE):
        self.source_language = normalise_language(source_language)
        self._cache: dict[tuple[str, str, str], TranslationResult] = {}
        self._small100_model: Any | None = None
        self._small100_tokenizer: Any | None = None
        self._ct2small100_translator: Any | None = None
        self._ct2small100_tokenizer: Any | None = None
        self._opencc_converters: dict[str, Any] = {}

    @staticmethod
    def chinese_script_conversion_status() -> dict[str, Any]:
        ready = importlib.util.find_spec("opencc") is not None
        version = None
        if ready:
            try:
                version = metadata.version("OpenCC")
            except metadata.PackageNotFoundError:
                version = "unknown"
        return {
            "ready": ready,
            "version": version,
            "license": "Apache-2.0",
            "profiles": {
                CHINESE_SIMPLIFIED: "t2s",
                CHINESE_TRADITIONAL: "s2hk",
            },
            "message": (
                "OpenCC is ready for consistent Simplified and Hong Kong Traditional Chinese output."
                if ready
                else "Install the OpenCC translation dependency to enable separate Simplified and Traditional Chinese choices."
            ),
        }

    def _convert_chinese_script(self, text: str, target_language: str) -> tuple[str, str | None, str | None]:
        variant = CHINESE_VARIANTS.get(target_language)
        if variant is None:
            return text, None, None
        profile = str(variant["opencc_profile"])
        try:
            from opencc import OpenCC  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"OpenCC Chinese script conversion is not installed: {exc}") from exc
        converter = self._opencc_converters.get(profile)
        if converter is None:
            converter = OpenCC(profile)
            self._opencc_converters[profile] = converter
        try:
            version = metadata.version("OpenCC")
        except metadata.PackageNotFoundError:
            version = "unknown"
        return str(converter.convert(text)), profile, version

    def provider_status(self, provider: str) -> dict:
        provider = (provider or "disabled").lower().strip()
        if provider in {"", "disabled", "none"}:
            return {"provider": "disabled", "ready": False, "message": "Translation provider is disabled."}
        if provider == "demo":
            return {"provider": "demo", "ready": True, "message": "Demo routing provider only; not real translation."}
        if provider == "both":
            argos_status = self.provider_status("argos")
            ct2_status = self.provider_status(CT2_SMALL100_PROVIDER)
            small_status = self.provider_status("small100")
            return {
                "provider": "both",
                "ready": bool(argos_status.get("ready") or ct2_status.get("ready") or small_status.get("ready")),
                "message": f"Auto mode uses the Recommended package / CTranslate2 INT8 first, then Base / Argos, then Compatibility / PyTorch SMaLL-100 when needed. Recommended: {ct2_status.get('message', 'unknown')} Base: {argos_status.get('message', 'unknown')} Compatibility: {small_status.get('message', 'unknown')}",
                "argos": argos_status,
                "ct2small100": ct2_status,
                "small100": small_status,
            }
        if provider == "argos":
            try:
                from argostranslate import translate as argos_translate  # type: ignore
                installed = argos_translate.get_installed_languages()
                pairs: list[str] = []
                for source in installed:
                    for target in installed:
                        if source.code != target.code:
                            translation = source.get_translation(target)
                            if translation is not None:
                                pairs.append(f"{source.code}->{target.code}")
                return {
                    "provider": "argos",
                    "ready": bool(pairs),
                    "message": f"Argos Translate installed. Installed pairs: {', '.join(sorted(set(pairs))) or 'none'}. Install models with scripts/install-translation-models-argos.sh.",
                }
            except Exception as exc:
                return {"provider": "argos", "ready": False, "message": f"Argos Translate is not installed or not ready: {exc}"}
        if provider == "small100":
            missing = [
                name
                for name in ("torch", "transformers", "huggingface_hub")
                if importlib.util.find_spec(name) is None
            ]
            if not missing:
                return {
                    "provider": "small100",
                    "ready": True,
                    "message": "Core SMaLL-100 support is installed. The model loads on first use and may use noticeably more RAM/CPU.",
                }
            return {
                "provider": "small100",
                "ready": False,
                "message": f"Core SMaLL-100 is not installed yet. Missing: {', '.join(missing)}.",
            }
        if provider == CT2_SMALL100_PROVIDER:
            missing = [
                name
                for name in ("ctranslate2", "huggingface_hub", "sentencepiece")
                if importlib.util.find_spec(name) is None
            ]
            if missing:
                return {
                    "provider": CT2_SMALL100_PROVIDER,
                    "ready": False,
                    "message": f"Recommended package / CTranslate2 INT8 is not installed yet. Missing: {', '.join(missing)}.",
                    "model_dir": str(CT2_SMALL100_MODEL_DIR),
                }
            try:
                import ctranslate2  # type: ignore
                contains = getattr(ctranslate2, "contains_model", None)
                model_ready = bool(contains(str(CT2_SMALL100_MODEL_DIR))) if contains else (CT2_SMALL100_MODEL_DIR / "model.bin").exists()
            except Exception:
                model_ready = (CT2_SMALL100_MODEL_DIR / "model.bin").exists()
            if model_ready:
                return {
                    "provider": CT2_SMALL100_PROVIDER,
                    "ready": True,
                    "message": "Recommended package / CTranslate2 INT8 model is installed. It is the preferred efficient neural translation runtime.",
                    "model_dir": str(CT2_SMALL100_MODEL_DIR),
                }
            return {
                "provider": CT2_SMALL100_PROVIDER,
                "ready": False,
                "message": f"Recommended package / CTranslate2 INT8 model is not converted yet. Install it from the Languages page or run scripts/install-small100-ct2-int8.*.",
                "model_dir": str(CT2_SMALL100_MODEL_DIR),
            }
        return {"provider": provider, "ready": False, "message": f"Unknown translation provider: {provider}"}

    def translation_resources(self) -> dict[str, Any]:
        argos_installed: list[str] = []
        argos_pairs: list[str] = []
        chinese_conversion = self.chinese_script_conversion_status()
        try:
            from argostranslate import translate as argos_translate  # type: ignore
            installed = argos_translate.get_installed_languages()
            for source in installed:
                for target in installed:
                    if source.code == target.code:
                        continue
                    translation = source.get_translation(target)
                    if translation is not None:
                        argos_pairs.append(f"{source.code}->{target.code}")
                        if source.code == self.source_language:
                            if target.code in {"zh", "zt"}:
                                if chinese_conversion["ready"]:
                                    argos_installed.extend((CHINESE_SIMPLIFIED, CHINESE_TRADITIONAL))
                            else:
                                argos_installed.append(ARGOS_TO_CHURCH_LANGUAGE_ALIASES.get(target.code, target.code))
        except Exception:
            pass
        return {
            "argos": {
                "installed_languages": sorted(set(argos_installed)),
                "installed_pairs": sorted(set(argos_pairs)),
                "status": self.provider_status("argos"),
            },
            "ct2small100": {
                "languages": sorted(
                    (set(SMALL100_LANGUAGE_NAMES) - {"zh"})
                    | (set(CHINESE_VARIANTS) if chinese_conversion["ready"] else set())
                ),
                "status": self.provider_status(CT2_SMALL100_PROVIDER),
                "license": "MIT model weights; converted CTranslate2 files inherit the source model distribution obligations",
            },
            "small100": {
                "languages": sorted(
                    (set(SMALL100_LANGUAGE_NAMES) - {"zh"})
                    | (set(CHINESE_VARIANTS) if chinese_conversion["ready"] else set())
                ),
                "status": self.provider_status("small100"),
                "license": "MIT",
            },
            "chinese_script_conversion": chinese_conversion,
        }

    def supported_languages_for_provider(self, provider: str) -> list[str]:
        provider = (provider or "disabled").lower().strip()
        resources = self.translation_resources()
        argos_languages = {
            ARGOS_TO_CHURCH_LANGUAGE_ALIASES.get(language, language)
            for language in resources.get("argos", {}).get("installed_languages", [])
        }
        ct2_ready = bool(resources.get("ct2small100", {}).get("status", {}).get("ready"))
        ct2_languages = set(resources.get("ct2small100", {}).get("languages", [])) if ct2_ready else set()
        small100_ready = bool(resources.get("small100", {}).get("status", {}).get("ready"))
        small100_languages = set(resources.get("small100", {}).get("languages", [])) if small100_ready else set()
        if provider == "argos":
            languages = argos_languages
        elif provider == CT2_SMALL100_PROVIDER:
            languages = ct2_languages
        elif provider == "small100":
            languages = small100_languages
        elif provider == "both":
            languages = argos_languages | ct2_languages | small100_languages
        elif provider == "demo":
            languages = set(LANGUAGE_BY_CODE)
            if not bool(resources.get("chinese_script_conversion", {}).get("ready")):
                languages -= set(CHINESE_VARIANTS)
        else:
            languages = set()
        languages.add(self.source_language)
        return sorted(language for language in languages if language in LANGUAGE_BY_CODE)

    def unload_models(self) -> None:
        self._small100_model = None
        self._small100_tokenizer = None
        self._ct2small100_translator = None
        self._ct2small100_tokenizer = None
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def cached_result(self, text: str, target_language: str, *, provider: str) -> TranslationResult | None:
        target_language = normalise_language(target_language)
        provider = (provider or "disabled").lower().strip()
        return self._cache.get((provider, target_language, text))

    def translate(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        target_language = normalise_language(target_language)
        provider = (provider or "disabled").lower().strip()
        if target_language == self.source_language:
            return TranslationResult(
                text=text,
                applied=False,
                requested_provider=provider,
                outcome="source_language",
                target_variant=target_language,
            )
        if not enabled:
            return TranslationResult(
                text=text,
                applied=False,
                warning="Translated captions are not currently enabled. Showing the source language.",
                requested_provider=provider,
                outcome="disabled",
                target_variant=target_language,
            )
        if provider in {"", "disabled", "none"}:
            return TranslationResult(
                text=text,
                applied=False,
                warning="No local translation provider is configured.",
                requested_provider=provider or "disabled",
                outcome="disabled",
                target_variant=target_language,
            )

        cache_key = (provider, target_language, text)
        if cache_key in self._cache:
            return self._cache[cache_key]

        attempts: list[str] = []
        actual_provider: str | None = None
        if provider == "demo":
            attempts.append("demo")
            result = TranslationResult(
                text=f"[{target_language.upper()} demo] {text}",
                applied=True,
                warning="Demo provider only; not a real translation.",
            )
            actual_provider = "demo"
        elif provider == "argos":
            attempts.append("argos")
            result = self._translate_with_argos(text, target_language)
            actual_provider = "argos"
        elif provider == CT2_SMALL100_PROVIDER:
            attempts.append(CT2_SMALL100_PROVIDER)
            result = self._translate_with_ct2small100(text, target_language)
            actual_provider = CT2_SMALL100_PROVIDER
        elif provider == "small100":
            attempts.append("small100")
            result = self._translate_with_small100(text, target_language)
            actual_provider = "small100"
        elif provider == "both":
            warnings = []
            attempts.append(CT2_SMALL100_PROVIDER)
            result = self._translate_with_ct2small100(text, target_language)
            if result.applied:
                actual_provider = CT2_SMALL100_PROVIDER
            if not result.applied:
                if result.warning:
                    warnings.append(result.warning)
                attempts.append("argos")
                result = self._translate_with_argos(text, target_language)
                if result.applied:
                    actual_provider = "argos"
            if not result.applied:
                if result.warning:
                    warnings.append(result.warning)
                attempts.append("small100")
                result = self._translate_with_small100(text, target_language)
                if result.applied:
                    actual_provider = "small100"
            if not result.applied and warnings and result.warning:
                warnings.append(result.warning)
                result = TranslationResult(text=text, applied=False, warning=" ".join(dict.fromkeys(warnings)))
                actual_provider = attempts[-1]
        else:
            result = TranslationResult(text=text, applied=False, warning=f"Unknown translation provider: {provider}")

        if result.applied and target_language in CHINESE_VARIANTS:
            try:
                converted, conversion_profile, conversion_version = self._convert_chinese_script(
                    result.text,
                    target_language,
                )
            except Exception as exc:
                result = TranslationResult(
                    text=text,
                    applied=False,
                    warning=str(exc),
                    target_variant=target_language,
                )
            else:
                result = replace(
                    result,
                    text=converted,
                    target_variant=target_language,
                    conversion_profile=conversion_profile,
                    conversion_profile_version=conversion_version,
                )

        warning = str(result.warning or "").lower()
        if result.applied:
            outcome = "applied"
        elif "failed" in warning or "error" in warning:
            outcome = "failed"
        elif any(marker in warning for marker in ("not installed", "no installed", "does not support", "unavailable", "unknown translation provider")):
            outcome = "unavailable"
        elif result.text == text and not warning:
            outcome = "unchanged"
        else:
            outcome = "source_shown"
        result = replace(
            result,
            requested_provider=provider,
            actual_provider=actual_provider,
            fallback_chain=tuple(attempts),
            retry_count=max(0, len(attempts) - 1),
            outcome=outcome,
            target_variant=target_language,
        )

        if len(self._cache) > 2000:
            self._cache.clear()
        self._cache[cache_key] = result
        return result

    async def translate_async(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        import asyncio
        return await asyncio.to_thread(self.translate, text, target_language, enabled=enabled, provider=provider)

    def _translate_with_argos(self, text: str, target_language: str) -> TranslationResult:
        try:
            from argostranslate import translate as argos_translate  # type: ignore
        except Exception as exc:
            return TranslationResult(text=text, applied=False, warning=f"Argos Translate is not installed: {exc}")

        try:
            installed = argos_translate.get_installed_languages()
            source = next((lang for lang in installed if getattr(lang, "code", None) == self.source_language), None)
            if target_language == CHINESE_TRADITIONAL:
                target_codes = ("zt", "zh")
            elif target_language == CHINESE_SIMPLIFIED:
                target_codes = ("zh", "zt")
            else:
                target_codes = (ARGOS_LANGUAGE_ALIASES.get(target_language, target_language),)
            target = next(
                (lang for code in target_codes for lang in installed if getattr(lang, "code", None) == code),
                None,
            )
            if source is None or target is None:
                return TranslationResult(
                    text=text,
                    applied=False,
                    warning=f"No installed Argos model for {self.source_language}->{target_language}.",
                )
            translation = source.get_translation(target)
            if translation is None:
                return TranslationResult(
                    text=text,
                    applied=False,
                    warning=f"No installed Argos model for {self.source_language}->{target_language}.",
                )
            translated = translation.translate(text)
            if translated and translated.strip() and translated != text:
                return TranslationResult(text=translated, applied=True)

            return TranslationResult(
                text=text,
                applied=False,
                warning=f"No installed Argos model for {self.source_language}->{target_language}.",
            )
        except Exception as exc:
            return TranslationResult(text=text, applied=False, warning=f"Argos Translate failed: {exc}")

    def _load_small100_tokenizer(self) -> Any:
        if self._small100_tokenizer is not None:
            return self._small100_tokenizer
        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"Core SMaLL-100 tokenizer dependency is not installed: {exc}") from exc
        tokenizer_file = Path(hf_hub_download(CT2_SMALL100_MODEL_NAME, "tokenization_small100.py"))
        module_name = "_church_cap_small100_tokenizer"
        module = sys.modules.get(module_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(module_name, tokenizer_file)
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load SMaLL-100 tokenizer module.")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        tokenizer_cls = getattr(module, "SMALL100Tokenizer")
        self._small100_tokenizer = tokenizer_cls.from_pretrained(CT2_SMALL100_MODEL_NAME)
        return self._small100_tokenizer

    def _load_small100(self) -> tuple[Any, Any]:
        if self._small100_model is not None and self._small100_tokenizer is not None:
            return self._small100_model, self._small100_tokenizer
        try:
            import torch  # type: ignore
            from transformers import M2M100ForConditionalGeneration  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"Core SMaLL-100 dependencies are not installed: {exc}") from exc
        self._small100_tokenizer = self._load_small100_tokenizer()
        self._small100_model = M2M100ForConditionalGeneration.from_pretrained(CT2_SMALL100_MODEL_NAME)
        self._small100_model.eval()
        if torch.cuda.is_available():
            self._small100_model.to("cuda")
        return self._small100_model, self._small100_tokenizer

    def _load_ct2small100(self) -> tuple[Any, Any]:
        if self._ct2small100_translator is not None and self._ct2small100_tokenizer is not None:
            return self._ct2small100_translator, self._ct2small100_tokenizer
        try:
            import ctranslate2  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"Recommended package / CTranslate2 is not installed: {exc}") from exc
        status = self.provider_status(CT2_SMALL100_PROVIDER)
        if not status.get("ready"):
            raise RuntimeError(status.get("message") or "Recommended package / CTranslate2 INT8 model is not ready.")
        cuda_devices = 0
        try:
            cuda_devices = int(ctranslate2.get_cuda_device_count())
        except Exception:
            cuda_devices = 0
        requested_device = os.environ.get("CHURCHCAP_CT2_SMALL100_DEVICE", "auto").lower().strip()
        if requested_device not in {"auto", "cpu", "cuda"}:
            requested_device = "auto"
        device = "cuda" if requested_device == "cuda" or (requested_device == "auto" and cuda_devices > 0) else "cpu"
        compute_type = os.environ.get("CHURCHCAP_CT2_SMALL100_COMPUTE_TYPE")
        if not compute_type:
            compute_type = "int8_float16" if device == "cuda" else "int8"
        self._ct2small100_tokenizer = self._load_small100_tokenizer()
        self._ct2small100_translator = ctranslate2.Translator(
            str(CT2_SMALL100_MODEL_DIR),
            device=device,
            compute_type=compute_type,
            inter_threads=1,
        )
        return self._ct2small100_translator, self._ct2small100_tokenizer

    @staticmethod
    def _tokenizer_language_token(tokenizer: Any, language: str) -> str:
        get_lang_id = getattr(tokenizer, "get_lang_id", None)
        if callable(get_lang_id):
            return tokenizer.convert_ids_to_tokens(int(get_lang_id(language)))
        mapping = getattr(tokenizer, "lang_code_to_token", None) or {}
        if language in mapping:
            return mapping[language]
        return f"__{language}__"

    @staticmethod
    def _decode_tokens(tokenizer: Any, tokens: list[str]) -> str:
        try:
            ids = tokenizer.convert_tokens_to_ids(tokens)
            if isinstance(ids, list):
                return tokenizer.decode(ids, skip_special_tokens=True).strip()
        except Exception:
            pass
        try:
            return tokenizer.convert_tokens_to_string(tokens).strip()
        except Exception:
            return " ".join(tokens).replace("▁", " ").strip()

    def _translate_with_ct2small100(self, text: str, target_language: str) -> TranslationResult:
        target_variant = normalise_language(target_language)
        target_language = translation_model_language(target_variant)
        if target_language not in SMALL100_LANGUAGE_NAMES:
            return TranslationResult(text=text, applied=False, warning=f"Recommended package translation does not support {target_variant}.")
        try:
            translator, tokenizer = self._load_ct2small100()
            try:
                tokenizer.src_lang = self.source_language
            except Exception:
                pass
            try:
                tokenizer.tgt_lang = target_language
            except Exception:
                pass
            inputs = tokenizer(text, truncation=True, max_length=256)
            input_ids = inputs.get("input_ids") if isinstance(inputs, dict) else getattr(inputs, "input_ids", None)
            if input_ids is None:
                return TranslationResult(text=text, applied=False, warning="Recommended package tokenizer did not return input IDs.")
            if input_ids and isinstance(input_ids[0], list):
                input_ids = input_ids[0]
            source_tokens = tokenizer.convert_ids_to_tokens(input_ids)

            def run_ct2_translation(*, target_prefix: list[list[str]] | None = None) -> str:
                kwargs: dict[str, Any] = {
                    "beam_size": 2,
                    "max_input_length": 256,
                    "max_decoding_length": 256,
                }
                if target_prefix is not None:
                    kwargs["target_prefix"] = target_prefix
                result = translator.translate_batch([source_tokens], **kwargs)[0]
                tokens = list(result.hypotheses[0]) if result.hypotheses else []
                target_token = self._tokenizer_language_token(tokenizer, target_language)
                if tokens and tokens[0] == target_token:
                    tokens = tokens[1:]
                return self._decode_tokens(tokenizer, tokens)

            translated = run_ct2_translation()
            if translated and translated != text:
                return TranslationResult(text=translated, applied=True)

            target_token = self._tokenizer_language_token(tokenizer, target_language)
            prefixed = run_ct2_translation(target_prefix=[[target_token]])
            if prefixed and prefixed != text:
                return TranslationResult(text=prefixed, applied=True)
            return TranslationResult(text=text, applied=False, warning="Recommended package translation returned the source caption.")
        except Exception as exc:
            return TranslationResult(text=text, applied=False, warning=f"Recommended package / CTranslate2 INT8 translation failed: {exc}")

    def _translate_with_small100(self, text: str, target_language: str) -> TranslationResult:
        target_variant = normalise_language(target_language)
        target_language = translation_model_language(target_variant)
        if target_language not in SMALL100_LANGUAGE_NAMES:
            return TranslationResult(text=text, applied=False, warning=f"Core translation does not support {target_variant}.")
        try:
            import torch  # type: ignore
            model, tokenizer = self._load_small100()
            tokenizer.tgt_lang = target_language
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
            try:
                device = next(model.parameters()).device
                inputs = {key: value.to(device) for key, value in inputs.items()}
            except Exception:
                pass
            with torch.no_grad():
                generated = model.generate(**inputs, max_length=256, num_beams=5)
            translated = tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
            if translated and translated != text:
                return TranslationResult(text=translated, applied=True)
            return TranslationResult(text=text, applied=False, warning="Core translation returned the source caption.")
        except Exception as exc:
            return TranslationResult(text=text, applied=False, warning=f"Core SMaLL-100 translation failed: {exc}")
