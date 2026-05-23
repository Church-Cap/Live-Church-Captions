from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from app.models import CaptionSegment
from app.paths import data_path


class TranscriptStore:
    """Small encrypted-at-rest cache for retained caption transcript segments."""

    def __init__(
        self,
        encrypted_path: Path | None = None,
        key_path: Path | None = None,
        plaintext_fallback_path: Path | None = None,
    ):
        self.encrypted_path = encrypted_path or data_path("transcript_history.json.enc")
        self.key_path = key_path or data_path("transcript_history.key")
        self.plaintext_fallback_path = plaintext_fallback_path or data_path("transcript_history.json")

    def load_segments(self, *, retention_minutes: int, history_limit: int) -> list[CaptionSegment]:
        payload = self._read_payload()
        return self._segments_from_payload(payload, retention_minutes=retention_minutes, history_limit=history_limit)

    def prune_expired_cache(self, *, fallback_retention_minutes: int, history_limit: int) -> None:
        payload = self._read_payload()
        retention_minutes = self._payload_retention_minutes(payload, fallback_retention_minutes)
        segments = self._segments_from_payload(payload, retention_minutes=retention_minutes, history_limit=history_limit)
        if not segments:
            self.clear()
            return
        self._write_payload(segments, retention_minutes=retention_minutes)

    def save_segments(self, segments: Iterable[CaptionSegment], *, retention_minutes: int, history_limit: int) -> None:
        filtered = self._filter_segments(list(segments), retention_minutes=retention_minutes, history_limit=history_limit)
        if not filtered:
            self.clear()
            return

        self._write_payload(filtered, retention_minutes=retention_minutes)

    def clear(self) -> None:
        self._delete_file(self.encrypted_path)
        self._delete_file(self.plaintext_fallback_path)

    @property
    def encryption_available(self) -> bool:
        return self._fernet_class() is not None

    @staticmethod
    def _filter_segments(segments: list[CaptionSegment], *, retention_minutes: int, history_limit: int) -> list[CaptionSegment]:
        if retention_minutes <= 0:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(0, int(retention_minutes)))
        filtered = [seg for seg in segments if seg.created_at >= cutoff and seg.text.strip()]
        return filtered[-max(1, int(history_limit)) :]

    def _segments_from_payload(self, payload: dict, *, retention_minutes: int, history_limit: int) -> list[CaptionSegment]:
        raw_segments = payload.get("segments") if isinstance(payload, dict) else []
        if not isinstance(raw_segments, list):
            return []

        segments: list[CaptionSegment] = []
        for item in raw_segments:
            try:
                segments.append(CaptionSegment.model_validate(item))
            except Exception:
                continue
        return self._filter_segments(segments, retention_minutes=retention_minutes, history_limit=history_limit)

    @staticmethod
    def _payload_retention_minutes(payload: dict, fallback_retention_minutes: int) -> int:
        try:
            return max(0, int(payload.get("retention_minutes", fallback_retention_minutes)))
        except Exception:
            return max(0, int(fallback_retention_minutes))

    def _write_payload(self, segments: list[CaptionSegment], *, retention_minutes: int) -> None:
        latest_segment_at = max((seg.created_at for seg in segments), default=datetime.now(timezone.utc))
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "retention_minutes": max(0, int(retention_minutes)),
            "expires_at": (latest_segment_at + timedelta(minutes=max(0, int(retention_minutes)))).isoformat(),
            "segments": [seg.model_dump(mode="json") for seg in segments],
        }
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        encrypted = self._encrypt(data)
        if encrypted is not None:
            self._atomic_write(self.encrypted_path, encrypted)
            self._delete_file(self.plaintext_fallback_path)
            return

        self._atomic_write(self.plaintext_fallback_path, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
        self._delete_file(self.encrypted_path)

    @staticmethod
    def _fernet_class():
        try:
            from cryptography.fernet import Fernet  # type: ignore

            return Fernet
        except Exception:
            return None

    def _read_payload(self) -> dict:
        if self.encrypted_path.exists():
            try:
                decrypted = self._decrypt(self.encrypted_path.read_bytes())
                if decrypted is not None:
                    return json.loads(decrypted.decode("utf-8"))
            except Exception:
                return {}

        if self.plaintext_fallback_path.exists():
            try:
                return json.loads(self.plaintext_fallback_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _get_key(self) -> bytes | None:
        Fernet = self._fernet_class()
        if Fernet is None:
            return None
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()
        key = Fernet.generate_key()
        self._atomic_write(self.key_path, key)
        return key

    def _encrypt(self, data: bytes) -> bytes | None:
        Fernet = self._fernet_class()
        key = self._get_key()
        if Fernet is None or key is None:
            return None
        return Fernet(key).encrypt(data)

    def _decrypt(self, data: bytes) -> bytes | None:
        Fernet = self._fernet_class()
        key = self._get_key()
        if Fernet is None or key is None:
            return None
        return Fernet(key).decrypt(data)

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except Exception:
            pass
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        try:
            tmp.chmod(0o600)
        except Exception:
            pass
        os.replace(tmp, path)

    @staticmethod
    def _delete_file(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
