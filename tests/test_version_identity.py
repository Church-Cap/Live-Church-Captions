import importlib.util
import json
import re
import stat
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path


class VersionIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.version = Path("VERSION").read_text(encoding="utf-8").strip()

    def test_code_settings_and_manifests_match_version_file(self):
        source = Path("app/settings.py").read_text(encoding="utf-8")
        code_version = re.search(r'^APP_VERSION = "([^"]+)"$', source, re.MULTILINE)
        settings_version = re.search(r'^    app_version: str = "([^"]+)"$', source, re.MULTILINE)
        self.assertIsNotNone(code_version)
        self.assertIsNotNone(settings_version)
        self.assertEqual(code_version.group(1), self.version)
        self.assertEqual(settings_version.group(1), self.version)
        self.assertEqual(json.loads(Path("desktop/package.json").read_text())["version"], self.version)
        self.assertEqual(json.loads(Path("desktop/package-lock.json").read_text())["version"], self.version)
        self.assertEqual(json.loads(Path("desktop/src-tauri/tauri.conf.json").read_text())["version"], self.version)
        cargo = Path("desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
        self.assertRegex(cargo, rf'(?m)^version = "{re.escape(self.version)}"$')

    def test_environment_example_and_active_browser_assets_match(self):
        source = Path("env.example").read_text(encoding="utf-8")
        self.assertIn(f"APP_VERSION={self.version}", source)
        for name in ("captions", "display", "obs", "operator", "service_leader", "setup", "setup_finish", "setup_recovery"):
            template = Path(f"app/templates/{name}.html").read_text(encoding="utf-8")
            self.assertIn(f"v={self.version}", template)
        packaging = Path("packaging/engine/README.md").read_text(encoding="utf-8")
        self.assertIn(f"V{self.version}_IMPLEMENTATION.md", packaging)

    def test_installer_artwork_is_reusable_across_versions(self):
        macos = Path("scripts/release/generate-macos-dmg-background.swift").read_text(
            encoding="utf-8"
        )
        windows = Path("scripts/release/generate-windows-installer-branding.ps1").read_text(
            encoding="utf-8"
        )
        version_in_artwork = re.compile(r"Church Cap\s+v?\d+\.\d+\.\d+", re.IGNORECASE)
        self.assertNotRegex(macos, version_in_artwork)
        self.assertNotRegex(windows, version_in_artwork)
        self.assertIn('drawCentred("churchcap.org"', macos)

    def test_version_bump_is_allow_listed(self):
        script = Path("scripts/set-version.py").read_text(encoding="utf-8")
        self.assertIn("PLAIN_TEXT_FILES", script)
        self.assertIn("updated_cargo_lock", script)
        self.assertIn("stat.S_IMODE(path.stat().st_mode)", script)
        self.assertIn("os.chmod(temporary, existing_mode)", script)
        self.assertNotIn('"README.md",', script)
        self.assertNotIn('"requirements-packaged.txt",', script)
        self.assertNotIn('"packaging/locks/', script)

    def test_version_bump_atomic_write_preserves_executable_mode(self):
        script_path = Path("scripts/set-version.py").resolve()
        spec = importlib.util.spec_from_file_location("church_cap_set_version", script_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with TemporaryDirectory() as temporary:
            target = Path(temporary) / "release-script.sh"
            target.write_text("before\n", encoding="utf-8")
            target.chmod(0o755)
            expected_mode = stat.S_IMODE(target.stat().st_mode)
            module.atomic_write(target, "after\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), expected_mode)


if __name__ == "__main__":
    unittest.main()
