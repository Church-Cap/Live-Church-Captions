from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable
from urllib.parse import urlsplit

from app.paths import data_path, migrate_project_data

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

COOKIE_NAME = "caption_operator_session"
AUTH_FORM_CSRF_COOKIE_NAME = "caption_auth_request"
AUTH_FORM_CSRF_MAX_AGE_SECONDS = 10 * 60
AUTH_PATH = data_path("operator_auth.json")
AUTH_BACKUP_PATH = data_path("operator_auth.backup.json")
FACTORY_RESET_MARKER = data_path("factory_reset.flag")
_lock = Lock()


class AuthenticationThrottle:
    """Bound repeated password guesses without creating a long-lived lockout.

    The first five failures are immediate. Further failures receive a short,
    exponentially increasing pause capped at 30 seconds. Entries expire after
    15 minutes and are held in memory only, so restarting Church Cap never
    leaves an operator locked out on a service day.
    """

    def __init__(
        self,
        *,
        free_attempts: int = 5,
        maximum_delay_seconds: int = 30,
        observation_seconds: int = 15 * 60,
        max_entries: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.free_attempts = max(1, free_attempts)
        self.maximum_delay_seconds = max(1, maximum_delay_seconds)
        self.observation_seconds = max(60, observation_seconds)
        self.max_entries = max(128, max_entries)
        self._clock = clock
        self._entries: dict[str, dict[str, float | int]] = {}
        self._lock = Lock()

    def _prune(self, now: float) -> None:
        stale = [
            key
            for key, entry in self._entries.items()
            if now - float(entry.get("last_failure", 0.0)) > self.observation_seconds
        ]
        for key in stale:
            self._entries.pop(key, None)

    def retry_after(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(key)
            if not entry:
                return 0
            remaining = float(entry.get("blocked_until", 0.0)) - now
            return max(0, int(remaining + 0.999))

    def record_failure(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            self._prune(now)
            if key not in self._entries and len(self._entries) >= self.max_entries:
                oldest_key = min(self._entries, key=lambda item: float(self._entries[item].get("last_failure", 0.0)))
                self._entries.pop(oldest_key, None)
            entry = self._entries.setdefault(key, {"failures": 0, "last_failure": now, "blocked_until": 0.0})
            failures = int(entry.get("failures", 0)) + 1
            entry["failures"] = failures
            entry["last_failure"] = now
            if failures >= self.free_attempts:
                delay = min(self.maximum_delay_seconds, 2 ** (failures - self.free_attempts + 1))
                entry["blocked_until"] = now + delay
                return delay
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


authentication_throttle = AuthenticationThrottle()


def _factory_reset_pending() -> bool:
    """Keep legacy environment credentials out of a deliberate clean setup."""
    try:
        return FACTORY_RESET_MARKER.is_file()
    except OSError:
        return False


@dataclass(frozen=True)
class AuthConfig:
    password: str | None
    secret: str
    max_age_seconds: int
    password_hash: str | None = None
    needs_setup: bool = False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64(digest)


def create_form_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_form_csrf_token(cookie_token: str | None, submitted_token: str | None) -> bool:
    if not cookie_token or not submitted_token:
        return False
    return hmac.compare_digest(cookie_token, submitted_token)


def auth_form_request_is_valid(
    request: Request,
    cookie_token: str | None,
    submitted_token: str | None,
) -> bool:
    """Accept a protected form by token or a browser-verified same-origin request.

    The same-origin fallback keeps a login page opened before an upgrade usable,
    while a valid double-submit token handles proxies and privacy settings that
    omit or rewrite Origin/Referer headers.
    """
    if request.headers.get("sec-fetch-site", "").strip().lower() == "cross-site":
        return False
    return verify_form_csrf_token(cookie_token, submitted_token) or request_has_same_origin(request)


def create_operator_csrf_token(session_token: str, config: AuthConfig) -> str:
    return _sign(f"operator-csrf:{session_token}", config.secret)


def verify_operator_csrf_token(session_token: str, submitted_token: str | None, config: AuthConfig) -> bool:
    if not submitted_token:
        return False
    expected = create_operator_csrf_token(session_token, config)
    return hmac.compare_digest(expected, submitted_token)


def request_has_same_origin(request: Request) -> bool:
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if fetch_site == "cross-site":
        return False
    if fetch_site == "same-origin":
        return True

    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer")
        if referer:
            parsed = urlsplit(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"
    if not origin:
        return False

    expected_origins = {
        f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/"),
    }
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    if forwarded_host:
        forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        expected_origins.add(f"{forwarded_scheme or request.url.scheme}://{forwarded_host}".rstrip("/"))

    forwarded = request.headers.get("forwarded", "").split(",", 1)[0]
    forwarded_values: dict[str, str] = {}
    for item in forwarded.split(";"):
        key, separator, value = item.strip().partition("=")
        if separator:
            forwarded_values[key.lower()] = value.strip().strip('"')
    if forwarded_values.get("host"):
        expected_origins.add(
            f"{forwarded_values.get('proto') or request.url.scheme}://{forwarded_values['host']}".rstrip("/")
        )

    return origin.rstrip("/") in expected_origins


def operator_mutation_origin_is_valid(request: Request) -> bool:
    """Validate origin evidence after the session-bound CSRF token has passed.

    Remote Safari form submissions can omit or rewrite origin evidence when
    Church Cap is reached through a LAN hostname or address. Easy Offline mode
    deliberately exposes operator controls on that LAN, so its valid,
    session-bound CSRF token may be used as the fallback proof. Explicitly
    cross-site requests remain rejected, and the fallback is unavailable while
    the operator localhost lock is enabled.
    """
    if request_has_same_origin(request):
        return True
    if request.headers.get("sec-fetch-site", "").strip().lower() == "cross-site":
        return False

    from app.runtime_config import load_runtime_config

    runtime = load_runtime_config()
    return (
        runtime.get("security_mode") == "easy_offline"
        and not bool(runtime.get("lock_operator_to_localhost", True))
    )


def throttle_key(request: Request, flow: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{flow}:{client_host}"


def require_operator_mutation(request: Request, submitted_token: str | None = None) -> None:
    from app.settings import get_settings

    settings = get_settings()
    config = get_auth_config(
        max_age_seconds=settings.session_max_age_seconds,
        env_password=settings.operator_password,
        env_secret=settings.session_secret,
    )
    session_token = request.cookies.get(COOKIE_NAME) or ""
    token = submitted_token if submitted_token is not None else request.headers.get("x-csrf-token")
    if not verify_operator_csrf_token(session_token, token, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid operator request token")
    if not operator_mutation_origin_is_valid(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin did not match Church Cap")


def hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 250_000)
    return f"pbkdf2_sha256${salt}${_b64(digest)}"


def verify_password_hash(submitted: str, stored: str) -> bool:
    try:
        scheme, salt, _digest = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(hash_password(submitted, salt), stored)


def _read_store_file(path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def protect_auth_storage() -> dict[str, str | bool]:
    """Best-effort protection for the local authentication store.

    POSIX installations can enforce owner-only directory and file modes. On
    Windows, the files remain inside the current user's application-data
    directory and access is governed by that account's ACLs. Permission
    hardening must never prevent Church Cap from starting on filesystems that
    do not implement POSIX modes.
    """
    if os.name != "posix":
        return {
            "protected": True,
            "status": "platform_managed",
            "message": "Protected by the current Windows user's application-data permissions.",
        }

    try:
        AUTH_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        for path in (AUTH_PATH, AUTH_BACKUP_PATH):
            if path.exists():
                path.chmod(0o600)
        exposed = [
            path.name
            for path in (AUTH_PATH, AUTH_BACKUP_PATH)
            if path.exists() and (path.stat().st_mode & 0o077)
        ]
        if exposed:
            return {
                "protected": False,
                "status": "warning",
                "message": "The filesystem did not retain owner-only permissions for: " + ", ".join(exposed),
            }
        return {
            "protected": True,
            "status": "owner_only",
            "message": "Operator authentication files are restricted to the current user.",
        }
    except OSError as exc:
        return {
            "protected": False,
            "status": "warning",
            "message": f"Church Cap could not verify owner-only authentication-file permissions: {exc}",
        }


def _write_store_file(path, store: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    if os.name == "posix":
        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass
    os.replace(tmp_path, path)
    protect_auth_storage()


def _load_store() -> dict:
    migrate_project_data("operator_auth.json", AUTH_PATH)
    protect_auth_storage()
    with _lock:
        store = _read_store_file(AUTH_PATH)
        backup = _read_store_file(AUTH_BACKUP_PATH)

        # If the primary file has been lost, corrupted, or left incomplete, but
        # the backup still has the operator password, restore it automatically.
        if not store.get("password_hash") and backup.get("password_hash"):
            _write_store_file(AUTH_PATH, backup)
            return backup
        return store


def _save_store(store: dict) -> dict:
    with _lock:
        _write_store_file(AUTH_PATH, store)
        if store.get("password_hash") and store.get("session_secret"):
            _write_store_file(AUTH_BACKUP_PATH, store)
        return store


def bootstrap_auth_store(env_password: str | None = None, env_secret: str | None = None) -> dict:
    """Ensure a local auth store exists.

    Keep the session secret stable across app restarts so Sunday-morning
    operators are not unexpectedly logged out after stopping and restarting the
    server. Sessions rotate on password changes and if the operator manually
    deletes the auth store.
    """
    reset_pending = _factory_reset_pending()
    if reset_pending:
        env_password = None
        env_secret = None
    store = _load_store()
    changed = False

    if not store.get("session_secret"):
        store["session_secret"] = secrets.token_urlsafe(48)
        changed = True

    env_password_is_real = bool(env_password and env_password not in {"change-me", ""})
    if not store.get("password_hash") and env_password_is_real:
        store["password_hash"] = hash_password(env_password or "")
        store["password_source"] = "migrated_from_env"
        changed = True

    backup_missing = not AUTH_BACKUP_PATH.exists()
    if changed or (backup_missing and store.get("password_hash") and store.get("session_secret")):
        _save_store(store)
    return store


def get_auth_config(max_age_seconds: int, env_password: str | None = None, env_secret: str | None = None) -> AuthConfig:
    if _factory_reset_pending():
        env_password = None
        env_secret = None
    store = _load_store()
    password_hash = store.get("password_hash")
    secret = store.get("session_secret") or env_secret or secrets.token_urlsafe(48)
    env_password_is_real = bool(env_password and env_password not in {"change-me", ""})
    return AuthConfig(
        password=env_password if env_password_is_real else None,
        secret=secret,
        max_age_seconds=max_age_seconds,
        password_hash=password_hash,
        needs_setup=not bool(password_hash) and not env_password_is_real,
    )


def set_operator_password(new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    store = _load_store()
    store["password_hash"] = hash_password(new_password)
    store["password_source"] = "local_setup"
    # Rotate sessions after a password change only.
    store["session_secret"] = secrets.token_urlsafe(48)
    _save_store(store)


def create_session_token(config: AuthConfig) -> str:
    issued = str(int(time.time()))
    signature = _sign(issued, config.secret)
    return f"{issued}.{signature}"


def verify_session_token(token: str | None, config: AuthConfig) -> bool:
    if not token or "." not in token:
        return False
    issued, signature = token.split(".", 1)
    if not issued.isdigit():
        return False
    expected = _sign(issued, config.secret)
    if not hmac.compare_digest(signature, expected):
        return False
    age = int(time.time()) - int(issued)
    return 0 <= age <= config.max_age_seconds


def password_is_valid(submitted: str, config: AuthConfig) -> bool:
    if config.password_hash:
        return verify_password_hash(submitted, config.password_hash)
    if config.password:
        return hmac.compare_digest(submitted, config.password)
    return False


def require_operator(request: Request) -> None:
    from app.settings import get_settings

    settings = get_settings()
    config = get_auth_config(
        max_age_seconds=settings.session_max_age_seconds,
        env_password=settings.operator_password,
        env_secret=settings.session_secret,
    )
    if config.needs_setup:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/setup"})
    session_token = request.cookies.get(COOKIE_NAME)
    if verify_session_token(session_token, config):
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in {
            "/logout",
            "/account/password",
        }:
            require_operator_mutation(request)
        return
    if request.url.path == "/operator":
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator login required")


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
