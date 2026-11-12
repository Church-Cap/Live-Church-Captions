from __future__ import annotations

from pathlib import Path

from app.platform_services.paths import (
    SOURCE_ROOT as PROJECT_ROOT,
    app_support_dir,
    data_path,
    model_data_dir,
    resource_root,
    runtime_mode,
    runtime_paths,
)


def migrate_project_data(filename: str, destination: Path) -> None:
    """Copy old project-local data/<filename> to the new stable location once."""
    # A factory reset must not immediately resurrect a legacy project-local
    # password or runtime configuration before the new setup is completed.
    if (destination.parent / "factory_reset.flag").is_file():
        return
    legacy = PROJECT_ROOT / "data" / filename
    if destination.exists() or not legacy.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(legacy.read_bytes())


__all__ = [
    "PROJECT_ROOT",
    "app_support_dir",
    "data_path",
    "migrate_project_data",
    "model_data_dir",
    "resource_root",
    "runtime_mode",
    "runtime_paths",
]
