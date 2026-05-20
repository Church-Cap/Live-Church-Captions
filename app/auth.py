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

from app.paths import data_path, migrate_project_data

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

COOKIE_NAME = "caption_operator_session"
AUTH_PATH = data_path("operator_auth.json")
AUTH_BACKUP_PATH = data_path("operator_auth.backup.json")
_lock = Lock()


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


def _write_store_file(path, store: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _load_store() -> dict:
    migrate_project_data("operator_auth.json", AUTH_PATH)
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
    if verify_session_token(request.cookies.get(COOKIE_NAME), config):
        return
    if request.url.path == "/operator":
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator login required")


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
