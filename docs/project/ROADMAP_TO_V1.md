# Roadmap To v1.0.0

Church Cap maintains one shared browser application with platform-specific packaging around it:

- a native desktop application for Apple Silicon macOS and Windows x64;
- a source-based Linux CLI installation; and
- explicit `appliance_cpu` and `appliance_gpu` deployment profiles for future Church Cap appliances.

Shared captioning, audio, translation, security, update, and browser UI code remains in one project. Platform wrappers provide only the lifecycle, installer, system integration, and update behaviour required by each operating system.

## v0.8.x Release And Maintenance

- Publish the Apple-notarized macOS DMG, Windows x64 installer, Linux CLI archive, checksums, updater signatures, and release notes under one semantic-version GitHub Release.
- Publish each desktop updater manifest only after its corresponding release artifact is anonymously downloadable and verified.
- Keep downloaded models, settings, credentials, logs, recovery data, and exports in per-user storage rather than inside an application bundle.
- Maintain one shared FastAPI/browser application, typed platform-service contracts, a packaged engine, and a thin Tauri supervisor.
- Improve installation and recovery guidance from clean-machine feedback without duplicating browser behaviour across platforms.
- Continue testing macOS, Windows CPU, Windows NVIDIA, Linux CPU, Linux NVIDIA, and the explicit appliance profiles.
- Keep Windows Authenticode signing as a post-v0.8.0 improvement; v0.8.0 remains clearly labelled as unsigned and checksum-verifiable on Windows.
- Guide new installations through password/security, local hardware recommendations, optional translated-caption setup, conservative capacity limits, and visible installation progress.

## v0.9.x Public Candidate

- Complete update-from-v0.8 acceptance on supported desktop platforms.
- Refine the operator and first-run workflows from real church feedback, limiting changes to bug fixes and usability improvements.
- Complete privacy, safeguarding, translation, accessibility, migration, rollback, and recovery documentation.
- Add clearer hardware recommendations based on measured caption and translation performance.
- Verify that desktop installations never enter appliance mode unless explicitly configured.
- Complete keyboard, screen-reader, touch, high-contrast, and small-display acceptance.

## v1.0.0 Criteria

- A non-technical church can install, start, recover, and update Church Cap using the published documentation.
- The browser-first experience remains consistent across macOS, Windows, Linux, and appliance deployments.
- English captions are stable on the published recommended hardware.
- Multilingual captions have clear supported-hardware guidance and fail safely when the hardware is unsuitable.
- Desktop wrappers reliably supervise the local server without orphan processes or misleading server state.
- Signed update channels reject missing, altered, or incorrectly signed artifacts.
- Privacy, safeguarding, legal, accessibility, and third-party notices are complete and easy to find.
- Automated tests and clean-machine acceptance cover every supported release path.

Implementation details are maintained in the [cross-platform architecture](CROSS_PLATFORM_ARCHITECTURE.md), current [v0.9.0 implementation record](V0.9.0_IMPLEMENTATION.md), retained [v0.8.1 implementation record](V0.8.1_IMPLEMENTATION.md), and [desktop update release runbook](DESKTOP_UPDATE_RELEASE_RUNBOOK.md).
