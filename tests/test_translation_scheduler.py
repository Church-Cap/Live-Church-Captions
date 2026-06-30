import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path

try:
    import fastapi  # noqa: F401
except ModuleNotFoundError:
    sys.modules["fastapi"] = types.SimpleNamespace(WebSocket=object)

from app.broadcast import CaptionHub
from app.i18n import TranslationResult
from app.models import CaptionSegment
from app.transcript_store import TranscriptStore


class FakeWebSocket:
    def __init__(self):
        self.payloads = []

    async def send_json(self, payload):
        self.payloads.append(payload)


class DelayedTranslator:
    def __init__(self):
        self.calls = []
        self.release_old = asyncio.Event()

    async def translate_async(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        self.calls.append((target_language, text))
        if text == "old caption":
            await self.release_old.wait()
        return TranslationResult(text=f"{target_language}:{text}", applied=True)


class TranslationSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_translation_state_keeps_source_language_available(self):
        hub = CaptionHub()

        state = hub.translation_state()

        self.assertEqual(hub.source_language, "en")
        self.assertIn("en", state["available_languages"])
        self.assertIn("en", state["allowed_languages"])

    async def asyncTearDown(self):
        task = getattr(self, "worker_task", None)
        if task is not None:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_latest_translation_batch_wins_and_skips_stale_languages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TranscriptStore(
                encrypted_path=Path(tmpdir) / "transcript.json.enc",
                key_path=Path(tmpdir) / "transcript.key",
                plaintext_fallback_path=Path(tmpdir) / "transcript.json",
            )
            hub = CaptionHub(transcript_store=store)
            hub.translation_enabled = True
            hub.translation_provider = "demo"
            hub.translation_allowed_languages = {"en", "es", "fr"}
            hub.translation_max_active_languages = 2
            translator = DelayedTranslator()
            hub.translator = translator
            es = FakeWebSocket()
            fr = FakeWebSocket()
            async with hub._lock:
                hub._clients = {es: "es", fr: "fr"}
                hub._viewer_clients = {es, fr}

            hub._queue_translation_batch(CaptionSegment(text="old caption", is_final=True), ["es", "fr"])
            await asyncio.sleep(0)
            hub._queue_translation_batch(CaptionSegment(text="new caption", is_final=True), ["es", "fr"])
            translator.release_old.set()

            for _ in range(40):
                caption_payloads = [
                    payload
                    for payload in [*es.payloads, *fr.payloads]
                    if payload.get("type") == "caption"
                ]
                if len(caption_payloads) >= 2:
                    break
                await asyncio.sleep(0.01)

            self.worker_task = hub._translation_worker_task
            caption_texts = [
                payload["data"]["text"]
                for payload in [*es.payloads, *fr.payloads]
                if payload.get("type") == "caption"
            ]
            self.assertEqual(sorted(caption_texts), ["es:new caption", "fr:new caption"])
            self.assertNotIn(("fr", "old caption"), translator.calls)


if __name__ == "__main__":
    unittest.main()
