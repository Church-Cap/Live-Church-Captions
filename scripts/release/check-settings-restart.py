#!/usr/bin/env python3
"""Verify a packaged Church Cap engine preserves language policy across restarts."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


EVENT_PREFIX = "CHURCH_CAP_ENGINE_EVENT="
SHUTDOWN_COMMAND = 'CHURCH_CAP_ENGINE_COMMAND={"command":"shutdown","protocol_version":2}\n'


def read_output(
    process: subprocess.Popen[str], output: list[str], events: queue.Queue[dict[str, Any]]
) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        output.append(line.rstrip())
        if not line.startswith(EVENT_PREFIX):
            continue
        try:
            events.put(json.loads(line.removeprefix(EVENT_PREFIX)))
        except json.JSONDecodeError:
            pass


def get_json(url: str) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=10) as response:
        return json.loads(response.read())


def run_cycle(
    engine: Path,
    data_dir: Path,
    viewer_port: int,
    operator_port: int,
    timeout: float,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "CHURCH_CAP_RUNTIME_MODE": "packaged",
            "CHURCH_CAP_DATA_DIR": str(data_dir),
            "VIEWER_PORT": str(viewer_port),
            "OPERATOR_PORT": str(operator_port),
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [str(engine)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=environment,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    output: list[str] = []
    events: queue.Queue[dict[str, Any]] = queue.Queue()
    reader = threading.Thread(target=read_output, args=(process, output, events), daemon=True)
    reader.start()
    states: list[str] = []
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"engine exited before readiness with {process.returncode}: {output[-12:]}"
                )
            try:
                event = events.get(timeout=0.25)
            except queue.Empty:
                continue
            state = str(event.get("state") or "")
            states.append(state)
            if state == "ready":
                break
        else:
            raise TimeoutError("engine did not become ready")

        health = get_json(f"http://127.0.0.1:{viewer_port}/health")
        languages = get_json(f"http://127.0.0.1:{viewer_port}/api/languages")
        translation = languages.get("translation") or {}
        if not health.get("ok"):
            raise RuntimeError(f"health check failed: {health}")
        if translation.get("language_policy") != "restricted":
            raise RuntimeError(f"language policy was not restored: {translation}")
        if set(translation.get("available_languages") or []) != {"en", "fr"}:
            raise RuntimeError(f"allowed languages were not restored: {translation}")
    finally:
        if process.poll() is None and process.stdin is not None:
            process.stdin.write(SHUTDOWN_COMMAND)
            process.stdin.flush()
        try:
            process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        reader.join(timeout=5)
        while not events.empty():
            states.append(str(events.get_nowait().get("state") or ""))

    if process.returncode != 0:
        raise RuntimeError(f"engine shutdown returned {process.returncode}: {output[-12:]}")
    if states[-2:] != ["stopping", "stopped"]:
        raise RuntimeError(f"engine did not stop cleanly: {states}")
    return {"states": states, "policy": "restricted", "languages": ["en", "fr"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--viewer-port", type=int, default=18082)
    parser.add_argument("--operator-port", type=int, default=19092)
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    args = parser.parse_args()
    engine = args.engine.expanduser().resolve()
    if not engine.is_file():
        parser.error(f"engine does not exist: {engine}")

    with tempfile.TemporaryDirectory(prefix="church-cap-settings-restart-") as temporary:
        root = Path(temporary)
        config_path = root / "data" / "runtime_config.json"
        config_path.parent.mkdir(parents=True)
        saved = {
            "translation_enabled": True,
            "translation_provider": "demo",
            "translation_allowed_languages": ["en", "fr"],
            "translation_max_active_languages": 2,
            "translation_language_policy": "restricted",
            "translation_priority_mode": "pinned_first",
            "translation_language_requests_enabled": False,
            "translation_timing_mode": "responsive",
            "operator_theme": "dark",
        }
        config_path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        before = config_path.read_bytes()
        first = run_cycle(
            engine, root, args.viewer_port, args.operator_port, args.startup_timeout
        )
        after_first = config_path.read_bytes()
        second = run_cycle(
            engine, root, args.viewer_port, args.operator_port, args.startup_timeout
        )
        after_second = config_path.read_bytes()
        if before != after_first or before != after_second:
            raise RuntimeError("the saved runtime configuration changed during restart testing")

    print(
        json.dumps(
            {
                "ok": True,
                "engine": str(engine),
                "cycles": [first, second],
                "config_unchanged": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
