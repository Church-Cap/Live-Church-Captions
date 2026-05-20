import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from fastapi import WebSocket
from app.models import CaptionSegment, CaptionState
from app.i18n import LocalTranslator, normalise_language


class CaptionHub:
    def __init__(self, history_limit: int = 200, retention_minutes: int = 120, transcript_saving_enabled: bool = True):
        self._clients: dict[WebSocket, str] = {}
        self._history: list[CaptionSegment] = []
        self._current: CaptionSegment | None = None
        self._status: str = "idle"
        self._history_limit = history_limit
        self._retention_minutes = retention_minutes
        self._transcript_saving_enabled = transcript_saving_enabled
        self._sensitive_mode = False
        self._lock = asyncio.Lock()
        self.translation_enabled = False
        self.translation_provider = "disabled"
        self.translation_allowed_languages: set[str] = {"en"}
        self.translation_max_active_languages = 1
        self.translator = LocalTranslator("en")

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
        self._purge_old_history()

    def retention_state(self) -> dict:
        return {
            "transcript_retention_minutes": self._retention_minutes,
            "transcript_saving_enabled": self._transcript_saving_enabled,
        }

    def _purge_old_history(self) -> None:
        if self._retention_minutes <= 0:
            self._history.clear()
            return
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._retention_minutes)
        self._history = [seg for seg in self._history if seg.created_at >= cutoff]
        self._history = self._history[-self._history_limit:]

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
            history=[self._translate_segment_for_language(seg, language) for seg in self._history[-50:]],
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
        if not text.strip() or not self._history:
            return False
        current = self._normalise_for_duplicate(text)
        for previous in self._history[-3:]:
            prev = self._normalise_for_duplicate(previous.text)
            if current == prev or (current and current in prev):
                return True
        return False

    def final_segments(self) -> list[CaptionSegment]:
        self._purge_old_history()
        return list(self._history)

    async def publish(self, segment: CaptionSegment) -> None:
        if self._sensitive_mode:
            return
        self._current = segment
        if segment.is_final and self._looks_duplicate_final(segment.text):
            return
        if self._transcript_saving_enabled and segment.is_final and segment.text.strip():
            self._history.append(segment)
            self._purge_old_history()
        await self._broadcast_caption(segment)

    async def set_sensitive_mode(self, enabled: bool) -> None:
        self._sensitive_mode = bool(enabled)
        if enabled:
            self._current = CaptionSegment(
                text="Captions are paused for a private or sensitive moment.",
                raw_text="sensitive mode",
                is_final=False,
            )
            await self._broadcast({"type": "sensitive", "enabled": True, "message": self._current.text})
        else:
            self._current = CaptionSegment(text="Captions have resumed.", raw_text="resumed", is_final=False)
            await self._broadcast({"type": "sensitive", "enabled": False, "message": self._current.text})

    async def clear(self) -> None:
        self._current = None
        self._history.clear()
        await self._broadcast({"type": "clear"})

    async def _broadcast_caption(self, segment: CaptionSegment) -> None:
        async with self._lock:
            clients = list(self._clients.items())
        if not clients:
            return

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
                    "source_text": segment.text,
                    "language": lang,
                    "translation_applied": translation_applied,
                    "translation_warning": translation_warning,
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
