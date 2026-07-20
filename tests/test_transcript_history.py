import tempfile
import threading
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.WebSocket = object
sys.modules.setdefault("fastapi", fastapi_stub)

from app.broadcast import CaptionHub
from app.models import CaptionSegment
from app.transcript_store import TranscriptStore


class TranscriptHistoryTests(unittest.IsolatedAsyncioTestCase):
    def make_store(self, root: Path) -> TranscriptStore:
        return TranscriptStore(
            encrypted_path=root / "transcript.json.enc",
            key_path=root / "transcript.key",
            plaintext_fallback_path=root / "transcript.json",
        )

    async def test_partial_captions_are_retained_as_scrollable_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)

            await hub.publish(CaptionSegment(text="Good morning everyone", is_final=False, created_at=datetime.now(timezone.utc)))
            await hub.publish(CaptionSegment(text="Good morning everyone and welcome to church", is_final=False, created_at=datetime.now(timezone.utc)))
            await hub.publish(CaptionSegment(text="and welcome to church as we gather to worship", is_final=False, created_at=datetime.now(timezone.utc)))

            segments = hub.final_segments()
            self.assertEqual(len(segments), 1)
            self.assertEqual(
                segments[0].text,
                "Good morning everyone and welcome to church as we gather to worship",
            )
            self.assertFalse(segments[0].is_final)
            self.assertTrue((root / "transcript.json.enc").exists() or (root / "transcript.json").exists())

            reloaded = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)
            self.assertEqual(reloaded.final_segments(), [])
            self.assertEqual(
                [seg.text for seg in store.load_segments(retention_minutes=60, history_limit=10)],
                [seg.text for seg in segments],
            )

    async def test_corrected_rolling_hypotheses_update_one_transcript_cue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)

            await hub.publish(CaptionSegment(text="Empty space does not stay empty", raw_text="Empty space does not stay empty", is_final=False))
            first = hub.final_segments()[0]
            await hub.publish(CaptionSegment(text="Empty space does not remain empty", raw_text="Empty space does not remain empty", is_final=False))
            revised = hub.final_segments()[0]
            await hub.publish(CaptionSegment(text="Empty space does not remain empty", raw_text="Empty space does not remain empty", is_final=True))

            segments = hub.final_segments()
            self.assertEqual(len(segments), 1)
            self.assertEqual(segments[0].text, "Empty space does not remain empty")
            self.assertTrue(segments[0].is_final)
            self.assertEqual(first.cue_id, revised.cue_id)
            self.assertEqual(revised.cue_id, segments[0].cue_id)
            self.assertGreater(segments[0].cue_revision, revised.cue_revision)

    async def test_startup_prunes_expired_cache_without_loading_previous_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            old_created_at = datetime.now(timezone.utc) - timedelta(minutes=90)

            store._write_payload(
                [CaptionSegment(text="Last service should expire", is_final=True, created_at=old_created_at)],
                retention_minutes=30,
            )
            self.assertTrue((root / "transcript.json.enc").exists() or (root / "transcript.json").exists())

            hub = CaptionHub(history_limit=10, retention_minutes=120, transcript_saving_enabled=True, transcript_store=store)

            self.assertEqual(hub.final_segments(), [])
            self.assertFalse((root / "transcript.json.enc").exists())
            self.assertFalse((root / "transcript.json").exists())

    async def test_startup_keeps_unexpired_cache_on_disk_but_starts_visible_session_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            store.save_segments(
                [CaptionSegment(text="Previous service remains on disk only", is_final=True, created_at=datetime.now(timezone.utc))],
                retention_minutes=1440,
                history_limit=10,
            )

            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)

            self.assertEqual(hub.final_segments(), [])
            self.assertTrue((root / "transcript.json.enc").exists() or (root / "transcript.json").exists())

    async def test_repeated_phrase_loop_is_trimmed_from_session_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)
            phrase = "So, when Jesus meets Simon, the Bible is made by the Bible."
            repeated = " ".join([phrase] * 5)

            await hub.publish(CaptionSegment(text=repeated, is_final=False, created_at=datetime.now(timezone.utc)))
            await hub.publish(CaptionSegment(text=repeated, is_final=True, created_at=datetime.now(timezone.utc)))

            texts = [seg.text for seg in hub.final_segments()]
            self.assertEqual(texts, [phrase.rstrip(".")])


    async def test_sensitive_mode_discards_private_and_buffered_transcript_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)

            await hub.publish(CaptionSegment(text="Public welcome before privacy", is_final=True, created_at=datetime.now(timezone.utc)))
            await hub.set_sensitive_mode(True)
            await hub.publish(CaptionSegment(text="Private pastoral detail should not be stored", is_final=True, created_at=datetime.now(timezone.utc)))
            await hub.set_sensitive_mode(False)
            await hub.publish(CaptionSegment(text="Buffered private words should also be dropped", is_final=True, created_at=datetime.now(timezone.utc)))

            texts = [seg.text for seg in hub.final_segments()]
            self.assertIn("Public welcome before privacy", texts)
            self.assertNotIn("Private pastoral detail should not be stored", texts)
            self.assertNotIn("Buffered private words should also be dropped", texts)
            self.assertEqual([seg.text for seg in store.load_segments(retention_minutes=60, history_limit=10)], texts)

    async def test_clearing_or_disabling_retention_deletes_transcript_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root)
            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)

            await hub.publish(CaptionSegment(text="This caption should be deleted", is_final=True, created_at=datetime.now(timezone.utc)))
            self.assertTrue((root / "transcript.json.enc").exists() or (root / "transcript.json").exists())

            await hub.clear()
            self.assertFalse((root / "transcript.json.enc").exists())
            self.assertFalse((root / "transcript.json").exists())

            await hub.publish(CaptionSegment(text="This caption should also be deleted", is_final=True, created_at=datetime.now(timezone.utc)))
            hub.configure_retention(retention_minutes=0, transcript_saving_enabled=True)
            self.assertFalse((root / "transcript.json.enc").exists())
            self.assertFalse((root / "transcript.json").exists())

    async def test_transcript_persistence_failure_does_not_stop_live_captions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            class FailingStore(TranscriptStore):
                def save_segments(self, *args, **kwargs):
                    raise FileNotFoundError("simulated transcript cache write failure")

            store = FailingStore(
                encrypted_path=root / "transcript.json.enc",
                key_path=root / "transcript.key",
                plaintext_fallback_path=root / "transcript.json",
            )
            hub = CaptionHub(history_limit=10, retention_minutes=60, transcript_saving_enabled=True, transcript_store=store)

            await hub.publish(CaptionSegment(text="Live captions should continue", is_final=True, created_at=datetime.now(timezone.utc)))

            self.assertEqual([seg.text for seg in hub.final_segments()], ["Live captions should continue"])

    async def test_atomic_transcript_write_uses_unique_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.json.enc"
            errors = []
            start = threading.Barrier(8)

            def writer(index: int) -> None:
                try:
                    start.wait()
                    TranscriptStore._atomic_write(path, f"payload-{index}".encode("utf-8"))
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertTrue(path.exists())
            self.assertTrue(path.read_text(encoding="utf-8").startswith("payload-"))


if __name__ == "__main__":
    unittest.main()
