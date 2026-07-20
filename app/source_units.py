from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.models import CaptionSegment
from app.text_cleanup import clean_caption_text, collapse_repeated_phrase


@dataclass(frozen=True)
class _TimedToken:
    text: str
    normalised: str
    start: float | None = None
    end: float | None = None


class SourceUnitBuilder:
    """Build stable, revisioned display cues from rolling Whisper hypotheses.

    The previous implementation guessed whether whole-window strings were new
    speech. A failed guess permanently appended the old and corrected versions.
    This implementation follows a local-agreement policy instead: the complete
    newest hypothesis is displayed immediately. Words shared by consecutive
    hypotheses form a stable prefix; only the newest tail remains mutable.
    This mirrors streaming speech APIs without adding another recognition-pass
    delay on top of Whisper's own rolling-window cadence.

    Segment timestamps are used when a backend supplies them. Text-only input
    remains supported for mock/replay paths and automated tests.
    """

    def __init__(
        self,
        *,
        minimum_words: int = 2,
        punctuation_minimum_words: int = 5,
        maximum_words: int = 14,
        maximum_duration_seconds: float = 5.0,
        timestamp_tolerance_seconds: float = 0.18,
    ) -> None:
        self.minimum_words = max(1, int(minimum_words))
        self.punctuation_minimum_words = max(self.minimum_words, int(punctuation_minimum_words))
        self.maximum_words = max(self.punctuation_minimum_words, int(maximum_words))
        self.maximum_duration_seconds = max(2.0, float(maximum_duration_seconds))
        self.timestamp_tolerance_seconds = max(0.05, float(timestamp_tolerance_seconds))
        self._context_group_id = str(uuid4())
        self.reset()

    @property
    def current_draft(self) -> CaptionSegment | None:
        return self._draft

    @property
    def sealed_audio_end_monotonic(self) -> float | None:
        """Newest immutable source-audio boundary safe for buffer trimming."""
        return self._sealed_audio_end

    def reset(self) -> None:
        self._cue_id = str(uuid4())
        self._cue_revision = 0
        self._cue_started_at = datetime.now(timezone.utc)
        self._confirmed: list[_TimedToken] = []
        self._confirmed_context: list[_TimedToken] = []
        self._pending: list[_TimedToken] = []
        self._committed_end: float | None = None
        self._sealed_audio_end: float | None = None
        self._draft: CaptionSegment | None = None
        self._last_emitted_text = ""
        self._context_group_id = str(uuid4())

    @staticmethod
    def _normalise_token(text: str) -> str:
        return re.sub(r"[^\w']+", "", str(text or "").casefold(), flags=re.UNICODE)

    @classmethod
    def _tokenise_text(
        cls,
        text: str,
        *,
        start: float | None = None,
        end: float | None = None,
    ) -> list[_TimedToken]:
        words = str(text or "").split()
        if not words:
            return []
        duration = None if start is None or end is None else max(0.0, end - start)
        tokens: list[_TimedToken] = []
        for index, word in enumerate(words):
            token_start = None
            token_end = None
            if duration is not None:
                token_start = start + duration * (index / len(words))
                token_end = start + duration * ((index + 1) / len(words))
            normalised = cls._normalise_token(word)
            if normalised:
                tokens.append(_TimedToken(word, normalised, token_start, token_end))
        return tokens

    def _tokens_from_segment(self, segment: CaptionSegment) -> list[_TimedToken]:
        base = segment.capture_started_monotonic
        if segment.recognition_spans:
            display_words = str(segment.text or "").split()
            if (
                display_words
                and len(display_words) == len(segment.recognition_spans)
                and all(span.word_aligned for span in segment.recognition_spans)
            ):
                tokens = []
                for word, span in zip(display_words, segment.recognition_spans):
                    normalised = self._normalise_token(word)
                    if not normalised:
                        continue
                    tokens.append(_TimedToken(
                        word,
                        normalised,
                        None if base is None else base + float(span.start_seconds),
                        None if base is None else base + float(span.end_seconds),
                    ))
                if tokens:
                    return tokens

            tokens: list[_TimedToken] = []
            for span in segment.recognition_spans:
                start = None if base is None else base + float(span.start_seconds)
                end = None if base is None else base + float(span.end_seconds)
                tokens.extend(self._tokenise_text(span.text, start=start, end=end))
            if tokens:
                # Preserve glossary/profanity corrections even when they alter
                # token count, while retaining the recogniser's real time range.
                corrected = self._tokenise_text(
                    segment.text,
                    start=tokens[0].start,
                    end=tokens[-1].end,
                )
                return corrected or tokens
        return self._tokenise_text(segment.raw_text or segment.text)

    @staticmethod
    def _join(tokens: list[_TimedToken]) -> str:
        return clean_caption_text(collapse_repeated_phrase(" ".join(token.text for token in tokens)))

    @staticmethod
    def _same_token(left: _TimedToken, right: _TimedToken) -> bool:
        return bool(left.normalised and left.normalised == right.normalised)

    def _strip_committed_overlap(self, tokens: list[_TimedToken]) -> list[_TimedToken]:
        if not tokens:
            return []
        if self._committed_end is not None and any(token.end is not None for token in tokens):
            threshold = self._committed_end + self.timestamp_tolerance_seconds
            timed = [token for token in tokens if token.end is None or token.end > threshold]
            if len(timed) != len(tokens):
                return timed

        context = self._confirmed_context[-64:]
        max_overlap = min(len(context), len(tokens), 32)
        for size in range(max_overlap, 0, -1):
            if all(self._same_token(a, b) for a, b in zip(context[-size:], tokens[:size])):
                return tokens[size:]
        return tokens

    def _agreement_count(self, previous: list[_TimedToken], current: list[_TimedToken]) -> int:
        count = 0
        for old, new in zip(previous, current):
            if not self._same_token(old, new):
                break
            count += 1
        return count

    def _timed_alignment(
        self,
        previous: list[_TimedToken],
        current: list[_TimedToken],
    ) -> tuple[int, int, int] | None:
        if not previous or not current:
            return None
        if not any(token.start is not None for token in previous):
            return None
        if not any(token.start is not None for token in current):
            return None

        best: tuple[int, int, int] | None = None
        for previous_index, old in enumerate(previous):
            for current_index, new in enumerate(current):
                if not self._same_token(old, new):
                    continue
                if old.start is not None and new.start is not None:
                    if abs(old.start - new.start) > max(0.75, self.timestamp_tolerance_seconds * 3):
                        continue
                count = 0
                while (
                    previous_index + count < len(previous)
                    and current_index + count < len(current)
                    and self._same_token(previous[previous_index + count], current[current_index + count])
                ):
                    count += 1
                candidate = (previous_index, current_index, count)
                if best is None or candidate[2] > best[2]:
                    best = candidate
        return best

    def _remember_confirmed(self, tokens: list[_TimedToken]) -> None:
        if not tokens:
            return
        self._confirmed.extend(tokens)
        self._confirmed_context.extend(tokens)
        self._confirmed_context = self._confirmed_context[-96:]
        ends = [token.end for token in tokens if token.end is not None]
        if ends:
            self._committed_end = max(self._committed_end or ends[-1], max(ends))

    def _new_cue(self) -> None:
        self._cue_id = str(uuid4())
        self._cue_revision = 0
        self._cue_started_at = datetime.now(timezone.utc)
        self._last_emitted_text = ""
        self._draft = None

    def _segment(
        self,
        source: CaptionSegment,
        tokens: list[_TimedToken],
        *,
        is_final: bool,
        boundary_reason: str | None,
        stable_word_count: int,
    ) -> CaptionSegment | None:
        text = self._join(tokens)
        if len(text.split()) < self.minimum_words:
            return None
        self._cue_revision += 1
        status = "sealed" if is_final else "draft"
        operation = "seal" if is_final else "upsert"
        segment = source.model_copy(update={
            "id": self._cue_id,
            "text": text,
            "raw_text": source.raw_text or source.text,
            "is_final": is_final,
            "created_at": self._cue_started_at,
            "source_unit_id": self._cue_id,
            "source_revision": self._cue_revision,
            "source_status": "final" if is_final else "draft",
            "source_started_at": self._cue_started_at,
            "source_ended_at": datetime.now(timezone.utc) if is_final else None,
            "context_group_id": self._context_group_id,
            "source_boundary_reason": boundary_reason,
            "cue_id": self._cue_id,
            "cue_revision": self._cue_revision,
            "cue_status": status,
            "cue_operation": operation,
            "cue_stable_word_count": len(tokens) if is_final else min(len(tokens), max(0, stable_word_count)),
            "cue_mutable_word_count": 0 if is_final else max(0, len(tokens) - stable_word_count),
        })
        self._draft = None if is_final else segment
        self._last_emitted_text = text
        return segment

    def _boundary(self, *, force: bool) -> tuple[int, str] | None:
        if not self._confirmed:
            return None
        if force:
            return len(self._confirmed), "whisper_final"

        limit = min(len(self._confirmed), self.maximum_words)
        for index in range(self.punctuation_minimum_words - 1, limit):
            if re.search(r"[.!?][\"')\]]?$", self._confirmed[index].text):
                return index + 1, "local_agreement_punctuation"
        if len(self._confirmed) >= self.maximum_words:
            return self.maximum_words, "local_agreement_maximum_words"
        timed = [token for token in self._confirmed if token.start is not None and token.end is not None]
        if timed and timed[-1].end - timed[0].start >= self.maximum_duration_seconds:
            return len(self._confirmed), "local_agreement_maximum_duration"
        return None

    def _seal_ready(self, source: CaptionSegment, *, force: bool) -> list[CaptionSegment]:
        updates: list[CaptionSegment] = []
        while True:
            boundary = self._boundary(force=force)
            if boundary is None:
                break
            count, reason = boundary
            cue_tokens = self._confirmed[:count]
            self._confirmed = self._confirmed[count:]
            sealed_ends = [token.end for token in cue_tokens if token.end is not None]
            if sealed_ends:
                self._sealed_audio_end = max(self._sealed_audio_end or sealed_ends[-1], max(sealed_ends))
            final = self._segment(
                source,
                cue_tokens,
                is_final=True,
                boundary_reason=reason,
                stable_word_count=len(cue_tokens),
            )
            if final is not None:
                updates.append(final)
            self._new_cue()
            if force and not self._confirmed:
                break
        return updates

    def ingest(self, source: CaptionSegment, *, now: float | None = None) -> list[CaptionSegment]:
        # ``now`` remains accepted for replay/test compatibility. Publishing no
        # longer waits on a wall-clock revision gate.
        del now
        current = self._strip_committed_overlap(self._tokens_from_segment(source))
        if not current and not source.is_final:
            return []

        if source.is_final:
            # The last recogniser pass is authoritative for the mutable tail.
            self._remember_confirmed(current)
            self._pending = []
        else:
            alignment = self._timed_alignment(self._pending, current)
            if alignment is not None:
                previous_index, current_index, agreement = alignment
                self._remember_confirmed(self._pending[:previous_index])
                self._remember_confirmed(current[current_index:current_index + agreement])
                self._pending = current[current_index + agreement:]
            else:
                agreement = self._agreement_count(self._pending, current)
                if agreement:
                    self._remember_confirmed(current[:agreement])
                    self._pending = current[agreement:]
                else:
                    current_starts = [token.start for token in current if token.start is not None]
                    boundary = min(current_starts) + self.timestamp_tolerance_seconds if current_starts else None
                    fallen = [
                        token
                        for token in self._pending
                        if boundary is not None and token.end is not None and token.end <= boundary
                    ]
                    self._remember_confirmed(fallen)
                    self._pending = current

        updates = self._seal_ready(source, force=source.is_final)
        if source.is_final:
            return updates

        active_tokens = [*self._confirmed, *self._pending]
        active_text = self._join(active_tokens)
        if len(active_text.split()) < self.minimum_words:
            return updates
        if active_text == self._last_emitted_text:
            return updates
        draft = self._segment(
            source,
            active_tokens,
            is_final=False,
            boundary_reason=None,
            stable_word_count=len(self._confirmed),
        )
        if draft is not None:
            updates.append(draft)
        return updates
