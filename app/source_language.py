"""Speech languages supported by the operator's source-language selector.

Keep this independent of the speech runtime so opening the operator page does
not load Whisper or download models. Codes are shared by Whisper and translation.
"""

SOURCE_LANGUAGES = {
    "en": "English", "sv": "Swedish", "da": "Danish", "no": "Norwegian",
    "fi": "Finnish", "de": "German", "nl": "Dutch", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian", "pl": "Polish",
    "uk": "Ukrainian", "ru": "Russian", "ar": "Arabic", "hi": "Hindi",
    "ja": "Japanese", "ko": "Korean", "tr": "Turkish", "el": "Greek",
}


def validate_source_language(value: object) -> str:
    if not isinstance(value, str) or value not in SOURCE_LANGUAGES:
        raise ValueError("Choose a supported source language.")
    return value


def source_model(model: str, language: str) -> str:
    """Preserve the chosen model size, using multilingual weights when needed."""
    return model.removesuffix(".en") if language != "en" else model
