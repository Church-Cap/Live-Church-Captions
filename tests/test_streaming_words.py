import unittest

from app.models import RecognitionSpan
from app.transcription.streaming_words import IncompleteEdgeGuard, cadence_delay_seconds


def word(text: str, start: float, end: float, confidence: float) -> RecognitionSpan:
    return RecognitionSpan(
        text=text,
        start_seconds=start,
        end_seconds=end,
        confidence=confidence,
        word_aligned=True,
    )


class IncompleteEdgeGuardTests(unittest.TestCase):
    def test_weak_live_edge_word_waits_for_second_matching_decode(self):
        guard = IncompleteEdgeGuard(margin_seconds=0.32, confidence_threshold=0.65)
        spans = [word("the", 0.2, 0.5, 0.98), word("message", 0.6, 0.95, 0.42)]

        first = guard.filter(spans, audio_duration_seconds=1.0, protect_live_edge=True)
        second = guard.filter(spans, audio_duration_seconds=1.0, protect_live_edge=True)

        self.assertEqual([item.text for item in first.spans], ["the"])
        self.assertEqual(first.withheld_words, 1)
        self.assertEqual([item.text for item in second.spans], ["the", "message"])
        self.assertEqual(second.confirmed_edge_words, 1)

    def test_high_confidence_or_completed_edge_word_is_immediate(self):
        guard = IncompleteEdgeGuard(margin_seconds=0.32, confidence_threshold=0.65)

        confident = guard.filter(
            [word("message", 0.6, 0.98, 0.91)],
            audio_duration_seconds=1.0,
            protect_live_edge=True,
        )
        punctuated = guard.filter(
            [word("message.", 0.6, 0.98, 0.30)],
            audio_duration_seconds=1.0,
            protect_live_edge=True,
        )

        self.assertEqual(len(confident.spans), 1)
        self.assertEqual(len(punctuated.spans), 1)
        self.assertEqual(confident.withheld_words + punctuated.withheld_words, 0)

    def test_silence_finalisation_never_holds_the_last_word(self):
        guard = IncompleteEdgeGuard(margin_seconds=0.32, confidence_threshold=0.65)
        result = guard.filter(
            [word("amen", 0.6, 0.98, 0.2)],
            audio_duration_seconds=1.0,
            protect_live_edge=False,
        )
        self.assertEqual([item.text for item in result.spans], ["amen"])

    def test_start_to_start_cadence_subtracts_compute_time(self):
        self.assertAlmostEqual(
            cadence_delay_seconds(pass_started=10.0, now=10.6, interval_seconds=1.0),
            0.4,
        )
        self.assertEqual(
            cadence_delay_seconds(pass_started=10.0, now=11.2, interval_seconds=1.0),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
