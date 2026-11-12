from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from app.factory_reset import FACTORY_RESET_DIRECTORIES, factory_reset_local_state
from app.paths import migrate_project_data


class FactoryResetTests(unittest.TestCase):
    def test_reset_scope_includes_every_managed_download_location(self):
        self.assertIn("models", FACTORY_RESET_DIRECTORIES)
        self.assertIn("tts", FACTORY_RESET_DIRECTORIES)
        self.assertIn("cuda-runtime", FACTORY_RESET_DIRECTORIES)

    def test_reset_removes_known_state_and_preserves_unrelated_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            support = root / "support"
            models = root / "source-models"
            for directory in FACTORY_RESET_DIRECTORIES:
                path = support / directory
                path.mkdir(parents=True)
                (path / "before-reset.txt").write_text(directory, encoding="utf-8")
            models.mkdir()
            (models / "translation.bin").write_bytes(b"model")
            unrelated = support / "keep-me.txt"
            unrelated.write_text("keep", encoding="utf-8")

            result = factory_reset_local_state(support_dir=support, models_dir=models)

            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")
            self.assertFalse(models.exists())
            for directory in FACTORY_RESET_DIRECTORIES:
                if directory != "data":
                    self.assertFalse((support / directory).exists())
            self.assertEqual(result.marker.read_text(encoding="utf-8"), "factory-reset\n")
            self.assertFalse((support / ".factory-reset-staging").exists())

    def test_reset_does_not_follow_a_known_directory_symlink(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            support = root / "support"
            external = root / "external"
            support.mkdir()
            external.mkdir()
            protected = external / "keep.txt"
            protected.write_text("keep", encoding="utf-8")
            try:
                (support / "logs").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows account lacks symbolic-link privilege")
                raise

            factory_reset_local_state(support_dir=support, models_dir=support / "models")

            self.assertEqual(protected.read_text(encoding="utf-8"), "keep")
            self.assertFalse((support / "logs").exists())

    def test_reset_rejects_a_broad_home_target(self):
        with self.assertRaises(ValueError):
            factory_reset_local_state(support_dir=Path.home(), models_dir=Path.home() / "models")

    def test_factory_reset_marker_blocks_legacy_data_migration(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            destination = root / "support" / "data" / "runtime_config.json"
            legacy = project / "data" / "runtime_config.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"translation_enabled": true}', encoding="utf-8")
            destination.parent.mkdir(parents=True)
            (destination.parent / "factory_reset.flag").write_text("factory-reset\n", encoding="utf-8")

            with patch("app.paths.PROJECT_ROOT", project):
                migrate_project_data("runtime_config.json", destination)

            self.assertFalse(destination.exists())

    def test_factory_reset_ignores_legacy_environment_credentials(self):
        from app import main

        with patch.object(main, "factory_reset_requested", return_value=True), patch.object(
            main, "get_auth_config"
        ) as get_auth:
            main.auth_config()

        self.assertIsNone(get_auth.call_args.kwargs["env_password"])
        self.assertIsNone(get_auth.call_args.kwargs["env_secret"])

    def test_auth_guards_also_ignore_environment_password_during_factory_reset(self):
        from app import auth

        with TemporaryDirectory() as temporary:
            marker = Path(temporary) / "factory_reset.flag"
            marker.write_text("factory-reset\n", encoding="utf-8")
            with patch.object(auth, "FACTORY_RESET_MARKER", marker), patch.object(
                auth, "_load_store", return_value={}
            ):
                config = auth.get_auth_config(
                    max_age_seconds=3600,
                    env_password="legacy-password",
                    env_secret="legacy-secret",
                )

            self.assertTrue(config.needs_setup)
            self.assertIsNone(config.password)
            self.assertNotEqual(config.secret, "legacy-secret")

    def test_native_and_linux_surfaces_require_deliberate_confirmation(self):
        root = Path(__file__).resolve().parents[1]
        desktop = (root / "desktop/src/index.html").read_text(encoding="utf-8")
        desktop_js = (root / "desktop/src/main.js").read_text(encoding="utf-8")
        rust = (root / "desktop/src-tauri/src/lifecycle.rs").read_text(encoding="utf-8")
        linux = (root / "factory-reset-linux.sh").read_text(encoding="utf-8")
        manifest = (root / "packaging/linux/release-manifest.txt").read_text(encoding="utf-8")
        setup = (root / "app/templates/setup.html").read_text(encoding="utf-8")
        setup_theme = (root / "app/static/setup-theme.js").read_text(encoding="utf-8")

        self.assertIn('id="factoryResetApplication"', desktop)
        self.assertIn('id="factoryResetConfirmation"', desktop)
        self.assertIn("value !== 'RESET'", desktop_js)
        self.assertIn("localStorage.clear()", desktop_js)
        self.assertIn("sessionStorage.clear()", desktop_js)
        self.assertIn("factory_reset_application", rust)
        self.assertIn('Type RESET to continue', linux)
        self.assertIn("factory-reset-linux.sh", manifest)
        self.assertIn('data-factory-reset=', setup)
        self.assertIn("localStorage.clear()", setup_theme)
        self.assertIn("sessionStorage.clear()", setup_theme)
        self.assertIn('.env("XDG_CACHE_HOME", &cache_dir)', rust)
        self.assertIn('.env("HF_HOME", &huggingface_cache)', rust)


if __name__ == "__main__":
    unittest.main()
