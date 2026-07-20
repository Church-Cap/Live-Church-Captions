import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.i18n import (
    CHINESE_SIMPLIFIED,
    CHINESE_TRADITIONAL,
    LANGUAGE_BY_CODE,
    LocalTranslator,
    TranslationResult,
    normalise_language,
)


class FakeCT2Result:
    hypotheses = [["Bonjour"]]


class FakeCT2Translator:
    def __init__(self):
        self.calls = []

    def translate_batch(self, source_batch, **kwargs):
        self.calls.append((source_batch, kwargs))
        return [FakeCT2Result()]


class FakeSmall100Tokenizer:
    def __init__(self):
        self.src_lang = None
        self.tgt_lang = None
        self.tgt_lang_when_tokenized = None

    def __call__(self, text, **_kwargs):
        self.tgt_lang_when_tokenized = self.tgt_lang
        return {"input_ids": [10, 11, 2]}

    def convert_ids_to_tokens(self, ids):
        return [f"tok{item}" for item in ids]

    def get_lang_id(self, language):
        return 999 if language == "fr" else 998

    def convert_tokens_to_ids(self, tokens):
        return [999 if token == "__fr__" else 100 for token in tokens]

    def convert_ids_to_tokens_single(self, idx):
        return "__fr__" if idx == 999 else "__xx__"

    def convert_tokens_to_string(self, tokens):
        return " ".join(tokens)

    def decode(self, ids, skip_special_tokens=True):
        return "Bonjour"



class StubTranslator(LocalTranslator):
    def __init__(self):
        super().__init__("en")
        self.calls = []
        self.argos_result = TranslationResult("argos text", True)
        self.ct2_result = TranslationResult("fast core text", True)
        self.small100_result = TranslationResult("core text", True)

    def _translate_with_argos(self, text: str, target_language: str) -> TranslationResult:
        self.calls.append(("argos", target_language, text))
        return self.argos_result

    def _translate_with_ct2small100(self, text: str, target_language: str) -> TranslationResult:
        self.calls.append(("ct2small100", target_language, text))
        return self.ct2_result

    def _translate_with_small100(self, text: str, target_language: str) -> TranslationResult:
        self.calls.append(("small100", target_language, text))
        return self.small100_result


class CT2RuntimeStubTranslator(LocalTranslator):
    def __init__(self):
        super().__init__("en")
        self.fake_translator = FakeCT2Translator()
        self.fake_tokenizer = FakeSmall100Tokenizer()

    def _load_ct2small100(self):
        return self.fake_translator, self.fake_tokenizer

    @staticmethod
    def _tokenizer_language_token(tokenizer, language: str) -> str:
        return f"__{language}__"


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
            "ct2small100": {
                "languages": ["es", "fr"],
                "status": {"ready": True},
            },
            "small100": {
                "languages": [],
                "status": {"ready": False},
            },
        }


