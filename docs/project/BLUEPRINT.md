# Church Cap Blueprint

Church Cap is an open-source, local-first live caption application for churches. It listens to one audio input, transcribes speech locally, and publishes captions to phones, tablets, room displays, and OBS browser sources over the local network.

This document describes the first public GitHub preview.

## Current Release

Version: `v.0.2.3 public preview`

Status: early public prototype suitable for local testing and pilot churches. It is not a finished compliance-certified product, and churches remain responsible for their own privacy, safeguarding, accessibility, and copyright policies.

## Project Goals

- Improve accessibility for Deaf and hard-of-hearing people in church settings.
- Keep the core captioning workflow local-first and usable without cloud hosting.
- Let visitors scan a QR code and read captions without installing an app.
- Protect operator controls behind a password.
- Provide practical privacy and safeguarding controls for churches.
- Keep the project approachable for open-source contributors.

## Core Workflow

```text
Church microphones
  -> sound desk / mixer / audio interface
  -> Church Cap server running locally
  -> local speech-to-text engine
  -> glossary cleanup and optional bad-word censor
  -> optional local translation
  -> WebSocket caption broadcast
  -> phones, tablets, display screens, and OBS
```

## Main Pages

- `/` — public mobile/tablet caption viewer.
- `/operator` — password-protected operator dashboard.
- `/display` — large-screen caption display.
- `/obs` — transparent OBS browser-source overlay.
- `/obs/help` — operator-only OBS setup guide.
- `/setup/network` — operator-only local network and hostname guide.
- `/docs/privacy` — operator-only privacy notes.
- `/docs/church-notice` — operator-only suggested church notice wording.
- `/docs/disclaimer` — operator-only disclaimer notes.
- Operator **Diagnostics** section — operator-only local support export with confirmation, system specs, runtime status, metrics, and redacted updater/CUDA logs.
- Operator **Updates** section — operator-only GitHub release-tag check, confirmation, integrity-checked in-place update, rollback backup, restart, and reconnect flow.
- `/api/diagnostics/export` — local diagnostics JSON export, operator login and local computer required.

## Main Components

### FastAPI Server

The server handles routing, templates, WebSocket connections, API controls, caption state, operator-only current-session transcript exports, and operator authentication.

Key files:

```text
app/main.py
app/settings.py
app/auth.py
app/broadcast.py
app/transcript_store.py
app/runtime_config.py
app/exporting.py
```

### Audio And Transcription

The transcription layer supports standard local OpenAI Whisper and the lower-latency `faster-whisper` backend. Both use a rolling-window approach with partial and final captions. The operator dashboard includes performance presets and advanced controls so churches can choose between lower delay and higher accuracy without editing `.env`.

Performance settings are stored in `runtime_config.json` in the per-user data folder. Saved operator settings override matching `.env` defaults when a new caption session starts. Existing sessions keep their loaded model and stream settings until captions are stopped and started again.

Key files:

```text
app/transcription/whisper_live.py
app/transcription/faster_whisper_live.py
app/transcription/base.py
app/hardware.py
app/runtime_config.py
```

### Caption Cleanup

Caption text can be corrected with a simple CSV glossary and masked with the bad-word censor before it is shown, translated, stored, or exported.

Key files:

```text
app/glossary.py
app/profanity_filter.py
config/glossary.csv
config/profanity_filter.txt
```

### Caption Broadcast

Captions are transcribed once, then broadcast to connected clients using WebSockets. This avoids running transcription per viewer. The broadcast layer also maintains the retained session transcript, including stable sections derived from rolling partial captions so continuous speech can still appear in the scrollback history.

Key file:

```text
app/broadcast.py
app/transcript_store.py
```

### Client Viewer

The public caption viewer is designed for phones and tablets. It uses a start-aligned, bottom-to-top caption stream: captions read from the left edge in left-to-right languages, wrap naturally, and use the available caption box from the bottom upward as new lines arrive. This avoids a middle-of-the-box caption feel and gives viewers a stable reading surface. If no confirmed caption is available yet, it can show a live draft so continuous speech does not leave viewers on the waiting screen. It includes an optional server-backed, scrollable, timestamped session transcript for the current app session with newest captions first, operator-only export controls with a privacy warning, font controls, automatic system light/dark theme with local override, transcript show/hide, pause/clear controls, UI language selection, AI accuracy notices, and optional translated-caption routing. Sensitive moment mode discards captions and transcript drafts while blanked, resets live transcription buffers, and briefly drops captions after resume so private speech is not retained or exported. A new app start keeps the visible transcript empty while pruning any saved local cache according to the retention window stored with that cache. On phone and tablet landscape viewports, the viewer uses a compact side-by-side layout so the live caption feed takes about 75% of the width while the transcript remains available when enabled; transcript history scrolls inside its panel so it does not push the live feed down, and hiding the transcript lets the live feed use the full width.

Key files:

```text
app/templates/captions.html
app/static/client.js
app/static/styles.css
```

### Operator Dashboard

The operator dashboard includes:

- start/stop captions
- audio input selection
- performance presets for faster/lower-accuracy through slower/higher-accuracy captioning
- advanced transcription tuning for backend, model size, CPU/GPU, compute type, refresh interval, listening window, silence timing, stability checks, and beam size
- microphone level monitor
- source caption preview
- sensitive blank/pause mode
- QR codes and audience links
- OBS links
- translation controls
- bad-word censor controls
- transcript retention controls and a local transcript-folder reveal action
- dedicated diagnostics support export with confirmation and privacy wording
- account/password controls

Key file:

```text
app/templates/operator.html
```

### Translation

Translation support is experimental. The UI supports language selection, and Argos Translate can be installed locally. Only English is enabled by default; additional languages must be deliberately enabled by the operator.

