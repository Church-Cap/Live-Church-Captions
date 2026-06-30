import unittest
from pathlib import Path

from app.i18n import LocalTranslator, TranslationResult


class StubTranslator(LocalTranslator):
    def __init__(self):
        super().__init__("en")
        self.calls = []
        self.argos_result = TranslationResult("argos text", True)
        self.small100_result = TranslationResult("core text", True)

    def _translate_with_argos(self, text: str, target_language: str) -> TranslationResult:
        self.calls.append(("argos", target_language, text))
        return self.argos_result

    def _translate_with_small100(self, text: str, target_language: str) -> TranslationResult:
        self.calls.append(("small100", target_language, text))
        return self.small100_result


class ResourceStubTranslator(LocalTranslator):
    def supported_languages_for_provider(self, provider: str) -> list[str]:
        if provider == "argos":
            return ["en", "es", "fr", "no"]
        if provider == "disabled":
            return ["en"]
        return super().supported_languages_for_provider(provider)

    def translation_resources(self) -> dict:
        return {
            "argos": {
                "installed_languages": ["nb"],
                "installed_pairs": ["en->nb"],
                "status": {"ready": True},
            },
            "small100": {
                "languages": [],
                "status": {"ready": False},
            },
        }


class TranslationProviderRoutingTests(unittest.TestCase):
    def test_both_mode_prefers_argos_when_available(self):
        translator = StubTranslator()
        result = translator.translate("Good morning", "fr", enabled=True, provider="both")
        self.assertTrue(result.applied)
        self.assertEqual(result.text, "argos text")
        self.assertEqual([call[0] for call in translator.calls], ["argos"])

    def test_both_mode_falls_back_to_small100(self):
        translator = StubTranslator()
        translator.argos_result = TranslationResult("Good morning", False, "No Argos model.")
        result = translator.translate("Good morning", "be", enabled=True, provider="both")
        self.assertTrue(result.applied)
        self.assertEqual(result.text, "core text")
        self.assertEqual([call[0] for call in translator.calls], ["argos", "small100"])

    def test_argos_aliases_norwegian_bokmal_to_norwegian(self):
        translator = ResourceStubTranslator()

        self.assertIn("no", translator.supported_languages_for_provider("argos"))

    def test_restricted_policy_filters_audience_available_languages(self):
        source = Path("app/broadcast.py").read_text(encoding="utf-8")

        self.assertIn("self.source_language = SOURCE_LANGUAGE", source)
        self.assertIn("LocalTranslator(self.source_language)", source)
        self.assertIn('self.translation_language_policy == "restricted"', source)
        self.assertIn("self.translation_allowed_languages | {self.source_language}", source)
        self.assertIn("& provider_languages", source)
        self.assertIn('"available_languages": available_languages', source)


if __name__ == "__main__":
    unittest.main()
