import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from fastapi import WebSocket
from app.models import CaptionSegment, CaptionState
from app.i18n import LocalTranslator, normalise_language
from app.transcript_store import TranscriptStore


class CaptionHub:
    def __init__(
        self,
        history_limit: int = 1000,
        retention_minutes: int = 120,
        transcript_saving_enabled: bool = True,
        transcript_store: TranscriptStore | None = None,
    ):
        self._clients: dict[WebSocket, str] = {}
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
        self.translation_enabled = False
        self.translation_provider = "disabled"
        self.translation_allowed_languages: set[str] = {"en"}
        self.translation_max_active_languages = 1
        self.translator = LocalTranslator("en")
        self._transcript_store = transcript_store or TranscriptStore()
        self._session_cache_written = False
        self._start_new_session()

    @property
    def viewer_count(self) -> int:
        return len(self._clients)

    @property
    def sensitive_mode(self) -> bool:
        return self._sensitive_mode

    async def connect(self, websocket: WebSocket, language: str = "en") -> None:
        await websocket.accept()
        language = normalise_language(language)
        async with self._lock:
            self._clients[websocket] = language
        await websocket.send_json({"type": "state", "data": self._state_for_language(language).model_dump(mode="json"), "language": language})
        await self._broadcast_viewer_meta()

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(websocket, None)
        await self._broadcast_viewer_meta()

    def set_status(self, status: str) -> None:
        self._status = status

    def configure_translation(self, *, enabled: bool, provider: str, allowed_languages: list[str], max_active_languages: int) -> None:
        self.translation_enabled = bool(enabled)
        self.translation_provider = provider or "disabled"
        self.translation_allowed_languages = set(normalise_language(x) for x in allowed_languages)
        self.translation_allowed_languages.add("en")
        self.translation_max_active_languages = max(1, min(8, int(max_active_languages)))

    def language_counts(self) -> dict[str, int]:
        return dict(Counter(self._clients.values()))

    def active_translated_languages(self) -> list[str]:
        counts = Counter(lang for lang in self._clients.values() if lang != "en")
        allowed = [lang for lang, _ in counts.most_common() if lang in self.translation_allowed_languages]
        return allowed[: self.translation_max_active_languages]

    def translation_state(self) -> dict:
        return {
            "enabled": self.translation_enabled,
            "provider": self.translation_provider,
            "provider_status": self.translator.provider_status(self.translation_provider),
            "allowed_languages": sorted(self.translation_allowed_languages),
            "max_active_languages": self.translation_max_active_languages,
            "viewer_languages": self.language_counts(),
            "active_translated_languages": self.active_translated_languages(),
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
        if language not in self.translation_allowed_languages:
            return segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text})
        if language not in self.active_translated_languages():
            return segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text})
        result = self.translator.translate(
            segment.text,
            language,
            enabled=self.translation_enabled,
            provider=self.translation_provider,
        )
        return segment.model_copy(update={"text": result.text, "raw_text": segment.text})

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

    async def publish(self, segment: CaptionSegment) -> None:
        if self._sensitive_mode or self._inside_sensitive_drain_window():
            return
        self._current = segment
        transcript_updates = self._record_transcript_segment(segment)
        if segment.is_final and self._looks_duplicate_final(segment.text) and not transcript_updates:
            return
        await self._broadcast_caption(segment, transcript_updates)
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

    async def set_sensitive_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled:
            self._sensitive_mode = True
            self._sensitive_resume_ignore_until = None
            self._discard_sensitive_transcript_draft()
            self._current = CaptionSegment(
                text="Captions are paused for a private or sensitive moment.",
                raw_text="sensitive mode",
                is_final=False,
            )
            await self._broadcast({"type": "sensitive", "enabled": True, "message": self._current.text})
        else:
            self._sensitive_mode = False
            self._discard_sensitive_transcript_draft()
            self._sensitive_resume_ignore_until = datetime.now(timezone.utc) + timedelta(seconds=3)
            self._current = CaptionSegment(text="Captions have resumed.", raw_text="resumed", is_final=False)
            await self._broadcast({"type": "sensitive", "enabled": False, "message": self._current.text})

    async def clear(self) -> None:
        self._current = None
        self._history.clear()
        self._history_draft = None
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
        text = " ".join(str(text or "").split()).strip()
        if self._word_count(text) < 2:
            return None
        self._history_draft = self._copy_segment(source, text=text, is_final=False)
        return self._history_draft

    def _record_partial_transcript(self, segment: CaptionSegment) -> list[CaptionSegment]:
        text = " ".join(segment.text.split()).strip()
        if self._word_count(text) < 2:
            return []

        suffix = self._dedupe_against_previous(text, self._recent_history_text())
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

        advanced = self._dedupe_against_previous(suffix, draft.text)
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
        text = " ".join(segment.text.split()).strip()
        if self._word_count(text) < 2:
            return []

        updates: list[CaptionSegment] = []
        suffix = self._dedupe_against_previous(text, self._recent_history_text())
        draft = self._history_draft
        if draft is not None:
            if not suffix or self._texts_overlap(draft.text, suffix):
                best_text = suffix if self._word_count(suffix) >= self._word_count(draft.text) else draft.text
                self._history_draft = self._copy_segment(segment, text=best_text, is_final=False, existing=draft)
                committed = self._commit_draft()
                if committed:
                    updates.append(committed)
                return updates
            committed = self._commit_draft()
            if committed:
                updates.append(committed)

        suffix = self._dedupe_against_previous(text, self._recent_history_text())
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

    async def _broadcast_caption(self, segment: CaptionSegment, transcript_updates: list[CaptionSegment] | None = None) -> None:
        async with self._lock:
            clients = list(self._clients.items())
        if not clients:
            return

        transcript_updates = transcript_updates or []
        dead: list[WebSocket] = []
        active_translated = set(self.active_translated_languages())
        languages_needed = sorted({lang for _, lang in clients if lang != "en"})
        translated_by_language: dict[str, tuple[CaptionSegment, str | None, bool]] = {}

        # Translate once per active target language, then reuse that result for
        # every connected viewer using that language. This avoids multiplying CPU
        # work by the number of phones in the room.
        for lang in languages_needed:
            warning = None
            applied = False
            display_segment = segment
            if lang not in self.translation_allowed_languages:
                warning = "This language is not enabled by the operator. Showing source captions."
            elif lang not in active_translated:
                warning = "Translation language limit reached. Showing source captions to protect system performance."
            else:
                result = await self.translator.translate_async(
                    segment.text,
                    lang,
                    enabled=self.translation_enabled,
                    provider=self.translation_provider,
                )
                applied = result.applied
                warning = result.warning
                if result.applied:
                    display_segment = segment.model_copy(update={"text": result.text, "raw_text": segment.text})
                else:
                    display_segment = segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text})
                if lang != "en" and not applied and not warning:
                    warning = "Translation is experimental or unavailable. Showing source captions."
            translated_by_language[lang] = (display_segment, warning, applied)

        for ws, lang in clients:
            if lang == "en":
                display_segment = segment
                translation_warning = None
                translation_applied = False
            else:
                display_segment, translation_warning, translation_applied = translated_by_language.get(
                    lang,
                    (segment.model_copy(update={"text": segment.text, "raw_text": segment.raw_text or segment.text}), "Translation unavailable. Showing source captions.", False),
                )
            try:
                await ws.send_json({
                    "type": "caption",
                    "data": display_segment.model_dump(mode="json"),
                    "transcript_updates": [
                        self._translate_segment_for_language(update, lang).model_dump(mode="json")
                        for update in transcript_updates
                    ],
                    "source_text": segment.text,
                    "language": lang,
                    "translation_applied": translation_applied,
                    "translation_warning": translation_warning,
                    **self.retention_state(),
                    "viewers": self.viewer_count,
                })
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.pop(ws, None)
            await self._broadcast_viewer_meta()

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
