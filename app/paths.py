from __future__ import annotations

import os
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def app_support_dir() -> Path:
    """Return a stable per-user data directory for Church Cap.

    This deliberately lives outside the downloaded/extracted project folder so
    operator passwords and runtime settings survive app updates, re-extracts,
    Terminal restarts, and virtualenv rebuilds.
    """
    override = os.getenv("CHURCH_CAP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Church Cap"

    if platform.system() == "Windows":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Church Cap"

    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "church-cap"


def data_path(filename: str) -> Path:
    return app_support_dir() / "data" / filename


def migrate_project_data(filename: str, destination: Path) -> None:
    """Copy old project-local data/<filename> to the new stable location once."""
    legacy = PROJECT_ROOT / "data" / filename
    if destination.exists() or not legacy.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(legacy.read_bytes())
