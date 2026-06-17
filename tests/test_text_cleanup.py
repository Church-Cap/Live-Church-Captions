import unittest

from app.text_cleanup import clean_caption_text


class CaptionTextCleanupTests(unittest.TestCase):
    def test_removes_punctuation_only_caption_noise(self):
        self.assertEqual(clean_caption_text(". . . . . . . ."), "")
        self.assertEqual(clean_caption_text("• • • • •"), "")
        self.assertEqual(clean_caption_text("… … …"), "")

    def test_keeps_normal_caption_text(self):
        self.assertEqual(clean_caption_text(" The reading is from John 3. "), "The reading is from John 3.")

    def test_keeps_translated_non_latin_caption_text(self):
        self.assertEqual(clean_caption_text("Высокія навушнікі."), "Высокія навушнікі.")
        self.assertEqual(clean_caption_text("שלום לכולם"), "שלום לכולם")


if __name__ == "__main__":
    unittest.main()
