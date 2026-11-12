"""Guard the single shared web-application source used by every platform."""

from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CrossPlatformStructureTests(unittest.TestCase):
    def test_shared_resource_directory_uses_canonical_lowercase_name(self) -> None:
        child_names = {path.name for path in (ROOT / "app").iterdir()}
        self.assertIn("resources", child_names)
        self.assertNotIn("Resources", child_names)

    def test_frozen_engine_bundles_all_shared_browser_asset_roots(self) -> None:
        spec = (ROOT / "packaging" / "engine" / "church_cap_engine.spec").read_text(
            encoding="utf-8"
        )
        for shared_path in (
            'ROOT / "app" / "templates"',
            'ROOT / "app" / "static"',
            'ROOT / "app" / "locales"',
            'ROOT / "app" / "resources"',
            'ROOT / "docs" / "legal"',
            'ROOT / "engine" / "entrypoint.py"',
        ):
            with self.subTest(shared_path=shared_path):
                self.assertIn(shared_path, spec)

    def test_desktop_wrapper_does_not_duplicate_shared_web_trees(self) -> None:
        desktop = ROOT / "desktop"
        for duplicated_path in (
            desktop / "app",
            desktop / "src" / "app",
            desktop / "src" / "templates",
            desktop / "src" / "static",
        ):
            with self.subTest(path=duplicated_path):
                self.assertFalse(duplicated_path.exists())

    def test_windows_engine_hides_console_without_disabling_protocol_pipes(self) -> None:
        spec = (ROOT / "packaging" / "engine" / "church_cap_engine.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("console=True", spec)
        self.assertIn('hide_console="hide-early" if sys.platform == "win32" else None', spec)
        self.assertNotIn("console=False", spec)

        main = (ROOT / "desktop" / "src-tauri" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )
        lifecycle = (
            ROOT / "desktop" / "src-tauri" / "src" / "lifecycle.rs"
        ).read_text(encoding="utf-8")
        self.assertIn('windows_subsystem = "windows"', main)
        self.assertIn("CREATE_NO_WINDOW", lifecycle)
        self.assertIn("command.creation_flags(CREATE_NO_WINDOW)", lifecycle)

        shared_app = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW', shared_app)
        self.assertGreaterEqual(shared_app.count("**_background_process_kwargs()"), 3)

    def test_windows_installer_has_canonical_branding_and_optional_cuda_page(self) -> None:
        overlay = (
            ROOT / "desktop" / "src-tauri" / "tauri.windows.conf.json"
        ).read_text(encoding="utf-8")
        hooks = (
            ROOT
            / "desktop"
            / "src-tauri"
            / "installer"
            / "windows"
            / "installer-hooks.nsh"
        ).read_text(encoding="utf-8")
        self.assertIn('"headerImage": "installer/windows/header.bmp"', overlay)
        self.assertIn('"sidebarImage": "installer/windows/sidebar.bmp"', overlay)
        self.assertIn('"installerHooks": "installer/windows/installer-hooks.nsh"', overlay)
        self.assertIn('"installerIcon": "installer/windows/installer-icon.ico"', overlay)
        self.assertIn("Install optional NVIDIA CUDA acceleration", hooks)
        self.assertIn("--install-windows-cuda-runtime", hooks)
        self.assertIn("cuda-install-requested.flag", hooks)
        self.assertIn("cuda-installer-handoff.log", hooks)
        self.assertIn('IfFileExists "$APPDATA\\Church Cap\\data\\cuda-install-requested.flag" 0 ChurchCapCudaDone', hooks)
        self.assertLess(hooks.index("cuda-install-requested.flag"), hooks.index("!macro NSIS_HOOK_POSTINSTALL"))
        self.assertIn("cublasLt64_12.dll", hooks)
        self.assertIn("MUI_WELCOMEFINISHPAGE_BITMAP_STRETCH AspectFitHeight", hooks)

        installer_dir = ROOT / "desktop" / "src-tauri" / "installer" / "windows"
        header = (installer_dir / "header.bmp").read_bytes()
        sidebar = (installer_dir / "sidebar.bmp").read_bytes()
        self.assertEqual(struct.unpack_from("<ii", header, 18), (450, 171))
        self.assertEqual(struct.unpack_from("<ii", sidebar, 18), (492, 942))

        icon = (installer_dir / "installer-icon.ico").read_bytes()
        icon_count = struct.unpack_from("<H", icon, 4)[0]
        self.assertGreaterEqual(icon_count, 8)
        for index in range(icon_count):
            image_offset = struct.unpack_from("<I", icon, 18 + (index * 16))[0]
            self.assertNotEqual(icon[image_offset : image_offset + 8], b"\x89PNG\r\n\x1a\n")

        shared_app = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('CUDA_RUNTIME_REQUEST_MARKER = "cuda-install-requested.flag"', shared_app)
        self.assertIn("await asyncio.to_thread(start_cuda_runtime_install)", shared_app)
        self.assertIn("_windows_cuda_runtime_files_ready()", shared_app)
        self.assertIn('origin="installer first-launch retry"', shared_app)

        branding = (ROOT / "scripts" / "release" / "generate-windows-installer-branding.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("church-cap-installer-sidebar-background.png", branding)
        self.assertIn("$Graphics.DrawImage($SidebarBackground, $Area)", branding)
        self.assertNotIn("Add-RadialGlow", branding)
        self.assertNotIn("FromArgb(110, 231, 168)", branding)
        self.assertTrue(
            (ROOT / "assets" / "branding" / "church-cap-installer-sidebar-background.png").is_file()
        )

    def test_common_wrapper_configuration_keeps_platform_resources_external(self) -> None:
        common_config = (
            ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
        ).read_text(encoding="utf-8")
        self.assertIn('"resources": []', common_config)
        self.assertNotIn("engine-macos-arm64", common_config)
        self.assertNotIn("engine-windows-x64", common_config)

    def test_native_wrapper_uses_the_existing_cross_platform_data_locations(self) -> None:
        lifecycle = (
            ROOT / "desktop" / "src-tauri" / "src" / "lifecycle.rs"
        ).read_text(encoding="utf-8")
        self.assertIn('join("Application Support")', lifecycle)
        self.assertIn('PathBuf::from(roaming).join("Church Cap")', lifecycle)
        self.assertIn('join(".local").join("share").join("church-cap")', lifecycle)
        # The engine must be pointed at the canonical root, never at Tauri's
        # identifier-derived folder.
        self.assertIn('.env("CHURCH_CAP_DATA_DIR", &data_dir)', lifecycle)
        self.assertIn("let data_dir = church_cap_data_dir(app)?;", lifecycle)
        self.assertNotIn("let data_dir = app\n            .path()\n            .app_local_data_dir()", lifecycle)

    def test_native_wrapper_migrates_pre_v090_desktop_data_before_engine_start(self) -> None:
        # Every desktop build before 9a3ec57 stored its data in Tauri's
        # app_local_data_dir(). The legacy path must be resolved with that same
        # call so it matches on each platform, and the move must happen before
        # the engine can mistake an empty canonical folder for a fresh install.
        lifecycle = (
            ROOT / "desktop" / "src-tauri" / "src" / "lifecycle.rs"
        ).read_text(encoding="utf-8")
        self.assertIn("app.path().app_local_data_dir().ok()", lifecycle)
        start_body = lifecycle.split("let data_dir = church_cap_data_dir(app)?;", 1)[1]
        self.assertLess(
            start_body.index("crate::recovery::migrate_legacy_app_data(&legacy_dir, &data_dir)?;"),
            start_body.index("let mut command = Command::new(&engine_path);"),
        )
        factory_reset = lifecycle.split("pub fn factory_reset_application(", 1)[1]
        self.assertIn("crate::recovery::clear_legacy_app_data(&legacy_dir, &data_dir)", factory_reset)
        recovery = (
            ROOT / "desktop" / "src-tauri" / "src" / "recovery.rs"
        ).read_text(encoding="utf-8")
        for guard in (
            "AUTH_PRIMARY_FILE).is_file()",
            "FACTORY_RESET_MARKER).is_file()",
            "LEGACY_MIGRATION_MARKER).is_file()",
        ):
            self.assertIn(guard, recovery.split("pub fn legacy_root_needs_migration(", 1)[1].split("pub fn migrate_legacy_app_data(", 1)[0])

    def test_public_updater_key_is_committable_without_weakening_secret_scan(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github" / "workflows" / "python-check.yml"
        ).read_text(encoding="utf-8")
        public_key_path = "packaging/updater/church-cap-updater-public.key"
        self.assertIn(f"!{public_key_path}", gitignore)
        self.assertIn(f"-path './{public_key_path}' -prune", workflow)
        self.assertIn("pip install -r requirements-packaged.txt", workflow)
        self.assertIn("pip-audit --requirement requirements-packaged.txt", workflow)

    def test_windows_overlay_maps_only_the_native_engine_bundle(self) -> None:
        windows_config = (
            ROOT / "desktop" / "src-tauri" / "tauri.windows.conf.json"
        ).read_text(encoding="utf-8")
        self.assertIn("../../dist/engine-windows-x64/church-cap-engine/", windows_config)
        self.assertIn('"engine/church-cap-engine/"', windows_config)
        self.assertNotIn('"app/"', windows_config)

    def test_windows_small_engine_requires_hash_pinned_cpu_pytorch(self) -> None:
        overlay = (
            ROOT / "packaging" / "engine" / "requirements-windows-cpu.txt"
        ).read_text(encoding="utf-8")
        build = (ROOT / "scripts" / "release" / "build-engine-windows.ps1").read_text(encoding="utf-8")
        handoff = (
            ROOT / "docs" / "project" / "WINDOWS_V0.9.0_BUILD_HANDOFF.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "torch-2.13.0-cp312-cp312-win_amd64.whl"
            "#sha256=024c6cc0c1b085f2f91f20a3dc27b0471d021c31ce84b81be3afdc39f791fd9d",
            overlay,
        )
        self.assertIn('print(torch.__version__, torch.version.cuda)', build)
        self.assertIn("$Torch -notmatch '^2\\.13\\.0(?:\\+cpu)? None$'", build)
        self.assertLess(
            handoff.index("pip install --no-cache-dir -r packaging\\engine\\requirements-windows-cpu.txt"),
            handoff.index("pip install -r requirements-packaged.txt"),
        )


if __name__ == "__main__":
    unittest.main()
