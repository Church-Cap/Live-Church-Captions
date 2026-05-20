#!/usr/bin/env python3
"""Run Church Cap with separate public viewer and operator ports.

This keeps transcription state in one Python process while exposing two local
HTTP listeners:
- viewer port: public read-only caption/display/OBS pages
- operator port: password-protected controls, optionally localhost-only
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure relative paths are stable even if launched from another directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enable the port-aware security middleware before settings are loaded.
os.environ["DUAL_PORT_MODE"] = "true"

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402
from app.runtime_config import load_runtime_config  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def main() -> None:
    settings = get_settings()
    runtime = load_runtime_config()
    lock_operator = bool(runtime.get("lock_operator_to_localhost", settings.lock_operator_to_localhost))
    operator_host = "127.0.0.1" if lock_operator else settings.host

    viewer_config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.viewer_port,
        log_level="info",
        lifespan="on",
    )
    operator_config = uvicorn.Config(
        app,
        host=operator_host,
        port=settings.operator_port,
        log_level="info",
        lifespan="off",
    )

    viewer_server = uvicorn.Server(viewer_config)
    operator_server = uvicorn.Server(operator_config)

    print("Church Cap dual-port mode")
    print(f"  Viewer:   http://0.0.0.0:{settings.viewer_port}/")
    print(f"  Operator: http://{operator_host}:{settings.operator_port}/operator")
    print(f"  Operator localhost lock: {'on' if lock_operator else 'off'}")

    await asyncio.gather(viewer_server.serve(), operator_server.serve())


if __name__ == "__main__":
    asyncio.run(main())
