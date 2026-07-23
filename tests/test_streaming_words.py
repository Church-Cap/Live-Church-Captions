import unittest

from app.models import RecognitionSpan
from app.transcription.streaming_words import (
    IncompleteEdgeGuard,
    cadence_delay_seconds,
    looks_unreliable_hypothesis,
    speech_bounded_audio_range,
    should_suppress_silence_hypothesis,
)


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

        first = guard.filter(
            spans,
            audio_duration_seconds=1.0,
            protect_live_edge=True,
            speech_progress_seconds=0.9,
        )
        second = guard.filter(
            spans,
            audio_duration_seconds=1.0,
            protect_live_edge=True,
            speech_progress_seconds=1.0,
        )

        self.assertEqual([item.text for item in first.spans], ["the"])
        self.assertEqual(first.withheld_words, 1)
        self.assertEqual([item.text for item in second.spans], ["the", "message"])
        self.assertEqual(second.confirmed_edge_words, 1)

    def test_high_confidence_edge_word_is_immediate_but_punctuation_is_not_acoustic_evidence(self):
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
        self.assertEqual(len(punctuated.spans), 0)
        self.assertEqual(confident.withheld_words, 0)
        self.assertEqual(punctuated.withheld_words, 1)

    def test_same_bounded_audio_cannot_confirm_a_weak_suffix_during_a_pause(self):
        guard = IncompleteEdgeGuard(margin_seconds=0.32, confidence_threshold=0.65)
        spans = [word("message", 0.6, 0.98, 0.42)]

        first = guard.filter(
            spans,
            audio_duration_seconds=1.0,
            protect_live_edge=True,
            speech_progress_seconds=0.9,
        )
        repeated = guard.filter(
            spans,
            audio_duration_seconds=1.0,
            protect_live_edge=True,
            speech_progress_seconds=0.9,
        )

        self.assertEqual(first.spans, ())
        self.assertEqual(repeated.spans, ())
        self.assertEqual(repeated.withheld_words, 1)

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

    def test_nonempty_decode_started_after_voice_grace_is_suppressed(self):
        self.assertTrue(
            should_suppress_silence_hypothesis(
                "Thank you for watching.",
                had_recent_voice_at_capture=False,
            )
        )
        self.assertFalse(
            should_suppress_silence_hypothesis(
                "The final words are real.",
                had_recent_voice_at_capture=True,
            )
        )
        self.assertFalse(
            should_suppress_silence_hypothesis(
                "",
                had_recent_voice_at_capture=False,
            )
        )

    def test_whisper_metadata_rejects_no_speech_and_low_probability(self):
        self.assertTrue(
            looks_unreliable_hypothesis(
                "A plausible phrase from silence.",
                no_speech_probabilities=(0.81, 0.75),
                average_log_probabilities=(-0.4, -0.5),
            )
        )
        self.assertTrue(
            looks_unreliable_hypothesis(
                "A weak decoding result.",
                no_speech_probabilities=(0.1,),
                average_log_probabilities=(-1.3,),
            )
        )
        self.assertFalse(
            looks_unreliable_hypothesis(
                "A confident decoding result.",
                no_speech_probabilities=(0.08,),
                average_log_probabilities=(-0.35,),
            )
        )

    def test_pathological_repetition_is_rejected_without_language_text_storage(self):
        self.assertTrue(looks_unreliable_hypothesis("amen amen amen amen amen amen"))
        self.assertFalse(looks_unreliable_hypothesis("We say amen together."))

    def test_rolling_audio_ends_after_small_last_voice_safety_pad(self):
        selected = speech_bounded_audio_range(
            total_samples=7 * 16000,
            sample_rate=16000,
            audio_end_monotonic=10.0,
            last_voice_at=9.0,
            window_seconds=6.0,
            tail_padding_seconds=0.25,
        )

        self.assertEqual(selected.start_sample, 4000)
        self.assertEqual(selected.end_sample, 100000)
        self.assertEqual(selected.capture_started_monotonic, 3.25)
        self.assertEqual(selected.trailing_silence_trimmed_seconds, 0.75)

    def test_active_speech_keeps_the_complete_window(self):
        selected = speech_bounded_audio_range(
            total_samples=7 * 16000,
            sample_rate=16000,
            audio_end_monotonic=10.0,
            last_voice_at=9.95,
            window_seconds=6.0,
            tail_padding_seconds=0.25,
        )

        self.assertEqual(selected.end_sample, 7 * 16000)
        self.assertEqual(selected.end_sample - selected.start_sample, 6 * 16000)
        self.assertEqual(selected.trailing_silence_trimmed_seconds, 0.0)

    def test_no_detected_voice_never_reaches_whisper(self):
        selected = speech_bounded_audio_range(
            total_samples=16000,
            sample_rate=16000,
            audio_end_monotonic=10.0,
            last_voice_at=0.0,
            window_seconds=6.0,
        )

        self.assertEqual((selected.start_sample, selected.end_sample), (0, 0))
        self.assertEqual(selected.trailing_silence_trimmed_seconds, 1.0)

    def test_committed_audio_trim_and_speech_end_are_both_respected(self):
        selected = speech_bounded_audio_range(
            total_samples=7 * 16000,
            sample_rate=16000,
            audio_end_monotonic=10.0,
            last_voice_at=9.0,
            window_seconds=6.0,
            tail_padding_seconds=0.25,
            trim_before_monotonic=8.0,
            committed_overlap_seconds=1.0,
        )

        self.assertEqual(selected.capture_started_monotonic, 7.0)
        self.assertEqual(selected.end_sample - selected.start_sample, int(2.25 * 16000))


if __name__ == "__main__":
    unittest.main()
