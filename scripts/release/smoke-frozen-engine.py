#!/usr/bin/env python3
"""Run a repeatable, dependency-free smoke test against a frozen engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EVENT_PREFIX = "CHURCH_CAP_ENGINE_EVENT="
SHUTDOWN_COMMAND = 'CHURCH_CAP_ENGINE_COMMAND={"command":"shutdown","protocol_version":2}\n'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _request(url: str) -> tuple[int, dict[str, str], bytes]:
    # The engine is always local. Ignore host/CI proxy settings so loopback
    # checks cannot leave the machine or fail because of proxy policy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    request = urllib.request.Request(url, method="GET")
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = opener.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(0.5)
                continue
            break
        with response:
            return response.status, dict(response.headers.items()), response.read()
    raise RuntimeError(f"GET {url} failed after bounded retries: {last_error}") from last_error


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if process.stdin is not None:
        try:
            process.stdin.write(SHUTDOWN_COMMAND)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _read_output(process: subprocess.Popen[str], output: list[str], events: queue.Queue[dict[str, Any]]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        output.append(line.rstrip("\r\n"))
        if line.startswith(EVENT_PREFIX):
            try:
                events.put(json.loads(line.removeprefix(EVENT_PREFIX)))
            except json.JSONDecodeError:
                continue


def run_smoke(engine: Path, viewer_port: int, operator_port: int, timeout: float) -> dict[str, Any]:
    engine = engine.resolve()
    if not engine.is_file():
        raise FileNotFoundError(f"Frozen engine does not exist: {engine}")

    bundle_digest_before = _directory_digest(engine.parent)
    started_at = time.monotonic()
    output: list[str] = []
    events: queue.Queue[dict[str, Any]] = queue.Queue()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    with tempfile.TemporaryDirectory(prefix="church-cap-engine-smoke-") as data_dir:
        environment = os.environ.copy()
        environment.update(
            {
                "CHURCH_CAP_RUNTIME_MODE": "packaged",
                "CHURCH_CAP_DATA_DIR": data_dir,
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
            creationflags=creationflags,
        )
        reader = threading.Thread(target=_read_output, args=(process, output, events), daemon=True)
        reader.start()
        states: list[str] = []

        try:
            deadline = started_at + timeout
            ready_event: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Engine exited before readiness with code {process.returncode}")
                try:
                    event = events.get(timeout=0.25)
                except queue.Empty:
                    continue
                state = str(event.get("state", ""))
                states.append(state)
                if state == "ready":
                    ready_event = event
                    break
                if state == "error":
                    raise RuntimeError(f"Engine reported an error: {event.get('detail', '')}")
            if ready_event is None:
                raise TimeoutError(f"Engine did not become ready within {timeout:.0f} seconds")

            startup_seconds = round(time.monotonic() - started_at, 3)
            viewer = f"http://127.0.0.1:{viewer_port}"
            operator = f"http://127.0.0.1:{operator_port}"
            checks: dict[str, Any] = {}

            health_status, _, health_body = _request(f"{viewer}/health")
            health = json.loads(health_body)
            checks["health"] = (
                health_status == 200
                and health.get("ok") is True
                and health.get("app_version") == "0.9.0"
                and health.get("runtime_mode") == "packaged"
                and health.get("engine_protocol_version") == 2
            )

            for name, url in {
                "viewer": f"{viewer}/",
                "display": f"{viewer}/display",
                "obs": f"{viewer}/obs",
                "static": f"{viewer}/static/styles.css",
            }.items():
                status, _, _ = _request(url)
                checks[name] = status == 200

            operator_status, operator_headers, _ = _request(f"{operator}/operator")
            checks["operator_setup_redirect"] = (
                operator_status == 303
                and {key.lower(): value for key, value in operator_headers.items()}.get("location") == "/setup"
            )
            if os.name == "nt":
                setup_status, _, setup_body = _request(f"{operator}/setup")
                checks["windows_cpu_pytorch_label"] = (
                    setup_status == 200
                    and b"PyTorch compatibility (CPU)" in setup_body
                    and b"CPU fallback" in setup_body
                    and b"CUDA verified" not in setup_body
                )
            if not all(checks.values()):
                raise RuntimeError(f"One or more route checks failed: {checks}")
        finally:
            _stop_process(process)
            reader.join(timeout=5)
            while not events.empty():
                states.append(str(events.get_nowait().get("state", "")))

        if process.returncode != 0:
            raise RuntimeError(f"Engine shutdown returned code {process.returncode}")
        if states[-2:] != ["stopping", "stopped"]:
            raise RuntimeError(f"Engine did not report a clean terminal lifecycle: {states}")

        bundle_digest_after = _directory_digest(engine.parent)
        if bundle_digest_after != bundle_digest_before:
            raise RuntimeError("The frozen engine bundle changed while it was running")

        return {
            "ok": True,
            "engine": str(engine),
            "bundle_bytes": _directory_size(engine.parent),
            "bundle_sha256": bundle_digest_after,
            "bundle_unchanged": True,
            "startup_seconds": startup_seconds,
            "app_version": health.get("app_version"),
            "engine_protocol_version": health.get("engine_protocol_version"),
            "states": states,
            "checks": checks,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--viewer-port", type=int, default=18080)
    parser.add_argument("--operator-port", type=int, default=19090)
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    args = parser.parse_args()

    try:
        result = run_smoke(args.engine, args.viewer_port, args.operator_port, args.startup_timeout)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
