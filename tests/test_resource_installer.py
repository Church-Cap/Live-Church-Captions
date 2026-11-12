import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.resource_installer import (
    install_translation,
    install_tts,
    validate_tokenizer_save_paths,
    validate_packaged_installer_runtime,
)


class PackagedResourceInstallerTests(unittest.TestCase):
    def test_tokenizer_save_rejects_chat_template_path_traversal(self):
        tokenizer = type("Tokenizer", (), {"chat_template": {"../../outside": "unsafe"}})()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "unsafe chat-template path"):
                validate_tokenizer_save_paths(tokenizer, Path(temporary) / "tokenizer")

    def test_tokenizer_save_accepts_plain_chat_template_names(self):
        tokenizer = type("Tokenizer", (), {"chat_template": {"default": "safe"}})()
        with tempfile.TemporaryDirectory() as temporary:
            validate_tokenizer_save_paths(tokenizer, Path(temporary) / "tokenizer")

    def test_translation_kind_dispatch_is_allow_listed(self):
        with patch("app.resource_installer.install_argos") as argos:
            install_translation("argos_all")
        argos.assert_called_once_with(all_languages=True)

        with self.assertRaisesRegex(ValueError, "Unknown translation install kind"):
            install_translation("shell")

    def test_tts_runs_bundled_verified_voice_installer(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "app.resource_installer.resource_root", return_value=Path(temporary)
        ), patch(
            "app.resource_installer.validate_packaged_installer_runtime"
        ), patch("app.resource_installer.runpy.run_path", return_value={}) as run_path:
            install_tts("es,fr")

        run_path.assert_called_once_with(
            str(Path(temporary) / "scripts" / "install-tts-voices.py"),
            run_name="__main__",
        )

    def test_packaged_translation_models_use_application_data(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"CHURCH_CAP_RUNTIME_MODE": "packaged", "CHURCH_CAP_DATA_DIR": temporary},
            clear=True,
        ), patch("app.resource_installer.install_argos"):
            install_translation("argos")
            packages_dir = Path(os.environ["ARGOS_PACKAGES_DIR"])

        self.assertEqual(
            packages_dir,
            Path(temporary).resolve() / "models" / "argos-packages",
        )

    def test_parent_translation_caches_are_refreshed_after_install(self):
        from app.main import refresh_translation_resources

        argos = types.ModuleType("argostranslate")
        argos.__path__ = []
        translate = types.ModuleType("argostranslate.translate")
        translate.get_installed_languages = types.SimpleNamespace(cache_clear=Mock())
        with patch.dict(
            sys.modules,
            {"argostranslate": argos, "argostranslate.translate": translate},
        ), patch("app.main.hub.translator.unload_models") as unload:
            refresh_translation_resources()

        translate.get_installed_languages.cache_clear.assert_called_once_with()
        unload.assert_called_once_with()

    def test_packaged_installer_validation_checks_native_and_bundled_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "docs" / "legal").mkdir(parents=True)
            (root / "scripts" / "install-tts-voices.py").write_text("# bundled\n", encoding="utf-8")
            (root / "docs" / "legal" / "SPOKEN_LANGUAGE_MODELS.md").write_text("notices\n", encoding="utf-8")
            with patch("app.resource_installer.resource_root", return_value=root):
                validate_packaged_installer_runtime()

            (root / "scripts" / "install-tts-voices.py").unlink()
            with patch("app.resource_installer.resource_root", return_value=root):
                with self.assertRaisesRegex(RuntimeError, "installer file is missing"):
                    validate_packaged_installer_runtime()


if __name__ == "__main__":
    unittest.main()
