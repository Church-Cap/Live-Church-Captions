from pathlib import Path
import unittest


class LinuxScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages = Path("scripts/linux-system-packages.sh").read_text(encoding="utf-8")
        cls.setup = Path("setup-linux.sh").read_text(encoding="utf-8")
        cls.start = Path("start-linux.sh").read_text(encoding="utf-8")

    def test_common_package_managers_are_detected(self):
        for manager in ("dnf", "apt-get", "zypper", "pacman", "apk", "yum"):
            self.assertIn(manager, self.packages)

    def test_python_floor_is_checked(self):
        self.assertIn("sys.version_info >= (3, 10)", self.packages)
        self.assertIn("find_supported_linux_python", self.setup)

    def test_python_packages_stay_in_virtual_environment(self):
        self.assertIn(".venv/bin/python", self.setup)
        self.assertIn('"$VENV_PY" -m pip install -r requirements.txt', self.setup)

    def test_linux_start_uses_dual_port_runner(self):
        self.assertIn('exec "$VENV_PY" scripts/run-dual.py', self.start)


if __name__ == "__main__":
    unittest.main()
