import asyncio
import logging
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from fastapi import WebSocket
from app.models import CaptionSegment, CaptionState
from app.i18n import LocalTranslator, MAX_TRANSLATION_LANGUAGES, SOURCE_LANGUAGE, normalise_language
from app.transcript_store import TranscriptStore
from app.text_cleanup import clean_caption_text, collapse_repeated_phrase
from app.source_units import SourceUnitBuilder
from app.translation_scheduler import BoundedFairTranslationScheduler, TranslationJob
from app.metrics import (
    record_caption,
    record_english_publish,
    record_translation,
    record_translation_batch,
    record_translation_skip,
    record_translation_started,
    record_translation_queue_event,
    record_translation_shutdown,
    record_source_unit,
    record_cue_processing,
    record_viewer_counts,
)


logger = logging.getLogger(__name__)


class CaptionHub:
    def __init__(
        self,
        history_limit: int = 1000,
        retention_minutes: int = 120,
        transcript_saving_enabled: bool = True,
        transcript_store: TranscriptStore | None = None,
        translation_queue_capacity_per_language: int = 8,
    ):
        self._clients: dict[WebSocket, str] = {}
        self._viewer_clients: set[WebSocket] = set()
        self._history: list[CaptionSegment] = []
        self._history_draft: CaptionSegment | None = None
        self._current: CaptionSegment | None = None
        self._status: str = "idle"
        self._history_limit = history_limit
        self._retention_minutes = retention_minutes
        self._transcript_saving_enabled = transcript_saving_enabled
        self._sensitive_mode = False
        self._sensitive_resume_ignore_until: datetime | None = None
        self._lock = asyncio.Lock()
        self.source_language = SOURCE_LANGUAGE
        self.translation_enabled = False
        self.translation_provider = "disabled"
        self.translation_allowed_languages: set[str] = {self.source_language}
        self.translation_max_active_languages = 2
        self.translation_language_policy = "automatic"
        self.translation_priority_mode = "most_viewers"
        self.translation_timing_mode = "responsive"
        self.translator = LocalTranslator(self.source_language)
        self._translation_sequence = 0
        self._last_partial_translation_at: dict[str, datetime] = {}
        self._last_partial_translation_text: dict[str, str] = {}
        self._last_partial_translation_stable_words: dict[str, int] = {}
        self._translation_cue_first_seen_monotonic: dict[str, float] = {}
        self._translation_published_cues: set[tuple[str, str]] = set()
        self._translation_latency_seconds: dict[str, float] = {}
        self._translation_latency_at: dict[str, str] = {}
        self._source_unit_builder = SourceUnitBuilder()
        self._translation_scheduler = BoundedFairTranslationScheduler(translation_queue_capacity_per_language)
        self._translation_worker_event: asyncio.Event | None = None
        self._translation_worker_task: asyncio.Task | None = None
        self._translation_idle_event: asyncio.Event | None = None
        self._translation_in_flight: TranslationJob | None = None
        self._transcript_store = transcript_store or TranscriptStore()
        self._session_cache_written = False
        self._start_new_session()

    @property
    def viewer_count(self) -> int:
        return len(self._viewer_clients)

    @property
    def sensitive_mode(self) -> bool:
        return self._sensitive_mode

    @property
    def translation_queue_capacity_per_language(self) -> int:
        return self._translation_scheduler.capacity_per_language

    async def connect(self, websocket: WebSocket, language: str = "en", count_viewer: bool = True) -> None:
        await websocket.accept()
        language = normalise_language(language)
        async with self._lock:
            self._clients[websocket] = language
            if count_viewer:
                self._viewer_clients.add(websocket)
            else:
                self._viewer_clients.discard(websocket)
        await websocket.send_json({"type": "state", "data": self._state_for_language(language).model_dump(mode="json"), "language": language})
        record_viewer_counts(self.language_counts())
        await self._broadcast_viewer_meta()

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(websocket, None)
            self._viewer_clients.discard(websocket)
        record_viewer_counts(self.language_counts())
        await self._broadcast_viewer_meta()

    def set_status(self, status: str) -> None:
        self._status = status

    def configure_translation(
        self,
        *,
        enabled: bool,
        provider: str,
        allowed_languages: list[str],
        max_active_languages: int,
        language_policy: str = "automatic",
        priority_mode: str = "most_viewers",
        timing_mode: str = "responsive",
    ) -> None:
        self.translation_enabled = bool(enabled)
        self.translation_provider = provider or "disabled"
        self.translation_allowed_languages = set(normalise_language(x) for x in allowed_languages)
        self.translation_allowed_languages.add(self.source_language)
        self.translation_max_active_languages = max(1, min(MAX_TRANSLATION_LANGUAGES, int(max_active_languages)))
        self.translation_language_policy = language_policy if language_policy in {"automatic", "restricted"} else "automatic"
        self.translation_priority_mode = priority_mode if priority_mode in {"most_viewers", "pinned_first"} else "most_viewers"
        previous_timing_mode = self.translation_timing_mode
        if timing_mode in {"contextual", "extended"}:
            timing_mode = "responsive"
        self.translation_timing_mode = timing_mode if timing_mode in {"live", "stable", "responsive"} else "responsive"
        if previous_timing_mode != self.translation_timing_mode:
            self._reset_translation_timing_state()
            self._translation_scheduler.clear()
        if not self.translation_enabled or self.translation_provider not in {"small100", "both"}:
            self.translator.unload_models()

    def language_counts(self) -> dict[str, int]:
        return dict(Counter(lang for ws, lang in self._clients.items() if ws in self._viewer_clients))

    def active_translated_languages(self) -> list[str]:
        counts = Counter(lang for ws, lang in self._clients.items() if ws in self._viewer_clients and lang != self.source_language)
        if self.translation_language_policy == "restricted":
            allowed = [lang for lang, _ in counts.most_common() if lang in self.translation_allowed_languages]
        else:
            allowed = [lang for lang, _ in counts.most_common()]
        if self.translation_priority_mode == "pinned_first":
            pinned = [lang for lang in sorted(self.translation_allowed_languages) if lang != self.source_language and counts.get(lang)]
            rest = [lang for lang in allowed if lang not in pinned]
            allowed = pinned + rest
        return allowed[: self.translation_max_active_languages]

    def translation_state(self) -> dict:
        try:
            provider_languages = set(self.translator.supported_languages_for_provider(self.translation_provider if self.translation_enabled else "disabled"))
        except Exception as exc:
            provider_languages = {self.source_language}
            provider_error = str(exc)
        else:
            provider_error = ""
        provider_languages.add(self.source_language)
        if self.translation_enabled and self.translation_language_policy == "restricted":
            available_languages = sorted((self.translation_allowed_languages | {self.source_language}) & provider_languages)
            requestable_languages = sorted(provider_languages - self.translation_allowed_languages - {self.source_language})
        else:
            available_languages = sorted(provider_languages)
            requestable_languages = []
        try:
            provider_status = self.translator.provider_status(self.translation_provider)
        except Exception as exc:
            provider_status = {"provider": self.translation_provider, "ready": False, "message": f"Translation provider status failed: {exc}"}
        if provider_error and provider_status.get("ready"):
            provider_status = {**provider_status, "ready": False, "message": f"Translation language list failed: {provider_error}"}
        try:
            resources = self.translator.translation_resources()
        except Exception as exc:
            resources = {"error": str(exc)}
        return {
            "enabled": self.translation_enabled,
            "provider": self.translation_provider,
            "provider_status": provider_status,
            "allowed_languages": sorted(self.translation_allowed_languages),
            "max_active_languages": self.translation_max_active_languages,
            "language_policy": self.translation_language_policy,
            "priority_mode": self.translation_priority_mode,
            "timing_mode": self.translation_timing_mode,
            "viewer_languages": self.language_counts(),
            "active_translated_languages": self.active_translated_languages(),
            "translation_latency_seconds": dict(self._translation_latency_seconds),
            "translation_latency_at": dict(self._translation_latency_at),
            "scheduler": self._translation_scheduler.snapshot(),
            "resources": resources,
            "available_languages": available_languages,
            "requestable_languages": requestable_languages,
        }

    def configure_retention(self, retention_minutes: int, transcript_saving_enabled: bool) -> None:
        self._retention_minutes = max(0, int(retention_minutes))
        self._transcript_saving_enabled = bool(transcript_saving_enabled)
        if not self._transcript_saving_enabled:
            self._history.clear()
            self._history_draft = None
            self._transcript_store.clear()
            return
        self._purge_old_history()

    def retention_state(self) -> dict:
        return {
            "transcript_retention_minutes": self._retention_minutes,
            "transcript_saving_enabled": self._transcript_saving_enabled,
        }

    async def broadcast_retention_state(self) -> None:
        await self._broadcast({"type": "retention", "data": self.retention_state()})

    def _purge_old_history(self, *, persist: bool = True) -> None:
        if self._retention_minutes <= 0 or not self._transcript_saving_enabled:
            self._history.clear()
            self._history_draft = None
            self._transcript_store.clear()
            return
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._retention_minutes)
        self._history = [seg for seg in self._history if seg.created_at >= cutoff]
        if self._history_draft and self._history_draft.created_at < cutoff:
            self._history_draft = None
        if self._history_draft:
            self._history = self._history[-max(0, self._history_limit - 1):]
        else:
            self._history = self._history[-self._history_limit:]
        if persist:
            self._persist_history()

    def _display_history(self) -> list[CaptionSegment]:
        history = list(self._history)
        if self._history_draft is not None:
            history.append(self._history_draft)
        return history[-self._history_limit:]

    def _persist_history(self) -> None:
        try:
            if not self._transcript_saving_enabled or self._retention_minutes <= 0:
                self._transcript_store.clear()
                self._session_cache_written = False
                return
            display_history = self._display_history()
            if not display_history and not self._session_cache_written:
                return
            self._transcript_store.save_segments(
                display_history,
                retention_minutes=self._retention_minutes,
                history_limit=self._history_limit,
            )
            self._session_cache_written = bool(display_history)
        except Exception as exc:
            logger.warning("Transcript history cache could not be saved; live captions will continue: %s", exc)

    def _start_new_session(self) -> None:
        self._history.clear()
        self._history_draft = None
        self._session_cache_written = False
        if not self._transcript_saving_enabled or self._retention_minutes <= 0:
            self._transcript_store.clear()
            return
        self._transcript_store.prune_expired_cache(
            fallback_retention_minutes=self._retention_minutes,
            history_limit=self._history_limit,
        )

    def _translate_segment_for_language(self, segment: CaptionSegment, language: str) -> CaptionSegment:
        language = normalise_language(language)
        if language == "en":
            return segment
        if self.translation_language_policy == "restricted" and language not in self.translation_allowed_languages:
            return segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text})
        if language not in self.active_translated_languages():
            return segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text})
        cached = self.translator.cached_result(segment.text, language, provider=self.translation_provider)
        if cached and cached.applied:
            return segment.model_copy(update={"text": cached.text, "raw_text": segment.text})
        return segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text})

    def _state_for_language(self, language: str) -> CaptionState:
        self._purge_old_history()
        language = normalise_language(language)
        return CaptionState(
            status="sensitive" if self._sensitive_mode else self._status,
            current=self._translate_segment_for_language(self._current, language) if self._current else None,
            history=[self._translate_segment_for_language(seg, language) for seg in self._display_history()],
            viewers=self.viewer_count,
            sensitive_mode=self._sensitive_mode,
            transcript_saving_enabled=self._transcript_saving_enabled,
            transcript_retention_minutes=self._retention_minutes,
        )

    def state(self) -> CaptionState:
        return self._state_for_language("en")

    @staticmethod
    def _normalise_for_duplicate(text: str) -> str:
        return " ".join(text.lower().replace("…", " ").replace(".", " ").replace(",", " ").replace(";", " ").replace(":", " ").split())

    def _looks_duplicate_final(self, text: str) -> bool:
        if not text.strip() or not self._display_history():
            return False
        current = self._normalise_for_duplicate(text)
        for previous in self._display_history()[-3:]:
            prev = self._normalise_for_duplicate(previous.text)
            if current == prev or (current and current in prev):
                return True
        return False

    def final_segments(self) -> list[CaptionSegment]:
        self._purge_old_history()
        return list(self._display_history())

    def sealed_audio_end_monotonic(self) -> float | None:
        return self._source_unit_builder.sealed_audio_end_monotonic

    async def publish(self, segment: CaptionSegment) -> None:
        if self._sensitive_mode or self._inside_sensitive_drain_window():
            return
        text = clean_caption_text(collapse_repeated_phrase(segment.text))
        if not text:
            return
        if text != segment.text:
            segment = segment.model_copy(update={"text": text, "raw_text": segment.raw_text or segment.text})
        source_ready_monotonic = segment.source_ready_monotonic or time.monotonic()
        if segment.source_ready_monotonic is None:
            segment = segment.model_copy(update={"source_ready_monotonic": source_ready_monotonic})
        cue_processing_started = time.monotonic()
        source_units = self._source_unit_builder.ingest(segment, now=source_ready_monotonic)
        record_cue_processing(time.monotonic() - cue_processing_started)
        self._current = source_units[-1] if source_units else (self._source_unit_builder.current_draft or segment)
        transcript_updates = self._record_cue_transcript(source_units)
        record_caption(is_final=segment.is_final, transcript_commits=len(transcript_updates))
        if segment.is_final and not source_units and self._looks_duplicate_final(segment.text) and not transcript_updates:
            return
        for source_unit in source_units:
            cue_lifetime = None
            if source_unit.is_final and source_unit.source_started_at and source_unit.source_ended_at:
                cue_lifetime = max(
                    0.0,
                    (source_unit.source_ended_at - source_unit.source_started_at).total_seconds(),
                )
            record_source_unit(
                is_final=source_unit.is_final,
                revision=int(source_unit.source_revision or 1),
                boundary_reason=source_unit.source_boundary_reason,
                cue_lifetime_seconds=cue_lifetime,
                stable_word_count=int(source_unit.cue_stable_word_count or 0),
                mutable_word_count=int(source_unit.cue_mutable_word_count or 0),
            )
        await self._broadcast_caption(
            segment,
            transcript_updates,
            source_units=source_units,
            source_ready_monotonic=source_ready_monotonic,
        )
        if transcript_updates:
            await asyncio.to_thread(self._persist_history)

    def _inside_sensitive_drain_window(self) -> bool:
        if self._sensitive_resume_ignore_until is None:
            return False
        if datetime.now(timezone.utc) < self._sensitive_resume_ignore_until:
            return True
        self._sensitive_resume_ignore_until = None
        return False

    def _discard_sensitive_transcript_draft(self) -> None:
        self._history_draft = None

    def _reset_translation_timing_state(self) -> None:
        self._last_partial_translation_at.clear()
        self._last_partial_translation_text.clear()
        self._last_partial_translation_stable_words.clear()
        self._translation_cue_first_seen_monotonic.clear()
        self._translation_published_cues.clear()

    async def set_sensitive_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled:
            self._sensitive_mode = True
            self._sensitive_resume_ignore_until = None
            self._discard_sensitive_transcript_draft()
            self._source_unit_builder.reset()
            self._reset_translation_timing_state()
            self._translation_scheduler.clear()
            self._current = CaptionSegment(
                text="Captions are paused for a private or sensitive moment.",
                raw_text="sensitive mode",
                is_final=False,
            )
            await self._broadcast({
                "type": "sensitive",
                "enabled": True,
                "message": self._current.text,
                "message_key": "sensitive_paused_message",
            })
        else:
            self._sensitive_mode = False
            self._discard_sensitive_transcript_draft()
            self._source_unit_builder.reset()
            self._reset_translation_timing_state()
            self._translation_scheduler.clear()
            self._sensitive_resume_ignore_until = datetime.now(timezone.utc) + timedelta(seconds=3)
            self._current = CaptionSegment(text="Captions have resumed.", raw_text="resumed", is_final=False)
            await self._broadcast({
                "type": "sensitive",
                "enabled": False,
                "message": self._current.text,
                "message_key": "sensitive_resumed_message",
            })

    async def clear(self) -> None:
        self._current = None
        self._history.clear()
        self._history_draft = None
        self._source_unit_builder.reset()
        self._reset_translation_timing_state()
        self._translation_scheduler.clear()
        self._transcript_store.clear()
        await self._broadcast({"type": "clear"})

    @staticmethod
    def _word_count(text: str) -> int:
        return len(str(text or "").split())

    @classmethod
    def _normalise_words(cls, text: str) -> list[str]:
        return cls._normalise_for_duplicate(text).split()

    @classmethod
    def _tail_head_overlap(cls, previous: str, current: str, max_words: int = 16) -> int:
        previous_words = cls._normalise_words(previous)
        current_words = cls._normalise_words(current)
        max_overlap = min(len(previous_words), len(current_words), max_words)
        for size in range(max_overlap, 0, -1):
            if previous_words[-size:] == current_words[:size]:
                return size
        return 0

    @classmethod
    def _texts_overlap(cls, previous: str, current: str) -> bool:
        previous_norm = cls._normalise_for_duplicate(previous)
        current_norm = cls._normalise_for_duplicate(current)
        if not previous_norm or not current_norm:
            return False
        return (
            previous_norm == current_norm
            or previous_norm in current_norm
            or current_norm in previous_norm
            or cls._tail_head_overlap(previous, current) >= 2
        )

    @classmethod
    def _dedupe_against_previous(cls, text: str, previous: str) -> str:
        text = " ".join(str(text or "").split()).strip()
        previous = " ".join(str(previous or "").split()).strip()
        if not text or not previous:
            return text
        current = cls._normalise_for_duplicate(text)
        committed = cls._normalise_for_duplicate(previous)
        if current == committed or (current and current in committed):
            return ""
        if current.startswith(committed):
            return " ".join(text.split()[len(previous.split()):]).strip(" ,.;:-")
        previous_words = previous.split()
        text_words = text.split()
        max_overlap = min(len(previous_words), len(text_words), 16)
        for size in range(max_overlap, 0, -1):
            prev_tail = [word.lower().strip(".,;:!?") for word in previous_words[-size:]]
            text_head = [word.lower().strip(".,;:!?") for word in text_words[:size]]
            if prev_tail == text_head:
                return " ".join(text_words[size:]).strip(" ,.;:-")
        return text

    def _recent_history_text(self) -> str:
        return " ".join(seg.text for seg in self._history[-12:])

    def _copy_segment(self, source: CaptionSegment, *, text: str, is_final: bool, existing: CaptionSegment | None = None) -> CaptionSegment:
        return source.model_copy(
            update={
                "id": existing.id if existing else source.id,
                "text": text,
                "raw_text": source.raw_text or source.text,
                "is_final": is_final,
                "created_at": existing.created_at if existing else source.created_at,
            }
        )

    def _commit_draft(self) -> CaptionSegment | None:
        if self._history_draft is None:
            return None
        committed = self._history_draft.model_copy(update={"is_final": True})
        self._history.append(committed)
        self._history_draft = None
        return committed

    def _start_draft(self, source: CaptionSegment, text: str) -> CaptionSegment | None:
        text = clean_caption_text(collapse_repeated_phrase(text))
        if self._word_count(text) < 2:
            return None
        self._history_draft = self._copy_segment(source, text=text, is_final=False)
        return self._history_draft

    def _record_partial_transcript(self, segment: CaptionSegment) -> list[CaptionSegment]:
        text = clean_caption_text(collapse_repeated_phrase(segment.text))
        if self._word_count(text) < 2:
            return []

        suffix = clean_caption_text(collapse_repeated_phrase(self._dedupe_against_previous(text, self._recent_history_text())))
        if self._word_count(suffix) < 2:
            return []

        updates: list[CaptionSegment] = []
        draft = self._history_draft
        if draft is None:
            started = self._start_draft(segment, suffix)
            if started:
                updates.append(started)
            return updates

        draft_norm = self._normalise_for_duplicate(draft.text)
        suffix_norm = self._normalise_for_duplicate(suffix)
        if suffix_norm.startswith(draft_norm) or draft_norm in suffix_norm:
            if len(suffix) > len(draft.text):
                self._history_draft = self._copy_segment(segment, text=suffix, is_final=False, existing=draft)
                updates.append(self._history_draft)
            return updates

        advanced = clean_caption_text(collapse_repeated_phrase(self._dedupe_against_previous(suffix, draft.text)))
        if self._word_count(advanced) >= 2 and self._texts_overlap(draft.text, suffix):
            committed = self._commit_draft()
            if committed:
                updates.append(committed)
            started = self._start_draft(segment, advanced)
            if started:
                updates.append(started)
            return updates

        committed = self._commit_draft()
        if committed:
            updates.append(committed)
        started = self._start_draft(segment, suffix)
        if started:
            updates.append(started)
        return updates

    def _record_final_transcript(self, segment: CaptionSegment) -> list[CaptionSegment]:
        text = clean_caption_text(collapse_repeated_phrase(segment.text))
        if self._word_count(text) < 2:
            return []

        updates: list[CaptionSegment] = []
        suffix = clean_caption_text(collapse_repeated_phrase(self._dedupe_against_previous(text, self._recent_history_text())))
        draft = self._history_draft
        if draft is not None:
            if not suffix or self._texts_overlap(draft.text, suffix):
                best_text = clean_caption_text(collapse_repeated_phrase(suffix if self._word_count(suffix) >= self._word_count(draft.text) else draft.text))
                if not best_text:
                    self._history_draft = None
                    return updates
                self._history_draft = self._copy_segment(segment, text=best_text, is_final=False, existing=draft)
                committed = self._commit_draft()
                if committed:
                    updates.append(committed)
                return updates
            committed = self._commit_draft()
            if committed:
                updates.append(committed)

        suffix = clean_caption_text(collapse_repeated_phrase(self._dedupe_against_previous(text, self._recent_history_text())))
        if self._word_count(suffix) >= 2 and not self._looks_duplicate_final(suffix):
            committed = self._copy_segment(segment, text=suffix, is_final=True)
            self._history.append(committed)
            updates.append(committed)
        return updates

    def _record_transcript_segment(self, segment: CaptionSegment) -> list[CaptionSegment]:
        if not self._transcript_saving_enabled or self._retention_minutes <= 0 or not segment.text.strip():
            return []
        updates = self._record_final_transcript(segment) if segment.is_final else self._record_partial_transcript(segment)
        if updates:
            self._purge_old_history(persist=False)
        return updates

    def _record_cue_transcript(self, cue_updates: list[CaptionSegment]) -> list[CaptionSegment]:
        """Mirror authoritative cue revisions into the optional transcript."""
        if not self._transcript_saving_enabled or self._retention_minutes <= 0:
            return []
        updates: list[CaptionSegment] = []
        for cue in cue_updates:
            cue_id = cue.cue_id or cue.source_unit_id or cue.id
            if cue.is_final or cue.cue_status == "sealed":
                committed = cue.model_copy(update={"id": cue_id, "is_final": True})
                existing_index = next(
                    (
                        index
                        for index, item in enumerate(self._history)
                        if (item.cue_id or item.source_unit_id or item.id) == cue_id
                    ),
                    None,
                )
                if existing_index is None:
                    self._history.append(committed)
                else:
                    self._history[existing_index] = committed
                if self._history_draft is not None:
                    draft_id = self._history_draft.cue_id or self._history_draft.source_unit_id or self._history_draft.id
                    if draft_id == cue_id:
                        self._history_draft = None
                updates.append(committed)
            else:
                self._history_draft = cue.model_copy(update={"id": cue_id, "is_final": False})
                updates.append(self._history_draft)
        if updates:
            self._purge_old_history(persist=False)
        return updates

    def _source_language_segment(self, segment: CaptionSegment, *, as_draft: bool = False) -> CaptionSegment:
        update = {"text": segment.text, "raw_text": segment.raw_text or segment.text}
        if as_draft and segment.is_final:
            update["is_final"] = False
        return segment.model_copy(update=update)

    @staticmethod
    def _translated_segment(segment: CaptionSegment, text: str) -> CaptionSegment:
        translated_words = str(text or "").split()
        if segment.is_final:
            stable_words = len(translated_words)
        else:
            # The source prefix is stable, but translation word order can still
            # change as that prefix grows. Keep a small target tail explicitly
            # mutable so the client only preserves wording that survived a
            # previous retranslation.
            stable_words = max(0, len(translated_words) - 2)
        return segment.model_copy(update={
            "text": text,
            "raw_text": segment.text,
            "cue_stable_word_count": stable_words,
            "cue_mutable_word_count": max(0, len(translated_words) - stable_words),
        })

    def _should_translate_partial(self, language: str, segment: CaptionSegment) -> bool:
        text = segment.text.strip()
        if segment.is_final:
            self._last_partial_translation_text.pop(language, None)
            self._last_partial_translation_at.pop(language, None)
            self._last_partial_translation_stable_words.pop(language, None)
            return bool(text)
        word_count = self._word_count(text)
        if word_count < 3:
            return False

        now = datetime.now(timezone.utc)
        previous = self._last_partial_translation_at.get(language)
        if self.translation_timing_mode == "responsive":
            minimum_gap = 1.5
            minimum_words = 3
        elif self.translation_timing_mode == "stable":
            minimum_gap = 2.8
            minimum_words = 5
        else:
            minimum_gap = 2.0
            minimum_words = 3
        if word_count < minimum_words:
            return False
        previous_text = self._last_partial_translation_text.get(language)
        if previous_text == text:
            return False
        if previous and (now - previous).total_seconds() < minimum_gap:
            return False
        if self.translation_timing_mode == "responsive":
            previous_words = self._last_partial_translation_stable_words.get(language, 0)
            # Do not spend CPU translating every recognition pass. Three new
            # stable English words trigger a revision; a corrected prefix may
            # trigger one sooner because it no longer extends the old wording.
            if previous_text and text.startswith(f"{previous_text} ") and word_count - previous_words < 3:
                return False
            self._last_partial_translation_stable_words[language] = word_count
        self._last_partial_translation_at[language] = now
        self._last_partial_translation_text[language] = text
        return True

    def _translation_units_for_timing(
        self,
        source_units: list[CaptionSegment],
        *,
        force_context_flush: bool = False,
    ) -> list[CaptionSegment]:
        del force_context_flush  # Retained for Stop-call compatibility.
        now = time.monotonic()
        for unit in source_units:
            cue_id = unit.cue_id or unit.source_unit_id or unit.id
            self._translation_cue_first_seen_monotonic.setdefault(
                cue_id,
                unit.source_ready_monotonic or now,
            )
        if self.translation_timing_mode != "responsive":
            return source_units

        ready: list[CaptionSegment] = []
        for unit in source_units:
            if unit.is_final:
                ready.append(unit)
                continue
            words = unit.text.split()
            stable_words = min(len(words), max(0, int(unit.cue_stable_word_count or 0)))
            if stable_words < 3:
                continue
            stable_text = " ".join(words[:stable_words]).strip()
            ready.append(unit.model_copy(update={
                "text": stable_text,
                "raw_text": stable_text,
                "cue_stable_word_count": stable_words,
                "cue_mutable_word_count": 0,
                "source_boundary_reason": "responsive_stable_prefix",
            }))
        return ready

    def _ensure_translation_worker(self) -> None:
        if self._translation_worker_event is None:
            self._translation_worker_event = asyncio.Event()
        if self._translation_idle_event is None:
            self._translation_idle_event = asyncio.Event()
            if not self._translation_scheduler.has_jobs() and self._translation_in_flight is None:
                self._translation_idle_event.set()
        if self._translation_worker_task is None or self._translation_worker_task.done():
            self._translation_worker_task = asyncio.create_task(self._translation_worker_loop())

    def _queue_translation_batch(
        self,
        segment: CaptionSegment,
        languages: list[str],
        *,
        source_ready_monotonic: float | None = None,
    ) -> None:
        languages = list(dict.fromkeys(normalise_language(language) for language in languages if normalise_language(language) != "en"))
        if not languages:
            return
        record_translation_batch(
            languages=languages,
            is_final=segment.is_final,
            replaced_pending=False,
            replaced_final_pending=False,
            replaced_languages=[],
        )
        self._translation_sequence += 1
        sequence = self._translation_sequence
        cue_id = segment.cue_id or segment.source_unit_id or segment.id
        cue_first_seen = self._translation_cue_first_seen_monotonic.setdefault(
            cue_id,
            segment.source_ready_monotonic or source_ready_monotonic or time.monotonic(),
        )
        for language in languages:
            job = TranslationJob(
                language=language,
                segment=segment,
                sequence=sequence,
                enqueued_monotonic=time.monotonic(),
                source_ready_monotonic=source_ready_monotonic or time.monotonic(),
                generation=self._translation_scheduler.generation,
                cue_first_seen_monotonic=cue_first_seen,
            )
            result = self._translation_scheduler.enqueue(job)
            record_translation_queue_event("queue_depth", language=language, depth=result.depth)
            for event in result.events:
                record_translation_queue_event(event, language=language, depth=result.depth)
        self._ensure_translation_worker()
        if self._translation_idle_event is not None:
            self._translation_idle_event.clear()
        if self._translation_worker_event is not None:
            self._translation_worker_event.set()
        if segment.is_final:
            self._translation_cue_first_seen_monotonic.pop(cue_id, None)

    async def _translation_worker_loop(self) -> None:
        while True:
            if self._translation_worker_event is None:
                return
            await self._translation_worker_event.wait()
            self._translation_worker_event.clear()
            while self._translation_scheduler.has_jobs():
                job = self._translation_scheduler.pop_next()
                for language in self._translation_scheduler.take_recovery_events():
                    record_translation_queue_event("recovered", language=language)
                if job is None:
                    break
                if not self._translation_scheduler.is_current(job):
                    record_translation_skip("stale", language=job.language, is_final=job.is_final)
                    continue
                self._translation_in_flight = job
                try:
                    await self._broadcast_translated_caption(job)
                finally:
                    self._translation_in_flight = None
            if not self._translation_scheduler.has_jobs() and self._translation_in_flight is None:
                if self._translation_idle_event is not None:
                    self._translation_idle_event.set()

    async def drain_translation_work(self, timeout_seconds: float = 2.0) -> dict:
        """Bound Stop latency while making every outstanding job explicit in metrics."""
        timeout_seconds = max(0.0, float(timeout_seconds))
        self._translation_units_for_timing([], force_context_flush=True)
        pending_at_stop = self._translation_scheduler.pending_counts()
        in_flight_at_stop = (
            {self._translation_in_flight.language: 1}
            if self._translation_in_flight is not None
            else {}
        )
        initial_outstanding = sum(pending_at_stop.values()) + sum(in_flight_at_stop.values())
        timed_out = False

        if initial_outstanding:
            self._ensure_translation_worker()
            if self._translation_worker_event is not None and self._translation_scheduler.has_jobs():
                self._translation_worker_event.set()
            if self._translation_idle_event is not None:
                self._translation_idle_event.clear()
                try:
                    await asyncio.wait_for(self._translation_idle_event.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    timed_out = True

        remaining = self._translation_scheduler.pending_counts()
        if self._translation_in_flight is not None:
            remaining[self._translation_in_flight.language] = remaining.get(self._translation_in_flight.language, 0) + 1
        if remaining:
            timed_out = True

        if timed_out:
            task = self._translation_worker_task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._translation_scheduler.clear()
            self._translation_worker_task = None
            self._translation_worker_event = None
            self._translation_idle_event = None
            self._translation_in_flight = None

        record_translation_shutdown(
            drain_timeout_seconds=timeout_seconds,
            pending_at_stop=pending_at_stop,
            in_flight_at_stop=in_flight_at_stop,
            cancelled_at_stop=remaining,
            timed_out=timed_out,
        )
        return {
            "pending_at_stop": pending_at_stop,
            "in_flight_at_stop": in_flight_at_stop,
            "cancelled_at_stop": remaining,
            "timed_out": timed_out,
        }

    def _caption_payload(
        self,
        segment: CaptionSegment,
        *,
        language: str,
        source_text: str,
        transcript_updates: list[CaptionSegment] | None = None,
        live_source_updates: list[CaptionSegment] | None = None,
        translation_applied: bool = False,
        translation_warning: str | None = None,
    ) -> dict:
        return {
            "type": "caption",
            "data": segment.model_dump(mode="json"),
            "transcript_updates": [
                update.model_dump(mode="json")
                for update in (transcript_updates or [])
            ],
            "live_source_updates": [
                update.model_dump(mode="json")
                for update in (live_source_updates or [])
            ],
            "source_text": source_text,
            "language": language,
            "translation_applied": translation_applied,
            "translation_warning": translation_warning,
            **self.retention_state(),
            "viewers": self.viewer_count,
        }

    def _translation_status_payload(self, *, language: str, warning: str) -> dict:
        return {
            "type": "translation_status",
            "language": language,
            "translation_warning": warning,
            **self.retention_state(),
            "viewers": self.viewer_count,
        }

    async def _send_caption_payload(self, clients: list[WebSocket], payload: dict) -> list[WebSocket]:
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        return dead

    async def _remove_dead_clients(self, dead: list[WebSocket]) -> None:
        if not dead:
            return
        async with self._lock:
            for ws in dead:
                self._clients.pop(ws, None)
        await self._broadcast_viewer_meta()

    async def _broadcast_translated_caption(
        self,
        job: TranslationJob,
    ) -> None:
        segment = job.segment
        language = job.language
        async with self._lock:
            clients = [ws for ws, lang in self._clients.items() if lang == language]
        if not clients or not self._translation_scheduler.is_current(job):
            record_translation_skip(
                "no_viewers" if not clients else "stale",
                language=language,
                is_final=segment.is_final,
            )
            return
        started_at = time.monotonic()
        record_translation_started(language, max(0.0, started_at - job.enqueued_monotonic))
        try:
            result = await self.translator.translate_async(
                segment.text,
                language,
                enabled=self.translation_enabled,
                provider=self.translation_provider,
            )
            elapsed = max(0.0, time.monotonic() - started_at)
            self._translation_latency_seconds[language] = elapsed
            self._translation_latency_at[language] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            elapsed = max(0.0, time.monotonic() - started_at)
            self._translation_latency_seconds[language] = elapsed
            self._translation_latency_at[language] = datetime.now(timezone.utc).isoformat()
            result = None
            warning = f"Translation failed for {language}: {exc}"
        if result is None:
            display_segment = self._source_language_segment(segment)
            applied = False
        else:
            warning = result.warning
            applied = result.applied
            display_segment = self._translated_segment(segment, result.text) if applied else self._source_language_segment(segment)
        metric_outcome = "failed" if result is None else ("applied" if applied else result.outcome)
        if not applied and not warning:
            warning = "Translation is experimental or unavailable. Showing source captions."
        if not self._translation_scheduler.is_current(job):
            record_translation(
                language,
                elapsed,
                applied=applied,
                failed=result is None or getattr(result, "outcome", None) == "failed",
                fallback=not applied,
                outcome=metric_outcome,
                requested_provider=self.translation_provider if result is None else result.requested_provider,
                actual_provider=None if result is None else result.actual_provider,
                fallback_chain=() if result is None else result.fallback_chain,
                retry_count=0 if result is None else result.retry_count,
                published=False,
                not_published_reason="stale_after_compute",
            )
            return

        async with self._lock:
            clients = [ws for ws, lang in self._clients.items() if lang == language]
        if not clients:
            record_translation(
                language,
                elapsed,
                applied=applied,
                failed=result is None or getattr(result, "outcome", None) == "failed",
                fallback=not applied,
                outcome=metric_outcome,
                requested_provider=self.translation_provider if result is None else result.requested_provider,
                actual_provider=None if result is None else result.actual_provider,
                fallback_chain=() if result is None else result.fallback_chain,
                retry_count=0 if result is None else result.retry_count,
                published=False,
                not_published_reason="no_language_viewers_after_compute",
            )
            return
        if not applied and not segment.is_final:
            payload = self._translation_status_payload(language=language, warning=warning)
            await self._remove_dead_clients(await self._send_caption_payload(clients, payload))
            record_translation(
                language,
                elapsed,
                applied=False,
                failed=result is None or getattr(result, "outcome", None) == "failed",
                fallback=True,
                outcome=metric_outcome,
                requested_provider=self.translation_provider if result is None else result.requested_provider,
                actual_provider=None if result is None else result.actual_provider,
                fallback_chain=() if result is None else result.fallback_chain,
                retry_count=0 if result is None else result.retry_count,
                source_to_publish_seconds=max(0.0, time.monotonic() - job.source_ready_monotonic),
                published=False,
                not_published_reason="unspecified",
            )
            return
        payload = self._caption_payload(
            display_segment,
            language=language,
            source_text=segment.text,
            translation_applied=applied,
            translation_warning=warning,
        )
        await self._remove_dead_clients(await self._send_caption_payload(clients, payload))
        cue_id = segment.cue_id or segment.source_unit_id or segment.id
        published_key = (language, cue_id)
        first_cue_publish_seconds = None
        if published_key not in self._translation_published_cues:
            self._translation_published_cues.add(published_key)
            first_cue_publish_seconds = max(0.0, time.monotonic() - job.cue_first_seen_monotonic)
        record_translation(
            language,
            elapsed,
            applied=applied,
            failed=result is None or getattr(result, "outcome", None) == "failed",
            fallback=not applied,
            outcome=metric_outcome,
            requested_provider=self.translation_provider if result is None else result.requested_provider,
            actual_provider=None if result is None else result.actual_provider,
            fallback_chain=() if result is None else result.fallback_chain,
            retry_count=0 if result is None else result.retry_count,
            source_to_publish_seconds=max(0.0, time.monotonic() - job.source_ready_monotonic),
            cue_first_publish_seconds=first_cue_publish_seconds,
            is_final=segment.is_final,
        )
        if segment.is_final:
            self._translation_published_cues.discard(published_key)

    async def _broadcast_caption(
        self,
        segment: CaptionSegment,
        transcript_updates: list[CaptionSegment] | None = None,
        *,
        source_units: list[CaptionSegment] | None = None,
        source_ready_monotonic: float,
    ) -> None:
        async with self._lock:
            clients = list(self._clients.items())
        if not clients:
            return

        transcript_updates = transcript_updates or []
        dead: list[WebSocket] = []
        active_translated = set(self.active_translated_languages())
        clients_by_language: dict[str, list[WebSocket]] = {}
        for ws, lang in clients:
            clients_by_language.setdefault(lang, []).append(ws)
        languages_to_translate: list[str] = []

        for lang, sockets in clients_by_language.items():
            if lang == "en":
                payload = self._caption_payload(
                    segment,
                    language=lang,
                    source_text=segment.text,
                    transcript_updates=transcript_updates,
                    live_source_updates=source_units,
                )
                dead.extend(await self._send_caption_payload(sockets, payload))
                sent_at = time.monotonic()
                capture_delay = None
                if segment.capture_started_monotonic is not None:
                    capture_delay = max(0.0, sent_at - segment.capture_started_monotonic)
                record_english_publish(
                    max(0.0, sent_at - source_ready_monotonic),
                    estimated_capture_to_publish_seconds=capture_delay,
                )
                continue

            warning = None
            should_translate = False
            if self.translation_language_policy == "restricted" and lang not in self.translation_allowed_languages:
                warning = "This language is not enabled by the operator. Showing source captions."
            elif lang not in active_translated:
                warning = "Translation capacity is full right now, so captions are shown in the source language. Please speak to the welcome team if you need help."
            else:
                should_translate = True
                if self.translation_timing_mode == "responsive" and not segment.is_final:
                    warning = "Translating the growing stable English caption for responsive context. The newest wording may refine in place."
                elif self.translation_timing_mode == "stable" and not segment.is_final:
                    warning = "Preparing a steadier translation from corrected English. New translated text updates during speech after the wording settles."
                else:
                    warning = "Translating captions locally. New translated text will appear as soon as it is ready."

            if should_translate:
                payload = self._translation_status_payload(language=lang, warning=warning)
                dead.extend(await self._send_caption_payload(sockets, payload))
            else:
                source_segment = self._source_language_segment(segment)
                payload = self._caption_payload(
                    source_segment,
                    language=lang,
                    source_text=segment.text,
                    translation_warning=warning,
                )
                dead.extend(await self._send_caption_payload(sockets, payload))

            if should_translate:
                languages_to_translate.append(lang)

        await self._remove_dead_clients(dead)
        if not languages_to_translate:
            return
        translation_units = self._translation_units_for_timing(source_units or [])
        for source_unit in translation_units:
            unit_languages = [
                language
                for language in languages_to_translate
                if self._should_translate_partial(language, source_unit)
            ]
            if unit_languages:
                self._queue_translation_batch(
                    source_unit,
                    unit_languages,
                    source_ready_monotonic=source_ready_monotonic,
                )

    async def _broadcast_viewer_meta(self) -> None:
        await self._broadcast({"type": "viewer_meta", "data": self.translation_state(), "viewers": self.viewer_count})

    async def _broadcast(self, payload: dict) -> None:
        async with self._lock:
            clients = list(self._clients.keys())
        if not clients:
            return
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.pop(ws, None)
