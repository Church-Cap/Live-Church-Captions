# Church Cap Cross-Platform Architecture

Last updated: 2026-08-21

## One product, one browser application

Church Cap remains browser-first on every platform. The native Mac and Windows applications start, supervise, update, and stop the same local web server; Linux may continue to use CLI scripts around that server. Platform packaging must never create a second Operator interface or a platform-specific copy of the web application.

| Area | Source of truth | Responsibility |
| --- | --- | --- |
| Browser UI, API routes, authentication, captions, settings, translations, legal pages | `app/` | Shared unchanged across macOS, Windows, and Linux |
| Stable packaged server entry point and lifecycle protocol | `engine/` | Shared engine contract used by every native wrapper |
| OS-aware paths and install/update capabilities exposed to the web app | `app/platform_services/` | Narrow typed boundary; source and packaged adapters |
| Frozen server composition | `packaging/engine/church_cap_engine.spec` | Bundles the same `app/` templates, static assets, locales, resources, and legal files on each target |
| Native tray/menu, process ownership, start-at-login, installer, permissions, signing, update/relaunch | `desktop/` and platform packaging overlays | May differ where the operating systems require it |
| Linux source/CLI setup and service scripts | root setup/start scripts and `scripts/` | Starts the same shared `app/` server; no separate UI fork |

Allowed dependency direction:

```text
desktop wrapper -> packaged engine -> shared app
Linux CLI -------------------------> shared app
shared app -> typed platform_services contract
platform adapter -> operating-system capability
```

The shared app must not import Tauri/Rust code or assume a particular installer. The wrapper must not copy or reimplement web templates, routes, authentication, caption logic, translation logic, or legal content.

## Engine lifecycle protocol (version 2)

The engine and the desktop supervisor exchange single JSON lines defined in `engine/protocol.py` and `desktop/src-tauri/src/model.rs`:

| Direction | Prefix | Allowed values |
| --- | --- | --- |
| Engine → supervisor, stdout | `CHURCH_CAP_ENGINE_EVENT=` | Lifecycle `state` with version, URLs, detail, and PID |
| Engine → supervisor, stdout | `CHURCH_CAP_ENGINE_REQUEST=` | `{"request":"open_updates","protocol_version":2,"pid":…}` only |
| Supervisor → engine, stdin | `CHURCH_CAP_ENGINE_COMMAND=` | `{"command":"shutdown","protocol_version":2}` only |

The engine sends `open_updates` only when an authenticated local operator selects **Updates → Check for updates** in a packaged Mac or Windows build. Repeated clicks within a few seconds send one request. The supervisor accepts the request only from the engine PID it owns. It shows the control window on **Settings** and runs the same signed-updater check as that tab's button. Installing still needs the operator to confirm in the desktop app. Any other request value is ignored.

## Change workflow

For every product change:

1. Implement browser-visible or domain behaviour once under `app/`.
2. Add or update shared tests under `tests/`.
3. If an operating-system capability is needed, extend the typed `app/platform_services/` contract and implement only the adapter/native portion that differs.
4. Freeze the same source on the target operating system with `packaging/engine/church_cap_engine.spec`.
5. Exercise the source test suite and the frozen-engine smoke test on that target.
6. Test the native supervisor lifecycle and installer separately without duplicating the web change.

Do not solve a Windows issue by copying a template or stylesheet into `desktop/`. Do not solve a Mac issue by placing mutable settings or downloaded models inside the application bundle. Mutable packaged data belongs in the per-user path selected by `app/platform_services/paths.py`:

- macOS: `~/Library/Application Support/Church Cap`
- Windows: `%APPDATA%\Church Cap`
- Linux: `$XDG_DATA_HOME/church-cap`, or `~/.local/share/church-cap`

## Platform-specific wrapper work

The wrappers are expected to differ only for genuine OS integration:

- executable/resource resolution;
- child-process ownership and no-orphan guarantees;
- tray/menu and window restoration behaviour;
- microphone/privacy metadata;
- opt-in per-user start-at-login;
- DMG versus NSIS installer construction;
- Developer ID/notarization versus Authenticode signing;
- native update installation and relaunch.

The Tauri common configuration is `desktop/src-tauri/tauri.conf.json`. Target overlays map independently frozen engines into the same stable resource destination. macOS currently uses `tauri.macos.conf.json`; Windows must add an equivalent overlay that maps `dist/engine-windows-x64/church-cap-engine/` to `engine/church-cap-engine/`.

## Structural guardrail

`tests/test_cross_platform_structure.py` verifies that the frozen-engine specification includes every shared browser asset category and that the desktop wrapper does not contain duplicated `app`, `templates`, or `static` trees. Keep this test small and structural; functional consistency remains covered by the shared Python suite and target-native frozen-engine smoke tests.

## Generated and retained files

These directories are reproducible build inputs/caches and may be regenerated when needed: `.venv-packaging/`, `.tooling/`, `desktop/node_modules/`, `desktop/src-tauri/target/`, `build/`, and standalone `dist/engine-<platform>/` intermediates. They must not become the only copy of source, credentials, signing keys, or release evidence.

Current signed release artifacts and notarization evidence under `dist/` are not caches. Do not delete or modify them during Windows development.
