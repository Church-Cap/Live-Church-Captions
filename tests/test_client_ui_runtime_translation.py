import unittest

from app.i18n import TranslationResult
from app.localisation import get_runtime_translated_client_ui_strings


class RuntimeUiTranslator:
    async def translate_async(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        return TranslationResult(text=f"{target_language}:{text}", applied=True)


class FailingRuntimeUiTranslator:
    async def translate_async(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        return TranslationResult(text=text, applied=False, warning="No Argos model.")


class ClientUiRuntimeTranslationTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_ui_language_can_use_argos_runtime_translation(self):
        strings, source = await get_runtime_translated_client_ui_strings(
            "ast",
            translator=RuntimeUiTranslator(),
            provider="small100",
            cache={},
        )

        self.assertEqual(source, "runtime-argos")
        self.assertEqual(strings["live_captions"], "ast:Live captions")
        self.assertEqual(strings["pause"], "ast:Pause")

    async def test_missing_ui_language_falls_back_to_english_when_argos_is_unavailable(self):
        strings, source = await get_runtime_translated_client_ui_strings(
            "ast",
            translator=FailingRuntimeUiTranslator(),
            provider="argos",
            cache={},
        )

        self.assertEqual(source, "fallback")
        self.assertEqual(strings["live_captions"], "Live captions")
        self.assertEqual(strings["pause"], "Pause")


if __name__ == "__main__":
    unittest.main()
