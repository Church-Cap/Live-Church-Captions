# Roadmap To v1.0.0

Church Cap v0.5.0 starts the move from a single preview app toward one maintained codebase with two supported experiences:

- the open-source desktop app for macOS, Windows, and Linux
- the Church Cap Appliance profile for locked-down AlmaLinux boxes

The aim is not to fork the app. Shared captioning, audio, translation, security, update, and UI code should stay in one project. Appliance-specific behaviour should be selected by explicit deployment identity, not by guessing from hardware.

## v0.5.x Stabilisation

- Keep the explicit deployment profile system: `desktop`, `appliance_cpu`, and `appliance_gpu`.
- Keep appliance setup on the secure local operator port `9090`.
- Finish server-side capability guards so appliance limits cannot be bypassed by stale runtime settings or manual API calls.
- Add regression tests for deployment profiles, CPU appliance translation caps, warning flows, and appliance identity files.
- Continue polishing the appliance shell on 7-inch touch displays.

## v0.6.x Translation Performance

- Move heavier translation paths toward CTranslate2/INT8 where practical.
- Keep Argos as the lightweight Base path for language packs that perform well enough.
- Benchmark CPU-only systems with 1-2 active translated languages and GPU systems with higher active-language limits.
- Add clearer operator recommendations based on measured latency, CPU load, GPU readiness, and active viewer-language demand.

## v0.7.x Appliance Update And Recovery

- Provide a signed or checksum-verified updater path for the Church Cap app.
- Provide a matching updater path for the appliance shell.
- Document rollback, recovery, and factory reset procedures.
- Keep `/etc/churchcap-appliance/identity.json` and appliance secrets outside app release folders.

## v0.8.x Release Hardening

- Run a repeatable test matrix across macOS, Windows CPU, Windows NVIDIA, Linux CPU, Linux NVIDIA, AlmaLinux CPU appliance, and AlmaLinux GPU appliance.
- Add diagnostics that clearly report deployment profile, CUDA readiness, audio device formats, and translation capacity.
- Review accessibility, keyboard/touch use, and small-display layouts.

## v0.9.x Public Candidate

- Freeze the operator workflow and appliance setup flow except for bug fixes.
- Complete privacy, safeguarding, translation, and accessibility documentation.
- Produce a clean migration guide from preview releases.
- Verify that desktop installs never enter appliance mode unless explicitly configured.

## v1.0.0 Criteria

- A non-technical church can install, start, recover, and update the standard app from the docs.
- A Church Cap Appliance can boot into the kiosk shell, join Wi-Fi, use the correct profile, and recover from common faults without terminal access.
- English captions are stable on recommended CPU hardware.
- Multilingual captions have clear supported-hardware guidance and fail safely when hardware is not suitable.
- The project has tests and documentation covering the supported desktop and appliance paths.
