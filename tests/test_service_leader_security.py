from pathlib import Path
import unittest


class ServiceLeaderSecuritySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = Path("app/main.py").read_text(encoding="utf-8")
        cls.auth = Path("app/service_leader_auth.py").read_text(encoding="utf-8")
        cls.runner = Path("scripts/run-dual.py").read_text(encoding="utf-8")
        cls.engine = Path("engine/entrypoint.py").read_text(encoding="utf-8")
        cls.service_leader = Path("app/templates/service_leader.html").read_text(encoding="utf-8")
        cls.pair = Path("app/templates/service_leader_pair.html").read_text(encoding="utf-8")
        cls.login = Path("app/templates/login.html").read_text(encoding="utf-8")
        cls.operator = Path("app/templates/operator.html").read_text(encoding="utf-8")
        cls.styles = Path("app/static/styles.css").read_text(encoding="utf-8")

    def test_full_operator_lock_remains_in_middleware(self):
        self.assertIn("not is_remote_service_leader_path(path)", self.main)
        self.assertIn("lock_operator_to_localhost", self.main)

    def test_port_boundary_uses_actual_server_socket_before_host_header(self):
        request_port = self.main.split("def _request_port", 1)[1].split("PUBLIC_PREFIXES", 1)[0]
        self.assertIn('request.scope.get("server")', request_port)
        self.assertLess(request_port.index('request.scope.get("server")'), request_port.index("request.url.port"))

    def test_remote_scope_only_uses_service_leader_handoff_and_static_prefixes(self):
        allowlist = self.main.split("REMOTE_SERVICE_LEADER_PREFIXES", 1)[1].split("\n", 1)[0]
        self.assertIn('"/service-leader/"', allowlist)
        self.assertIn('"/download-handoff/"', allowlist)
        self.assertIn('"/download-handoff-qr/"', allowlist)
        self.assertIn('"/static/"', allowlist)
        self.assertIn('"/service-leader/audience-qr.png"', self.main)
        self.assertIn('"/service-leader/transcript.txt"', self.main)
        self.assertIn('"/service-leader/support-logs.json"', self.main)
        self.assertNotIn('"/operator"', allowlist)

    def test_pairing_secret_uses_url_fragment_not_query_string(self):
        self.assertIn('/service-leader/pair#{token}', self.main)
        self.assertIn("location.hash.slice(1)", self.pair)
        self.assertIn("history.replaceState", self.pair)
        self.assertNotIn("?token=", self.main)

    def test_service_leader_cookie_is_scoped_and_hardened(self):
        exchange = self.main.split('async def service_leader_pair_exchange', 1)[1].split('@app.get("/service-leader"', 1)[0]
        self.assertIn('httponly=True', exchange)
        self.assertIn('samesite="strict"', exchange)
        self.assertIn('path="/service-leader"', exchange)

    def test_mutations_require_csrf_and_origin(self):
        self.assertIn('request.headers.get("x-csrf-token")', self.main)
        self.assertIn('request.headers.get("origin")', self.main)
        self.assertIn("require_service_leader_mutation(request, session)", self.main)
        accept_route = self.main.split("async def service_leader_accept_language_request", 1)[1].split(
            '@app.post("/service-leader/api/language-requests/{language}/reject")', 1
        )[0]
        reject_route = self.main.split("async def service_leader_reject_language_request", 1)[1].split(
            '@app.post("/api/language-requests/{language}/accept")', 1
        )[0]
        self.assertIn("require_service_leader_mutation(request, session)", accept_route)
        self.assertIn("require_service_leader_mutation(request, session)", reject_route)
        self.assertIn("accept_language_request_action(language)", accept_route)
        self.assertIn("reject_language_request_action(language)", reject_route)

    def test_service_leader_role_has_no_operator_sensitive_routes(self):
        for forbidden in (
            "/api/privacy",
            "/api/update",
            "/api/diagnostics",
            "/account",
        ):
            self.assertNotIn(forbidden, self.service_leader)

    def test_operator_listener_relies_on_application_boundary(self):
        self.assertIn("from engine.entrypoint import main", self.runner)
        self.assertIn("operator_host = settings.host", self.engine)
        self.assertIn("service-leader session", self.engine)

    def test_service_leader_language_control_preserves_operator_provider(self):
        route = self.main.split('async def service_leader_update_languages', 1)[1].split('@app.post("/api/service-leader/revoke")', 1)[0]
        self.assertIn('runtime.get("translation_provider")', route)
        self.assertNotIn('body.get("translation_provider")', route)
        self.assertIn('body.get("translation_language_policy")', route)
        self.assertIn('language_policy', route)
        self.assertIn('{"automatic", "restricted"}', route)
        self.assertIn('operator_allowed_codes', route)
        self.assertIn('selectable_codes', route)

    def test_service_leader_audio_change_is_scoped_and_requires_stopped_captions(self):
        route = self.main.split('async def service_leader_update_audio', 1)[1].split('@app.post("/service-leader/api/session/extend")', 1)[0]
        self.assertIn("captions_are_running()", route)
        self.assertIn("set_audio_device(device)", route)
        self.assertIn("require_service_leader_mutation(request, session)", route)

    def test_health_thresholds_match_documented_ranges(self):
        health = self.main.split("def caption_health_snapshot", 1)[1].split("def _request_port", 1)[0]
        self.assertIn("live_delay < 2.5", health)
        self.assertIn("live_delay <= 3.5", health)

    def test_session_extension_route_exists(self):
        self.assertIn('"/service-leader/api/session/extend"', self.main)
        self.assertIn("extend_session", self.main)

    def test_login_uses_a_visible_service_leader_button(self):
        self.assertIn("Connect a service leader device", self.login)
        self.assertIn("toggleServiceLeaderPairing()", self.login)
        self.assertNotIn("<details", self.login)

    def test_service_leader_theme_toggle_is_local_and_persistent(self):
        self.assertIn("serviceLeaderThemeToggle", self.service_leader)
        self.assertIn("toggleServiceLeaderTheme", self.service_leader)
        self.assertIn("serviceLeaderThemeManual", self.service_leader)
        self.assertIn("applyServiceLeaderTheme()", self.service_leader)
        self.assertIn(".service-leader-header-actions", self.styles)
        self.assertIn(".service-leader-page.light-mode .secondary-button", self.styles)

    def test_operator_language_save_button_is_before_restricted_list(self):
        primary_save_index = self.operator.index('id="translationPrimarySave"')
        advanced_save_index = self.operator.index('id="translationAdvancedSave"')
        maximum_index = self.operator.index('Maximum active translated languages')
        advanced_index = self.operator.index('data-subpage="advanced-language-controls"')
        list_index = self.operator.index('Restricted-language list')
        bottom_copy_index = self.operator.index('Recommended package uses CTranslate2 INT8')
        self.assertLess(maximum_index, primary_save_index)
        self.assertLess(primary_save_index, advanced_index)
        self.assertLess(advanced_index, advanced_save_index)
        self.assertLess(advanced_save_index, list_index)
        self.assertLess(list_index, bottom_copy_index)
        self.assertEqual(self.operator.count('onclick="saveTranslationSettings()">Save language settings</button>'), 2)
        self.assertIn('text-align: center;', self.styles)
        self.assertIn('.language-save-row', self.styles)

    def test_translation_mode_copy_uses_the_current_app_version(self):
        self.assertIn('window.CC_APP_VERSION_LABEL = {{ app_version_label | tojson }};', self.operator)
        self.assertIn("preferred ${window.CC_APP_VERSION_LABEL || 'current release'} path", self.operator)
        self.assertNotIn('preferred v0.6.x path', self.operator)

    def test_service_leader_operator_page_explains_the_role(self):
        self.assertIn('What is Service Leader?', self.operator)
        self.assertIn('Simple controls for the person running the service', self.operator)
        self.assertIn('not the full operator settings', self.operator)
        self.assertIn('.service-leader-explainer', self.styles)
        explainer_styles = self.styles.split('.service-leader-explainer {', 1)[1].split('}', 1)[0]
        self.assertIn('border-radius: 26px;', explainer_styles)

    def test_diagnostics_and_updates_icons_use_clear_inspect_and_download_shapes(self):
        diagnostics = self.styles.split('.nav-icon-diagnostics::before', 1)[1].split('.nav-icon-updates::before', 1)[0]
        updates = self.styles.split('.nav-icon-updates::before', 1)[1].split('.nav-label', 1)[0]
        self.assertIn('transform: rotate(45deg);', diagnostics)
        self.assertIn('clip-path: polygon(', updates)
        self.assertIn('border-top: 0;', updates)

    def test_operator_audience_outputs_are_clear_and_appliance_guarded(self):
        self.assertIn('<span class="nav-label">Congregation</span>', self.operator)
        self.assertIn('data-subsection="room-access" data-description="Help congregation members join live captions', self.operator)
        self.assertIn('>Join Live Captions</button>', self.operator)
        self.assertIn("Congregation QR codes", self.operator)
        self.assertIn('data-subpage="room-display"', self.operator)
        self.assertIn('data-subpage="obs-live-stream"', self.operator)
        self.assertIn("Projector or confidence screen", self.operator)
        self.assertIn("Livestream browser source", self.operator)
        self.assertIn("output-option-card", self.operator)
        self.assertIn("Appliance safeguard", self.operator)
        self.assertIn("handleApplianceOutputLink", self.operator)
        self.assertIn("applianceOutputDialog", self.operator)
        self.assertIn("output-option-grid", self.styles)

    def test_congregation_icon_uses_three_people(self):
        congregation_button = self.operator.split('data-menu-category="audience"', 1)[1].split('</button>', 1)[0]
        self.assertIn('class="nav-icon nav-icon-congregation"', congregation_button)
        self.assertIn('viewBox="0 0 24 24"', congregation_button)
        self.assertEqual(congregation_button.count('<circle'), 3)
        self.assertEqual(congregation_button.count('<path'), 3)
        self.assertIn('.nav-icon-congregation svg', self.styles)

    def test_operator_navigation_uses_single_open_submenus(self):
        expected_subsections = (
            "live-service",
            "performance",
            "multilingual-captions",
            "advanced-language-controls",
            "spoken-translated-audio",
            "room-access",
            "room-display",
            "obs-live-stream",
            "security",
            "transcript-controls",
            "guidance",
            "support",
            "application-storage",
        )
        for subsection in expected_subsections:
            self.assertIn(f'data-subsection="{subsection}"', self.operator)
        self.assertIn("setExpandedNavGroup", self.operator)
        self.assertIn("toggleNavGroup", self.operator)
        self.assertIn("operatorSubsectionDefaults", self.operator)
        self.assertIn("grid-template-rows: 0fr", self.styles)
        self.assertIn(".nav-menu-group.expanded .nav-submenu", self.styles)
        self.assertNotIn('<p class="nav-category">Guides</p>', self.operator)

    def test_operator_subpages_keep_requested_companion_layouts(self):
        self.assertIn('data-subpages="multilingual-captions advanced-language-controls"', self.operator)
        self.assertIn("Viewer language activity", self.operator)
        self.assertEqual(self.operator.count('data-subpage="transcript-controls"'), 1)
        self.assertEqual(self.operator.count('data-subpage="guidance"'), 2)
        self.assertIn('>Transcript Controls</button>', self.operator)
        self.assertIn('>Guidance and Caption Safety</button>', self.operator)
        self.assertIn('data-subpage="support"', self.operator)
        self.assertIn('data-subpage="application-storage"', self.operator)
        self.assertIn('>Application Storage</button>', self.operator)
        self.assertNotIn('Application Storage (Local Storage)', self.operator)

    def test_service_leader_page_has_health_audio_and_expiry_controls(self):
        self.assertIn("How to improve caption health", self.service_leader)
        self.assertIn("Source delay", self.service_leader)
        self.assertIn("Language delay", self.service_leader)
        self.assertIn("serviceLeaderTranslationDelay", self.service_leader)
        self.assertIn('"translation_delay_seconds": translation_delay', self.main)
        self.assertIn("serviceLeaderAudioDevice", self.service_leader)
        self.assertIn("sessionWarning", self.service_leader)
        self.assertIn("idle_remaining_seconds <= 600", self.service_leader)
        self.assertIn("confirmServiceLeaderLogout()", self.service_leader)
        self.assertIn("renderServiceLeaderLanguageList", self.service_leader)
        self.assertIn("requestServiceLeaderLanguage", self.service_leader)
        self.assertIn("/service-leader/api/language-requests", self.service_leader)
        self.assertIn("No languages found.", self.service_leader)
        self.assertIn("shareServiceLeaderDownload('audience_qr')", self.service_leader)
        self.assertIn("service-leader-qr-button", self.service_leader)
        self.assertIn("Share Audience QR", self.service_leader)
        self.assertIn("downloadServiceLeaderExport", self.service_leader)
        self.assertIn("shareServiceLeaderDownload('support_logs')", self.service_leader)
        self.assertIn("exportWarningDialog", self.service_leader)
        self.assertIn("Share support logs?", self.service_leader)
        self.assertIn("download-handoff", self.service_leader)
        self.assertNotIn("window.confirm", self.service_leader)
        self.assertIn("/service-leader/transcript.txt", self.service_leader)
        self.assertIn("confirmed=1", self.service_leader)
        self.assertIn("serviceLeaderLanguageRequestCard", self.service_leader)
        self.assertIn("resolveServiceLeaderLanguageRequest", self.service_leader)
        self.assertIn("/service-leader/api/language-requests/${encodeURIComponent(code)}/${action}", self.service_leader)
        self.assertIn("serviceLeaderActiveTranslationSlots", self.service_leader)
        self.assertIn("serviceLeaderLanguageDemand", self.service_leader)
        self.assertIn('"active_translated_languages": list(hub.active_translated_languages())', self.main)
        self.assertIn("for code, count in hub.language_counts().items()", self.main)
        self.assertIn(".service-leader-language-request-card", self.styles)
        self.assertIn("serviceLeaderLanguageRequestDrop", self.styles)
        self.assertIn("translateY(calc(-100% - 6rem))", self.styles)
        self.assertIn("top: max(0.75rem, env(safe-area-inset-top));", self.styles)
        self.assertIn("Incoming language request", self.service_leader)
        self.assertIn("Select Accept to enable a language for this service", self.service_leader)

    def test_service_leader_uses_an_on_the_go_single_section_menu(self):
        for section in ("health", "audio", "audience", "languages", "exports"):
            self.assertIn(f'data-service-leader-section="{section}"', self.service_leader)
            self.assertIn(f'data-service-leader-panel="{section}"', self.service_leader)
        self.assertIn("On-the-go menu", self.service_leader)
        self.assertIn("toggleServiceLeaderMenuGroup", self.service_leader)
        self.assertIn("showServiceLeaderSection", self.service_leader)
        self.assertIn("serviceLeaderRequestMenuBadge", self.service_leader)
        self.assertIn("serviceLeaderConnectionPill", self.service_leader)
        self.assertIn("shareServiceLeaderAudienceLink", self.service_leader)
        self.assertIn("navigator.share", self.service_leader)
        self.assertIn("openServiceLeaderAudienceShareDialog", self.service_leader)
        self.assertIn('id="audienceShareDialog"', self.service_leader)
        self.assertIn("copyServiceLeaderAudienceLink", self.service_leader)
        self.assertIn("sms:?body=", self.service_leader)
        self.assertIn("mailto:?subject=", self.service_leader)
        self.assertIn("AirDrop, Nearby Share, apps or copy", self.service_leader)
        self.assertIn("nav-icon nav-icon-service service-leader-menu-operator-icon", self.service_leader)
        self.assertIn("nav-icon nav-icon-congregation service-leader-menu-operator-icon", self.service_leader)
        self.assertIn("nav-icon nav-icon-diagnostics service-leader-menu-operator-icon", self.service_leader)
        self.assertIn("sessionStorage.setItem('serviceLeaderSection'", self.service_leader)
        self.assertIn(".service-leader-menu-group.is-expanded", self.styles)
        self.assertIn(".service-leader-menu-group:not(.is-expanded) .service-leader-submenu", self.styles)
        self.assertIn(".service-leader-section-panel[hidden]", self.styles)
        active_style = self.styles.split(".service-leader-submenu-button.is-active {", 1)[1].split("}", 1)[0]
        self.assertNotIn("box-shadow", active_style)

    def test_service_leader_page_has_language_policy_and_dismissible_notices(self):
        self.assertIn("serviceLeaderLanguagePolicy", self.service_leader)
        self.assertIn("Automatic — visitors can request supported languages", self.service_leader)
        self.assertIn("Manual — only selected languages are enabled", self.service_leader)
        self.assertIn("serviceLeaderHttpNoticeDismissed", self.service_leader)
        self.assertIn("serviceLeaderPreviewNoticeDismissed", self.service_leader)
        self.assertIn("dismissServiceLeaderNotice", self.service_leader)

    def test_service_leader_uses_live_caption_observer_stream(self):
        self.assertIn("new WebSocket(serviceLeaderWsUrl())", self.service_leader)
        self.assertIn("role=service-leader", self.service_leader)
        self.assertIn('websocket.query_params.get("role") != "service-leader"', self.main)
        self.assertIn("count_viewer=count_viewer", self.main)
        self.assertIn("self._viewer_clients", Path("app/broadcast.py").read_text(encoding="utf-8"))

    def test_service_leader_has_start_stop_progress_messages(self):
        self.assertIn("Starting captions — loading the speech model and audio input. This can take a moment.", self.service_leader)
        self.assertIn("Stopping captions — audience pages will return to the waiting screen shortly.", self.service_leader)
        self.assertIn("Resuming captions — new speech will appear after the private-moment buffer clears.", self.service_leader)
        self.assertIn("serviceLeaderControlNotice", self.service_leader)
        self.assertIn("data-control-button", self.service_leader)
        self.assertLess(
            self.service_leader.index('id="serviceLeaderControlNotice"'),
            self.service_leader.index('class="service-leader-control-grid"'),
        )

    def test_service_leader_action_buttons_are_compact(self):
        self.assertIn("service-leader-action-icon", self.service_leader)
        self.assertIn("<strong>Pause</strong>", self.service_leader)
        self.assertIn('data-control-state="start"', self.service_leader)
        self.assertIn('aria-pressed="false"', self.service_leader)
        self.assertIn("setActiveServiceLeaderControl", self.service_leader)
        self.assertIn(".service-leader-action.active", self.styles)
        self.assertIn("--service-leader-active-glow", self.styles)
        self.assertIn(".service-leader-page.light-mode .service-leader-start", self.styles)
        self.assertIn(".service-leader-page.light-mode .service-leader-stop", self.styles)
        self.assertIn(".service-leader-page.light-mode .service-leader-blank", self.styles)
        self.assertIn(".service-leader-page.light-mode .service-leader-resume", self.styles)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", self.styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", self.styles)
        self.assertIn("min-height: 4.35rem;", self.styles)

    def test_service_leader_polish_uses_operator_meter_and_disconnect_dialog(self):
        self.assertIn('class="large-meter service-leader-large-meter"', self.service_leader)
        self.assertIn('id="serviceLeaderMeterFill" class="meter-fill"', self.service_leader)
        self.assertIn("serviceLeaderAudioPercent", self.service_leader)
        self.assertIn("serviceLeaderAudioWarning", self.service_leader)
        self.assertIn("data.audio_warning", self.service_leader)
        self.assertIn('"audio_warning": metrics.get("audio_input_warning")', self.main)
        self.assertIn('id="disconnectDialog"', self.service_leader)
        self.assertIn("service-leader-confirm-dialog", self.service_leader)
        self.assertIn("service-leader-danger-button", self.styles)
        self.assertIn(".service-leader-field-stack", self.styles)

    def test_operator_language_search_select_all_and_live_sync_exist(self):
        self.assertIn("operatorLanguageSearch", self.operator)
        self.assertIn("normaliseLanguageSearch", self.operator)
        self.assertIn("selectAllOperatorLanguages(true)", self.operator)
        self.assertIn("syncOperatorTranslationControls(data.translation)", self.operator)
        self.assertIn("syncOperatorAudioSelection(data.settings?.audio_device)", self.operator)

    def test_operator_controls_have_active_glow_and_status_sync(self):
        self.assertIn('data-operator-control-state="start"', self.operator)
        self.assertIn('data-operator-control-state="stop"', self.operator)
        self.assertIn('data-operator-control-state="pause"', self.operator)
        self.assertIn('data-operator-control-state="resume"', self.operator)
        self.assertIn("operatorCaptionActionLabel", self.operator)
        self.assertIn("Starting captions — loading the speech model and audio input. This can take a moment.", self.operator)
        self.assertIn("Stopping captions — audience pages will return to the waiting screen shortly.", self.operator)
        self.assertIn("Test caption sent to connected viewers.", self.operator)
        self.assertIn("setActiveOperatorControl", self.operator)
        self.assertIn("setActiveOperatorControl(data.status || 'stopped', !!data.sensitive_mode)", self.operator)
        self.assertIn(".operator-control-active", self.styles)
        self.assertIn("--operator-active-glow", self.styles)
        self.assertIn(".operator-start-notice.success", self.styles)
        self.assertIn(".operator-start-notice.error", self.styles)

    def test_operator_has_service_leader_management_section(self):
        self.assertIn('data-section="service-leader"', self.operator)
        self.assertIn('id="operator-section-service-leader"', self.operator)
        self.assertIn("createServiceLeaderPairing()", self.operator)
        self.assertIn("cancelServiceLeaderPairing()", self.operator)
        self.assertIn("revokeServiceLeaderAccess()", self.operator)
        self.assertIn('"/api/service-leader/pairing"', self.main)
        self.assertIn('"/api/service-leader/pairing/cancel"', self.main)
        self.assertIn('"/api/language-requests/{language}/accept"', self.main)
        self.assertIn('"/api/language-requests/{language}/reject"', self.main)

    def test_operator_pairing_generation_remains_local_only(self):
        route = self.main.split("async def create_operator_service_leader_pairing", 1)[1].split(
            '@app.post("/api/service-leader/pairing/cancel")', 1
        )[0]
        self.assertIn("is_local_client(request)", route)
        self.assertIn("_qr_data_uri(pairing_url)", route)

    def test_public_health_does_not_expose_service_leader_session_counts(self):
        health = self.main.split("async def health()", 1)[1].split("def _device_to_api", 1)[0]
        self.assertNotIn("service_leader_access", health)

    def test_polish_styles_include_spacing_orange_and_centered_version(self):
        self.assertIn(".operator-login-card", self.styles)
        self.assertIn(".centered-version", self.styles)
        self.assertIn("rgba(194, 65, 12, 0.88)", self.styles)


if __name__ == "__main__":
    unittest.main()