Key files:

```text
app/i18n.py
app/broadcast.py
scripts/install-translation-models-argos.sh
scripts/install-translation-models-argos.ps1
requirements-translation.txt
docs/translation.md
```

## Local-First Security Model

The default macOS and Windows start scripts run in dual-port mode:

```text
Viewer port:   8080
Operator port: 9090
```

The viewer port is intended for public read-only caption pages:

```text
/
/display
/obs
/qr.png
/qr-ip.png
/api/languages
/ws/captions
```

The operator port is intended for password-protected controls, transcript exports, and operator documentation. When localhost lock is enabled, operator routes are only served to the local machine.

Recommended controls:

- Do not port-forward Church Cap to the internet.
- Use a strong operator password.
- Keep the public caption page read-only.
- Keep operator controls password-protected and localhost-focused.
- Use guest Wi-Fi rules where possible so guests can access only the viewer port.
- Keep transcript saving off or limited where appropriate.
- Use sensitive blank/pause mode for private or pastoral moments.
- Review transcripts before publishing them.

## Runtime Data

Operator authentication and runtime settings are stored in a stable per-user data directory, not only inside the extracted project folder.

On macOS:

```text
~/Library/Application Support/Church Cap/data/operator_auth.json
~/Library/Application Support/Church Cap/data/operator_auth.backup.json
~/Library/Application Support/Church Cap/data/runtime_config.json
```

On Windows:

```text
%APPDATA%\Church Cap\data\operator_auth.json
%APPDATA%\Church Cap\data\operator_auth.backup.json
%APPDATA%\Church Cap\data\runtime_config.json
```

The operator password is stored as a salted PBKDF2 hash. The session secret is stored locally because it is needed to verify signed session cookies. The backup auth file is written from the same data so the app can recover if the primary auth file is lost, corrupted, or left incomplete. These files must not be committed to GitHub.

Runtime settings include the selected audio input, transcript retention, translation, profanity filter, security mode, and performance tuning. Performance changes from the operator dashboard are saved automatically and apply when the next caption session starts.

Older project-local files are migrated from:

```text
data/operator_auth.json
data/runtime_config.json
```

when the stable Application Support files do not already exist.

## Privacy And Compliance Notes

Church Cap supports privacy-conscious local captioning, but it does not make a church legally compliant by itself.

Churches should consider:

- UK GDPR / data protection responsibilities.
- Whether personal data or special category data may appear in captions.
- Whether transcripts are saved and for how long.
- Whether notices are displayed telling people that AI captions are being generated.
- Safeguarding practice for private prayer, testimony, pastoral details, children, or vulnerable adults.
- Copyright permissions before publishing transcripts, captions, Bible text, worship lyrics, liturgy, poems, or quotations.

See:

```text
docs/legal/PRIVACY.md
docs/legal/DISCLAIMER.md
docs/legal/NOTICE_TEMPLATE_FOR_CHURCHES.md
docs/security_privacy_networking.md
```

## GitHub Launch Checklist

Before publishing the repository publicly:

- Confirm `.env`, `.venv/`, `data/`, `certs/`, logs, and local runtime files are not committed.
- Confirm `.gitignore` is present.
- Confirm `LICENSE` is present.
- Confirm `README.md` gives a clear quick start.
- Confirm `.github/SECURITY.md`, `.github/CONTRIBUTING.md`, and `.github/CODE_OF_CONDUCT.md` are present.
- Confirm issue and pull request templates are present.
- Confirm `docs/legal/THIRD_PARTY_NOTICES.md` lists exact direct dependency versions and model/distribution notes.
- Confirm dependency versions are pinned in `requirements.txt` and `requirements-translation.txt`.
- Confirm scripts are executable:
  - `setup-macos.sh`
  - `start-macos.sh`
  - `start-macos-https.sh`
  - `reset-operator-password.sh`
  - `fix-permissions.sh`
  - `update-macos.sh`
  - `scripts/*.sh`
  - `scripts/*.py`
  - Windows `.cmd` launchers are present for setup, start, password reset, update, and optional CUDA runtime force reinstall.
- Confirm updater scripts preserve `.env`, `.venv`, `data/`, `logs/`, `certs/`, and local config while refreshing app-owned release metadata.
- Confirm updater scripts validate downloaded ZIPs, required release files, release version, staged Python syntax, and SHA-256 installed-file checksums before reporting success.

If permissions are lost in a copied or unzipped folder, users can run:

```bash
bash fix-permissions.sh
```

## Windows Reliability QA Targets

- Test fresh setup on CPU-only Windows and NVIDIA Windows laptops.
- Confirm the dashboard clearly reports NVIDIA driver detection, CTranslate2 CUDA availability, missing CUDA DLLs, and CPU fallback mode.
- Confirm **Download diagnostics** names included system specs clearly and excludes transcripts, `.env`, passwords, session secrets, and unredacted local paths.
- Confirm `setup-windows.cmd`, `start-windows.cmd`, `update-windows.cmd`, and the operator-page update flow work from a clean folder.
- Revisit minimum and recommended hardware after real service benchmarks from several churches.

## Suggested Repository Description

```text
Open-source, local-first live captions for churches.
```

## Suggested GitHub Topics

```text
accessibility
church
captions
deaf-accessibility
hard-of-hearing
fastapi
whisper
local-first
assistive-technology
obs
```

## Roadmap Ideas

- Better packaged app installer.
- Operator IP allowlist.
- Improved local certificate workflow.
- Better VAD and lower-latency streaming transcription.
- Better glossary and sermon-notes context.
- More robust translation provider support.
- Better signed/packaged update flow.
- Accessibility testing with Deaf and hard-of-hearing users.
