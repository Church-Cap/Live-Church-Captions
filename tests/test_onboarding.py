import re
import tempfile
import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.onboarding import (
    ONBOARDING_LANGUAGE_SELECTION_LIMIT,
    build_onboarding_recommendation,
    clamp_onboarding_active_limit,
    clear_password_recovery_request,
    onboarding_language_pack_config,
    onboarding_language_packs_config,
    password_recovery_requested,
    validate_onboarding_language_pack,
    validate_onboarding_language_packs,
    validate_onboarding_languages,
)


def performance(
    *,
    platform="Windows",
    cuda=False,
    cpu_count=8,
    preset="fast",
    model="base.en",
    memory_gb=None,
    pytorch_cuda=False,
    cuda_requested=False,
    nvidia_driver=False,
    windows_packaged_cpu_torch=False,
):
    result = {
        "detected_platform": platform.lower(),
        "hardware_acceleration": {
            "platform": platform,
            "cuda_available": cuda,
            "nvidia_driver_status": "detected" if nvidia_driver else "not_detected",
        },
        "recommendation": {
            "cpu_count": cpu_count,
            "reason": "Safe test recommendation.",
            "config": {"performance_preset": preset, "whisper_model": model},
        },
        "pytorch_cuda_available": pytorch_cuda,
        "cuda_runtime_requested": cuda_requested,
        "windows_packaged_cpu_torch": windows_packaged_cpu_torch,
    }
    if memory_gb is not None:
        result["total_memory_bytes"] = int(memory_gb * (1024 ** 3))
    return result


def deployment(*, allow=True, limit=None):
    return {"capabilities": {"allow_translation": allow, "translation_max_limit": limit, "message": "Profile status."}}


