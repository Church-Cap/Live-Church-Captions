import unittest
from unittest.mock import Mock, patch

from starlette.requests import Request

from app.auth import AuthConfig
from app import main


def setup_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/setup",
            "raw_path": b"/setup",
            "query_string": b"",
            "headers": [(b"host", b"127.0.0.1:9090")],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 9090),
        }
    )


def auth_config(*, needs_setup: bool, secret: str) -> AuthConfig:
    return AuthConfig(
        password=None,
        secret=secret,
        max_age_seconds=3600,
        needs_setup=needs_setup,
    )


class OnboardingRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_setup_checks_pytorch_cuda_when_nvidia_driver_is_visible(self):
        performance = {
            "detected_platform": "windows",
            "hardware_acceleration": {
                "platform": "Windows",
                "cuda_available": False,
                "nvidia_driver_status": "detected",
                "nvidia_smi_available": False,
                "cuda_device_count": 0,
            },
            "recommendation": {
                "cpu_count": 8,
                "config": {"performance_preset": "balanced", "whisper_model": "base.en"},
            },
        }
        marker = Mock()
        marker.is_file.return_value = False
        with patch.object(main, "performance_status", return_value=performance), patch.object(
            main, "_total_memory_bytes", return_value=16 * 1024 ** 3
        ), patch.object(main, "_cuda_runtime_request_marker_path", return_value=marker), patch.object(
            main, "local_pytorch_cuda_available", return_value=True
        ) as cuda_probe, patch.object(
            main, "safe_deployment_context", return_value={"capabilities": {"allow_translation": True}}
        ), patch.object(main, "public_voice_catalog", return_value=[]), patch.object(
            main, "_voice_download_label", return_value="0 MB"
        ), patch.object(main, "factory_reset_requested", return_value=False), patch.object(
            main, "selected_audio_device", return_value=""
        ), patch.object(main, "setup_audio_input_context", return_value={}):
            context = main.first_run_setup_context()

        cuda_probe.assert_called_once_with()
        self.assertEqual(context["onboarding"]["recommended_language_pack"], "compatibility")
        self.assertEqual(context["onboarding"]["default_language_pack"], "compatibility")

    def test_setup_audio_inputs_are_local_filtered_and_name_stable(self):
        fake_sd = Mock()
        fake_sd.default.device = (2, 0)
        fake_sd.query_devices.return_value = [
            {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000},
            {"name": "USB Mixer", "max_input_channels": 2, "default_samplerate": 48000},
            {"name": "Built-in Microphone", "max_input_channels": 1, "default_samplerate": 44100},
        ]
        with patch.object(main, "sd", fake_sd):
            context = main.setup_audio_input_context("USB Mixer")

        self.assertTrue(context["ok"])
        self.assertEqual(context["selected"], "USB Mixer")
        self.assertEqual([device["name"] for device in context["devices"]], ["USB Mixer", "Built-in Microphone"])
        self.assertEqual(context["devices"][0]["value"], "USB Mixer")
        self.assertEqual(context["default_name"], "Built-in Microphone")

    def test_setup_audio_input_is_revalidated_before_saving(self):
        fake_sd = Mock()
        fake_sd.query_devices.return_value = {"name": "USB Mixer", "max_input_channels": 2}
        with patch.object(main, "sd", fake_sd):
            self.assertIsNone(main.validate_setup_audio_device(""))
            self.assertEqual(main.validate_setup_audio_device("USB Mixer"), "USB Mixer")
        fake_sd.query_devices.return_value = {"name": "Speakers", "max_input_channels": 0}
        with patch.object(main, "sd", fake_sd), self.assertRaisesRegex(ValueError, "not an audio input"):
            main.validate_setup_audio_device("Speakers")

    def test_translation_install_batch_advances_only_after_first_pack_finishes(self):
        previous_process = main._translation_install_process
        previous_state = main._translation_install_state
        process = Mock()
        process.poll.return_value = 0
        main._translation_install_process = process
        main._translation_install_state = {
            "status": "installing",
            "kind": "ct2small100",
            "batch_kinds": ["ct2small100", "small100"],
            "batch_index": 1,
            "progress": {"percent": 50},
        }
        try:
            with patch.object(
                main, "_current_installer_progress", return_value={"percent": 100, "detail": "First pack ready."}
            ), patch.object(main, "refresh_translation_resources"), patch.object(
                main, "_launch_translation_install", return_value={}
            ) as launch:
                state = main.translation_install_state()
            launch.assert_called_once_with(
                "small100",
                batch_kinds=("ct2small100", "small100"),
                batch_index=2,
                preserve_log=True,
            )
            self.assertEqual(state["batch_index"], 1)
        finally:
            main._translation_install_process = previous_process
            main._translation_install_state = previous_state

    def test_spoken_audio_waits_for_caption_language_install(self):
        previous_process = main._translation_install_process
        previous_state = main._translation_install_state
        previous_queue = main._onboarding_tts_queue
        process = Mock()
        process.poll.return_value = 0
        main._translation_install_process = process
        main._translation_install_state = {
            "status": "installing",
            "kind": "ct2small100",
            "batch_kinds": ["ct2small100"],
            "batch_index": 1,
            "progress": {"percent": 90},
        }
        main._onboarding_tts_queue = {"status": "waiting", "package_ids": ["es"]}
        try:
            with patch.object(
                main, "_current_installer_progress", return_value={"percent": 100, "detail": "Ready."}
            ), patch.object(main, "refresh_translation_resources"), patch.object(
                main, "start_pending_onboarding_spoken_audio_install", return_value={}
            ) as start_spoken:
                state = main.translation_install_state()
            self.assertEqual(state["status"], "complete")
            start_spoken.assert_called_once_with()
        finally:
            main._translation_install_process = previous_process
            main._translation_install_state = previous_state
            main._onboarding_tts_queue = previous_queue

    async def test_finish_page_renders_an_install_error_without_progress_data(self):
        runtime = {
            "translation_enabled": True,
            "translation_allowed_languages": ["en", "fr"],
            "translation_max_active_languages": 1,
        }
        request = setup_request()
        with patch.object(main, "load_runtime_config", return_value=runtime), patch.object(
            main, "translation_install_state", return_value={"status": "error", "error": "Test failure"}
        ), patch.object(
            main, "onboarding_spoken_audio_install_state", return_value={"status": "idle", "progress": {}}
        ), patch.object(
            main,
            "base_template_context",
            return_value={"request": request, "app_version_label": "v0.8.1"},
        ):
            response = await main.setup_finish_page(request, None)

        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn('data-state="error"', body)
        self.assertIn("Test failure", body)

    async def test_password_recovery_does_not_reapply_caption_or_language_settings(self):
        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        with patch.object(main, "auth_config", side_effect=[before, after]), patch.object(
            main, "password_recovery_requested", return_value=True
        ), patch.object(main, "_auth_form_is_valid", return_value=True), patch.object(
            main, "set_security_config"
        ) as set_security, patch.object(main, "set_operator_password") as set_password, patch.object(
            main, "clear_password_recovery_request"
        ) as clear_marker, patch.object(main, "set_performance_config") as set_performance, patch.object(
            main, "set_translation_config"
        ) as set_translation, patch.object(main, "set_operator_theme") as set_theme, patch.object(
            main, "set_audio_device"
        ) as set_audio, patch.object(
            main, "start_translation_installs"
        ) as start_install:
            response = await main.setup_operator(
                setup_request(),
                password="replacement-password",
                confirm_password="replacement-password",
                security_mode="easy_offline",
                performance_setup="recommended",
                language_packs=["efficient"],
                translation_max_active_languages=3,
                csrf_token="valid",
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/operator")
        set_security.assert_called_once_with("easy_offline")
        set_password.assert_called_once_with("replacement-password")
        clear_marker.assert_called_once_with()
        set_performance.assert_not_called()
        set_translation.assert_not_called()
        set_theme.assert_not_called()
        set_audio.assert_not_called()
        start_install.assert_not_called()

    async def test_fresh_english_setup_starts_no_translation_download(self):
        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        recommendation = {
            "translation_available": True,
            "maximum_active_languages": 4,
            "performance_config": {"performance_preset": "balanced"},
        }
        translation_config = {
            "translation_enabled": False,
            "translation_provider": "ct2small100",
            "translation_allowed_languages": ["en"],
            "translation_max_active_languages": 1,
            "translation_language_policy": "automatic",
            "translation_priority_mode": "most_viewers",
            "translation_timing_mode": "responsive",
        }
        with patch.object(main, "auth_config", side_effect=[before, after]), patch.object(
            main, "password_recovery_requested", return_value=False
        ), patch.object(main, "_auth_form_is_valid", return_value=True), patch.object(
            main, "first_run_setup_context", return_value={"onboarding": recommendation}
        ), patch.object(main, "set_performance_config") as set_performance, patch.object(
            main, "set_security_config"
        ), patch.object(main, "set_operator_theme") as set_theme, patch.object(
            main, "validate_setup_audio_device", return_value="USB Mixer"
        ) as validate_audio, patch.object(main, "set_audio_device") as set_audio, patch.object(
            main, "set_translation_config", return_value=translation_config
        ) as set_translation, patch.object(
            main.hub, "configure_translation"
        ), patch.object(main, "set_operator_password"), patch.object(
            main, "start_translation_installs"
        ) as start_install:
            response = await main.setup_operator(
                setup_request(),
                password="first-password",
                confirm_password="first-password",
                security_mode="secure_operator",
                performance_setup="recommended",
                audio_device="USB Mixer",
                language_packs=["english"],
                translation_max_active_languages=3,
                setup_theme="light",
                csrf_token="valid",
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/setup/finish")
        set_performance.assert_called_once_with({"performance_preset": "balanced"})
        validate_audio.assert_called_once_with("USB Mixer")
        set_audio.assert_called_once_with("USB Mixer")
        set_theme.assert_called_once_with("light")
        self.assertEqual(set_translation.call_args.args[0:2], (False, ["en"]))
        start_install.assert_not_called()

    async def test_fresh_translated_setup_uses_recommended_local_bundle(self):
        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        recommendation = {
            "translation_available": True,
            "maximum_active_languages": 4,
            "performance_config": {},
        }
        translation_config = {
            "translation_enabled": True,
            "translation_provider": "ct2small100",
            "translation_allowed_languages": ["en", "fr", "es"],
            "translation_max_active_languages": 2,
            "translation_language_policy": "automatic",
            "translation_priority_mode": "most_viewers",
            "translation_timing_mode": "responsive",
        }
        with patch.object(main, "auth_config", side_effect=[before, after]), patch.object(
            main, "password_recovery_requested", return_value=False
        ), patch.object(main, "_auth_form_is_valid", return_value=True), patch.object(
            main, "first_run_setup_context", return_value={"onboarding": recommendation}
        ), patch.object(main, "set_security_config"), patch.object(
            main, "set_operator_theme"
        ), patch.object(main, "set_audio_device"), patch.object(
            main, "set_translation_config", return_value=translation_config
        ) as set_translation, patch.object(main.hub, "configure_translation"), patch.object(
            main, "set_operator_password"
        ), patch.object(main, "start_translation_installs", return_value={}) as start_install:
            response = await main.setup_operator(
                setup_request(),
                password="first-password",
                confirm_password="first-password",
                security_mode="secure_operator",
                performance_setup="later",
                language_packs=["efficient"],
                translation_max_active_languages=3,
                csrf_token="valid",
            )

        self.assertEqual(response.status_code, 303)
        enabled, languages, active_limit, provider, policy, priority = set_translation.call_args.args[0:6]
        self.assertTrue(enabled)
        # Availability is Automatic, so the pack's languages come from the
        # validated install rather than a pre-ticked Restricted list.
        self.assertEqual(languages, ["en"])
        self.assertEqual(policy, "automatic")
        self.assertEqual(priority, "most_viewers")
        self.assertEqual(active_limit, 3)
        self.assertEqual(provider, "ct2small100")
        start_install.assert_called_once_with(["ct2small100"])

    async def test_translated_setup_can_queue_selected_spoken_languages(self):
        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        recommendation = {
            "translation_available": True,
            "maximum_active_languages": 4,
            "performance_config": {},
        }
        translation_config = {
            "translation_enabled": True,
            "translation_provider": "ct2small100",
            "translation_allowed_languages": ["en", "fr", "es"],
            "translation_max_active_languages": 2,
            "translation_language_policy": "automatic",
            "translation_priority_mode": "most_viewers",
            "translation_timing_mode": "responsive",
        }
        with patch.object(main, "auth_config", side_effect=[before, after]), patch.object(
            main, "password_recovery_requested", return_value=False
        ), patch.object(main, "_auth_form_is_valid", return_value=True), patch.object(
            main, "first_run_setup_context", return_value={"onboarding": recommendation}
        ), patch.object(main, "set_security_config"), patch.object(
            main, "set_operator_theme"
        ), patch.object(main, "set_audio_device"), patch.object(
            main, "set_translation_config", return_value=translation_config
        ), patch.object(main.hub, "configure_translation"), patch.object(
            main, "set_operator_password"
        ), patch.object(main, "clear_onboarding_spoken_audio_install") as clear_spoken, patch.object(
            main, "schedule_onboarding_spoken_audio_install", return_value={}
        ) as queue_spoken, patch.object(
            main, "start_translation_installs", return_value={}
        ) as start_install:
            response = await main.setup_operator(
                setup_request(),
                password="first-password",
                confirm_password="first-password",
                security_mode="secure_operator",
                performance_setup="later",
                language_packs=["efficient"],
                translation_max_active_languages=2,
                spoken_audio_setup="install",
                spoken_audio_packages=["es", "fr", "es"],
                csrf_token="valid",
            )

        self.assertEqual(response.status_code, 303)
        clear_spoken.assert_called_once_with()
        queue_spoken.assert_called_once_with(("es", "fr"))
        start_install.assert_called_once_with(["ct2small100"])

    async def test_english_only_setup_ignores_spoken_audio_fields(self):
        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        recommendation = {
            "translation_available": True,
            "maximum_active_languages": 4,
            "performance_config": {},
        }
        translation_config = {
            "translation_enabled": False,
            "translation_provider": "ct2small100",
            "translation_allowed_languages": ["en"],
            "translation_max_active_languages": 1,
            "translation_language_policy": "automatic",
            "translation_priority_mode": "most_viewers",
            "translation_timing_mode": "responsive",
        }
        with patch.object(main, "auth_config", side_effect=[before, after]), patch.object(
            main, "password_recovery_requested", return_value=False
        ), patch.object(main, "_auth_form_is_valid", return_value=True), patch.object(
            main, "first_run_setup_context", return_value={"onboarding": recommendation}
        ), patch.object(main, "set_security_config"), patch.object(
            main, "set_operator_theme"
        ), patch.object(main, "set_audio_device"), patch.object(
            main, "set_translation_config", return_value=translation_config
        ), patch.object(main.hub, "configure_translation"), patch.object(
            main, "set_operator_password"
        ), patch.object(main, "clear_onboarding_spoken_audio_install"), patch.object(
            main, "schedule_onboarding_spoken_audio_install"
        ) as queue_spoken, patch.object(main, "start_translation_installs") as start_install:
            response = await main.setup_operator(
                setup_request(),
                password="first-password",
                confirm_password="first-password",
                security_mode="secure_operator",
                performance_setup="later",
                language_packs=["english"],
                translation_max_active_languages=2,
                spoken_audio_setup="install",
                spoken_audio_packages=["es"],
                csrf_token="valid",
            )

        self.assertEqual(response.status_code, 303)
        queue_spoken.assert_not_called()
        start_install.assert_not_called()

    async def test_multiple_packs_enable_automatic_provider_and_sequential_install(self):
        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        recommendation = {
            "translation_available": True,
            "maximum_active_languages": 4,
            "performance_config": {},
        }
        translation_config = {
            "translation_enabled": True,
            "translation_provider": "both",
            "translation_allowed_languages": ["en", "fr", "ti"],
            "translation_max_active_languages": 3,
            "translation_language_policy": "automatic",
            "translation_priority_mode": "most_viewers",
            "translation_timing_mode": "responsive",
        }
        with patch.object(main, "auth_config", side_effect=[before, after]), patch.object(
            main, "password_recovery_requested", return_value=False
        ), patch.object(main, "_auth_form_is_valid", return_value=True), patch.object(
            main, "first_run_setup_context", return_value={"onboarding": recommendation}
        ), patch.object(main, "set_security_config"), patch.object(
            main, "set_operator_theme"
        ), patch.object(main, "set_audio_device"), patch.object(
            main, "set_translation_config", return_value=translation_config
        ) as set_translation, patch.object(main.hub, "configure_translation"), patch.object(
            main, "set_operator_password"
        ), patch.object(main, "start_translation_installs", return_value={}) as start_install:
            response = await main.setup_operator(
                setup_request(),
                password="first-password",
                confirm_password="first-password",
                security_mode="secure_operator",
                performance_setup="later",
                language_packs=["efficient", "compatibility"],
                translation_max_active_languages=3,
                csrf_token="valid",
            )

        self.assertEqual(response.status_code, 303)
        enabled, languages, active_limit, provider, policy, priority = set_translation.call_args.args[0:6]
        self.assertTrue(enabled)
        self.assertEqual(provider, "both")
        self.assertEqual(active_limit, 3)
        self.assertEqual(languages, ["en"])
        self.assertEqual((policy, priority), ("automatic", "most_viewers"))
        start_install.assert_called_once_with(["ct2small100", "small100"])

    async def test_translated_setup_persists_automatic_availability_with_an_empty_restricted_list(self):
        """Reproduced on the owner's Mac: onboarding used to persist Restricted
        with every pack language pre-ticked, so Restricted appeared not to
        restrict anything. The documented default is Automatic, and Restricted
        must start empty so it means what it says when an operator chooses it."""
        import tempfile
        from pathlib import Path

        from app import runtime_config

        before = auth_config(needs_setup=True, secret="before")
        after = auth_config(needs_setup=False, secret="after")
        recommendation = {
            "translation_available": True,
            "maximum_active_languages": 4,
            "performance_config": {},
        }
        original = main.hub.translation_state()
        original_requests_enabled = main.hub.translation_language_requests_enabled
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with patch.object(runtime_config, "CONFIG_PATH", root / "runtime_config.json"), patch.object(
                    runtime_config, "BACKUP_PATH", root / "runtime_config.backup.json"
                ), patch.object(runtime_config, "migrate_project_data"), patch.object(
                    main, "auth_config", side_effect=[before, after]
                ), patch.object(main, "password_recovery_requested", return_value=False), patch.object(
                    main, "_auth_form_is_valid", return_value=True
                ), patch.object(
                    main, "first_run_setup_context", return_value={"onboarding": recommendation}
                ), patch.object(main, "set_security_config"), patch.object(
                    main, "set_operator_theme"
                ), patch.object(main, "set_audio_device"), patch.object(
                    main, "set_operator_password"
                ), patch.object(main, "start_translation_installs", return_value={}):
                    response = await main.setup_operator(
                        setup_request(),
                        password="first-password",
                        confirm_password="first-password",
                        security_mode="secure_operator",
                        performance_setup="later",
                        language_packs=["efficient"],
                        translation_max_active_languages=3,
                        csrf_token="valid",
                    )
                    self.assertEqual(response.status_code, 303)
                    saved = runtime_config.load_runtime_config()

                self.assertTrue(saved["translation_enabled"])
                self.assertEqual(saved["translation_provider"], "ct2small100")
                self.assertEqual(saved["translation_language_policy"], "automatic")
                self.assertEqual(saved["translation_priority_mode"], "most_viewers")
                self.assertEqual(saved["translation_allowed_languages"], ["en"])
                self.assertTrue(saved["translation_language_requests_enabled"])
                self.assertEqual(saved["translation_max_active_languages"], 3)
                # The live hub agrees: Automatic, so availability follows the
                # validated install rather than the allowed list.
                state = main.hub.translation_state()
                self.assertEqual(state["language_policy"], "automatic")
                self.assertEqual(state["allowed_languages"], ["en"])
        finally:
            main.hub.configure_translation(
                enabled=bool(original["enabled"]),
                provider=str(original["provider"]),
                allowed_languages=list(original["allowed_languages"]),
                max_active_languages=int(original["max_active_languages"]),
                language_policy=str(original["language_policy"]),
                language_requests_enabled=original_requests_enabled,
                priority_mode=str(original["priority_mode"]),
                timing_mode=str(original["timing_mode"]),
            )


if __name__ == "__main__":
    unittest.main()
