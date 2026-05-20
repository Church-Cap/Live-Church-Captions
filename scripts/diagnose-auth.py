#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def app_support_dir() -> Path:
    override = os.getenv("CHURCH_CAP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Church Cap"
    if platform.system() == "Windows":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Church Cap"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "church-cap"


AUTH_PATH = app_support_dir() / "data" / "operator_auth.json"
AUTH_BACKUP_PATH = app_support_dir() / "data" / "operator_auth.backup.json"

print("Church Cap auth diagnostic")
print(f"Project root: {PROJECT_ROOT}")
print(f"Stable data directory: {app_support_dir()}")
print(f"Auth file: {AUTH_PATH}")
print(f"Auth file exists: {AUTH_PATH.exists()}")
print(f"Auth backup file: {AUTH_BACKUP_PATH}")
print(f"Auth backup exists: {AUTH_BACKUP_PATH.exists()}")

def print_auth_file_status(path: Path, label: str) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{label} has password hash: {bool(data.get('password_hash'))}")
        print(f"{label} has session secret: {bool(data.get('session_secret'))}")
        print(f"{label} password source: {data.get('password_source', 'unknown')}")
    except Exception as exc:
        print(f"Could not read {label}: {exc}")


print_auth_file_status(AUTH_PATH, "Primary auth file")
print_auth_file_status(AUTH_BACKUP_PATH, "Backup auth file")

legacy = PROJECT_ROOT / "data" / "operator_auth.json"
print(f"Legacy project auth file: {legacy}")
print(f"Legacy project auth exists: {legacy.exists()}")
