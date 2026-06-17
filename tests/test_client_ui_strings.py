import re
import unittest
from pathlib import Path

from app.localisation import (
    get_client_ui_coverage,
    get_client_ui_language_strings,
    get_client_ui_sources,
    validate_client_ui_catalog,
)
from app.i18n import ARGOS_ENGLISH_TARGET_LANGUAGE_CODES, SUPPORTED_LANGUAGES


class ClientUiStringTests(unittest.TestCase):
    def test_catalog_is_internally_complete(self):
        self.assertEqual(validate_client_ui_catalog(), [])

    def test_finnish_ui_strings_are_static(self):
        sources = get_client_ui_sources(["fi"])
        strings = get_client_ui_language_strings("fi")
        english = get_client_ui_language_strings("en")

        self.assertEqual(sources["fi"], "static")
        self.assertEqual(strings["live_captions"], "Livetekstitys")
        self.assertNotEqual(strings["waiting"], english["waiting"])

    def test_catalog_covers_languages_argos_cannot_translate(self):
        codes = [language["code"] for language in SUPPORTED_LANGUAGES]
        coverage = get_client_ui_coverage(codes)
        missing_static = [
            code for code in codes
            if code != "en" and code not in ARGOS_ENGLISH_TARGET_LANGUAGE_CODES and not coverage[code]
        ]

        self.assertTrue(coverage["en"])
        self.assertTrue(coverage["fi"])
        self.assertTrue(coverage["ast"])
        self.assertEqual(missing_static, [])

    def test_non_english_static_locales_are_not_plain_english_copies(self):
        english = get_client_ui_language_strings("en")
        codes = [language["code"] for language in SUPPORTED_LANGUAGES if language["code"] != "en"]
        static_codes = [code for code, source in get_client_ui_sources(codes).items() if source == "static"]

        self.assertTrue(static_codes)
        self.assertEqual(
            [code for code in static_codes if get_client_ui_language_strings(code) == english],
            [],
        )

    def test_unsupported_ui_language_uses_english_fallback(self):
        sources = get_client_ui_sources(["zz"])
        strings = get_client_ui_language_strings("zz")
        english = get_client_ui_language_strings("en")

        self.assertEqual(sources["zz"], "fallback")
        self.assertEqual(strings["live_captions"], english["live_captions"])

    def test_caption_template_i18n_keys_exist_in_english(self):
        template = Path("app/templates/captions.html").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n(?:-[\\w-]+)?="([^"]+)"', template))
        english = get_client_ui_language_strings("en")

        self.assertTrue(keys)
        self.assertEqual(sorted(keys - set(english)), [])


if __name__ == "__main__":
    unittest.main()
