import unittest

from app.updater import normalise_version, version_label, version_tuple


class UpdaterVersionTests(unittest.TestCase):
    def test_normalise_release_tag_versions(self):
        self.assertEqual(normalise_version("v0.3.0"), "0.3.0")
        self.assertEqual(normalise_version("v.0.3.0"), "0.3.0")
        self.assertEqual(normalise_version("0.3.0"), "0.3.0")

    def test_version_label_uses_public_format(self):
        self.assertEqual(version_label("v0.3.0"), "v.0.3.0")

    def test_version_tuple_compares_release_tags(self):
        self.assertGreater(version_tuple("v0.3.1"), version_tuple("v0.3.0"))


if __name__ == "__main__":
    unittest.main()
