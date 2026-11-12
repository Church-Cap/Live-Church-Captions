# Church Cap Desktop Supervisor

This folder contains the small Windows/macOS host around the shared Church Cap engine. It owns process lifecycle, the system tray or menu-bar item, a centred control window, approved browser routes, start-at-login, recovery, and signed application updates. It does not duplicate the Operator dashboard.

## Security and ownership boundaries

- The Rust host owns the engine process. The webview cannot execute arbitrary commands, paths, or URLs.
- Frontend actions invoke only typed, allow-listed Rust commands.
- The engine accepts only versioned protocol commands. Protocol 2 permits graceful shutdown and reports caption-session boundaries without caption text.
- The browser remains the main Church Cap interface.
- Closing the control window hides it while the supervisor and engine remain available.
- A staged engine is generated build input and is never committed.

## Local toolchain

The initial development Mac uses an ignored, project-local Rust toolchain in `.tooling/`; no global PATH change is required. From the repository root:

```bash
export RUSTUP_HOME="$PWD/.tooling/rustup"
export CARGO_HOME="$PWD/.tooling/cargo"
export PATH="$CARGO_HOME/bin:$PATH"
cd desktop
npm ci
npm run tauri dev
```

For source-mode development, set `CHURCH_CAP_ENGINE_PATH` to the frozen engine executable. Release builds stage the complete one-folder engine beneath `src-tauri/engine/church-cap-engine/` before Tauri bundles it as an immutable application resource.

The white-glass application icon is generated from the canonical master at `assets/branding/church-cap-app-icon-white-glass.png`. Rebuild that master deterministically from the approved light-background mark with `scripts/release/generate-desktop-app-icon.swift assets/branding/church-cap-square-light.png assets/branding/church-cap-app-icon-white-glass.png`, then regenerate every macOS and Windows size from the repository root with `cd desktop && npm run icons`; do not edit the generated files independently. macOS uses the separate compact `src-tauri/icons/tray-template.png` asset for its status item so AppKit can apply correct light/dark menu-bar contrast.

## Status

The Apple Silicon release candidate is signed and notarized. The Windows x64 release candidate is intentionally Authenticode-unsigned for v0.8.0 but carries the mandatory Tauri updater signature. The project owner has completed clean-machine acceptance on both platforms. Consult `docs/project/CROSS_PLATFORM_ARCHITECTURE.md`, `docs/project/DESKTOP_UPDATE_RELEASE_RUNBOOK.md`, and `docs/project/V0.8.0_IMPLEMENTATION.md` for the source-of-truth rules, release procedure, and acceptance record.

The host accepts engine readiness only after a bounded loopback `/health` request confirms the exact application version, engine protocol, and packaged runtime mode. The tray/menu and centred window then derive availability from the same supervisor snapshot.

Windows builds use `tauri.windows.conf.json` to map the complete native one-folder engine into the same stable resource destination. The supervisor assigns the engine to a private Job Object with `KILL_ON_JOB_CLOSE` and stores explicit start-at-login choice only in the current user's `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` entry. Native compilation requires the pinned Rust toolchain plus Microsoft Visual C++ Build Tools and Windows SDK.

The 2026-08-21 native Windows run passes 23 Rust tests with 1 explicit state-changing test ignored (including a live kill-on-close Job Object test), locked offline compilation, formatting, strict Clippy, and 19 desktop JavaScript tests. The Windows overlay keeps NSIS tools under `target/.tauri`, disables signed-updater output for unsigned local candidates, and maps only the complete frozen engine folder. Use a temporary short drive mapping while invoking Tauri when the checkout path is long; NSIS otherwise exceeds legacy path limits on required nested third-party license files.

The earlier 256,013,999-byte unsigned NSIS candidate (SHA-256 `b829bbaac18948dda00ed9471765c5a495e8133bba5be2ba254e8b687ee661bb`) is superseded because it embeds the pre-rotation Tauri updater public key and must not be published. The replacement 256,027,492-byte installer embeds public key ID `BF1E020A4490108A`, has SHA-256 `51f7c0528811bb286848c649c1ea97a76f7450f5519f16eec15d6d1c63318e34`, and has an independently verified Tauri updater signature. It retains the Church Cap header/sidebar artwork, project licence, Church Cap Start-menu grouping, and unchecked optional-CUDA page. If selected, the durable per-user request marker and first-launch recovery path complete or retry the approximately 1.1 GB download without failing the main installation. The x64 desktop host is PE subsystem `Windows GUI`; the supervisor and packaged resource workers create the console-subsystem engine with `CREATE_NO_WINDOW` and isolated/redirected handles. Windows v0.8.0 remains deliberately Authenticode-unsigned; the project owner has confirmed the final candidate installs and operates correctly.

Earlier isolated install extraction and generated-uninstaller cleanup pass. The project owner has completed the final Windows clean-machine installation and operating check. Extended acceptance for the optional CUDA path, text/spoken-language downloads, start-at-login persistence, and uninstall cleanup remains part of ongoing maintenance. The ignored `windows_start_at_login_round_trip` test performs the native enable/read/disable/read sequence and has a cleanup guard; run it only with explicit approval and no pre-existing Church Cap Run entry.

Engine protocol 2 also reports caption-session boundaries without caption text. Restart, stop, tray/application Quit, Cmd+Q, and Dock Quit require confirmation while a session is starting, listening, or in sensitive/private mode.
