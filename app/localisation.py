from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

SOURCE_LANGUAGE = "en"
CATALOG_PATH = Path(__file__).resolve().parent / "locales" / "client_ui.json"


@lru_cache(maxsize=1)
def _client_ui_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _locales() -> dict[str, dict[str, str]]:
    locales = _client_ui_catalog().get("locales", {})
    return {str(code): dict(strings) for code, strings in locales.items() if isinstance(strings, dict)}


def _normalise_code(code: str | None) -> str:
    return str(code or SOURCE_LANGUAGE).lower().split("-")[0].strip()


def _required_keys() -> list[str]:
    keys = _client_ui_catalog().get("required_keys", [])
    return [str(key) for key in keys]


def client_ui_language_is_static(code: str | None) -> bool:
    return bool(code) and _normalise_code(code) in _locales()


def get_client_ui_language_strings(code: str | None) -> dict[str, str]:
    language = _normalise_code(code)
    locales = _locales()
    english = locales.get(SOURCE_LANGUAGE, {})
    selected = locales.get(language, {})
    return {key: str(selected.get(key, english.get(key, key))) for key in _required_keys()}


def get_client_ui_strings(language_codes: Iterable[str] | None = None) -> dict[str, dict[str, str]]:
    if language_codes is None:
        language_codes = sorted(_locales())
    return {str(code): get_client_ui_language_strings(str(code)) for code in language_codes}


def get_client_ui_sources(language_codes: Iterable[str] | None = None) -> dict[str, str]:
    if language_codes is None:
        language_codes = sorted(_locales())
    locales = set(_locales())
    return {str(code): "static" if str(code) in locales else "fallback" for code in language_codes}


def get_client_ui_coverage(language_codes: Iterable[str]) -> dict[str, bool]:
    locales = set(_locales())
    return {str(code): str(code) in locales for code in language_codes}


def normalise_client_ui_runtime_provider(provider: str | None) -> str:
    return "argos"


async def get_runtime_translated_client_ui_strings(
    code: str,
    *,
    translator,
    provider: str | None,
    cache: dict[tuple[str, str], dict[str, str]] | None = None,
) -> tuple[dict[str, str], str]:
    language = _normalise_code(code)
    provider_key = normalise_client_ui_runtime_provider(provider)
    cache_key = (provider_key, language)
    if cache is not None and cache_key in cache:
        return dict(cache[cache_key]), f"runtime-{provider_key}"

    english = get_client_ui_language_strings(SOURCE_LANGUAGE)
    translated: dict[str, str] = {}
    applied = 0
    for key, text in english.items():
        result = await translator.translate_async(text, language, enabled=True, provider=provider_key)
        value = result.text.strip() if result.applied and result.text and result.text.strip() else text
        translated[key] = value
        if value != text:
            applied += 1

    if applied:
        if cache is not None:
            if len(cache) > 200:
                cache.clear()
            cache[cache_key] = dict(translated)
        return translated, f"runtime-{provider_key}"
    return english, "fallback"


def validate_client_ui_catalog() -> list[str]:
    errors: list[str] = []
    locales = _locales()
    required = set(_required_keys())
    english = locales.get(SOURCE_LANGUAGE)
    if not english:
        errors.append("Missing English source locale.")
    elif set(english) != required:
        missing = sorted(required - set(english))
        extra = sorted(set(english) - required)
        if missing:
            errors.append(f"English locale missing keys: {', '.join(missing)}")
        if extra:
            errors.append(f"English locale has unexpected keys: {', '.join(extra)}")

    for code, strings in locales.items():
        extra = sorted(set(strings) - required)
        if extra:
            errors.append(f"{code} has unexpected keys: {', '.join(extra)}")

    return errors
