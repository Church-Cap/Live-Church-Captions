from pathlib import Path
import unittest


class LinuxScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages = Path("scripts/linux-system-packages.sh").read_text(encoding="utf-8")
        cls.python_runtime = Path("scripts/linux-python-runtime.sh").read_text(encoding="utf-8")
        cls.setup = Path("setup-linux.sh").read_text(encoding="utf-8")
        cls.start = Path("start-linux.sh").read_text(encoding="utf-8")
        cls.cuda_installer = Path("install-cuda-runtime-linux.sh").read_text(encoding="utf-8")
        cls.cuda_helper = Path("scripts/linux-cuda-runtime.sh").read_text(encoding="utf-8")
        cls.update = Path("update-linux.sh").read_text(encoding="utf-8")
        cls.shared_update = Path("scripts/update-unix.sh").read_text(encoding="utf-8")
        cls.factory_reset = Path("factory-reset-linux.sh").read_text(encoding="utf-8")
        cls.release_manifest = Path("packaging/linux/release-manifest.txt").read_text(encoding="utf-8")
        cls.release_checker = Path("scripts/release/check-linux-cli-release.py").read_text(encoding="utf-8")

    def test_common_package_managers_are_detected(self):
        for manager in ("dnf", "apt-get", "zypper", "pacman", "apk", "yum"):
            self.assertIn(manager, self.packages)

    def test_active_linux_firewall_managers_are_detected(self):
        self.assertIn("linux_active_firewall_manager", self.packages)
        self.assertIn("firewall-cmd", self.packages)
        self.assertIn("ufw", self.packages)

    def test_python_floor_is_checked(self):
        self.assertIn("(3, 10) <= sys.version_info[:2] < (3, 14)", self.packages)
        self.assertIn("python3.13", self.packages)
        self.assertIn("find_supported_linux_python", self.setup)

    def test_unsupported_system_python_gets_verified_project_local_python(self):
        self.assertIn('CHURCH_CAP_UV_VERSION="0.12.3"', self.python_runtime)
        self.assertIn('CHURCH_CAP_MANAGED_PYTHON_VERSION="3.12"', self.python_runtime)
        self.assertIn("releases.astral.sh/github/uv/releases/download", self.python_runtime)
        for digest in (
            "600cf9a742aca00d292673b16b5acffaa7b8c269a364ad0c2e79498dcb1fe101",
            "bb66cb52e7b1823aed1183630d8d8e5c958840d584a4c55ec10a4cfc168dcca2",
            "0643b9fb8c9fb27458e709ce6ff939695013c41975ff7b02d3f3b138d8d4bdb3",
            "fa513fca1eb2913334c944fe9adbdd410274a1cbe8dd05d03699a9eb85311d4e",
        ):
            self.assertIn(digest, self.python_runtime)
        self.assertIn('UV_PYTHON_INSTALL_DIR="$app_dir/.tools/python"', self.python_runtime)
        self.assertIn('UV_PYTHON_BIN_DIR="$app_dir/.tools/python-bin"', self.python_runtime)
        self.assertIn('python install "$CHURCH_CAP_MANAGED_PYTHON_VERSION"', self.python_runtime)
        self.assertNotIn("curl |", self.python_runtime)
        self.assertNotIn("curl -sSf |", self.python_runtime)
        self.assertIn('install_managed_linux_python "$APP_DIR" "$INSTALL_TMP"', self.setup)
        self.assertIn("tar", self.packages)

    def test_linux_setup_limits_temporary_disk_and_reports_quota_failures(self):
        self.assertIn("require_linux_install_space", self.setup)
        self.assertIn("PIP_NO_CACHE_DIR=1", self.setup)
        self.assertIn("--no-cache-dir -r requirements.txt", self.setup)
        self.assertIn("Disk quota exceeded", self.setup)
        self.assertIn(".church-cap-install-incomplete", self.setup)
        self.assertLess(
            self.setup.index("Remove only this Church Cap .venv"),
            self.setup.index('require_linux_install_space "$APP_DIR"'),
        )
        self.assertIn("linux_storage_diagnostics", self.packages)

    def test_python_packages_stay_in_virtual_environment(self):
        self.assertIn(".venv/bin/python", self.setup)
        self.assertIn('"$VENV_PY" -m pip install --no-cache-dir -r requirements.txt', self.setup)

    def test_linux_start_uses_dual_port_runner(self):
        self.assertIn('exec "$VENV_PY" scripts/run-dual.py', self.start)

    def test_linux_cuda_runtime_is_optional_and_project_local(self):
        self.assertIn("install-cuda-runtime-linux.sh", self.setup)
        self.assertIn("status.nvidia_smi_available or status.cuda_device_count > 0", self.setup)
        self.assertIn("Install the local CUDA runtime libraries inside .venv now? [y/N]", self.setup)
        self.assertIn('case "${cuda_answer:-no}"', self.setup)
        self.assertIn("y|Y|yes|YES) ./install-cuda-runtime-linux.sh", self.setup)
        self.assertIn("nvidia-cublas-cu12", self.cuda_installer)
        self.assertIn('"nvidia-cudnn-cu12==9.*"', self.cuda_installer)
        self.assertIn("--force-reinstall --no-cache-dir", self.cuda_installer)
        self.assertIn('prepare_linux_python_cuda_library_path "$VENV_PY"', self.start)
        self.assertIn("nvidia.cublas.lib", self.cuda_helper)
        self.assertIn("nvidia.cudnn.lib", self.cuda_helper)

    def test_linux_setup_offers_least_privilege_audience_firewall_rule(self):
        self.assertIn("Checking recommended audience firewall access", self.setup)
        self.assertIn("Add the recommended audience firewall rule now? [y/N]", self.setup)
        self.assertIn('case "${firewall_answer:-no}"', self.setup)
        self.assertIn("allow_linux_audience_port", self.setup)
        self.assertIn('run_as_root firewall-cmd --permanent --zone="$zone" --add-port="${port}/tcp"', self.packages)
        self.assertIn('run_as_root ufw allow "${port}/tcp"', self.packages)
        self.assertIn("It does not open operator port 9090", self.setup)
        self.assertNotIn('add-port="9090/tcp"', self.packages)

    def test_linux_updater_selects_curated_unified_release_asset(self):
        self.assertIn('CHURCH_CAP_UPDATE_TAG_PREFIX=""', self.update)
        self.assertIn('CHURCH_CAP_UPDATE_ASSET_NAME="Church-Cap-Linux-CLI.tar.gz"', self.update)
        self.assertIn('CHURCH_CAP_UPDATE_PLATFORM="linux"', self.update)
        self.assertIn('scripts/update-unix.sh', self.update)
        self.assertIn('LATEST_RELEASE_URL="https://api.github.com/repos/Church-Cap/Live-Church-Captions/releases/latest"', self.shared_update)
        self.assertIn('REMOTE_TAG="${RELEASE_TAG_PREFIX}v$REMOTE_VERSION"', self.shared_update)
        self.assertIn("Verifying the published Linux archive checksum", self.shared_update)
        self.assertIn('tar -tzf "$ARCHIVE_PATH"', self.shared_update)
        self.assertIn('EXTRACTED_DIR="$TMP_DIR/Church-Cap-Linux-CLI"', self.shared_update)
        self.assertIn('"scripts/linux-python-runtime.sh"', self.shared_update)
        self.assertIn('"engine/entrypoint.py"', self.shared_update)
        self.assertIn('"engine/protocol.py"', self.shared_update)
        self.assertGreaterEqual(self.shared_update.count(".env|.venv|.tools|.git|data|logs|certs"), 2)

    def test_linux_release_manifest_is_curated(self):
        for required in (
            "app",
            "engine",
            "config",
            "setup-linux.sh",
            "start-linux.sh",
            "update-linux.sh",
            "scripts/run-dual.py",
            "scripts/linux-python-runtime.sh",
            "factory-reset-linux.sh",
            "scripts/factory-reset.py",
        ):
            self.assertIn(required, self.release_manifest.splitlines())

    def test_linux_factory_reset_requires_confirmation_and_reopens_setup(self):
        self.assertIn('Type RESET to continue', self.factory_reset)
        self.assertIn('scripts/factory-reset.py --confirm RESET', self.factory_reset)
        self.assertIn('The complete first-time setup will open', Path("scripts/factory-reset.py").read_text(encoding="utf-8"))
        for forbidden in ("desktop", "dist", "tests", ".git", "work"):
            self.assertNotIn(forbidden, self.release_manifest.splitlines())
        self.assertNotIn("update-macos.sh", self.release_manifest.splitlines())
        self.assertIn("scripts/update-unix.sh", self.release_manifest.splitlines())
        self.assertIn('"engine/entrypoint.py"', self.release_checker)
        self.assertIn('"engine/protocol.py"', self.release_checker)


if __name__ == "__main__":
    unittest.main()
