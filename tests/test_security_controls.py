import io
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from starlette.requests import Request
from fastapi import HTTPException

from app.auth import (
    AuthConfig,
    AuthenticationThrottle,
    auth_form_request_is_valid,
    create_form_csrf_token,
    create_operator_csrf_token,
    operator_mutation_origin_is_valid,
    protect_auth_storage,
    request_has_same_origin,
    require_operator_mutation,
    verify_form_csrf_token,
    verify_operator_csrf_token,
)
from app.translation_packages import validate_argos_package_archive


def make_request(
    *,
    path: str = "/api/start",
    origin: str | None = None,
    referer: str | None = None,
    host: str = "churchcap.local:9090",
    forwarded_host: str | None = None,
    forwarded_proto: str | None = None,
    fetch_site: str | None = None,
    session_token: str | None = None,
) -> Request:
    headers = [(b"host", host.encode("ascii"))]
    if origin:
        headers.append((b"origin", origin.encode("ascii")))
    if referer:
        headers.append((b"referer", referer.encode("ascii")))
    if forwarded_host:
        headers.append((b"x-forwarded-host", forwarded_host.encode("ascii")))
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    if fetch_site:
        headers.append((b"sec-fetch-site", fetch_site.encode("ascii")))
    if session_token:
        headers.append((b"cookie", f"caption_operator_session={session_token}".encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("churchcap.local", 9090),
        }
    )


