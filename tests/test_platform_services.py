import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from app.platform_services.contracts import PlatformFeature
from app.platform_services.packaged_adapter import PackagedPlatformAdapter
from app.platform_services.paths import RuntimeMode, runtime_mode, runtime_paths
from app.platform_services.source_adapter import SourcePlatformAdapter
from engine.protocol import (
    COMMAND_PREFIX,
    ENGINE_PROTOCOL_VERSION,
    EVENT_PREFIX,
    EngineCommand,
    EngineCommandName,
    EngineEvent,
    EngineRequest,
    EngineRequestName,
    EngineState,
    REQUEST_PREFIX,
)


class RuntimePathTests(unittest.TestCase):
    def test_source_mode_keeps_models_in_the_source_tree(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"CHURCH_CAP_RUNTIME_MODE": "source", "CHURCH_CAP_DATA_DIR": temporary},
            clear=False,
        ):
            paths = runtime_paths()
        self.assertEqual(paths.mode, RuntimeMode.SOURCE)
        self.assertEqual(paths.support, Path(temporary).resolve())
        self.assertEqual(paths.models.name, "models")
        self.assertEqual(paths.models.parent.name, "data")

    def test_packaged_mode_puts_all_mutable_categories_in_app_support(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"CHURCH_CAP_RUNTIME_MODE": "packaged", "CHURCH_CAP_DATA_DIR": temporary},
            clear=False,
        ):
            paths = runtime_paths()
        self.assertEqual(paths.mode, RuntimeMode.PACKAGED)
        for path in (paths.data, paths.config, paths.models, paths.cache, paths.logs, paths.updates, paths.recovery, paths.exports):
            self.assertEqual(path.parent, Path(temporary).resolve())

    def test_invalid_explicit_runtime_mode_fails_closed(self):
        with patch.dict(os.environ, {"CHURCH_CAP_RUNTIME_MODE": "desktop-ish"}, clear=False):
            with self.assertRaises(ValueError):
                runtime_mode()


class PlatformAdapterTests(unittest.TestCase):
    def test_source_adapter_only_advertises_existing_allow_listed_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "update-macos.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            adapter = SourcePlatformAdapter(root, system="Darwin")
            self.assertTrue(adapter.capability(PlatformFeature.APPLICATION_UPDATE).available)
            self.assertFalse(adapter.capability(PlatformFeature.CUDA_RUNTIME_INSTALL).available)

    def test_packaged_adapter_defaults_to_no_native_privileges(self):
        adapter = PackagedPlatformAdapter()
        state = adapter.capability(PlatformFeature.PASSWORD_RESET)
        self.assertFalse(state.available)
        self.assertEqual(state.backend, "desktop-supervisor-ipc")

    def test_packaged_adapter_exposes_only_supervisor_advertised_features(self):
        adapter = PackagedPlatformAdapter([PlatformFeature.PASSWORD_RESET])
        self.assertTrue(adapter.capability(PlatformFeature.PASSWORD_RESET).available)
        self.assertFalse(adapter.capability(PlatformFeature.APPLICATION_UPDATE).available)


