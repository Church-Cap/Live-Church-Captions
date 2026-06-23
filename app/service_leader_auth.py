from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from threading import Lock


SERVICE_LEADER_COOKIE_NAME = "church_cap_service_leader"
PAIRING_TTL_SECONDS = 90
SESSION_MAX_AGE_SECONDS = 4 * 60 * 60
SESSION_IDLE_TIMEOUT_SECONDS = 2 * 60 * 60


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class ServiceLeaderSession:
    csrf_token: str
    created_at: float
    last_seen_at: float
    expires_at: float


class ServiceLeaderAccessManager:
    """In-memory, least-privilege access for the service-leader control page.

    Pairing tokens are single-use and short-lived. Service-leader sessions are separate
    from operator sessions, expire automatically, and disappear on app restart.
    Only token hashes are retained in server memory.
    """

    def __init__(
        self,
        *,
        pairing_ttl_seconds: int = PAIRING_TTL_SECONDS,
        session_max_age_seconds: int = SESSION_MAX_AGE_SECONDS,
        session_idle_timeout_seconds: int = SESSION_IDLE_TIMEOUT_SECONDS,
    ):
        self.pairing_ttl_seconds = max(15, int(pairing_ttl_seconds))
        self.session_max_age_seconds = max(60, int(session_max_age_seconds))
        self.session_idle_timeout_seconds = max(60, int(session_idle_timeout_seconds))
        self._pairings: dict[str, float] = {}
        self._sessions: dict[str, ServiceLeaderSession] = {}
        self._lock = Lock()

    def _prune(self, now: float) -> None:
        self._pairings = {key: expiry for key, expiry in self._pairings.items() if expiry >= now}
        self._sessions = {
            key: session
            for key, session in self._sessions.items()
            if session.expires_at >= now and now - session.last_seen_at <= self.session_idle_timeout_seconds
        }

    def create_pairing(self, now: float | None = None) -> str:
        now = time.time() if now is None else float(now)
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._prune(now)
            # A newly generated QR replaces older pending QRs.
            self._pairings.clear()
            self._pairings[_digest(token)] = now + self.pairing_ttl_seconds
        return token

    def access_state(self, now: float | None = None) -> dict[str, int | bool]:
        now = time.time() if now is None else float(now)
        with self._lock:
            self._prune(now)
            pairing_expiry = max(self._pairings.values(), default=0)
            return {
                "active_sessions": len(self._sessions),
                "pairing_active": pairing_expiry > now,
                "pairing_remaining_seconds": max(0, int(pairing_expiry - now)),
                "pairing_ttl_seconds": self.pairing_ttl_seconds,
                "session_idle_timeout_seconds": self.session_idle_timeout_seconds,
                "session_max_age_seconds": self.session_max_age_seconds,
            }

    def cancel_pairings(self) -> None:
        with self._lock:
            self._pairings.clear()

    def exchange_pairing(self, token: str, now: float | None = None) -> tuple[str, ServiceLeaderSession] | None:
        now = time.time() if now is None else float(now)
        token_hash = _digest(str(token or ""))
        with self._lock:
            self._prune(now)
            expiry = self._pairings.pop(token_hash, None)
            if expiry is None or expiry < now:
                return None
            session_token = secrets.token_urlsafe(32)
            session = ServiceLeaderSession(
                csrf_token=secrets.token_urlsafe(24),
                created_at=now,
                last_seen_at=now,
                expires_at=now + self.session_max_age_seconds,
            )
            self._sessions[_digest(session_token)] = session
            return session_token, session

    def verify_session(self, token: str | None, now: float | None = None, *, touch: bool = True) -> ServiceLeaderSession | None:
        if not token:
            return None
        now = time.time() if now is None else float(now)
        token_hash = _digest(token)
        with self._lock:
            self._prune(now)
            session = self._sessions.get(token_hash)
            if session is None:
                return None
            if touch:
                session.last_seen_at = now
            return session

    def csrf_is_valid(self, session: ServiceLeaderSession, submitted: str | None) -> bool:
        return bool(submitted) and hmac.compare_digest(session.csrf_token, str(submitted))

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(_digest(token), None)

    def session_timing(self, session: ServiceLeaderSession, now: float | None = None) -> dict[str, int]:
        now = time.time() if now is None else float(now)
        idle_remaining = max(0, int(self.session_idle_timeout_seconds - (now - session.last_seen_at)))
        absolute_remaining = max(0, int(session.expires_at - now))
        return {
            "idle_timeout_seconds": self.session_idle_timeout_seconds,
            "idle_remaining_seconds": min(idle_remaining, absolute_remaining),
            "absolute_remaining_seconds": absolute_remaining,
        }

    def extend_session(self, token: str | None, now: float | None = None) -> ServiceLeaderSession | None:
        if not token:
            return None
        now = time.time() if now is None else float(now)
        token_hash = _digest(token)
        with self._lock:
            self._prune(now)
            session = self._sessions.get(token_hash)
            if session is None:
                return None
            session.last_seen_at = now
            return session

    def revoke_all(self) -> None:
        with self._lock:
            self._pairings.clear()
            self._sessions.clear()
