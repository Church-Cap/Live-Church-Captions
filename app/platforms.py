from __future__ import annotations

import platform


def performance_platform_key(system_name: str | None = None) -> str:
    system_name = system_name or platform.system()
    if system_name == "Darwin":
        return "macos"
    if system_name == "Windows":
        return "windows"
    if system_name == "Linux":
        return "linux"
    return "unsupported"
