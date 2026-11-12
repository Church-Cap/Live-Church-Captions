import unittest
import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.settings import APP_VERSION, Settings
from app.updater import launch_update_process, run_update_check_script, normalise_version, parse_version_from_settings, poll_update_process_state, update_script_for_system, version_label, version_tuple


class UpdaterVersionTests(unittest.TestCase):
    def test_normalise_release_tag_versions(self):
        self.assertEqual(normalise_version("v0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("v.0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("0.4.0"), "0.4.0")

    def test_version_label_uses_public_format(self):
        self.assertEqual(version_label("v0.4.0"), "v0.4.0")

    def test_settings_version_parser_reads_code_owned_constant(self):
        self.assertEqual(parse_version_from_settings('APP_VERSION = "0.7.6"'), "0.7.6")

    def test_settings_version_parser_keeps_legacy_release_compatibility(self):
        self.assertEqual(parse_version_from_settings('app_version: str = "0.6.0"'), "0.6.0")

    def test_release_keeps_v070_download_validation_compatible(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "settings.py").read_text(encoding="utf-8")
        legacy_match = re.search(r'app_version\s*:\s*str\s*=\s*"([^"]+)"', source)
        self.assertIsNotNone(legacy_match)
        self.assertEqual(legacy_match.group(1), APP_VERSION)
        self.assertEqual(Settings.model_fields["app_version"].default, APP_VERSION)

    def test_macos_and_linux_updater_reads_code_owned_version(self):
        source = (Path(__file__).resolve().parents[1] / "scripts" / "update-unix.sh").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION", source)
        self.assertIn("app_version[[:space:]]*:", source)
        self.assertIn('Current version: v${CURRENT_VERSION:-unknown}', source)
        self.assertNotIn('Current version: v.${CURRENT_VERSION:-unknown}', source)
        self.assertIn("CHURCH_CAP_UPDATE_TARGET_VERSION", source)
        self.assertIn('pip install --upgrade "pip==26.1.2"', source)

    def test_windows_updater_reads_code_owned_version(self):
        source = (Path(__file__).resolve().parents[1] / "update-windows.ps1").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION\\s*=", source)
        self.assertIn("app_version\\s*:\\s*str", source)
        self.assertIn('Current version: v$CurrentVersion', source)
        self.assertNotIn('Current version: v.$CurrentVersion', source)
        self.assertIn("CHURCH_CAP_UPDATE_TARGET_VERSION", source)
        self.assertIn('pip install --upgrade "pip==26.1.2"', source)

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
                result = launch_update_process(root, "0.7.6")
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

    def test_linux_check_runs_update_script_in_check_only_mode(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Church Cap updater\nCurrent version: v0.9.0\nSelected GitHub release: v0.9.1\n  /app\n\nUpdate available: v0.9.1\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "update-linux.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            with patch.dict(os.environ, {"CHURCH_CAP_UPDATE_TARGET_VERSION": "0.1.0"}), patch(
                "app.updater.subprocess.run", return_value=completed
            ) as run:
                self.assertEqual(run_update_check_script(root), "0.9.1")
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], [str(root / "update-linux.sh"), "--check"])
        self.assertNotIn("--yes", command)
        self.assertNotIn("CHURCH_CAP_UPDATE_TARGET_VERSION", run.call_args.kwargs["env"])
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_linux_check_reports_script_failure_without_guessing_a_version(self):
        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Could not read the latest Church Cap release tag from GitHub.\n")
        silent = subprocess.CompletedProcess(args=[], returncode=0, stdout="Church Cap updater\n", stderr="")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "not available"):
                run_update_check_script(root)
            (root / "update-linux.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            with patch("app.updater.subprocess.run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, r"exit code 1\)\. Could not read"):
                    run_update_check_script(root)
            with patch("app.updater.subprocess.run", return_value=silent):
                with self.assertRaisesRegex(RuntimeError, "did not report"):
                    run_update_check_script(root)

    def test_packaged_desktop_check_hands_off_to_the_desktop_updater(self):
        from app import main

        with patch.dict(os.environ, {"CHURCH_CAP_SUPERVISOR_PID": "4321"}), patch(
            "app.main.runtime_mode", return_value=type("Mode", (), {"value": "packaged"})()
        ):
            for system in ("Darwin", "Windows"):
                self.assertTrue(main.desktop_shell_manages_updates(system))
            self.assertFalse(main.desktop_shell_manages_updates("Linux"))
        with patch.dict(os.environ, {"CHURCH_CAP_SUPERVISOR_PID": ""}), patch(
            "app.main.runtime_mode", return_value=type("Mode", (), {"value": "packaged"})()
        ):
            self.assertFalse(main.desktop_shell_manages_updates("Windows"))
        with patch.dict(os.environ, {"CHURCH_CAP_SUPERVISOR_PID": "4321"}), patch(
            "app.main.runtime_mode", return_value=type("Mode", (), {"value": "source"})()
        ):
            self.assertFalse(main.desktop_shell_manages_updates("Darwin"))

    def test_desktop_update_request_is_one_protocol_line_and_debounced(self):
        from app import main
        from engine.protocol import REQUEST_PREFIX, EngineRequest, EngineRequestName

        with patch.object(main, "_desktop_update_request_at", 0.0), patch("builtins.print") as printed, patch(
            "app.main.time.monotonic", side_effect=[100.0, 101.0, 104.0]
        ):
            self.assertTrue(main.request_desktop_update_check())
            self.assertFalse(main.request_desktop_update_check())
            self.assertTrue(main.request_desktop_update_check())
        self.assertEqual(printed.call_count, 2)
        line = printed.call_args.args[0]
        self.assertTrue(line.startswith(REQUEST_PREFIX))
        self.assertEqual(EngineRequest.parse(line).request, EngineRequestName.OPEN_UPDATES)
        self.assertTrue(printed.call_args.kwargs["flush"])

    def test_update_routes_keep_desktop_installs_in_the_signed_updater(self):
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "app" / "main.py").read_text(encoding="utf-8")
        check = main_source.split('async def check_for_update(', 1)[1].split("@app.get(", 1)[0]
        start = main_source.split('async def start_update(', 1)[1].split("@app.", 1)[0]
        self.assertLess(check.index("is_local_client(request)"), check.index("request_desktop_update_check()"))
        self.assertIn("run_update_check_script, PROJECT_ROOT", check)
        self.assertIn('capability["managed_by"] == "desktop"', start)
        self.assertLess(start.index('capability["managed_by"] == "desktop"'), start.index("launch_update_process"))
        operator_source = (root / "app" / "templates" / "operator.html").read_text(encoding="utf-8")
        self.assertIn("data.status === 'desktop_requested'", operator_source)

    def test_update_capability_converts_child_failure_to_safe_state(self):
        class FailedProcess:
            @staticmethod
            def poll():
                return 23

        state = poll_update_process_state(
            {"status": "updating", "remote_version": "0.7.6"},
            FailedProcess(),
        )
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["return_code"], 23)
        self.assertEqual(state["log"], "logs/update.log")
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), state["error"])


if __name__ == "__main__":
    unittest.main()
