import asyncio
import sys
import tempfile
import types
import unittest
from datetime import timedelta
from pathlib import Path

try:
    import fastapi  # noqa: F401
except ModuleNotFoundError:
    sys.modules["fastapi"] = types.SimpleNamespace(WebSocket=object)

from app.broadcast import CaptionHub
from app.i18n import TranslationResult
from app.models import CaptionSegment
from app.transcript_store import TranscriptStore
from app.translation_scheduler import BoundedFairTranslationScheduler, TranslationJob


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
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.transcript_store = TranscriptStore(
            encrypted_path=root / "transcript.json.enc",
            key_path=root / "transcript.key",
            plaintext_fallback_path=root / "transcript.json",
        )

    async def test_translation_state_keeps_source_language_available(self):
        hub = CaptionHub(transcript_store=self.transcript_store)

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
        self.tempdir.cleanup()

    async def test_stable_translation_mode_still_updates_during_continuous_speech(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_timing_mode = "stable"
        self.assertTrue(hub._should_translate_partial("es", CaptionSegment(text="this is enough corrected English words", is_final=False)))
        self.assertFalse(hub._should_translate_partial("es", CaptionSegment(text="this is enough corrected English words", is_final=False)))
        self.assertTrue(hub._should_translate_partial("es", CaptionSegment(text="final text", is_final=True)))

    async def test_responsive_mode_debounces_small_stable_prefix_growth(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_timing_mode = "responsive"
        self.assertTrue(hub._should_translate_partial("fa", CaptionSegment(text="Grace welcomes every", is_final=False)))
        hub._last_partial_translation_at["fa"] -= timedelta(seconds=2)
        self.assertFalse(hub._should_translate_partial("fa", CaptionSegment(text="Grace welcomes every person", is_final=False)))
        self.assertTrue(hub._should_translate_partial("fa", CaptionSegment(text="Grace welcomes every person gathered today", is_final=False)))

    async def test_responsive_mode_translates_stable_english_without_waiting_for_final(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_timing_mode = "responsive"
        draft = CaptionSegment(
            id="cue-one",
            text="Jesus welcomed the people who gathered",
            is_final=False,
            source_unit_id="cue-one",
            cue_id="cue-one",
            source_status="draft",
            source_revision=2,
            cue_revision=2,
            cue_stable_word_count=4,
            cue_mutable_word_count=2,
        )

        ready = hub._translation_units_for_timing([draft])

        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].text, "Jesus welcomed the people")
        self.assertEqual(ready[0].source_boundary_reason, "responsive_stable_prefix")
        self.assertFalse(ready[0].is_final)

    async def test_responsive_mode_does_not_translate_an_unstable_tail(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_timing_mode = "responsive"
        draft = CaptionSegment(
            id="cue-one",
            text="Jesus welcomed everyone gathered here",
            is_final=False,
            source_unit_id="cue-one",
            cue_id="cue-one",
            cue_stable_word_count=2,
            cue_mutable_word_count=3,
        )

        ready = hub._translation_units_for_timing([draft])

        self.assertEqual(ready, [])

    async def test_responsive_final_refines_the_same_cue_with_full_text(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_timing_mode = "responsive"
        final = CaptionSegment(
            id="cue-one",
            text="Jesus welcomed everyone who gathered there.",
            is_final=True,
            source_unit_id="cue-one",
            cue_id="cue-one",
            source_status="final",
            cue_status="sealed",
            source_revision=4,
            cue_revision=4,
            cue_stable_word_count=7,
        )

        ready = hub._translation_units_for_timing([final])
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].text, final.text)
        self.assertEqual(ready[0].cue_id, "cue-one")
        self.assertTrue(ready[0].is_final)

    async def test_legacy_context_modes_migrate_to_responsive(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        for legacy in ("contextual", "extended"):
            hub.configure_translation(
                enabled=True,
                provider="demo",
                allowed_languages=["en", "fa"],
                max_active_languages=1,
                timing_mode=legacy,
            )
            self.assertEqual(hub.translation_timing_mode, "responsive")

    async def test_raw_english_is_immediate_and_translation_uses_source_units_without_history(self):
        hub = CaptionHub(
            transcript_store=self.transcript_store,
            transcript_saving_enabled=False,
        )
        hub.translation_enabled = True
        hub.translation_timing_mode = "live"
        hub.translation_provider = "demo"
        hub.translation_allowed_languages = {"en", "fa"}
        translator = DelayedTranslator()
        hub.translator = translator
        english = FakeWebSocket()
        farsi = FakeWebSocket()
        async with hub._lock:
            hub._clients = {english: "en", farsi: "fa"}
            hub._viewer_clients = {english, farsi}

        await hub.publish(CaptionSegment(text="Grace welcomes every person here", is_final=False))

        english_captions = [payload for payload in english.payloads if payload.get("type") == "caption"]
        self.assertEqual(len(english_captions), 1)
        self.assertEqual(english_captions[0]["data"]["text"], "Grace welcomes every person here")
        self.assertIsNone(english_captions[0]["data"]["source_unit_id"])
        self.assertEqual(len(english_captions[0]["live_source_updates"]), 1)
        self.assertEqual(
            english_captions[0]["live_source_updates"][0]["text"],
            "Grace welcomes every person here",
        )
        self.assertEqual(english_captions[0]["live_source_updates"][0]["source_status"], "draft")
        self.assertTrue(english_captions[0]["live_source_updates"][0]["source_unit_id"])

        for _ in range(40):
            farsi_captions = [payload for payload in farsi.payloads if payload.get("type") == "caption"]
            if farsi_captions:
                break
            await asyncio.sleep(0.01)

        self.worker_task = hub._translation_worker_task
        self.assertEqual(len(farsi_captions), 1)
        self.assertEqual(farsi_captions[0]["data"]["source_status"], "draft")
        self.assertEqual(farsi_captions[0]["data"]["source_revision"], 1)
        self.assertTrue(farsi_captions[0]["data"]["source_unit_id"])

    async def test_responsive_translation_uses_the_growing_stable_english_cue(self):
        hub = CaptionHub(
            transcript_store=self.transcript_store,
            transcript_saving_enabled=False,
        )
        hub.translation_enabled = True
        hub.translation_provider = "demo"
        hub.translation_allowed_languages = {"en", "fa"}
        translator = DelayedTranslator()
        hub.translator = translator
        english = FakeWebSocket()
        farsi = FakeWebSocket()
        async with hub._lock:
            hub._clients = {english: "en", farsi: "fa"}
            hub._viewer_clients = {english, farsi}

        await hub.publish(CaptionSegment(text="Grace welcomes every person here", is_final=False))
        self.assertEqual(translator.calls, [])

        await hub.publish(CaptionSegment(text="Grace welcomes every person here today", is_final=False))
        for _ in range(40):
            if translator.calls:
                break
            await asyncio.sleep(0.01)

        self.worker_task = hub._translation_worker_task
        self.assertEqual(translator.calls, [("fa", "Grace welcomes every person here")])
        translated = [payload for payload in farsi.payloads if payload.get("type") == "caption"]
        self.assertEqual(len(translated), 1)
        self.assertFalse(translated[0]["data"]["is_final"])
        self.assertEqual(translated[0]["source_text"], "Grace welcomes every person here")
        self.assertEqual(
            translated[0]["data"]["cue_id"],
            [payload for payload in english.payloads if payload.get("type") == "caption"][-1]["live_source_updates"][-1]["cue_id"],
        )

        cue_id = translated[0]["data"]["cue_id"]
        hub._queue_translation_batch(
            CaptionSegment(
                id=cue_id,
                text="Grace welcomes every person here today.",
                is_final=True,
                source_unit_id=cue_id,
                cue_id=cue_id,
                source_status="final",
                cue_status="sealed",
                source_revision=3,
                cue_revision=3,
            ),
            ["fa"],
        )
        for _ in range(40):
            translated = [payload for payload in farsi.payloads if payload.get("type") == "caption"]
            if len(translated) == 2:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(len(translated), 2)
        self.assertEqual(translated[1]["data"]["cue_id"], cue_id)
        self.assertTrue(translated[1]["data"]["is_final"])
        self.assertEqual(translator.calls[-1], ("fa", "Grace welcomes every person here today."))

    async def test_stop_drains_outstanding_translation_work(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_enabled = True
        hub.translation_provider = "demo"
        hub.translation_allowed_languages = {"en", "fa"}
        hub.translator = DelayedTranslator()
        farsi = FakeWebSocket()
        async with hub._lock:
            hub._clients = {farsi: "fa"}
            hub._viewer_clients = {farsi}

        hub._queue_translation_batch(
            CaptionSegment(
                text="A completed thought",
                is_final=True,
                source_unit_id="unit-stop",
                source_status="final",
            ),
            ["fa"],
        )
        result = await hub.drain_translation_work(timeout_seconds=1.0)

        self.worker_task = hub._translation_worker_task
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["cancelled_at_stop"], {})
        self.assertEqual(len([item for item in farsi.payloads if item.get("type") == "caption"]), 1)

    async def test_stop_timeout_accounts_for_and_cancels_in_flight_work(self):
        hub = CaptionHub(transcript_store=self.transcript_store)
        hub.translation_enabled = True
        hub.translation_provider = "demo"
        hub.translation_allowed_languages = {"en", "fa"}
        translator = DelayedTranslator()
        hub.translator = translator
        farsi = FakeWebSocket()
        async with hub._lock:
            hub._clients = {farsi: "fa"}
            hub._viewer_clients = {farsi}

        hub._queue_translation_batch(
            CaptionSegment(
                text="old caption",
                is_final=True,
                source_unit_id="unit-timeout",
                source_status="final",
            ),
            ["fa"],
        )
        for _ in range(20):
            if translator.calls:
                break
            await asyncio.sleep(0.005)
        result = await hub.drain_translation_work(timeout_seconds=0.01)

        self.assertTrue(result["timed_out"])
        self.assertEqual(result["cancelled_at_stop"], {"fa": 1})
        self.assertIsNone(hub._translation_worker_task)

    @staticmethod
    def _job(language, text, sequence, *, unit_id=None, revision=1, final=False, generation=0):
        unit_id = unit_id or f"unit-{sequence}"
        return TranslationJob(
            language=language,
            segment=CaptionSegment(
                id=unit_id,
                text=text,
                is_final=final,
                source_unit_id=unit_id,
                source_revision=revision,
                source_status="final" if final else "draft",
            ),
            sequence=sequence,
            enqueued_monotonic=float(sequence),
            source_ready_monotonic=float(sequence),
            generation=generation,
        )

    async def test_draft_revisions_coalesce_but_final_revision_is_durable(self):
        scheduler = BoundedFairTranslationScheduler(capacity_per_language=3)
        first = self._job("fa", "first draft", 1, unit_id="unit-a", revision=1)
        revised = self._job("fa", "revised draft", 2, unit_id="unit-a", revision=2)
        final = self._job("fa", "completed thought", 3, unit_id="unit-a", revision=3, final=True)

        scheduler.enqueue(first)
        revised_result = scheduler.enqueue(revised)
        final_result = scheduler.enqueue(final)

        self.assertIn("draft_coalesced", revised_result.events)
        self.assertIn("draft_coalesced", final_result.events)
        self.assertFalse(scheduler.is_current(first))
        self.assertFalse(scheduler.is_current(revised))
        self.assertTrue(scheduler.is_current(final))
        self.assertEqual(scheduler.pop_next(), final)

    async def test_newer_revision_supersedes_queued_and_in_flight_final_for_same_cue(self):
        scheduler = BoundedFairTranslationScheduler(capacity_per_language=3)
        old_final = self._job("fa", "old corrected wording", 1, unit_id="cue-a", revision=3, final=True)
        new_final = self._job("fa", "new accurate wording", 2, unit_id="cue-a", revision=4, final=True)

        scheduler.enqueue(old_final)
        in_flight = scheduler.pop_next()
        scheduler.enqueue(new_final)

        self.assertFalse(scheduler.is_current(in_flight))
        self.assertTrue(scheduler.is_current(new_final))

        scheduler = BoundedFairTranslationScheduler(capacity_per_language=3)
        scheduler.enqueue(old_final)
        result = scheduler.enqueue(new_final)
        self.assertIn("final_revision_coalesced", result.events)
        self.assertEqual(scheduler.pop_next(), new_final)

    async def test_round_robin_prevents_one_language_starving_another(self):
        scheduler = BoundedFairTranslationScheduler(capacity_per_language=8)
        fa1 = self._job("fa", "fa one", 1, final=True)
        fa2 = self._job("fa", "fa two", 2, final=True)
        zh1 = self._job("zh", "zh one", 3, final=True)
        scheduler.enqueue(fa1)
        scheduler.enqueue(fa2)
        scheduler.enqueue(zh1)

        self.assertEqual([scheduler.pop_next(), scheduler.pop_next(), scheduler.pop_next()], [fa1, zh1, fa2])

    async def test_backpressure_discards_drafts_before_completed_units(self):
        scheduler = BoundedFairTranslationScheduler(capacity_per_language=2)
        final1 = self._job("fa", "final one", 1, final=True)
        draft = self._job("fa", "replaceable draft", 2)
        final2 = self._job("fa", "final two", 3, final=True)
        final3 = self._job("fa", "final three", 4, final=True)
        scheduler.enqueue(final1)
        scheduler.enqueue(draft)

        result = scheduler.enqueue(final2)
        overflow = scheduler.enqueue(final3)

        self.assertIn("draft_dropped_backpressure", result.events)
        self.assertIn("final_preserved_over_capacity", overflow.events)
        self.assertEqual([scheduler.pop_next(), scheduler.pop_next(), scheduler.pop_next()], [final1, final2, final3])

    async def test_scheduler_reports_recovery_after_overload_drains(self):
        scheduler = BoundedFairTranslationScheduler(capacity_per_language=2)
        scheduler.enqueue(self._job("zh", "final one", 1, final=True))
        scheduler.enqueue(self._job("zh", "final two", 2, final=True))
        scheduler.enqueue(self._job("zh", "final three", 3, final=True))
        self.assertEqual(scheduler.snapshot()["degraded_languages"], ["zh"])

        scheduler.pop_next()
        scheduler.pop_next()

        self.assertEqual(scheduler.take_recovery_events(), ["zh"])
        self.assertEqual(scheduler.snapshot()["degraded_languages"], [])

    async def test_completed_batches_are_not_replaced_by_newer_finals(self):
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
            es_caption_texts = [payload["data"]["text"] for payload in es.payloads if payload.get("type") == "caption"]
            fr_caption_texts = [payload["data"]["text"] for payload in fr.payloads if payload.get("type") == "caption"]
            self.assertEqual(es_caption_texts, ["es:old caption", "es:new caption"])
            self.assertEqual(fr_caption_texts, ["fr:old caption", "fr:new caption"])
            self.assertIn(("fr", "old caption"), translator.calls)


if __name__ == "__main__":
    unittest.main()
