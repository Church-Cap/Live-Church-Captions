import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import runtime_config


class RuntimeConfigPersistenceTests(unittest.TestCase):
    def paths(self, root: Path):
        primary = root / "data" / "runtime_config.json"
        backup = root / "data" / "runtime_config.backup.json"
        return patch.multiple(runtime_config, CONFIG_PATH=primary, BACKUP_PATH=backup)

    def test_translation_settings_survive_a_fresh_load(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.paths(root), patch.object(runtime_config, "migrate_project_data"):
                saved = runtime_config.set_translation_config(
                    True,
                    ["en", "fr", "es"],
                    4,
                    "demo",
                    "restricted",
                    "pinned_first",
                    False,
                    "stable",
                )
                loaded = runtime_config.load_runtime_config()

            self.assertEqual(loaded, saved)
            self.assertEqual(loaded["translation_language_policy"], "restricted")
            self.assertEqual(loaded["translation_allowed_languages"], ["en", "es", "fr"])
            self.assertFalse(loaded["translation_language_requests_enabled"])
            self.assertEqual(json.loads((root / "data" / "runtime_config.json").read_text()), saved)

    def test_corrupt_primary_recovers_from_last_complete_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.paths(root), patch.object(runtime_config, "migrate_project_data"):
                saved = runtime_config.set_translation_config(
                    True, ["en", "de"], 2, "demo", "restricted"
                )
                runtime_config.CONFIG_PATH.write_text('{"translation_enabled":', encoding="utf-8")
                loaded = runtime_config.load_runtime_config()

            self.assertEqual(loaded, saved)
            self.assertEqual(loaded["translation_allowed_languages"], ["de", "en"])

    def test_atomic_save_leaves_no_temporary_settings_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.paths(root), patch.object(runtime_config, "migrate_project_data"):
                runtime_config.set_operator_theme("dark")

            temporary_files = list((root / "data").glob("*.tmp")) + list(
                (root / "data").glob(".*.tmp")
            )
            self.assertEqual(temporary_files, [])
            if runtime_config.os.name == "posix":
                self.assertEqual(
                    (root / "data" / "runtime_config.json").stat().st_mode & 0o077,
                    0,
                )

    def test_atomic_save_retries_a_transient_windows_replace_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_replace = runtime_config.os.replace
            attempts = 0

            def transient_replace(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("simulated antivirus lock")
                return real_replace(source, destination)

            with self.paths(root), patch.object(
                runtime_config, "migrate_project_data"
            ), patch.object(runtime_config.os, "replace", side_effect=transient_replace), patch.object(
                runtime_config.time, "sleep"
            ):
                saved = runtime_config.set_operator_theme("dark")

            self.assertEqual(attempts, 4)
            self.assertEqual(saved["operator_theme"], "dark")
            self.assertEqual(
                json.loads((root / "data" / "runtime_config.json").read_text())["operator_theme"],
                "dark",
            )

    def test_language_api_saves_the_policy_returned_to_the_operator(self):
        from fastapi.testclient import TestClient

        from app import main

        original = main.hub.translation_state()
        original_requests_enabled = main.hub.translation_language_requests_enabled
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.paths(root), patch.object(
                    runtime_config, "migrate_project_data"
                ), patch.object(
                    main,
                    "translation_allowed_for_current_deployment",
                    return_value=(True, {"capabilities": {}}),
                ):
                    main.app.dependency_overrides[main.require_operator] = lambda: None
                    response = TestClient(main.app).post(
                        "/api/translation",
                        json={
                            "translation_enabled": True,
                            "translation_provider": "demo",
                            "translation_language_policy": "restricted",
                            "translation_priority_mode": "pinned_first",
                            "translation_timing_mode": "responsive",
                            "translation_language_requests_enabled": False,
                            "translation_allowed_languages": ["en", "fr"],
                            "translation_max_active_languages": 2,
                        },
                    )
                    main.app.dependency_overrides.pop(main.require_operator, None)

                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()
                    self.assertEqual(payload["status"], "saved")
                    self.assertEqual(payload["language_policy"], "restricted")
                    self.assertEqual(payload["allowed_languages"], ["en", "fr"])
                    loaded = runtime_config.load_runtime_config()
                    self.assertEqual(loaded["translation_language_policy"], "restricted")
                    self.assertEqual(loaded["translation_allowed_languages"], ["en", "fr"])
        finally:
            main.app.dependency_overrides.pop(main.require_operator, None)
            main.hub.configure_translation(
                enabled=bool(original["enabled"]),
                provider=str(original["provider"]),
                allowed_languages=list(original["allowed_languages"]),
                max_active_languages=int(original["max_active_languages"]),
                language_policy=str(original["language_policy"]),
                language_requests_enabled=original_requests_enabled,
                priority_mode=str(original["priority_mode"]),
                timing_mode=str(original["timing_mode"]),
            )

    def test_turning_translation_off_saves_and_keeps_the_selected_languages(self):
        """Reproduced on the owner's Mac on 2026-09-17: with the onboarding
        language pack still selected, choosing Off on the Operator page was
        refused client-side, so the server and every audience device kept
        translation on while the page showed Off. Off must save as disabled,
        audiences must receive English only, and the selection must survive
        for when translation is turned back on."""
        from fastapi.testclient import TestClient

        from app import main

        original = main.hub.translation_state()
        original_requests_enabled = main.hub.translation_language_requests_enabled
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.paths(root), patch.object(
                    runtime_config, "migrate_project_data"
                ), patch.object(
                    main,
                    "translation_allowed_for_current_deployment",
                    return_value=(True, {"capabilities": {}}),
                ):
                    main.app.dependency_overrides[main.require_operator] = lambda: None
                    client = TestClient(main.app)
                    body = {
                        "translation_enabled": False,
                        "translation_provider": "disabled",
                        "translation_language_policy": "restricted",
                        "translation_priority_mode": "pinned_first",
                        "translation_timing_mode": "responsive",
                        "translation_language_requests_enabled": True,
                        "translation_allowed_languages": ["en", "fr", "es"],
                        "translation_max_active_languages": 4,
                    }
                    response = client.post("/api/translation", json=body)
                    main.app.dependency_overrides.pop(main.require_operator, None)

                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()
                    self.assertEqual(payload["status"], "saved")
                    self.assertFalse(payload["enabled"])
                    self.assertEqual(payload["allowed_languages"], ["en", "es", "fr"])
                    loaded = runtime_config.load_runtime_config()
                    self.assertFalse(loaded["translation_enabled"])
                    self.assertEqual(loaded["translation_provider"], "disabled")
                    self.assertEqual(loaded["translation_allowed_languages"], ["en", "es", "fr"])

                    public = client.get("/api/languages").json()["translation"]
                    self.assertFalse(public["enabled"])
                    self.assertEqual(public["available_languages"], ["en"])
        finally:
            main.app.dependency_overrides.pop(main.require_operator, None)
            main.hub.configure_translation(
                enabled=bool(original["enabled"]),
                provider=str(original["provider"]),
                allowed_languages=list(original["allowed_languages"]),
                max_active_languages=int(original["max_active_languages"]),
                language_policy=str(original["language_policy"]),
                language_requests_enabled=original_requests_enabled,
                priority_mode=str(original["priority_mode"]),
                timing_mode=str(original["timing_mode"]),
            )

    def test_operator_page_never_refuses_to_save_translation_off(self):
        operator = (
            Path(__file__).resolve().parents[1] / "app" / "templates" / "operator.html"
        ).read_text(encoding="utf-8")
        save = operator.split("async function saveTranslationSettings()", 1)[1].split(
            "async function savePrivacySettings()", 1
        )[0]
        self.assertNotIn("Translation mode is Off", save)
        self.assertNotIn("providerSelect?.focus();\n        return;", save)
        self.assertIn("fetch('/api/translation'", save)
        self.assertIn("kept for when you turn translation back on", save)


if __name__ == "__main__":
    unittest.main()
