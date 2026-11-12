#!/usr/bin/env python3
"""Dependency-free Git safety checks. Reports paths/reasons, never secret values.

Default: scan the exact Git index (including files forced past .gitignore).
--worktree: scan tracked and non-ignored untracked working files.
--history: additionally check reachable local Git history for secret indicators.
This is a guardrail, not a guarantee that arbitrary credentials are detectable.
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

PUBLIC_KEY = "packaging/updater/church-cap-updater-public.key"
MAX_BYTES = 10 * 1024 * 1024
SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
GENERATED_PARTS = {
    "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cache", ".tooling", ".tools", "dist", "build", "target", "work", "models",
    "downloads", "release-assets", "release-evidence", "release-staging",
    "releases", "archive", "internal-notes",
}
PAYLOAD_SUFFIXES = (".exe", ".dmg", ".msi", ".zip", ".tar.gz", ".tar.bz2", ".7z",
                    ".onnx", ".pt", ".pth", ".safetensors", ".pyc", ".pyo", ".log")
SECRET_PATTERNS = (
    ("private key content", re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("Minisign secret key content", re.compile(rb"^untrusted comment:[^\r\n]*secret key", re.I | re.M)),
    ("GitHub access token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{60,255})\b")),
    ("AWS access key ID", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack access token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def path_issues(name: str, *, history: bool = False) -> list[str]:
    path = PurePosixPath(name.lower())
    leaf = path.name
    issues = []
    example = leaf in {".env.example", ".env.sample", "env.example"}
    if ((leaf == ".env" or leaf.startswith(".env.")) and not example
            or (path.suffix in SECRET_SUFFIXES and name != PUBLIC_KEY)
            or leaf in {"id_rsa", "id_ed25519", "runtime_config.json"}
            or leaf.startswith("operator_auth") and leaf.endswith(".json")
            or any(part in {"secrets", "certs", "data"} for part in path.parts)):
        issues.append("private/local configuration filename")
    if not history and (any(part in GENERATED_PARTS or part.startswith(".venv")
                            or part.endswith(".app") for part in path.parts)
                        or leaf.endswith(PAYLOAD_SUFFIXES)
                        or leaf == ".ds_store" or leaf.startswith("._")):
        issues.append("generated file, cache or release payload")
    return issues


def content_issues(name: str, content: bytes, *, history: bool = False) -> list[str]:
    issues = [label for label, pattern in SECRET_PATTERNS if pattern.search(content)]
    # Tauri signing files can wrap the Minisign document in base64.
    if len(content) < 16384:
        try:
            decoded = base64.b64decode(content.strip(), validate=True)
        except (ValueError, base64.binascii.Error):
            decoded = b""
        if re.search(rb"^untrusted comment:[^\r\n]*secret key", decoded, re.I | re.M):
            issues.append("encoded Minisign secret key content")
    if len(content) > MAX_BYTES and not history:
        issues.append("file exceeds the 10 MB source-file limit")
    return issues


def scan_index() -> list[tuple[str, str]]:
    findings = []
    for record in git("ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        name = raw_name.decode("utf-8", "surrogateescape")
        if stage != b"0":
            findings.append((name, "unresolved merge conflict"))
            continue
        if mode in {b"120000", b"160000"}:
            findings.append((name, "symlink/submodule requires explicit safety review"))
            continue
        issues = path_issues(name) + content_issues(name, git("cat-file", "blob", oid.decode()))
        findings.extend((name, issue) for issue in issues)
    return findings


def scan_worktree() -> list[tuple[str, str]]:
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    findings = []
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    for raw_name in sorted(set(names.split(b"\0")) - {b""}):
        name = raw_name.decode("utf-8", "surrogateescape")
        path = root / name
        if path.is_symlink():
            findings.append((name, "symlink requires explicit safety review"))
        elif path.is_file():
            issues = path_issues(name) + content_issues(name, path.read_bytes())
            findings.extend((name, issue) for issue in issues)
    return findings


def scan_history() -> list[tuple[str, str]]:
    findings = []
    # Scan unique reachable blobs. No credential values or blob contents are printed.
    records = git("rev-list", "--objects", "--all").splitlines()
    for record in records:
        oid, _, raw_name = record.partition(b" ")
        if git("cat-file", "-t", oid.decode()).strip() != b"blob":
            continue
        name = raw_name.decode("utf-8", "replace")
        issues = path_issues(name, history=True)
        issues += content_issues(name, git("cat-file", "blob", oid.decode()), history=True)
        findings.extend((f"history {oid.decode()[:12]} {name}", issue) for issue in issues)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    try:
        findings = scan_worktree() if args.worktree else scan_index()
        if args.history:
            findings += scan_history()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Repository check could not complete ({type(exc).__name__}); refusing to pass.", file=sys.stderr)
        return 2
    for name, reason in sorted(set(findings)):
        print(f"BLOCKED {name!r}: {reason}")
    if findings:
        print("Remove sensitive/generated files from the proposed commit. Never paste secrets into an issue.")
        return 1
    print("Repository hygiene checks passed (known patterns only; manual review still required).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
