"""Small, backend-neutral helpers for low-latency rolling transcription."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import RecognitionSpan


def _normalise_word(text: str) -> str:
    return re.sub(r"[^\w']+", "", str(text or "").casefold(), flags=re.UNICODE)


@dataclass(frozen=True)
class EdgeGuardResult:
    spans: tuple[RecognitionSpan, ...]
    withheld_words: int = 0
    confirmed_edge_words: int = 0


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
        self._confirmed = ""

    def reset(self) -> None:
        self._candidate = ""
        self._confirmed = ""

    def filter(
        self,
        spans: list[RecognitionSpan],
        *,
        audio_duration_seconds: float,
        protect_live_edge: bool,
    ) -> EdgeGuardResult:
        if not spans or not protect_live_edge or self.margin_seconds <= 0:
            self.reset()
            return EdgeGuardResult(tuple(spans))

        last = spans[-1]
        word = _normalise_word(last.text)
        remaining = max(0.0, float(audio_duration_seconds) - float(last.end_seconds))
        confidence = 1.0 if last.confidence is None else float(last.confidence)
        ends_thought = bool(re.search(r"[.!?][\"')\]]?$", str(last.text).strip()))
        risky = bool(
            word
            and not ends_thought
            and remaining <= self.margin_seconds
            and confidence < self.confidence_threshold
        )
        if not risky:
            self.reset()
            return EdgeGuardResult(tuple(spans))

        if word == self._confirmed:
            return EdgeGuardResult(tuple(spans))
        if word == self._candidate:
            self._confirmed = word
            return EdgeGuardResult(tuple(spans), confirmed_edge_words=1)

        self._candidate = word
        self._confirmed = ""
        return EdgeGuardResult(tuple(spans[:-1]), withheld_words=1)


def cadence_delay_seconds(*, pass_started: float, now: float, interval_seconds: float) -> float:
    """Return the remaining start-to-start cadence delay for one decode pass."""
    return max(0.0, float(pass_started) + max(0.0, float(interval_seconds)) - float(now))
