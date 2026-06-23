import unittest
from pathlib import Path

from app.updater import normalise_version, update_script_for_system, version_label, version_tuple


class UpdaterVersionTests(unittest.TestCase):
    def test_normalise_release_tag_versions(self):
        self.assertEqual(normalise_version("v0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("v.0.4.0"), "0.4.0")
        self.assertEqual(normalise_version("0.4.0"), "0.4.0")

    def test_version_label_uses_public_format(self):
        self.assertEqual(version_label("v0.4.0"), "v.0.4.0")

    def test_version_tuple_compares_release_tags(self):
        self.assertGreater(version_tuple("v0.4.1"), version_tuple("v0.4.0"))

    def test_linux_uses_linux_update_script(self):
        self.assertEqual(update_script_for_system(Path("/app"), "Linux"), Path("/app/update-linux.sh"))


if __name__ == "__main__":
    unittest.main()
