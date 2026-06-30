import asyncio
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from fastapi import WebSocket
from app.models import CaptionSegment, CaptionState
from app.i18n import LocalTranslator, MAX_TRANSLATION_LANGUAGES, SOURCE_LANGUAGE, normalise_language
from app.transcript_store import TranscriptStore
from app.text_cleanup import clean_caption_text, collapse_repeated_phrase
from app.metrics import get_metrics, update_metrics


class CaptionHub:
    def __init__(
        self,
        history_limit: int = 1000,
        retention_minutes: int = 120,
        transcript_saving_enabled: bool = True,
        transcript_store: TranscriptStore | None = None,
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
        self.translator = LocalTranslator(self.source_language)
        self._translation_sequence = 0
        self._latest_translation_sequence: dict[str, int] = {}
        self._last_partial_translation_at: dict[str, datetime] = {}
        self._pending_translation_job: dict | None = None
        self._translation_worker_event: asyncio.Event | None = None
        self._translation_worker_task: asyncio.Task | None = None
        self._transcript_store = transcript_store or TranscriptStore()
        self._session_cache_written = False
        self._start_new_session()

    @property
    def viewer_count(self) -> int:
        return len(self._viewer_clients)

    @property
    def sensitive_mode(self) -> bool:
        return self._sensitive_mode

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
        await self._broadcast_viewer_meta()

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(websocket, None)
            self._viewer_clients.discard(websocket)
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
    ) -> None:
        self.translation_enabled = bool(enabled)
        self.translation_provider = provider or "disabled"
        self.translation_allowed_languages = set(normalise_language(x) for x in allowed_languages)
        self.translation_allowed_languages.add(self.source_language)
        self.translation_max_active_languages = max(1, min(MAX_TRANSLATION_LANGUAGES, int(max_active_languages)))
        self.translation_language_policy = language_policy if language_policy in {"automatic", "restricted"} else "automatic"
        self.translation_priority_mode = priority_mode if priority_mode in {"most_viewers", "pinned_first"} else "most_viewers"
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
        else:
            available_languages = sorted(provider_languages)
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
            "viewer_languages": self.language_counts(),
            "active_translated_languages": self.active_translated_languages(),
            "resources": resources,
            "available_languages": available_languages,
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

    async def publish(self, segment: CaptionSegment) -> None:
        if self._sensitive_mode or self._inside_sensitive_drain_window():
            return
        text = clean_caption_text(collapse_repeated_phrase(segment.text))
        if not text:
            return
        if text != segment.text:
            segment = segment.model_copy(update={"text": text, "raw_text": segment.raw_text or segment.text})
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

    def _source_language_segment(self, segment: CaptionSegment, *, as_draft: bool = False) -> CaptionSegment:
        update = {"text": segment.text, "raw_text": segment.raw_text or segment.text}
        if as_draft and segment.is_final:
            update["is_final"] = False
        return segment.model_copy(update=update)

    @staticmethod
    def _translated_segment(segment: CaptionSegment, text: str) -> CaptionSegment:
        return segment.model_copy(update={"text": text, "raw_text": segment.text})

    def _should_translate_partial(self, language: str, segment: CaptionSegment) -> bool:
        if segment.is_final or self._word_count(segment.text) < 3:
            return segment.is_final
        now = datetime.now(timezone.utc)
        previous = self._last_partial_translation_at.get(language)
        if previous and (now - previous).total_seconds() < 2.0:
            return False
        self._last_partial_translation_at[language] = now
        return True

    def _ensure_translation_worker(self) -> None:
        if self._translation_worker_event is None:
            self._translation_worker_event = asyncio.Event()
        if self._translation_worker_task is None or self._translation_worker_task.done():
            self._translation_worker_task = asyncio.create_task(self._translation_worker_loop())

    def _queue_translation_batch(self, segment: CaptionSegment, languages: list[str]) -> None:
        languages = list(dict.fromkeys(normalise_language(language) for language in languages if normalise_language(language) != "en"))
        if not languages:
            return
        self._translation_sequence += 1
        sequence = self._translation_sequence
        for language in languages:
            self._latest_translation_sequence[language] = sequence
        self._pending_translation_job = {
            "sequence": sequence,
            "segment": segment,
            "languages": languages,
        }
        self._ensure_translation_worker()
        if self._translation_worker_event is not None:
            self._translation_worker_event.set()

    async def _translation_worker_loop(self) -> None:
        while True:
            if self._translation_worker_event is None:
                return
            await self._translation_worker_event.wait()
            self._translation_worker_event.clear()
            while self._pending_translation_job is not None:
                job = self._pending_translation_job
                self._pending_translation_job = None
                sequence = int(job["sequence"])
                segment = job["segment"]
                for language in job["languages"]:
                    if self._pending_translation_job is not None:
                        break
                    if self._latest_translation_sequence.get(language) != sequence:
                        continue
                    await self._broadcast_translated_caption(segment, language, sequence)

    def _caption_payload(
        self,
        segment: CaptionSegment,
        *,
        language: str,
        source_text: str,
        transcript_updates: list[CaptionSegment] | None = None,
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

    async def _broadcast_translated_caption(self, segment: CaptionSegment, language: str, sequence: int) -> None:
        async with self._lock:
            clients = [ws for ws, lang in self._clients.items() if lang == language]
        if not clients or self._latest_translation_sequence.get(language) != sequence:
            return
        started_at = time.monotonic()
        try:
            result = await self.translator.translate_async(
                segment.text,
                language,
                enabled=self.translation_enabled,
                provider=self.translation_provider,
            )
            update_metrics(
                last_translation_seconds=max(0.0, time.monotonic() - started_at),
                last_translation_at=time.monotonic(),
                translations_completed=int(get_metrics().get("translations_completed", 0)) + 1,
            )
        except Exception as exc:
            update_metrics(last_translation_seconds=max(0.0, time.monotonic() - started_at), last_translation_at=time.monotonic())
            result = None
            warning = f"Translation failed for {language}: {exc}"
        if result is None:
            display_segment = self._source_language_segment(segment)
            applied = False
        else:
            warning = result.warning
            applied = result.applied
            display_segment = self._translated_segment(segment, result.text) if applied else self._source_language_segment(segment)
        if not applied and not warning:
            warning = "Translation is experimental or unavailable. Showing source captions."
        if self._latest_translation_sequence.get(language) != sequence:
            return

        async with self._lock:
            clients = [ws for ws, lang in self._clients.items() if lang == language]
        if not clients:
            return
        if not applied and not segment.is_final:
            payload = self._translation_status_payload(language=language, warning=warning)
            await self._remove_dead_clients(await self._send_caption_payload(clients, payload))
            return
        payload = self._caption_payload(
            display_segment,
            language=language,
            source_text=segment.text,
            translation_applied=applied,
            translation_warning=warning,
        )
        await self._remove_dead_clients(await self._send_caption_payload(clients, payload))

    async def _broadcast_caption(self, segment: CaptionSegment, transcript_updates: list[CaptionSegment] | None = None) -> None:
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
                )
                dead.extend(await self._send_caption_payload(sockets, payload))
                continue

            warning = None
            should_translate = False
            if self.translation_language_policy == "restricted" and lang not in self.translation_allowed_languages:
                warning = "This language is not enabled by the operator. Showing source captions."
            elif lang not in active_translated:
                warning = "Translation capacity is full right now, so captions are shown in the source language. Please speak to the welcome team if you need help."
            else:
                should_translate = True
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

            if should_translate and self._should_translate_partial(lang, segment):
                languages_to_translate.append(lang)

        await self._remove_dead_clients(dead)
        if languages_to_translate:
            self._queue_translation_batch(segment, languages_to_translate)

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