class OnboardingRecommendationTests(unittest.TestCase):
    def test_verified_windows_cuda_renders_both_packs_checked(self):
        recommendation = build_onboarding_recommendation(
            performance(cuda=True, memory_gb=32, windows_packaged_cpu_torch=True), deployment()
        )
        template = Environment(loader=FileSystemLoader("app/templates"), autoescape=True).get_template("setup.html")
        rendered = template.render(
            onboarding=recommendation,
            form_values={},
            factory_reset_requested=False,
            error=None,
            audio_input={"devices": []},
            voice_catalog=[],
            voice_catalog_total_download_label="",
            csrf_token="test",
        )
        self.assertRegex(rendered, r'id="languagePackEfficient"[^>]*\bchecked\b')
        self.assertRegex(rendered, r'id="languagePackCompatibility"[^>]*\bchecked\b')
        self.assertNotRegex(rendered, r'id="languagePackEnglish"[^>]*\bchecked\b')

    def test_cuda_starts_balanced_and_conservative(self):
        result = build_onboarding_recommendation(performance(cuda=True, preset="balanced"), deployment())
        self.assertEqual(result["recommended_active_languages"], 4)
        self.assertEqual(result["maximum_active_languages"], 20)
        self.assertEqual(result["performance_label"], "Balanced")
        self.assertIn("NVIDIA", result["hardware_title"])
        self.assertEqual(result["recommended_language_pack"], "efficient")
        self.assertEqual(result["default_language_pack"], "efficient")
        self.assertEqual(result["default_language_packs"], ["efficient", "compatibility"])
        self.assertEqual(onboarding_language_packs_config(result["default_language_packs"])["provider"], "both")
        self.assertTrue(result["show_pytorch_pack"])
        self.assertEqual(result["pytorch_pack_badge"], "CUDA check needed")

        pytorch_ready = build_onboarding_recommendation(
            performance(cuda=True, pytorch_cuda=True, preset="balanced"), deployment()
        )
        self.assertTrue(pytorch_ready["pytorch_cuda_ready"])
        self.assertEqual(pytorch_ready["pytorch_pack_badge"], "CUDA verified")
        self.assertEqual(pytorch_ready["recommended_language_pack"], "compatibility")
        self.assertEqual(pytorch_ready["default_language_pack"], "compatibility")

        driver_only = build_onboarding_recommendation(
            performance(nvidia_driver=True), deployment()
        )
        self.assertTrue(driver_only["nvidia_detected"])
        self.assertTrue(driver_only["show_pytorch_pack"])
        self.assertEqual(driver_only["recommended_language_pack"], "efficient")
        self.assertEqual(driver_only["default_language_packs"], ["efficient"])
        self.assertEqual(driver_only["pytorch_pack_badge"], "CUDA check needed")

        linux_ready = build_onboarding_recommendation(
            performance(platform="Linux", nvidia_driver=True, pytorch_cuda=True, cuda=False), deployment()
        )
        self.assertEqual(linux_ready["recommended_language_pack"], "compatibility")
        self.assertEqual(linux_ready["default_language_pack"], "compatibility")
        self.assertEqual(linux_ready["default_language_packs"], ["compatibility"])
        self.assertEqual(linux_ready["recommended_active_languages"], 3)
        self.assertIn("PyTorch CUDA translation ready", linux_ready["local_check_summary"])

        device_visible = build_onboarding_recommendation(
            performance(platform="Linux", cuda=True, pytorch_cuda=True), deployment()
        )
        self.assertTrue(device_visible["nvidia_detected"])
        self.assertEqual(device_visible["recommended_language_pack"], "compatibility")

        mac = build_onboarding_recommendation(
            performance(platform="Darwin", pytorch_cuda=True), deployment()
        )
        self.assertFalse(mac["nvidia_detected"])
        self.assertEqual(mac["recommended_language_pack"], "efficient")

        pending = build_onboarding_recommendation(performance(cuda_requested=True), deployment())
        self.assertTrue(pending["show_pytorch_pack"])
        self.assertEqual(pending["pytorch_pack_badge"], "CUDA pending")
        self.assertEqual(pending["default_language_packs"], [pending["recommended_language_pack"]])

        packaged_cpu = build_onboarding_recommendation(
            performance(cuda=True, cuda_requested=True, windows_packaged_cpu_torch=True), deployment()
        )
        self.assertEqual(packaged_cpu["recommended_language_pack"], "efficient")
        self.assertEqual(packaged_cpu["default_language_packs"], ["efficient", "compatibility"])
        self.assertTrue(packaged_cpu["windows_packaged_cpu_torch"])
        self.assertEqual(packaged_cpu["pytorch_pack_badge"], "CPU fallback")
        self.assertIn("not this PyTorch pack", packaged_cpu["pytorch_pack_detail"])

    def test_cpu_and_deployment_limits_are_respected(self):
        strong_cpu = build_onboarding_recommendation(performance(cpu_count=12), deployment(limit=1))
        low_power = build_onboarding_recommendation(performance(cpu_count=4), deployment())
        unavailable = build_onboarding_recommendation(performance(cuda=True), deployment(allow=False, limit=3))
        self.assertEqual(strong_cpu["recommended_active_languages"], 1)
        self.assertEqual(strong_cpu["maximum_active_languages"], 1)
        self.assertEqual(low_power["recommended_active_languages"], 1)
        self.assertEqual(low_power["recommended_language_pack"], "english")
        self.assertEqual(low_power["default_language_pack"], "english")
        low_memory = build_onboarding_recommendation(performance(cpu_count=12, memory_gb=8), deployment())
        self.assertEqual(low_memory["recommended_language_pack"], "english")
        self.assertEqual(low_memory["default_language_pack"], "english")
        self.assertEqual(low_memory["default_language_packs"], ["english"])
        low_memory_gpu = build_onboarding_recommendation(
            performance(nvidia_driver=True, pytorch_cuda=True, memory_gb=8), deployment()
        )
        self.assertEqual(low_memory_gpu["recommended_language_pack"], "english")
        self.assertIn("8 GB memory", low_memory["local_check_summary"])
        self.assertFalse(unavailable["translation_available"])
        self.assertEqual(unavailable["recommended_language_pack"], "english")
        self.assertEqual(unavailable["default_language_packs"], ["english"])

    def test_language_selection_is_normalised_deduplicated_and_bounded(self):
        self.assertEqual(validate_onboarding_languages(["FR", "fr", "es", "unknown", "en"]), ["fr", "es"])
        with self.assertRaisesRegex(ValueError, "no more than"):
            validate_onboarding_languages(["fr", "es", "de", "it", "pt", "pl", "nl", "sv", "uk"])
        self.assertEqual(ONBOARDING_LANGUAGE_SELECTION_LIMIT, 8)

    def test_active_limit_cannot_exceed_selected_or_hardware_limit(self):
        self.assertEqual(clamp_onboarding_active_limit(5, maximum=4, selected_count=2), 2)
        self.assertEqual(clamp_onboarding_active_limit(0, maximum=4, selected_count=0), 1)

    def test_language_packs_are_allow_listed_and_define_local_catalogues(self):
        english = onboarding_language_pack_config("english")
        efficient = onboarding_language_pack_config("efficient")
        compatibility = onboarding_language_pack_config("compatibility")
        self.assertFalse(english["enabled"])
        self.assertEqual(english["languages"], ["en"])
        self.assertEqual(efficient["provider"], "ct2small100")
        self.assertEqual(efficient["installer"], "ct2small100")
        self.assertIn("ti", efficient["languages"])
        self.assertEqual(compatibility["provider"], "small100")
        self.assertNotIn("ti", compatibility["languages"])
        self.assertEqual(validate_onboarding_language_pack("efficient"), "efficient")
        with self.assertRaisesRegex(ValueError, "shown in setup"):
            validate_onboarding_language_pack("remote-cloud-pack")
        with self.assertRaisesRegex(ValueError, "not available"):
            validate_onboarding_language_pack("efficient", translation_available=False)

        combined = onboarding_language_packs_config(["efficient", "compatibility"])
        self.assertEqual(validate_onboarding_language_packs(["english", "efficient", "efficient"]), ["efficient"])
        self.assertEqual(combined["provider"], "both")
        self.assertEqual(combined["installers"], ["ct2small100", "small100"])
        self.assertIn("Automatic", combined["label"])
        self.assertIn("ti", combined["languages"])

    def test_password_recovery_marker_is_explicit_and_one_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "operator_password_recovery.flag"
            self.assertFalse(password_recovery_requested(marker))
            marker.write_text("password-reset\n", encoding="utf-8")
            self.assertTrue(password_recovery_requested(marker))
            clear_password_recovery_request(marker)
            self.assertFalse(password_recovery_requested(marker))

    def test_wizard_explains_optional_languages_and_progress(self):
        setup = Path("app/templates/setup.html").read_text(encoding="utf-8")
        finish = Path("app/templates/setup_finish.html").read_text(encoding="utf-8")
        recovery = Path("app/templates/setup_recovery.html").read_text(encoding="utf-8")
        script = Path("app/static/setup-onboarding.js").read_text(encoding="utf-8")
        theme_script = Path("app/static/setup-theme.js").read_text(encoding="utf-8")
        finish_script = Path("app/static/setup-finish.js").read_text(encoding="utf-8")
        styles = Path("app/static/styles.css").read_text(encoding="utf-8")
        main = Path("app/main.py").read_text(encoding="utf-8")
        self.assertEqual(setup.count('data-onboarding-step="'), 7)
        self.assertEqual(setup.count('tabindex="-1"'), 7)
        self.assertEqual(setup.count('data-setup-overview-step="'), 6)
        overview_numbers = re.findall(
            r'data-setup-overview-step="[^"]+"><span class="onboarding-feature-icon" aria-hidden="true">(\d+)</span>',
            setup,
        )
        self.assertEqual(overview_numbers, ["1", "2", "3", "4", "5", "6"])
        tracker_numbers = re.findall(r'data-step-indicator="[2-7]"[^>]*><span>(\d+)</span>', setup)
        self.assertEqual(tracker_numbers, ["1", "2", "3", "4", "5", "6"])
        self.assertIn('data-step-indicator="1" aria-current="step"><span aria-hidden="true">•</span>', setup)
        self.assertIn('aria-valuenow="0"', setup)
        self.assertIn('id="onboardingProgressPercent">0%</span>', setup)
        self.assertIn("const taskNumbers = activeNumbers.filter((number) => number !== 1);", script)
        self.assertIn("const percent = currentStep === 1 ? 0", script)
        self.assertIn("Tune this computer", setup)
        self.assertIn("Choose caption languages", setup)
        self.assertIn("Add spoken audio", setup)
        self.assertIn("Review and finish", setup)
        self.assertIn('name="audio_device"', setup)
        self.assertIn("Choose what Church Cap should listen to", setup)
        self.assertIn("reviewAudioInput", setup + script)
        self.assertIn("validate_setup_audio_device", main)
        self.assertIn("English captions only", setup)
        self.assertIn("Broad language pack", setup)
        self.assertIn("PyTorch SMaLL-100 language pack", setup)
        self.assertIn("NVIDIA PyTorch option detected", setup)
        self.assertIn("NVIDIA GPU detected.", setup)
        self.assertIn("onboarding.recommended_language_pack == 'compatibility'", setup)
        self.assertIn("pytorch-first", setup)
        self.assertIn(".onboarding-pack-fieldset.pytorch-first > .onboarding-advanced-pack { order: 1; }", styles)
        self.assertIn("<svg", setup)
        self.assertIn('name="language_packs"', setup)
        self.assertIn("form_values.get('language_packs') or onboarding.default_language_packs", setup)
        self.assertNotIn('name="language_pack" ', setup)
        self.assertNotIn('name="translation_languages"', setup)
        self.assertIn("No device profile is sent online", setup)
        self.assertIn("Simultaneous translated languages", setup)
        self.assertIn('type="range" min="1" max="{{ onboarding.maximum_active_languages }}"', setup)
        self.assertIn("updateActiveLanguageLimit", script)
        self.assertIn("2.5 GB", setup)
        self.assertIn("Spoken translated audio · Optional", setup)
        self.assertIn('name="spoken_audio_setup"', setup)
        self.assertIn('name="spoken_audio_packages"', setup)
        self.assertIn("Skip for now", setup)
        self.assertIn("Select all voices", setup)
        self.assertIn('role="progressbar"', setup)
        self.assertIn("updatePasswordRequirements", script)
        self.assertIn("updatePackSelection", script)
        self.assertIn("selectAllLanguagePacks", setup + script)
        self.assertIn("activeStepNumbers", script)
        self.assertIn("selectAllSpokenAudio", setup + script)
        self.assertIn("Continue to spoken audio", script)
        self.assertIn("classList.toggle('is-available'", script)
        self.assertIn("languagePackInfoDialog", setup + script)
        self.assertIn("prefers-reduced-motion: reduce", script)
        self.assertIn("outgoingAnimation?.cancel()", script)
        self.assertIn("window.scrollTo({top: 0, behavior: 'auto'})", script)
        self.assertIn("activeStep.scrollTop = 0", script)
        self.assertIn("onboardingThemeToggle", setup + finish + theme_script)
        self.assertIn("operatorTheme", theme_script)
        self.assertIn('name="setup_theme"', setup)
        self.assertIn("operator_theme", Path("app/templates/operator.html").read_text(encoding="utf-8"))
        self.assertIn("setup-theme.js", setup + finish)
        self.assertNotIn("{{ app_version_label }}", setup + finish + recovery)
        self.assertIn('href="/operator#languages"', finish)
        self.assertNotIn("#operator-section-languages", finish)
        self.assertIn(".onboarding-stage", styles)
        self.assertIn(".onboarding-hero", styles)
        self.assertIn("padding-bottom: 0.82rem", styles)
        self.assertIn(".light-mode.onboarding-page .onboarding-actions .secondary-button", styles)
        self.assertIn(".onboarding-step-indicators li[hidden]", styles)
        self.assertIn("WCAG AA contrast", styles)
        self.assertNotIn("inset 3px 0 #38bdf8", styles)
        self.assertIn('@app.get("/setup/finish"', main)
        self.assertIn('"progress": dict(install.get("progress") or {})', main)
        self.assertIn('start_translation_installs(pack_config["installers"])', main)
        self.assertIn("/api/setup/install-status", finish + finish_script)
        self.assertIn("onboardingSpokenInstallCard", finish)
        self.assertIn("performance settings will stay unchanged", recovery)
        self.assertNotIn('name="language_setup"', recovery)

    def test_setup_screens_theme_native_controls_for_dark_mode(self):
        styles = Path("app/static/styles.css").read_text(encoding="utf-8")
        dark = styles.split(".auth-page {\n  color-scheme:", 1)[1].split("}", 1)[0]
        light = styles.split(".auth-page.light-mode {\n  color-scheme:", 1)[1].split("}", 1)[0]
        option = styles.split(".auth-page select option {", 1)[1].split("}", 1)[0]
        self.assertEqual(dark.strip(" ;\n"), "dark")
        self.assertEqual(light.strip(" ;\n"), "light")
        self.assertIn("color: #121826;", option)
        self.assertIn("background: #ffffff;", option)
        for template in ("setup.html", "setup_finish.html", "setup_recovery.html"):
            source = Path("app/templates", template).read_text(encoding="utf-8")
            self.assertIn('<body class="auth-page', source, template)

    def test_source_setup_defers_optional_languages_to_the_same_browser_assistant(self):
        for filename in ("setup-macos.sh", "setup-linux.sh", "setup-windows.ps1"):
            source = Path(filename).read_text(encoding="utf-8")
            self.assertIn("browser", source.lower(), filename)
            self.assertNotIn("Choose translation setup", source, filename)


if __name__ == "__main__":
    unittest.main()
