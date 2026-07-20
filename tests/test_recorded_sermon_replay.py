import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


class RecordedSermonReplayTests(unittest.TestCase):
    def test_dry_run_validates_pcm_and_writes_privacy_safe_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sentinel = "private-sermon-name-sentinel.wav"
            recording = root / sentinel
            manifest = root / "manifest.json"
            second_manifest = root / "manifest-2.json"
            with wave.open(str(recording), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 1600)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/play-recorded-sermon.py",
                    str(recording),
                    "--dry-run",
                    "--run-label",
                    "matrix-d-live-1",
                    "--language",
                    "fa",
                    "--language",
                    "zh-hant",
                    "--timing-mode",
                    "live",
                    "--provider",
                    "both",
                    "--repeat",
                    "1",
                    "--manifest-out",
                    str(manifest),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "validated")
            self.assertEqual(payload["church_cap_settings"]["audience_languages"], ["fa", "zh-hant"])
            self.assertEqual(payload["playback"]["mode"], "real_time_external_loopback")
            self.assertNotIn(sentinel, json.dumps(payload))
            self.assertNotIn(str(root), json.dumps(payload))

            second_command = list(result.args)
            second_command[-1] = str(second_manifest)
            second = subprocess.run(second_command, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second_manifest.read_text(encoding="utf-8"))
            payload.pop("generated_at")
            second_payload.pop("generated_at")
            self.assertEqual(payload, second_payload)


if __name__ == "__main__":
    unittest.main()
