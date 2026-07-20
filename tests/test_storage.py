import tempfile
import unittest
from pathlib import Path

from app.storage import clear_storage_candidates, rotate_log_file, storage_snapshot, tail_log_lines


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.project = self.root / "project"
        self.support = self.root / "support"
        self.hub = self.root / "huggingface" / "hub"
        self.whisper = self.root / "whisper"
        for path in (self.project, self.support, self.hub, self.whisper):
            path.mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def snapshot(self, runtime=None):
        return storage_snapshot(
            self.project,
            self.support,
            runtime or {"transcriber_mode": "faster_whisper", "whisper_model": "base.en", "translation_provider": "argos"},
            huggingface_hub_cache=self.hub,
            whisper_cache=self.whisper,
        )

    def test_snapshot_counts_storage_without_exposing_paths(self):
        (self.project / "app.bin").write_bytes(b"a" * 20)
        (self.support / "settings.bin").write_bytes(b"b" * 10)
        (self.hub / "cache.bin").write_bytes(b"c" * 30)
        snapshot = self.snapshot()

        self.assertEqual(snapshot["total_bytes"], 60)
        self.assertEqual(sum(item["bytes"] for item in snapshot["categories"]), 60)
        self.assertNotIn(str(self.root), str(snapshot))

    def test_active_whisper_model_is_protected_and_inactive_model_is_available(self):
        active = self.hub / "models--Systran--faster-whisper-base.en"
        inactive = self.hub / "models--Systran--faster-whisper-small.en"
        active.mkdir()
        inactive.mkdir()
        (active / "model.bin").write_bytes(b"a" * 20)
        (inactive / "model.bin").write_bytes(b"b" * 30)

        candidates = self.snapshot()["cleanup_candidates"]

        self.assertNotIn("faster-whisper:base.en", {item["id"] for item in candidates})
        self.assertIn("faster-whisper:small.en", {item["id"] for item in candidates})

    def test_converted_small100_can_release_source_download_but_keeps_converted_model(self):
        source = self.hub / "models--alirezamsh--small100"
        converted = self.project / "data" / "models" / "small100-ct2-int8"
        source.mkdir()
        converted.mkdir(parents=True)
        (source / "weights.bin").write_bytes(b"s" * 40)
        (converted / "model.bin").write_bytes(b"c" * 25)
        runtime = {"transcriber_mode": "faster_whisper", "whisper_model": "base.en", "translation_provider": "ct2small100"}

        candidates = self.snapshot(runtime)["cleanup_candidates"]
        self.assertIn("small100-source-cache", {item["id"] for item in candidates})

        result = clear_storage_candidates(
            ["small100-source-cache"],
            self.project,
            self.support,
            runtime,
            huggingface_hub_cache=self.hub,
            whisper_cache=self.whisper,
        )
        self.assertEqual(result["reclaimed_bytes"], 40)
        self.assertFalse(source.exists())
        self.assertTrue((converted / "model.bin").exists())

    def test_cleanup_rejects_unknown_or_stale_identifier(self):
        with self.assertRaises(ValueError):
            clear_storage_candidates(
                ["arbitrary-path"],
                self.project,
                self.support,
                {},
                huggingface_hub_cache=self.hub,
                whisper_cache=self.whisper,
            )

    def test_log_rotation_and_bounded_tail(self):
        log = self.support / "logs" / "church-cap.out.log"
        log.parent.mkdir()
        log.write_text("old\n" * 100, encoding="utf-8")

        self.assertTrue(rotate_log_file(log, max_bytes=20, backups=2))
        self.assertFalse(log.exists())
        self.assertTrue(log.with_name("church-cap.out.log.1").exists())

        log.write_text("first\n" + "x" * 300 + "\nlast\n", encoding="utf-8")
        tail = tail_log_lines(log, max_lines=2, max_bytes=64)
        self.assertEqual(tail[-1], "last")
        self.assertLessEqual(len(tail), 2)
