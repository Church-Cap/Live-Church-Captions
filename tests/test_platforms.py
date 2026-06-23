import unittest

from app.platforms import performance_platform_key


class PerformancePlatformTests(unittest.TestCase):
    def test_supported_platform_names(self):
        self.assertEqual(performance_platform_key("Darwin"), "macos")
        self.assertEqual(performance_platform_key("Windows"), "windows")
        self.assertEqual(performance_platform_key("Linux"), "linux")

    def test_unknown_platform_is_unsupported(self):
        self.assertEqual(performance_platform_key("Plan9"), "unsupported")


if __name__ == "__main__":
    unittest.main()
