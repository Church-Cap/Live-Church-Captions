# Church Cap Blueprint

Church Cap is an open-source, local-first live caption application for churches. It listens to one audio input, transcribes speech locally, and publishes captions to phones, tablets, room displays, and OBS browser sources over the local network.

This document describes the first public GitHub preview.

## Current Release

Version: `0.1.0 public preview`

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

## Main Components

### FastAPI Server

The server handles routing, templates, WebSocket connections, API controls, caption state, exports, and operator authentication.

Key files:

```text
app/main.py
app/settings.py
app/auth.py
app/broadcast.py
app/runtime_config.py
app/exporting.py
```

### Audio And Transcription

The current transcription implementation uses `faster-whisper` with a rolling-window approach to reduce latency. It supports partial and final captions.

Key files:

```text
app/transcription/faster_whisper_live.py
app/transcription/base.py
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

Captions are transcribed once, then broadcast to connected clients using WebSockets. This avoids running transcription per viewer.

Key file:

```text
app/broadcast.py
```

### Client Viewer

The public caption viewer is designed for phones and tablets. It includes font controls, theme controls, pause/clear controls, UI language selection, AI accuracy notices, and optional translated-caption routing.

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
- microphone level monitor
- source caption preview
- sensitive blank/pause mode
- QR codes and audience links
- OBS links
- translation controls
- bad-word censor controls
- transcript retention controls
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
  - Windows `.cmd` launchers are present for setup, start, password reset, update, and optional CUDA runtime install.

If permissions are lost in a copied or unzipped folder, users can run:

```bash
bash fix-permissions.sh
```

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