class EngineProtocolTests(unittest.TestCase):
    def test_engine_event_is_versioned_single_line_json(self):
        line = EngineEvent(
            state=EngineState.STARTING,
            app_version="0.8.0",
            viewer_url="http://127.0.0.1:8080/",
            operator_url="http://127.0.0.1:9090/operator",
        ).line()
        self.assertTrue(line.startswith(EVENT_PREFIX))
        payload = json.loads(line.removeprefix(EVENT_PREFIX))
        self.assertEqual(payload["protocol_version"], ENGINE_PROTOCOL_VERSION)
        self.assertEqual(payload["state"], "starting")
        self.assertGreater(payload["pid"], 0)
        self.assertNotIn("\n", line)

    def test_engine_protocol_has_terminal_stopped_state(self):
        self.assertEqual(EngineState.STOPPED.value, "stopped")

    def test_caption_transitions_are_explicit_and_versioned(self):
        from engine.entrypoint import caption_state_transition

        live = caption_state_transition("stopped", "listening")
        self.assertEqual(live[0], EngineState.CAPTIONS_LIVE)
        self.assertEqual(caption_state_transition("stopped", "starting")[0], EngineState.CAPTIONS_LIVE)
        self.assertEqual(caption_state_transition("listening", "sensitive")[0], EngineState.CAPTIONS_LIVE)
        self.assertEqual(caption_state_transition("sensitive", "stopped")[0], EngineState.CAPTIONS_IDLE)
        self.assertIsNone(caption_state_transition("stopped", "idle"))
        self.assertEqual(ENGINE_PROTOCOL_VERSION, 2)

    def test_engine_shutdown_command_is_versioned_and_allow_listed(self):
        line = EngineCommand(EngineCommandName.SHUTDOWN).line()
        self.assertTrue(line.startswith(COMMAND_PREFIX))
        self.assertEqual(EngineCommand.parse(line), EngineCommand(EngineCommandName.SHUTDOWN))
        self.assertIsNone(EngineCommand.parse(COMMAND_PREFIX + '{"command":"run","protocol_version":2}'))
        self.assertIsNone(EngineCommand.parse(COMMAND_PREFIX + '{"command":"shutdown","protocol_version":1}'))

    def test_engine_update_request_is_versioned_and_allow_listed(self):
        line = EngineRequest(EngineRequestName.OPEN_UPDATES, pid=4321).line()
        self.assertTrue(line.startswith(REQUEST_PREFIX))
        self.assertFalse(line.startswith(EVENT_PREFIX))
        self.assertEqual(
            line,
            REQUEST_PREFIX + '{"pid":4321,"protocol_version":2,"request":"open_updates"}',
        )
        self.assertEqual(EngineRequest.parse(line), EngineRequest(EngineRequestName.OPEN_UPDATES, pid=4321))
        self.assertIsNone(EngineRequest.parse(REQUEST_PREFIX + '{"pid":4321,"protocol_version":2,"request":"install_update"}'))
        self.assertIsNone(EngineRequest.parse(REQUEST_PREFIX + '{"pid":4321,"protocol_version":1,"request":"open_updates"}'))
        self.assertIsNone(EngineRequest.parse(REQUEST_PREFIX + '{"pid":0,"protocol_version":2,"request":"open_updates"}'))
        self.assertIsNone(EngineRequest.parse(REQUEST_PREFIX + '{"pid":4321,"protocol_version":2,"request":"open_updates","url":"x"}'))

    def test_engine_interrupt_is_a_successful_supervisor_stop(self):
        from engine.entrypoint import main

        def interrupt(coroutine):
            coroutine.close()
            raise KeyboardInterrupt

        with patch("engine.entrypoint.asyncio.run", side_effect=interrupt):
            self.assertEqual(main(), 0)

    def test_packaged_runtime_keeps_model_cache_in_application_data(self):
        from engine.entrypoint import configure_runtime_environment

        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"CHURCH_CAP_RUNTIME_MODE": "packaged", "CHURCH_CAP_DATA_DIR": temporary},
            clear=True,
        ):
            configure_runtime_environment()
            self.assertEqual(Path(os.environ["HF_HOME"]), Path(temporary) / "cache" / "huggingface")

    def test_packaged_resource_install_uses_engine_without_starting_servers(self):
        from engine.entrypoint import main

        with patch.dict(
            os.environ,
            {
                "CHURCH_CAP_RESOURCE_INSTALL": "translation",
                "CHURCH_CAP_RESOURCE_KIND": "ct2small100",
            },
            clear=False,
        ), patch("app.resource_installer.install_translation") as install, patch(
            "engine.entrypoint.asyncio.run"
        ) as run:
            self.assertEqual(main(), 0)

        install.assert_called_once_with("ct2small100")
        run.assert_not_called()

    def test_unknown_packaged_resource_mode_fails_closed(self):
        from engine.entrypoint import main

        with patch.dict(os.environ, {"CHURCH_CAP_RESOURCE_INSTALL": "shell"}, clear=False), patch(
            "engine.entrypoint.asyncio.run"
        ) as run:
            self.assertEqual(main(), 1)

        run.assert_not_called()

    def test_engine_supervisor_liveness_probe_fails_closed(self):
        from engine.entrypoint import supervisor_process_is_alive

        with patch("engine.entrypoint.os.kill") as probe:
            self.assertTrue(supervisor_process_is_alive(4321))
            probe.assert_called_once_with(4321, 0)
        with patch("engine.entrypoint.os.kill", side_effect=ProcessLookupError):
            self.assertFalse(supervisor_process_is_alive(4321))
        self.assertFalse(supervisor_process_is_alive(1))

    def test_health_contract_advertises_runtime_and_protocol(self):
        source = Path("app/main.py").read_text(encoding="utf-8")
        health = source.split('async def health():', 1)[1].split("def _device_to_api", 1)[0]
        self.assertIn('"runtime_mode": runtime_mode().value', health)
        self.assertIn('"engine_protocol_version": ENGINE_PROTOCOL_VERSION', health)


class EngineTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_parent_monitor_requests_shutdown_after_reparenting(self):
        from engine.entrypoint import monitor_supervisor_process

        reasons = []
        forced = []
        with patch("engine.entrypoint.supervisor_process_is_alive", return_value=False):
            monitor_supervisor_process(
                4321,
                reasons.append,
                force_exit=forced.append,
                sleep=lambda _seconds: None,
                force_timeout_seconds=0,
            )
        self.assertEqual(reasons, ["supervisor_process_exited"])
        self.assertEqual(forced, [0])

    async def test_parent_monitor_force_deadline_survives_closed_event_loop(self):
        from engine.entrypoint import monitor_supervisor_process

        forced = []

        def closed_loop(_detail):
            raise RuntimeError("event loop is closed")

        with patch("engine.entrypoint.supervisor_process_is_alive", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "event loop is closed"):
                monitor_supervisor_process(
                    4321,
                    closed_loop,
                    force_exit=forced.append,
                    sleep=lambda _seconds: None,
                    force_timeout_seconds=0,
                )
        self.assertEqual(forced, [0])

    async def test_caption_monitor_emits_only_live_boundary_changes(self):
        from engine.entrypoint import monitor_caption_state

        class FakeHub:
            status = "stopped"

            def state(self):
                return SimpleNamespace(status=self.status)

        hub = FakeHub()
        shutdown = asyncio.Event()
        emitted = []
        task = asyncio.create_task(
            monitor_caption_state(hub, lambda state, detail: emitted.append((state, detail)), shutdown)
        )
        await asyncio.sleep(0)
        hub.status = "starting"
        await asyncio.sleep(0.25)
        hub.status = "listening"
        await asyncio.sleep(0.25)
        hub.status = "stopped"
        await asyncio.sleep(0.25)
        shutdown.set()
        await task

        self.assertEqual(
            [state for state, _ in emitted],
            [EngineState.CAPTIONS_LIVE, EngineState.CAPTIONS_LIVE, EngineState.CAPTIONS_IDLE],
        )


if __name__ == "__main__":
    unittest.main()