class TranslationProviderRoutingTests(unittest.TestCase):
    def test_argos_stanza_sentence_boundary_pipeline_is_disabled(self):
        self.assertEqual(os.environ.get("ARGOS_STANZA_AVAILABLE"), "0")

    def test_both_mode_prefers_recommended_fast_core_when_available(self):
        translator = StubTranslator()
        result = translator.translate("Good morning", "fr", enabled=True, provider="both")
        self.assertTrue(result.applied)
        self.assertEqual(result.text, "fast core text")
        self.assertEqual([call[0] for call in translator.calls], ["ct2small100"])
        self.assertEqual(result.requested_provider, "both")
        self.assertEqual(result.actual_provider, "ct2small100")
        self.assertEqual(result.fallback_chain, ("ct2small100",))
        self.assertEqual(result.retry_count, 0)
        self.assertEqual(result.outcome, "applied")

    def test_both_mode_falls_back_to_base_argos_before_compatibility_core(self):
        translator = StubTranslator()
        translator.ct2_result = TranslationResult("Good morning", False, "Recommended package unavailable.")
        result = translator.translate("Good morning", "be", enabled=True, provider="both")
        self.assertTrue(result.applied)
        self.assertEqual(result.text, "argos text")
        self.assertEqual([call[0] for call in translator.calls], ["ct2small100", "argos"])
        self.assertEqual(result.actual_provider, "argos")
        self.assertEqual(result.fallback_chain, ("ct2small100", "argos"))
        self.assertEqual(result.retry_count, 1)

    def test_provider_failure_has_a_machine_readable_failed_outcome(self):
        translator = StubTranslator()
        translator.argos_result = TranslationResult("Good morning", False, "Argos Translate failed: simulated")
        result = translator.translate("Good morning", "fr", enabled=True, provider="argos")
        self.assertFalse(result.applied)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.requested_provider, "argos")
        self.assertEqual(result.actual_provider, "argos")

    def test_argos_aliases_norwegian_bokmal_to_norwegian(self):
        translator = ResourceStubTranslator()

        self.assertIn("no", translator.supported_languages_for_provider("argos"))

    def test_ct2small100_provider_exposes_fast_core_languages(self):
        translator = ResourceStubTranslator()

        self.assertIn("es", translator.supported_languages_for_provider("ct2small100"))

    def test_ct2small100_sets_target_language_before_tokenizing(self):
        translator = CT2RuntimeStubTranslator()

        result = translator._translate_with_ct2small100("Good morning", "fr")

        self.assertTrue(result.applied)
        self.assertEqual(result.text, "Bonjour")
        self.assertEqual(translator.fake_tokenizer.tgt_lang_when_tokenized, "fr")
        self.assertEqual(translator.fake_translator.calls[0][1].get("target_prefix"), None)

    def test_chinese_language_codes_are_kept_separate_and_legacy_zh_is_simplified(self):
        self.assertIn(CHINESE_SIMPLIFIED, LANGUAGE_BY_CODE)
        self.assertIn(CHINESE_TRADITIONAL, LANGUAGE_BY_CODE)
        self.assertNotIn("zh", LANGUAGE_BY_CODE)
        self.assertEqual(normalise_language("zh"), CHINESE_SIMPLIFIED)
        self.assertEqual(normalise_language("zh-CN"), CHINESE_SIMPLIFIED)
        self.assertEqual(normalise_language("zh-HK"), CHINESE_TRADITIONAL)
        self.assertEqual(normalise_language("zh-Hant"), CHINESE_TRADITIONAL)

    def test_chinese_variant_is_enforced_after_any_provider_translation(self):
        translator = StubTranslator()
        with patch.object(
            translator,
            "_convert_chinese_script",
            return_value=("歡迎來到教會", "s2hk", "1.4.1"),
        ) as convert:
            result = translator.translate(
                "Welcome to church",
                CHINESE_TRADITIONAL,
                enabled=True,
                provider="ct2small100",
            )

        self.assertTrue(result.applied)
        self.assertEqual(result.text, "歡迎來到教會")
        self.assertEqual(result.target_variant, CHINESE_TRADITIONAL)
        self.assertEqual(result.conversion_profile, "s2hk")
        self.assertEqual(result.conversion_profile_version, "1.4.1")
        convert.assert_called_once_with("fast core text", CHINESE_TRADITIONAL)

    def test_small100_routes_both_chinese_variants_through_model_chinese(self):
        translator = CT2RuntimeStubTranslator()

        result = translator._translate_with_ct2small100("Good morning", CHINESE_TRADITIONAL)

        self.assertTrue(result.applied)
        self.assertEqual(translator.fake_tokenizer.tgt_lang_when_tokenized, "zh")

    def test_restricted_policy_filters_audience_available_languages(self):
        source = Path("app/broadcast.py").read_text(encoding="utf-8")

        self.assertIn("self.source_language = SOURCE_LANGUAGE", source)
        self.assertIn("LocalTranslator(self.source_language)", source)
        self.assertIn('self.translation_language_policy == "restricted"', source)
        self.assertIn("self.translation_allowed_languages | {self.source_language}", source)
        self.assertIn("& provider_languages", source)
        self.assertIn('"available_languages": available_languages', source)

    def test_restricted_mode_exposes_requestable_languages(self):
        source = Path("app/broadcast.py").read_text(encoding="utf-8")
        self.assertIn("requestable_languages = sorted(provider_languages - self.translation_allowed_languages - {self.source_language})", source)
        self.assertIn('"requestable_languages": requestable_languages', source)

    def test_translation_timing_mode_uses_responsive_stable_english(self):
        runtime = Path("app/runtime_config.py").read_text(encoding="utf-8")
        broadcast = Path("app/broadcast.py").read_text(encoding="utf-8")
        operator = Path("app/templates/operator.html").read_text(encoding="utf-8")
        main = Path("app/main.py").read_text(encoding="utf-8")

        self.assertIn('"translation_timing_mode": "responsive"', runtime)
        self.assertIn('self.translation_timing_mode == "responsive"', broadcast)
        self.assertIn('minimum_gap = 1.5', broadcast)
        self.assertIn('minimum_words = 3', broadcast)
        self.assertIn("updates during speech after the wording settles", broadcast)
        self.assertIn("translationTimingMode", operator)
        self.assertIn('option value="responsive"', operator)
        self.assertNotIn('option value="contextual"', operator)
        self.assertNotIn('option value="extended"', operator)
        self.assertIn('{"contextual", "extended"}', broadcast)
        self.assertIn("translation_timing_mode", main)

    def test_language_requests_can_be_disabled(self):
        runtime = Path("app/runtime_config.py").read_text(encoding="utf-8")
        main = Path("app/main.py").read_text(encoding="utf-8")
        operator = Path("app/templates/operator.html").read_text(encoding="utf-8")
        client = Path("app/static/client.js").read_text(encoding="utf-8")

        self.assertIn('"translation_language_requests_enabled": True', runtime)
        self.assertIn('Language requests are currently disabled by the operator.', main)
        self.assertIn('translationLanguageRequestsEnabled', operator)
        self.assertIn('translationState?.language_requests_enabled === false', client)

    def test_language_request_routes_are_operator_gated_for_resolution(self):
        source = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn('"/api/language-requests"', source)
        self.assertIn('"/service-leader/api/language-requests"', source)
        self.assertIn('Depends(require_operator)', source.split('async def accept_language_request', 1)[1].split('async def reject_language_request', 1)[0])
        self.assertIn("set_translation_config(", source.split('async def accept_language_request', 1)[1].split('@app.post("/api/language-requests/{language}/reject")', 1)[0])


if __name__ == "__main__":
    unittest.main()
