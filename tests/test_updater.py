import unittest
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.settings import APP_VERSION, Settings
from app.updater import launch_update_process, normalise_version, parse_version_from_settings, poll_update_process_state, update_script_for_system, version_label, version_tuple


class UpdaterVersionTests(unittest.TestCase):
    def test_normalise_release_tag_versions(self):
        self.assertEqual(normalise_version("v0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("v.0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("0.4.0"), "0.4.0")

    def test_version_label_uses_public_format(self):
        self.assertEqual(version_label("v0.4.0"), "v0.4.0")

    def test_settings_version_parser_reads_code_owned_constant(self):
        self.assertEqual(parse_version_from_settings('APP_VERSION = "0.7.2"'), "0.7.2")

    def test_settings_version_parser_keeps_legacy_release_compatibility(self):
        self.assertEqual(parse_version_from_settings('app_version: str = "0.6.0"'), "0.6.0")

    def test_release_keeps_v070_download_validation_compatible(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "settings.py").read_text(encoding="utf-8")
        legacy_match = re.search(r'app_version\s*:\s*str\s*=\s*"([^"]+)"', source)
        self.assertIsNotNone(legacy_match)
        self.assertEqual(legacy_match.group(1), APP_VERSION)
        self.assertEqual(Settings.model_fields["app_version"].default, APP_VERSION)

    def test_macos_and_linux_updater_reads_code_owned_version(self):
        source = (Path(__file__).resolve().parents[1] / "update-macos.sh").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION", source)
        self.assertIn("app_version[[:space:]]*:", source)
        self.assertIn('Current version: v${CURRENT_VERSION:-unknown}', source)
        self.assertNotIn('Current version: v.${CURRENT_VERSION:-unknown}', source)
        self.assertIn("CHURCH_CAP_UPDATE_TARGET_VERSION", source)

    def test_windows_updater_reads_code_owned_version(self):
        source = (Path(__file__).resolve().parents[1] / "update-windows.ps1").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION\\s*=", source)
        self.assertIn("app_version\\s*:\\s*str", source)
        self.assertIn('Current version: v$CurrentVersion', source)
        self.assertNotIn('Current version: v.$CurrentVersion', source)
        self.assertIn("CHURCH_CAP_UPDATE_TARGET_VERSION", source)

    def test_version_tuple_compares_release_tags(self):
        self.assertGreater(version_tuple("v0.4.1"), version_tuple("v0.4.0"))

    def test_linux_uses_linux_update_script(self):
        self.assertEqual(update_script_for_system(Path("/app"), "Linux"), Path("/app/update-linux.sh"))

    def test_update_launcher_returns_process_and_closes_parent_log_handle(self):
        fake_process = type("FakeProcess", (), {"pid": 4321})()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "update-linux.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            with patch("app.updater.platform.system", return_value="Linux"), patch(
                "app.updater.subprocess.Popen", return_value=fake_process
            ) as popen:
                result = launch_update_process(root, "0.7.2")
        self.assertEqual(result["pid"], 4321)
        self.assertIs(result["_process"], fake_process)
        self.assertTrue(popen.call_args.kwargs["stdout"].closed)

    def test_operator_monitors_update_process_failure(self):
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "app" / "main.py").read_text(encoding="utf-8")
        operator_source = (root / "app" / "templates" / "operator.html").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/update/status")', main_source)
        self.assertIn("poll_update_process_state(_update_state, _update_process", main_source)
        self.assertIn("/api/update/status?update=", operator_source)
        self.assertIn("showUpdateFailure(state.error)", operator_source)
        self.assertIn("downloadUpdateFailureDiagnostics()", operator_source)

    def test_update_capability_converts_child_failure_to_safe_state(self):
        class FailedProcess:
            @staticmethod
            def poll():
                return 23

        state = poll_update_process_state(
            {"status": "updating", "remote_version": "0.7.2"},
            FailedProcess(),
        )
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["return_code"], 23)
        self.assertEqual(state["log"], "logs/update.log")
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), state["error"])


if __name__ == "__main__":
    unittest.main()
