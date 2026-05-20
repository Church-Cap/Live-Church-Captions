from __future__ import annotations

import os
import socket
import subprocess
from functools import lru_cache


def local_ip() -> str:
    """Best-effort LAN IP address without sending traffic."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _run(cmd: list[str]) -> str | None:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


@lru_cache(maxsize=1)
def detected_local_hostname() -> str:
    """Return the best friendly local hostname for QR codes.

    On macOS, scutil LocalHostName maps to Bonjour/mDNS as <name>.local.
    If it is not configured, fall back to socket hostname + .local if sensible,
    and finally to the LAN IP address.
    """
    configured = os.environ.get("CAPTION_LOCAL_HOSTNAME", "").strip()
    if configured:
        return configured[:-1] if configured.endswith(".") else configured

    local_host = _run(["scutil", "--get", "LocalHostName"])
    if local_host:
        return local_host if local_host.endswith(".local") else f"{local_host}.local"

    host = socket.gethostname().strip().split(".")[0]
    if host and host.lower() not in {"localhost", "local"}:
        safe = "".join(ch for ch in host if ch.isalnum() or ch == "-").strip("-")
        if safe:
            return f"{safe}.local"

    return local_ip()


def default_base_url(port: int, scheme: str = "http") -> str:
    return f"{scheme}://{detected_local_hostname()}:{port}"
