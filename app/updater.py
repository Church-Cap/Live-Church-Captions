import os
import platform
import re
import subprocess
import time
import urllib.request
from pathlib import Path


REMOTE_SETTINGS_URL = "https://raw.githubusercontent.com/Church-Cap/Live-Church-Captions/main/app/settings.py"


def normalise_version(version: str | None) -> str:
    text = str(version or "").strip()
    if text.startswith("v."):
        text = text[2:]
    elif text.startswith("v"):
        text = text[1:]
    return text.strip()


def version_label(version: str | None) -> str:
    clean = normalise_version(version)
    return f"v.{clean}" if clean else "unknown"


def version_tuple(version: str | None) -> tuple[int, ...]:
    clean = normalise_version(version)
    parts = re.findall(r"\d+", clean)
    return tuple(int(part) for part in parts) if parts else (0,)


def is_remote_newer(remote_version: str | None, current_version: str | None) -> bool:
    return version_tuple(remote_version) > version_tuple(current_version)


def parse_version_from_settings(text: str) -> str | None:
    match = re.search(r'app_version\s*:\s*str\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def fetch_remote_version(timeout_seconds: int = 8) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            REMOTE_SETTINGS_URL,
            headers={"User-Agent": "Church-Cap-Updater"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
            remote_version = parse_version_from_settings(body)
            if not remote_version:
                raise RuntimeError("GitHub version file did not include an app version.")
            return normalise_version(remote_version)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2)
    raise RuntimeError(f"Could not read the latest Church Cap version from GitHub: {last_error}")


def update_script_for_system(project_root: Path, system_name: str | None = None) -> Path | None:
    system = system_name or platform.system()
    if system == "Darwin":
        return project_root / "update-macos.sh"
    if system == "Windows":
        return project_root / "update-windows.ps1"
    return None


def launch_update_process(project_root: Path, target_version: str | None = None) -> dict:
    system = platform.system()
    script = update_script_for_system(project_root, system)
    if script is None or not script.exists():
        raise RuntimeError(f"Church Cap updates are not configured for {system or 'this operating system'}.")

    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "update.log"
    log_file = open(log_path, "ab", buffering=0)
    env = os.environ.copy()
    env["CHURCH_CAP_UPDATE_STARTED_FROM"] = "operator"
    if target_version:
        env["CHURCH_CAP_UPDATE_TARGET_VERSION"] = normalise_version(target_version)

    server_pid = str(os.getpid())
    if system == "Darwin":
        cmd = ["/usr/bin/env", "bash", str(script), "--yes", "--restart", "--server-pid", server_pid]
        creation_kwargs = {"start_new_session": True}
    else:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Yes",
            "-Restart",
            "-ServerPid",
            server_pid,
        ]
        creationflags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        creation_kwargs = {"creationflags": creationflags} if creationflags else {}

    process = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        close_fds=(system != "Windows"),
        env=env,
        **creation_kwargs,
    )
    return {"pid": process.pid, "log_path": str(log_path)}