class AuthenticationSecurityTests(unittest.TestCase):
    def test_authentication_files_are_owner_only_on_posix(self):
        if __import__("os").name != "posix":
            self.skipTest("POSIX file modes are not available on this platform")
        from app import auth as auth_module

        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "data"
            auth_path = data_dir / "operator_auth.json"
            backup_path = data_dir / "operator_auth.backup.json"
            data_dir.mkdir(mode=0o755)
            auth_path.write_text('{"session_secret": "test"}', encoding="utf-8")
            backup_path.write_text('{"session_secret": "test"}', encoding="utf-8")
            auth_path.chmod(0o644)
            backup_path.chmod(0o644)
            with patch.object(auth_module, "AUTH_PATH", auth_path), patch.object(
                auth_module, "AUTH_BACKUP_PATH", backup_path
            ):
                state = protect_auth_storage()

            self.assertTrue(state["protected"])
            self.assertEqual(auth_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)

    def test_form_csrf_requires_matching_non_empty_tokens(self):
        token = create_form_csrf_token()
        self.assertTrue(verify_form_csrf_token(token, token))
        self.assertFalse(verify_form_csrf_token(token, "wrong"))
        self.assertFalse(verify_form_csrf_token(None, None))

    def test_operator_csrf_is_bound_to_session_and_secret(self):
        config = AuthConfig(password=None, secret="secret-one", max_age_seconds=60)
        token = create_operator_csrf_token("session-one", config)
        self.assertTrue(verify_operator_csrf_token("session-one", token, config))
        self.assertFalse(verify_operator_csrf_token("session-two", token, config))
        other_config = AuthConfig(password=None, secret="secret-two", max_age_seconds=60)
        self.assertFalse(verify_operator_csrf_token("session-one", token, other_config))

    def test_same_origin_accepts_origin_or_referer_and_rejects_cross_site(self):
        self.assertTrue(request_has_same_origin(make_request(origin="http://churchcap.local:9090")))
        self.assertTrue(request_has_same_origin(make_request(referer="http://churchcap.local:9090/operator")))
        self.assertFalse(request_has_same_origin(make_request(origin="https://example.invalid")))
        self.assertFalse(request_has_same_origin(make_request()))

    def test_same_origin_understands_forwarded_appliance_addresses(self):
        request = make_request(
            origin="http://churchcap.local:8000",
            host="127.0.0.1:9090",
            forwarded_host="churchcap.local:8000",
            forwarded_proto="http",
        )
        self.assertTrue(request_has_same_origin(request))
        self.assertTrue(
            request_has_same_origin(
                make_request(
                    origin="http://churchcap.local:8000",
                    host="127.0.0.1:9090",
                    fetch_site="same-origin",
                )
            )
        )
        self.assertFalse(
            request_has_same_origin(
                make_request(origin="https://example.invalid", fetch_site="cross-site")
            )
        )

    def test_easy_offline_accepts_valid_remote_operator_mutation_without_weakening_secure_modes(self):
        remote_request = make_request(
            path="/logout",
            origin="http://church-av-console.local:9090",
            host="192.168.50.20:9090",
            fetch_site="same-site",
            session_token="remote-session",
        )
        cross_site_request = make_request(
            path="/logout",
            origin="https://example.invalid",
            host="192.168.50.20:9090",
            fetch_site="cross-site",
            session_token="remote-session",
        )
        config = AuthConfig(password=None, secret="operator-secret", max_age_seconds=60)
        csrf_token = create_operator_csrf_token("remote-session", config)

        easy_offline = {"security_mode": "easy_offline", "lock_operator_to_localhost": False}
        with patch("app.runtime_config.load_runtime_config", return_value=easy_offline), patch(
            "app.auth.get_auth_config", return_value=config
        ):
            self.assertTrue(operator_mutation_origin_is_valid(remote_request))
            require_operator_mutation(remote_request, csrf_token)
            self.assertFalse(operator_mutation_origin_is_valid(cross_site_request))
            with self.assertRaises(HTTPException):
                require_operator_mutation(cross_site_request, csrf_token)

        for secure_mode in ("secure_operator", "managed_https"):
            runtime = {"security_mode": secure_mode, "lock_operator_to_localhost": True}
            with patch("app.runtime_config.load_runtime_config", return_value=runtime), patch(
                "app.auth.get_auth_config", return_value=config
            ):
                self.assertFalse(operator_mutation_origin_is_valid(remote_request))
                with self.assertRaises(HTTPException):
                    require_operator_mutation(remote_request, csrf_token)

    def test_auth_form_accepts_upgrade_or_proxy_safe_proof(self):
        same_origin = make_request(origin="http://churchcap.local:9090")
        self.assertTrue(auth_form_request_is_valid(same_origin, None, None))
        proxied = make_request(origin="http://proxy.invalid", host="127.0.0.1:9090")
        self.assertTrue(auth_form_request_is_valid(proxied, "matching-token", "matching-token"))
        cross_site = make_request(origin="https://example.invalid", fetch_site="cross-site")
        self.assertFalse(auth_form_request_is_valid(cross_site, None, None))
        self.assertFalse(
            auth_form_request_is_valid(cross_site, "matching-token", "matching-token")
        )

    def test_throttle_is_bounded_and_resets_after_success(self):
        now = [100.0]
        throttle = AuthenticationThrottle(clock=lambda: now[0])
        for _ in range(4):
            self.assertEqual(throttle.record_failure("login:local"), 0)
        self.assertEqual(throttle.record_failure("login:local"), 2)
        self.assertEqual(throttle.retry_after("login:local"), 2)
        now[0] += 2.1
        self.assertEqual(throttle.retry_after("login:local"), 0)
        self.assertEqual(throttle.record_failure("login:local"), 4)
        throttle.reset("login:local")
        self.assertEqual(throttle.retry_after("login:local"), 0)

    def test_templates_and_routes_include_request_protection(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "app/main.py").read_text(encoding="utf-8")
        operator = (root / "app/templates/operator.html").read_text(encoding="utf-8")
        login = (root / "app/templates/login.html").read_text(encoding="utf-8")
        setup = (root / "app/templates/setup.html").read_text(encoding="utf-8")
        recovery_setup = (root / "app/templates/setup_recovery.html").read_text(encoding="utf-8")
        setup_password_script = (root / "app/static/setup-onboarding.js").read_text(encoding="utf-8")
        recovery_password_script = (root / "app/static/setup-password.js").read_text(encoding="utf-8")
        account = (root / "app/templates/account.html").read_text(encoding="utf-8")
        self.assertIn("require_operator_mutation(request, csrf_token)", main)
        self.assertIn('headers.set(\'X-CSRF-Token\', csrfToken)', operator)
        self.assertGreaterEqual(operator.count('name="csrf_token"'), 1)
        self.assertGreaterEqual(login.count('name="csrf_token"'), 2)
        self.assertIn('name="csrf_token"', setup)
        self.assertIn('id="passwordRequirements"', setup)
        self.assertIn("At least 8 characters", setup)
        self.assertIn("Both password entries must match", setup)
        self.assertIn('id="passwordValidationMessage"', setup)
        self.assertLess(setup.index('value="secure_operator"'), setup.index('value="easy_offline"'))
        self.assertIn('recommended-badge">Recommended', setup)
        self.assertIn('caution-badge">Caution', setup)
        self.assertIn('id="easyOfflineInfoButton"', setup)
        self.assertIn('id="easyOfflineInfoDialog"', setup)
        self.assertIn("Other computers or tablets on the same private network can reach operator sign-in.", setup)
        self.assertIn("Convenient, but less isolated", setup)
        self.assertIn('data-onboarding-step="5"', setup)
        self.assertIn("Use at least 8 characters for the operator password.", setup_password_script)
        self.assertIn("The passwords do not match.", setup_password_script)
        self.assertIn("easyOfflineInfoDialog.showModal()", setup_password_script)
        self.assertIn('name="csrf_token"', recovery_setup)
        self.assertIn("settings will stay unchanged", recovery_setup)
        self.assertIn("Use at least 8 characters for the operator password.", recovery_password_script)
        self.assertIn("password_recovery_requested()", main)
        self.assertIn("clear_password_recovery_request()", main)
        self.assertIn('name="csrf_token"', account)
        self.assertIn("Captions and connected viewers are not affected.", main)
        self.assertIn('"desktop_password_reset": system in {"Darwin", "Windows"}', main)
        self.assertIn("if desktop_password_reset", login)
        self.assertIn("Church Cap desktop manager", login)
        self.assertIn("elif linux_password_reset", login)
        self.assertIn("./reset-operator-password.sh", login)
        self.assertNotIn("reset-operator-password.cmd", login)

    def test_public_payloads_and_headers_do_not_expose_operator_details(self):
        from fastapi.responses import Response
        from app.main import _apply_security_headers, is_public_viewer_path, public_translation_state

        detailed = {
            "enabled": True,
            "provider": "ct2small100",
            "available_languages": ["en", "fr"],
            "language_policy": "restricted",
            "language_requests_enabled": True,
            "requestable_languages": ["de"],
            "language_requests": [{"code": "de", "count": 4, "last_requested_at": "private"}],
            "resources": {"ct2small100": {"status": {"model_dir": "/private/model"}}},
            "scheduler": {"queue_depths": {"fr": 1}},
        }
        with patch("app.main.safe_translation_state", return_value=detailed):
            public = public_translation_state()
        self.assertEqual(public["available_languages"], ["en", "fr"])
        self.assertEqual(public["language_requests"], [{"code": "de"}])
        self.assertNotIn("resources", public)
        self.assertNotIn("scheduler", public)
        self.assertNotIn("provider", public)
        self.assertTrue(is_public_viewer_path("/ws/captions"))
        self.assertTrue(is_public_viewer_path("/ws/translation-audio"))
        self.assertFalse(is_public_viewer_path("/operator/api/status"))

        response = _apply_security_headers(Response())
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertNotIn("microphone=()", response.headers["permissions-policy"])

    def test_public_viewer_documents_bypass_stale_browser_cache(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "app/main.py").read_text(encoding="utf-8")
        viewer_routes = main.split('@app.get("/", response_class=HTMLResponse)', 1)[1].split('@app.get("/obs/help"', 1)[0]
        self.assertGreaterEqual(viewer_routes.count("return _no_cache(template_response("), 3)

    def test_public_health_is_minimal_and_operator_diagnostics_remain_available(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "app/main.py").read_text(encoding="utf-8")
        health = main.split('async def health():', 1)[1].split("def _device_to_api", 1)[0]
        self.assertIn('"app_version"', health)
        self.assertNotIn('"audio_device"', health)
        self.assertNotIn('"translation"', health)
        self.assertNotIn('"security"', health)
        public_request = main.split('async def request_language(request: Request):', 1)[1].split(
            '@app.post("/service-leader/api/language-requests")', 1
        )[0]
        self.assertIn('"translation": public_translation_state()', public_request)
        self.assertNotIn('"translation": safe_translation_state()', public_request)
        self.assertIn('"translation": translation_state', main)
        self.assertIn('"security": security_state()', main)
        self.assertLess(
            main.index("async def security_boundary_middleware"),
            main.index("async def browser_security_headers"),
        )

    def test_ci_uses_pinned_actions_and_security_checks(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/python-check.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", workflow)
        self.assertIn("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", workflow)
        self.assertIn('"pip==26.1.2"', workflow)
        self.assertIn("bandit==1.9.4", workflow)
        self.assertIn("pip-audit==2.10.1", workflow)


class TranslationPackageSecurityTests(unittest.TestCase):
    def _archive(self, member: ZipInfo | str, payload: bytes = b"ok") -> Path:
        temporary = tempfile.NamedTemporaryFile(suffix=".argosmodel", delete=False)
        temporary.close()
        path = Path(temporary.name)
        with ZipFile(path, "w") as archive:
            archive.writestr(member, payload)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_valid_argos_archive_is_accepted(self):
        validate_argos_package_archive(self._archive("model/metadata.json", b"{}"))

    def test_argos_archive_path_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            validate_argos_package_archive(self._archive("../outside.txt"))

    def test_argos_archive_symlink_is_rejected(self):
        member = ZipInfo("model/link")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            validate_argos_package_archive(self._archive(member, b"target"))

    def test_small100_uses_an_immutable_revision_and_integrity_check(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/i18n.py").read_text(encoding="utf-8")
        self.assertIn('CT2_SMALL100_MODEL_REVISION = "8ab680e26a596d2e3d2d2d17ae0f68df1037328c"', source)
        self.assertIn("CT2_SMALL100_TOKENIZER_SHA256", source)
        self.assertIn("revision=CT2_SMALL100_MODEL_REVISION", source)
        self.assertIn("use_safetensors=True", source)

    def test_transformers_loads_keep_the_pinned_commit_exception_conditions(self):
        # PYSEC-2026-3929 and PYSEC-2026-4174 are excepted in CI only while every
        # Hugging Face load uses an immutable commit pin or a local directory.
        root = Path(__file__).resolve().parents[1]
        sources = sorted(
            [*(root / "app").rglob("*.py"), *(root / "scripts").glob("install-*.sh"), *(root / "scripts").glob("install-*.ps1")]
        )
        loads = 0
        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertFalse("trust_remote_code=True" in source, path.name)
            self.assertFalse("custom_generate" in source, path.name)
            for value in re.findall(r'(?:revision|_REVISION)\s*=\s*"([^"]*)"', source):
                self.assertRegex(value, r"^[0-9a-f]{40}$", path.name)
            for match in re.finditer(r"(?:\.from_pretrained|TransformersConverter|hf_hub_download|snapshot_download)\(", source):
                depth, end = 1, match.end()
                while depth:
                    depth += {"(": 1, ")": -1}.get(source[end], 0)
                    end += 1
                call = source[match.start():end]
                loads += 1
                if "local_files_only=True" in call:
                    continue
                # The revision must be a commit literal, or a name assigned one in the same file.
                pin = re.search(r'revision=("[0-9a-f]{40}"|[A-Za-z_]\w*)\s*[,)]', call)
                self.assertIsNotNone(pin, f"{path.name}: {call}")
                if not pin.group(1).startswith('"'):
                    self.assertRegex(source, rf'(?m)^\s*{pin.group(1)}\s*=\s*"[0-9a-f]{{40}}"', f"{path.name}: {call}")
        self.assertGreater(loads, 10)
        workflow = (root / ".github/workflows/python-check.yml").read_text(encoding="utf-8")
        audit = (root / "docs/project/V0.9.0_DEPENDENCY_AUDIT.md").read_text(encoding="utf-8")
        for advisory in ("PYSEC-2026-3929", "PYSEC-2026-4174"):
            self.assertIn(f"--ignore-vuln {advisory}", workflow)
            self.assertIn(f"`{advisory}`", audit)

    def test_argos_uses_the_existing_bounded_cue_without_stanza(self):
        from app.i18n import _BoundedCueSentencizer, _use_bounded_argos_cue

        class Translation:
            sentencizer = object()

        class Wrapper:
            underlying = Translation()

        wrapper = Wrapper()
        _use_bounded_argos_cue(wrapper)
        self.assertIsInstance(wrapper.underlying.sentencizer, _BoundedCueSentencizer)
        self.assertEqual(wrapper.underlying.sentencizer.split_sentences("One short cue."), ["One short cue."])
        self.assertEqual(wrapper.underlying.sentencizer.split_sentences("   "), [])


if __name__ == "__main__":
    unittest.main()
