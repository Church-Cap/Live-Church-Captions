import unittest
from collections import deque
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.transcription.faster_whisper_live import FasterWhisperTranscriber
from app.transcription.streaming_words import IncompleteEdgeGuard
from app.transcription.whisper_live import WhisperLiveTranscriber


class _FakeModel:
    def __init__(self, segment):
        self.segment = segment
        self.options = None

    def transcribe(self, _audio, **options):
        self.options = options
        return iter((self.segment,)), SimpleNamespace()


class _FakeStandardModel:
    def __init__(self, result):
        self.result = result
        self.options = None

    def transcribe(self, _audio, **options):
        self.options = options
        return self.result


def _transcriber(segment):
    transcriber = FasterWhisperTranscriber.__new__(FasterWhisperTranscriber)
    transcriber.sample_rate = 16000
    transcriber.min_rms = 0.006
    transcriber.language = "en"
    transcriber.initial_prompt = None
    transcriber.word_timestamps_enabled = True
    transcriber._model = _FakeModel(segment)
    transcriber._edge_guard = IncompleteEdgeGuard()
    return transcriber


def _segment(*, no_speech_prob=0.05, avg_logprob=-0.2):
    return SimpleNamespace(
        text=" A genuine sentence.",
        start=0.0,
        end=1.0,
        no_speech_prob=no_speech_prob,
        avg_logprob=avg_logprob,
        words=(
            SimpleNamespace(word=" A", start=0.0, end=0.2, probability=0.94),
            SimpleNamespace(word=" genuine", start=0.2, end=0.55, probability=0.93),
            SimpleNamespace(word=" sentence.", start=0.55, end=1.0, probability=0.92),
        ),
    )


class FasterWhisperHallucinationGuardTests(unittest.TestCase):
    def test_confident_speech_remains_available_without_an_extra_pass(self):
        transcriber = _transcriber(_segment())

        text, spans = transcriber._transcribe_text(
            np.full(16000, 0.02, dtype=np.float32),
            True,
        )

        self.assertEqual(text, "A genuine sentence.")
        self.assertEqual([span.text for span in spans], ["A", "genuine", "sentence."])
        self.assertEqual(transcriber._model.options["hallucination_silence_threshold"], 0.5)
        self.assertEqual(
            transcriber._model.options["vad_parameters"],
            {
                "threshold": 0.5,
                "neg_threshold": 0.35,
                "min_speech_duration_ms": 100,
                "min_silence_duration_ms": 160,
                "speech_pad_ms": 100,
            },
        )

    def test_same_post_speech_audio_does_not_confirm_a_weak_last_word(self):
        segment = _segment()
        segment.words = (*segment.words[:-1], SimpleNamespace(
            word=" maybe",
            start=0.8,
            end=0.99,
            probability=0.4,
        ))
        transcriber = _transcriber(segment)
        audio = np.full(16000, 0.02, dtype=np.float32)

        first_text, _ = transcriber._transcribe_text(audio, True, 0.9)
        repeated_text, _ = transcriber._transcribe_text(audio, True, 0.9)

        self.assertEqual(first_text, "A genuine")
        self.assertEqual(repeated_text, "A genuine")

    def test_high_no_speech_hypothesis_is_not_returned(self):
        transcriber = _transcriber(_segment(no_speech_prob=0.82, avg_logprob=-0.35))

        text, spans = transcriber._transcribe_text(
            np.full(16000, 0.02, dtype=np.float32),
            False,
        )

        self.assertEqual(text, "")
        self.assertEqual(spans, [])

    def test_faster_backend_removes_growing_silence_before_decode(self):
        transcriber = FasterWhisperTranscriber.__new__(FasterWhisperTranscriber)
        transcriber.sample_rate = 100
        transcriber.window_seconds = 6.0
        transcriber._audio_lock = Lock()
        transcriber._audio_buffer = deque((np.arange(700, dtype=np.float32),))
        transcriber._audio_end_monotonic = 10.0
        transcriber._last_voice_at = 9.0
        transcriber._trim_before_monotonic = 0.0
        transcriber.committed_audio_overlap_seconds = 1.0
        transcriber.speech_tail_padding_seconds = 0.25

        audio, capture_started = transcriber._latest_audio()

        self.assertEqual(audio.size, 600)
        self.assertEqual(capture_started, 3.25)
        self.assertEqual(audio[-1], 624.0)

    def test_standard_backend_uses_the_same_speech_bounded_input(self):
        transcriber = WhisperLiveTranscriber.__new__(WhisperLiveTranscriber)
        transcriber.sample_rate = 100
        transcriber.window_seconds = 6.0
        transcriber._audio_lock = Lock()
        transcriber._audio_buffer = deque((np.arange(700, dtype=np.float32),))
        transcriber._audio_end_monotonic = 10.0
        transcriber._last_voice_at = 9.0
        transcriber.speech_tail_padding_seconds = 0.25

        audio, capture_started = transcriber._latest_audio()

        self.assertEqual(audio.size, 600)
        self.assertEqual(capture_started, 3.25)
        self.assertEqual(audio[-1], 624.0)

    def test_standard_backend_uses_silero_clips_and_word_timestamp_guard(self):
        transcriber = WhisperLiveTranscriber.__new__(WhisperLiveTranscriber)
        transcriber.sample_rate = 16000
        transcriber.min_rms = 0.006
        transcriber.language = "en"
        transcriber.device = "cpu"
        transcriber.beam_size = 1
        transcriber.initial_prompt = None
        transcriber._edge_guard = IncompleteEdgeGuard()
        transcriber._model = _FakeStandardModel({
            "text": " A genuine sentence.",
            "segments": [{
                "text": " A genuine sentence.",
                "start": 0.0,
                "end": 0.9,
                "no_speech_prob": 0.05,
                "avg_logprob": -0.2,
                "words": [
                    {"word": " A", "start": 0.0, "end": 0.2, "probability": 0.94},
                    {"word": " genuine", "start": 0.2, "end": 0.55, "probability": 0.93},
                    {"word": " sentence.", "start": 0.55, "end": 0.9, "probability": 0.92},
                ],
            }],
        })

        with patch(
            "app.transcription.whisper_live.get_speech_timestamps",
            return_value=[{"start": 0, "end": 14400}],
        ):
            text, spans = transcriber._transcribe_text(
                np.full(16000, 0.02, dtype=np.float32),
                True,
                0.9,
            )

        self.assertEqual(text, "A genuine sentence.")
        self.assertEqual([span.text for span in spans], ["A", "genuine", "sentence."])
        self.assertTrue(transcriber._model.options["word_timestamps"])
        self.assertEqual(transcriber._model.options["hallucination_silence_threshold"], 0.5)
        self.assertEqual(transcriber._model.options["clip_timestamps"], [0.0, 0.9])

    def test_low_log_probability_hypothesis_is_not_returned(self):
        transcriber = _transcriber(_segment(no_speech_prob=0.08, avg_logprob=-1.3))

        text, spans = transcriber._transcribe_text(
            np.full(16000, 0.02, dtype=np.float32),
            True,
        )

        self.assertEqual(text, "")
        self.assertEqual(spans, [])


if __name__ == "__main__":
    unittest.main()
