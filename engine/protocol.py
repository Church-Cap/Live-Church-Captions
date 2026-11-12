"""Versioned status events exchanged with the native desktop supervisor."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum


ENGINE_PROTOCOL_VERSION = 2
EVENT_PREFIX = "CHURCH_CAP_ENGINE_EVENT="
COMMAND_PREFIX = "CHURCH_CAP_ENGINE_COMMAND="
REQUEST_PREFIX = "CHURCH_CAP_ENGINE_REQUEST="


class EngineState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    CAPTIONS_LIVE = "captions_live"
    CAPTIONS_IDLE = "captions_idle"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class EngineCommandName(StrEnum):
    SHUTDOWN = "shutdown"


class EngineRequestName(StrEnum):
    # Bring the desktop window forward on Settings and run its signed-updater
    # check. Installing still needs the operator to confirm in the desktop app.
    OPEN_UPDATES = "open_updates"


@dataclass(frozen=True)
class EngineCommand:
    command: EngineCommandName
    protocol_version: int = ENGINE_PROTOCOL_VERSION

    def line(self) -> str:
        return COMMAND_PREFIX + json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def parse(cls, line: str) -> "EngineCommand | None":
        if not line.startswith(COMMAND_PREFIX):
            return None
        try:
            payload = json.loads(line.removeprefix(COMMAND_PREFIX))
            if payload.get("protocol_version") != ENGINE_PROTOCOL_VERSION:
                return None
            if set(payload) != {"command", "protocol_version"}:
                return None
            return cls(command=EngineCommandName(payload["command"]))
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class EngineEvent:
    state: EngineState
    app_version: str
    viewer_url: str
    operator_url: str
    detail: str = ""
    protocol_version: int = ENGINE_PROTOCOL_VERSION
    pid: int = 0

    def payload(self) -> dict[str, str | int]:
        values = asdict(self)
        values["pid"] = self.pid or os.getpid()
        return values

    def line(self) -> str:
        return EVENT_PREFIX + json.dumps(self.payload(), separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class EngineRequest:
    """A user-initiated request from the engine for the desktop supervisor."""

    request: EngineRequestName
    protocol_version: int = ENGINE_PROTOCOL_VERSION
    pid: int = 0

    def payload(self) -> dict[str, str | int]:
        values = asdict(self)
        values["pid"] = self.pid or os.getpid()
        return values

    def line(self) -> str:
        return REQUEST_PREFIX + json.dumps(self.payload(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def parse(cls, line: str) -> "EngineRequest | None":
        if not line.startswith(REQUEST_PREFIX):
            return None
        try:
            payload = json.loads(line.removeprefix(REQUEST_PREFIX))
            if payload.get("protocol_version") != ENGINE_PROTOCOL_VERSION:
                return None
            if set(payload) != {"request", "protocol_version", "pid"}:
                return None
            pid = payload["pid"]
            if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                return None
            return cls(request=EngineRequestName(payload["request"]), pid=pid)
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
            return None
