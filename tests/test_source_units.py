import unittest

from app.models import CaptionSegment, RecognitionSpan
from app.source_units import SourceUnitBuilder


class SourceUnitBuilderTests(unittest.TestCase):
    def test_word_aligned_spans_preserve_corrected_display_text(self):
        builder = SourceUnitBuilder(minimum_words=2)
        update = CaptionSegment(
            text="Holy Spirit",
            raw_text="wholly spirit",
            is_final=False,
            capture_started_monotonic=100.0,
            recognition_spans=[
                RecognitionSpan(text="wholly", start_seconds=0.1, end_seconds=0.5, confidence=0.8, word_aligned=True),
                RecognitionSpan(text="spirit", start_seconds=0.6, end_seconds=1.0, confidence=0.9, word_aligned=True),
            ],
        )

        result = builder.ingest(update)

        self.assertEqual(result[-1].text, "Holy Spirit")

    def test_final_word_timestamp_exposes_safe_audio_trim_boundary(self):
        builder = SourceUnitBuilder(minimum_words=2)
        final = CaptionSegment(
            text="Grace remains.",
            is_final=True,
            capture_started_monotonic=100.0,
            recognition_spans=[
                RecognitionSpan(text="Grace", start_seconds=0.2, end_seconds=0.8, confidence=0.9, word_aligned=True),
                RecognitionSpan(text="remains.", start_seconds=0.9, end_seconds=1.4, confidence=0.9, word_aligned=True),
            ],
        )

        result = builder.ingest(final)

        self.assertTrue(result[-1].is_final)
        self.assertAlmostEqual(builder.sealed_audio_end_monotonic or 0.0, 101.4)

    def test_rolling_hypotheses_revise_one_stable_unit(self):
        builder = SourceUnitBuilder()

        first = builder.ingest(CaptionSegment(text="Jesus welcomes every person", is_final=False), now=10.0)[0]
        second = builder.ingest(CaptionSegment(text="Jesus welcomes every person into his family", is_final=False), now=11.0)[0]

        self.assertEqual(first.source_unit_id, second.source_unit_id)
        self.assertEqual(first.source_revision, 1)
        self.assertEqual(second.source_revision, 2)
        self.assertEqual(second.source_status, "draft")
        self.assertEqual(first.cue_stable_word_count, 0)
        self.assertEqual(second.cue_stable_word_count, 4)
        self.assertEqual(second.cue_mutable_word_count, 3)
        self.assertFalse(second.is_final)

    def test_whisper_final_promotes_draft_without_changing_identity(self):
        builder = SourceUnitBuilder()
        draft = builder.ingest(CaptionSegment(text="Let us pray together", is_final=False), now=20.0)[0]

        final = builder.ingest(CaptionSegment(text="Let us pray together now", is_final=True), now=21.0)[0]

        self.assertEqual(final.source_unit_id, draft.source_unit_id)
        self.assertGreater(final.source_revision, draft.source_revision)
        self.assertEqual(final.source_status, "final")
        self.assertEqual(final.source_boundary_reason, "whisper_final")
        self.assertTrue(final.is_final)

    def test_punctuation_stays_replaceable_until_whisper_final(self):
        builder = SourceUnitBuilder()

        draft = builder.ingest(CaptionSegment(text="This is the word of the Lord.", is_final=False), now=30.0)[0]
        corrected = builder.ingest(CaptionSegment(text="This is the word of our Lord.", is_final=False), now=31.0)[0]

        self.assertFalse(draft.is_final)
        self.assertEqual(corrected.source_unit_id, draft.source_unit_id)
        self.assertEqual(builder.current_draft.text, "This is the word of our Lord.")
        self.assertEqual(corrected.cue_stable_word_count, 5)
        self.assertEqual(corrected.cue_mutable_word_count, 2)

        final = builder.ingest(CaptionSegment(text="This is the word of our Lord.", is_final=True), now=32.0)[0]
        self.assertTrue(final.is_final)
        self.assertEqual(final.source_unit_id, draft.source_unit_id)
        self.assertEqual(final.source_boundary_reason, "whisper_final")

    def test_rolling_punctuation_corrections_do_not_create_duplicate_final_units(self):
        builder = SourceUnitBuilder()

        first = builder.ingest(
            CaptionSegment(text="Empty space doesn't stay empty.", is_final=False),
            now=40.0,
        )
        second = builder.ingest(
            CaptionSegment(text="Empty space doesn't stay empty. If you don't feel it on purpose, your brain will.", is_final=False),
            now=41.0,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 2)
        self.assertFalse(first[0].is_final)
        self.assertTrue(second[0].is_final)
        self.assertEqual(second[0].source_unit_id, first[0].source_unit_id)
        self.assertEqual(second[0].text, "Empty space doesn't stay empty.")
        self.assertFalse(second[1].is_final)
        self.assertEqual(second[1].text, "If you don't feel it on purpose, your brain will.")
        self.assertNotEqual(second[1].source_unit_id, first[0].source_unit_id)

    def test_middle_word_correction_revises_the_existing_source_unit(self):
        builder = SourceUnitBuilder()
        first = builder.ingest(
            CaptionSegment(text="That rhyme. I didn't mean to rhyme there, but here's what Christians meant.", is_final=False),
            now=50.0,
        )[0]
        corrected = builder.ingest(
            CaptionSegment(text="That rhyme. I didn't mean to rhyme there, but here's what Christians miss.", is_final=False),
            now=51.0,
        )[0]
        sealed = builder.ingest(
            CaptionSegment(text="That rhyme. I didn't mean to rhyme there, but here's what Christians miss. Empty space.", is_final=False),
            now=52.0,
        )[0]

        self.assertFalse(first.is_final)
        self.assertFalse(corrected.is_final)
        self.assertEqual(corrected.source_unit_id, first.source_unit_id)
        self.assertEqual(corrected.text, "That rhyme. I didn't mean to rhyme there, but here's what Christians miss.")
        self.assertTrue(sealed.is_final)
        self.assertEqual(sealed.source_unit_id, first.source_unit_id)

    def test_unrelated_rolling_revision_is_immediate(self):
        builder = SourceUnitBuilder()
        draft = builder.ingest(CaptionSegment(text="The first completed thought", is_final=False), now=40.0)[0]

        update = builder.ingest(CaptionSegment(text="A completely different next thought", is_final=False), now=41.0)[0]
        duplicate = builder.ingest(CaptionSegment(text="A completely different next thought", is_final=False), now=42.0)

        self.assertEqual(update.source_unit_id, draft.source_unit_id)
        self.assertFalse(update.is_final)
        self.assertEqual(update.text, "A completely different next thought")
        self.assertEqual(update.cue_stable_word_count, 0)
        self.assertEqual(duplicate, [])

    def test_timestamp_alignment_commits_words_that_slide_out_of_the_window(self):
        builder = SourceUnitBuilder(maximum_words=20, maximum_duration_seconds=8.0)
        first = CaptionSegment(
            text="one two three four five six",
            raw_text="one two three four five six",
            is_final=False,
            capture_started_monotonic=100.0,
            recognition_spans=[RecognitionSpan(text="one two three four five six", start_seconds=0.0, end_seconds=6.0)],
        )
        second = CaptionSegment(
            text="three four five six seven eight",
            raw_text="three four five six seven eight",
            is_final=False,
            capture_started_monotonic=102.0,
            recognition_spans=[RecognitionSpan(text="three four five six seven eight", start_seconds=0.0, end_seconds=6.0)],
        )

        first_update = builder.ingest(first)[0]
        second_update = builder.ingest(second)[0]

        self.assertEqual(second_update.source_unit_id, first_update.source_unit_id)
        self.assertEqual(second_update.text, "one two three four five six seven eight")
        self.assertFalse(second_update.is_final)

    def test_forward_extension_remains_immediate(self):
        builder = SourceUnitBuilder()
        first = builder.ingest(CaptionSegment(text="Grace changes us", is_final=False), now=1.0)[0]
        second = builder.ingest(CaptionSegment(text="Grace changes us from within", is_final=False), now=2.0)[0]

        self.assertEqual(second.source_unit_id, first.source_unit_id)
        self.assertEqual(second.text, "Grace changes us from within")
        self.assertEqual(second.cue_stable_word_count, 3)

    def test_transient_tail_revision_is_published_without_an_extra_pass(self):
        builder = SourceUnitBuilder()
        original = builder.ingest(CaptionSegment(text="God welcomes every person", is_final=False), now=1.0)[0]
        transient = builder.ingest(CaptionSegment(text="God forgets every person", is_final=False), now=2.0)[0]
        restored = builder.ingest(CaptionSegment(text="God welcomes every person", is_final=False), now=3.0)[0]

        self.assertEqual(builder.current_draft.id, original.id)
        self.assertEqual(builder.current_draft.text, "God welcomes every person")
        self.assertEqual(transient.source_revision, 2)
        self.assertEqual(restored.source_revision, 3)
        self.assertEqual(transient.cue_stable_word_count, 1)
        self.assertEqual(restored.cue_stable_word_count, 1)

    def test_internal_recognition_spans_are_not_serialised(self):
        segment = CaptionSegment(
            text="timed speech",
            recognition_spans=[RecognitionSpan(text="timed speech", start_seconds=0.0, end_seconds=1.0)],
        )

        self.assertNotIn("recognition_spans", segment.model_dump(mode="json"))

    def test_reset_starts_a_new_privacy_context(self):
        builder = SourceUnitBuilder()
        first = builder.ingest(CaptionSegment(text="Private pastoral conversation", is_final=False), now=50.0)[0]

        builder.reset()
        second = builder.ingest(CaptionSegment(text="Public service has resumed", is_final=False), now=51.0)[0]

        self.assertNotEqual(first.context_group_id, second.context_group_id)
        self.assertNotEqual(first.source_unit_id, second.source_unit_id)


if __name__ == "__main__":
    unittest.main()
