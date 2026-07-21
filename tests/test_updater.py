import unittest
from pathlib import Path

from app.updater import normalise_version, parse_version_from_settings, update_script_for_system, version_label, version_tuple


class UpdaterVersionTests(unittest.TestCase):
    def test_normalise_release_tag_versions(self):
        self.assertEqual(normalise_version("v0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("v.0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("0.4.0"), "0.4.0")

    def test_version_label_uses_public_format(self):
        self.assertEqual(version_label("v0.4.0"), "v0.4.0")

    def test_settings_version_parser_reads_code_owned_constant(self):
        self.assertEqual(parse_version_from_settings('APP_VERSION = "0.7.1"'), "0.7.1")

    def test_settings_version_parser_keeps_legacy_release_compatibility(self):
        self.assertEqual(parse_version_from_settings('app_version: str = "0.6.0"'), "0.6.0")

    def test_macos_and_linux_updater_reads_code_owned_version(self):
        source = (Path(__file__).resolve().parents[1] / "update-macos.sh").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION", source)
        self.assertIn("app_version[[:space:]]*:", source)
        self.assertIn('Current version: v${CURRENT_VERSION:-unknown}', source)
        self.assertNotIn('Current version: v.${CURRENT_VERSION:-unknown}', source)

    def test_windows_updater_reads_code_owned_version(self):
        source = (Path(__file__).resolve().parents[1] / "update-windows.ps1").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION\\s*=", source)
        self.assertIn("app_version\\s*:\\s*str", source)
        self.assertIn('Current version: v$CurrentVersion', source)
        self.assertNotIn('Current version: v.$CurrentVersion', source)

    def test_version_tuple_compares_release_tags(self):
        self.assertGreater(version_tuple("v0.4.1"), version_tuple("v0.4.0"))

    def test_linux_uses_linux_update_script(self):
        self.assertEqual(update_script_for_system(Path("/app"), "Linux"), Path("/app/update-linux.sh"))


if __name__ == "__main__":
    unittest.main()
