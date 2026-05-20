#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then PYTHON_BIN="python3"; fi
"$PYTHON_BIN" - <<'PY'
import os
import platform
from pathlib import Path

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

paths = [
    app_support_dir() / "data" / "operator_auth.json",
    app_support_dir() / "data" / "operator_auth.backup.json",
]
deleted = False
for path in paths:
    if path.exists():
        path.unlink()
        deleted = True
        print(f"Deleted {path}")
    else:
        print(f"No auth file found at {path}")
if not deleted:
    print("No stored operator password files were found.")
print("Restart Church Cap and open /operator to create a new password.")
PY
