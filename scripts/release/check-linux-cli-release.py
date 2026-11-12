"""Validate the curated Church Cap Linux CLI release archive."""

from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path, PurePosixPath


REQUIRED = {
    "app/main.py",
    "app/templates/operator.html",
    "app/static/styles.css",
    "engine/entrypoint.py",
    "engine/protocol.py",
    "setup-linux.sh",
    "start-linux.sh",
    "update-linux.sh",
    "install-cuda-runtime-linux.sh",
    "factory-reset-linux.sh",
    "scripts/linux-system-packages.sh",
    "scripts/linux-python-runtime.sh",
    "scripts/factory-reset.py",
    "scripts/update-unix.sh",
    "scripts/run-dual.py",
    "requirements.txt",
    "env.example",
    "LICENSE",
}
FORBIDDEN_TOP_LEVEL = {"desktop", "dist", "tests", ".git", ".venv", ".tooling", "work", "build"}
FORBIDDEN_NAMES = {".DS_Store", "update-macos.sh"}


def check(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
    roots = {PurePosixPath(member.name).parts[0] for member in members if PurePosixPath(member.name).parts}
    if roots != {"Church-Cap-Linux-CLI"}:
        raise RuntimeError(f"Unexpected archive roots: {sorted(roots)}")
    relative: dict[str, tarfile.TarInfo] = {}
    for member in members:
        parts = PurePosixPath(member.name).parts
        if member.issym() or member.islnk():
            raise RuntimeError(f"Archive must not contain links: {member.name}")
        if len(parts) < 2:
            continue
        name = PurePosixPath(*parts[1:]).as_posix()
        if ".." in parts or PurePosixPath(name).is_absolute():
            raise RuntimeError(f"Unsafe member: {member.name}")
        if parts[1] in FORBIDDEN_TOP_LEVEL:
            raise RuntimeError(f"Forbidden release content: {member.name}")
        if PurePosixPath(name).name in FORBIDDEN_NAMES:
            raise RuntimeError(f"Forbidden platform/metadata file: {member.name}")
        relative[name] = member
    missing = sorted(REQUIRED - relative.keys())
    if missing:
        raise RuntimeError("Archive is missing required files: " + ", ".join(missing))
    for name, member in relative.items():
        if name.endswith(".sh") and member.mode & 0o111 == 0:
            raise RuntimeError(f"Shell script is not executable: {name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"Validated {path} ({len(relative)} files)")
    print(f"SHA-256 {digest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    check(args.archive.resolve())


if __name__ == "__main__":
    main()
