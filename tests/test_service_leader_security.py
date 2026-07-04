from pathlib import Path
import unittest


class ServiceLeaderSecuritySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = Path("app/main.py").read_text(encoding="utf-8")
        cls.auth = Path("app/service_leader_auth.py").read_text(encoding="utf-8")
        cls.runner = Path("scripts/run-dual.py").read_text(encoding="utf-8")
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

    def test_service_leader_role_has_no_operator_sensitive_routes(self):
        for forbidden in (
            "/api/privacy",
            "/api/update",
            "/api/diagnostics",
            "/account",
        ):
            self.assertNotIn(forbidden, self.service_leader)

    def test_operator_listener_relies_on_application_boundary(self):
        self.assertIn("operator_host = settings.host", self.runner)
        self.assertIn("service-leader session", self.runner)

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
        save_index = self.operator.index('class="button-row language-save-row"')
        list_index = self.operator.index('Restricted-language list')
        bottom_copy_index = self.operator.index('Recommended package uses CTranslate2 INT8')
        self.assertLess(save_index, list_index)
        self.assertLess(list_index, bottom_copy_index)
        self.assertIn('text-align: center;', self.styles)
        self.assertIn('.language-save-row', self.styles)

    def test_operator_audience_outputs_are_clear_and_appliance_guarded(self):
        self.assertIn("Room display and livestream", self.operator)
        self.assertIn("output-option-card", self.operator)
        self.assertIn("Appliance safeguard", self.operator)
        self.assertIn("handleApplianceOutputLink", self.operator)
        self.assertIn("applianceOutputDialog", self.operator)
        self.assertIn("output-option-grid", self.styles)

    def test_service_leader_page_has_health_audio_and_expiry_controls(self):
        self.assertIn("How to improve caption health", self.service_leader)
        self.assertIn("English delay", self.service_leader)
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
