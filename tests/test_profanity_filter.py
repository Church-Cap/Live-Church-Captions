import unittest

from app.profanity_filter import ProfanityFilter


class ProfanityFilterTests(unittest.TestCase):
    def test_masks_standalone_blocked_words(self):
        profanity_filter = ProfanityFilter(extra_words_path="/path/that/does/not/exist.txt")

        self.assertEqual("That was ****.", profanity_filter.apply("That was crap."))

    def test_does_not_mask_inside_larger_words(self):
        profanity_filter = ProfanityFilter(extra_words_path="/path/that/does/not/exist.txt")

        self.assertEqual("Classic passage.", profanity_filter.apply("Classic passage."))

    def test_can_be_disabled(self):
        profanity_filter = ProfanityFilter(extra_words_path="/path/that/does/not/exist.txt")

        self.assertEqual("That was crap.", profanity_filter.apply("That was crap.", enabled=False))


if __name__ == "__main__":
    unittest.main()
