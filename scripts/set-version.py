#!/usr/bin/env python3
"""Update allow-listed Church Cap application version declarations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")
PLAIN_TEXT_FILES = (
    "app/settings.py",
    "app/windows_cuda_runtime.py",
    "app/templates/captions.html",
    "app/templates/display.html",
    "app/templates/obs.html",
    "app/templates/operator.html",
    "app/templates/service_leader.html",
    "app/templates/setup.html",
    "app/templates/setup_finish.html",
    "app/templates/setup_recovery.html",
    "desktop/package.json",
    "desktop/package-lock.json",
    "desktop/src/index.html",
    "desktop/src/main.js",
    "desktop/src-tauri/Cargo.toml",
    "desktop/src-tauri/src/model.rs",
    "desktop/src-tauri/tauri.conf.json",
    "env.example",
    "packaging/engine/README.md",
    "scripts/release/build-internal-macos-dmg.sh",
    "scripts/release/build-macos-dmg.sh",
    "scripts/release/check-macos-app-bundle.sh",
    "scripts/release/check-macos-packaging-host.sh",
    "scripts/release/generate-macos-dmg-background.swift",
    "scripts/release/notarize-macos-dmg.sh",
    "scripts/release/smoke-frozen-engine.py",
    "scripts/linux-python-runtime.sh",
    "setup-linux.sh",
)


def atomic_write(path: Path, text: str) -> None:
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        if existing_mode is not None:
            os.chmod(temporary, existing_mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def updated_cargo_lock(old: str, new: str) -> tuple[Path, str]:
    path = ROOT / "desktop/src-tauri/Cargo.lock"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r'(\[\[package\]\]\nname = "church-cap-desktop"\nversion = ")' + re.escape(old) + r'("\n)')
    updated, count = pattern.subn(rf"\g<1>{new}\g<2>", text)
    if count != 1:
        raise RuntimeError(f"Expected one Church Cap package version in {path.relative_to(ROOT)}, found {count}.")
    return path, updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Semantic version without a leading v, for example 0.8.1")
    args = parser.parse_args()
    new = args.version.strip()
    if not SEMVER.fullmatch(new):
        parser.error("version must be semantic version text without a leading v")
    old = VERSION_FILE.read_text(encoding="utf-8").strip()
    if old == new:
        print(f"Church Cap is already {new}.")
        return 0
    if not SEMVER.fullmatch(old):
        raise RuntimeError("VERSION does not contain a valid current semantic version.")

    changes: dict[Path, str] = {}
    for relative in PLAIN_TEXT_FILES:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        if old not in text and new not in text:
            raise RuntimeError(f"Expected current or requested version in {relative}; no files were changed.")
        changes[path] = text.replace(old, new)
    cargo_path, cargo_text = updated_cargo_lock(old, new)
    changes[cargo_path] = cargo_text

    for relative in ("desktop/package.json", "desktop/package-lock.json", "desktop/src-tauri/tauri.conf.json"):
        json.loads(changes[ROOT / relative])
    for path, text in changes.items():
        atomic_write(path, text)
    atomic_write(VERSION_FILE, f"{new}\n")
    print(f"Updated Church Cap {old} -> {new}. Review the Git diff and run version identity tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
