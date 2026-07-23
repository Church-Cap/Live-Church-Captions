"""Small, backend-neutral helpers for low-latency rolling transcription."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import RecognitionSpan


def _normalise_word(text: str) -> str:
    return re.sub(r"[^\w']+", "", str(text or "").casefold(), flags=re.UNICODE)


def looks_unreliable_hypothesis(
    text: str,
    *,
    no_speech_probabilities: list[float] | tuple[float, ...] = (),
    average_log_probabilities: list[float] | tuple[float, ...] = (),
) -> bool:
    """Reject low-confidence or pathological Whisper hypotheses.

    Both supported Whisper backends expose no-speech and average log-probability
    metadata in slightly different structures. Keeping the policy here makes
    the audience-facing behaviour consistent without adding another model pass.
    """
    text = " ".join(str(text or "").split()).strip()
    if not text:
        return False
    no_speech = [float(value) for value in no_speech_probabilities]
    avg_logprob = [float(value) for value in average_log_probabilities]
    if no_speech and min(no_speech) >= 0.72:
        return True
    if avg_logprob and sum(avg_logprob) / len(avg_logprob) < -1.15:
        return True

    compact = re.sub(r"\s+", "", text)
    if re.search(r"(.)\1{7,}", compact):
        return True
    words = re.findall(r"[A-Za-z']+", text.casefold())
    repeated = 1
    for previous, current in zip(words, words[1:]):
        repeated = repeated + 1 if current == previous else 1
        if repeated >= 6:
            return True
    if len(text) >= 80:
        allowed_punctuation = ".,;:!?'-\"()"
        non_word = sum(
            1
            for char in text
            if not (char.isalnum() or char.isspace() or char in allowed_punctuation)
        )
        if non_word / max(len(text), 1) > 0.18:
            return True
    return False


def should_suppress_silence_hypothesis(text: str, *, had_recent_voice_at_capture: bool) -> bool:
    """Return whether a non-empty decode began outside the speech grace period.

    Rolling buffers still contain earlier speech after the speaker pauses. A
    decode started after the voice grace period must therefore never replace
    the last hypothesis that was captured while speech was active.
    """
    return bool(" ".join(str(text or "").split()).strip()) and not had_recent_voice_at_capture


@dataclass(frozen=True)
class EdgeGuardResult:
    spans: tuple[RecognitionSpan, ...]
    withheld_words: int = 0
    confirmed_edge_words: int = 0


@dataclass(frozen=True)
class SpeechBoundedAudioRange:
    start_sample: int
    end_sample: int
    capture_started_monotonic: float
    trailing_silence_trimmed_seconds: float = 0.0


def speech_bounded_audio_range(
    *,
    total_samples: int,
    sample_rate: int,
    audio_end_monotonic: float,
    last_voice_at: float,
    window_seconds: float,
    tail_padding_seconds: float = 0.25,
    trim_before_monotonic: float = 0.0,
    committed_overlap_seconds: float = 1.0,
) -> SpeechBoundedAudioRange:
    """Select rolling audio ending shortly after the last detected speech.

    The rolling buffer keeps growing during a pause. Passing that growing
    silence back to Whisper can produce a plausible suffix even though the
    earlier speech in the same window remains confident. This range keeps a
    small safety pad after the last voiced callback and does not otherwise
    change recognition cadence or request another decode.
    """
    total = max(0, int(total_samples))
    rate = max(1, int(sample_rate))
    audio_end = float(audio_end_monotonic)
    if total <= 0:
        return SpeechBoundedAudioRange(0, 0, audio_end)

    full_start = audio_end - (total / rate)
    if float(last_voice_at) <= 0:
        return SpeechBoundedAudioRange(
            0,
            0,
            audio_end,
            trailing_silence_trimmed_seconds=round(total / rate, 4),
        )

    effective_end = min(
        audio_end,
        max(full_start, float(last_voice_at) + max(0.0, float(tail_padding_seconds))),
    )
    capture_started = max(
        full_start,
        effective_end - max(0.0, float(window_seconds)),
    )
    if float(trim_before_monotonic) > 0:
        capture_started = max(
            capture_started,
            float(trim_before_monotonic) - max(0.0, float(committed_overlap_seconds)),
        )
    capture_started = min(effective_end, capture_started)
    start_sample = max(0, min(total, int(round((capture_started - full_start) * rate))))
    end_sample = max(start_sample, min(total, int(round((effective_end - full_start) * rate))))
    return SpeechBoundedAudioRange(
        start_sample,
        end_sample,
        capture_started,
        trailing_silence_trimmed_seconds=round(max(0.0, audio_end - effective_end), 4),
    )


class IncompleteEdgeGuard:
    """Withhold only a weak final word that may cross the live audio edge.

    A high-confidence final word remains visible immediately. A weak word very
    close to the end of the captured audio is released once a second decode
    agrees with it, or as soon as it is no longer at the live edge. This avoids
    holding the complete caption while reducing the most distracting last-word
    corrections.
    """

    def __init__(self, *, margin_seconds: float = 0.32, confidence_threshold: float = 0.65) -> None:
        self.margin_seconds = max(0.0, float(margin_seconds))
        self.confidence_threshold = min(1.0, max(0.0, float(confidence_threshold)))
        self._candidate = ""
        self._candidate_speech_progress: float | None = None
        self._confirmed = ""

    def reset(self) -> None:
        self._candidate = ""
        self._candidate_speech_progress = None
        self._confirmed = ""

    def filter(
        self,
        spans: list[RecognitionSpan],
        *,
        audio_duration_seconds: float,
        protect_live_edge: bool,
        speech_progress_seconds: float | None = None,
    ) -> EdgeGuardResult:
        if not spans or not protect_live_edge or self.margin_seconds <= 0:
            self.reset()
            return EdgeGuardResult(tuple(spans))

        last = spans[-1]
        word = _normalise_word(last.text)
        remaining = max(0.0, float(audio_duration_seconds) - float(last.end_seconds))
        confidence = 1.0 if last.confidence is None else float(last.confidence)
        risky = bool(
            word
            and remaining <= self.margin_seconds
            and confidence < self.confidence_threshold
        )
        if not risky:
            self.reset()
            return EdgeGuardResult(tuple(spans))

        if word == self._confirmed:
            return EdgeGuardResult(tuple(spans))
        if word == self._candidate:
            # Re-decoding the exact same bounded audio is not independent
            # evidence. Only confirm a weak live-edge word after genuinely new
            # speech has moved the acoustic boundary forward. This prevents a
            # plausible suffix inferred from a pause being "confirmed" by the
            # next scheduled pass over identical audio.
            progressed = (
                speech_progress_seconds is None
                or self._candidate_speech_progress is None
                or float(speech_progress_seconds) >= self._candidate_speech_progress + 0.06
            )
            if progressed:
                self._confirmed = word
                return EdgeGuardResult(tuple(spans), confirmed_edge_words=1)
            return EdgeGuardResult(tuple(spans[:-1]), withheld_words=1)

        self._candidate = word
        self._candidate_speech_progress = (
            None if speech_progress_seconds is None else float(speech_progress_seconds)
        )
        self._confirmed = ""
        return EdgeGuardResult(tuple(spans[:-1]), withheld_words=1)


def cadence_delay_seconds(*, pass_started: float, now: float, interval_seconds: float) -> float:
    """Return the remaining start-to-start cadence delay for one decode pass."""
    return max(0.0, float(pass_started) + max(0.0, float(interval_seconds)) - float(now))
