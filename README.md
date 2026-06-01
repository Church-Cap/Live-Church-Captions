# Church Cap

Version: **v.0.2.1 public preview**

![Church Cap logo](assets/branding/church-cap-wide-dark.png)

Church Cap is an open-source, local-first live caption app for churches.

Visitors scan a QR code, open a local web page on the church Wi-Fi, and read live captions on their phone. The app transcribes one audio feed from the church sound desk or audio interface, then broadcasts the captions to phones, room displays, and OBS browser sources over the local network.

For a non-technical setup guide, start with [START_HERE.md](START_HERE.md).

## Project Layout

- `START_HERE.md` — simplest setup guide for non-technical users.
- `setup-macos.sh`, `start-macos.sh`, `reset-operator-password.sh` — main Mac operator scripts.
- `setup-windows.cmd`, `start-windows.cmd`, `reset-operator-password.cmd` — easiest Windows operator launchers.
- `install-cuda-runtime-windows.cmd` — optional Windows GPU runtime installer for NVIDIA CUDA.
- `update-macos.sh`, `update-windows.cmd` — replace the current folder with the latest GitHub source after checking the remote version.
- `setup-windows.ps1`, `start-windows.ps1`, `reset-operator-password.ps1` — Windows PowerShell scripts used by the launchers.
- `app/` — Church Cap web app.
- `config/` — editable glossary and profanity-filter additions.
- `docs/` — user guides, legal notes, architecture, networking, and translation docs.
- `.github/` — GitHub-standard contribution, security, code of conduct, issue, pull request, and CI files.
- `docker/` — optional Docker development files.
- `scripts/` — helper scripts used by setup, development, diagnostics, and maintenance.

## What It Includes

- Local FastAPI web server.
- QR codes for audience access, including hostname and IP fallback links.
- Mobile caption page with a left-to-right, bottom-to-top caption stream, optional server-backed scrollable session transcript with newest captions first, timestamps, font size, automatic system light/dark theme with local override, comfort/compact, pause, and local clear controls.
- Operator login, first-run password setup, and account/password page.
- Operator feedback page with version-aware email link.
- Secure dual-port mode: public viewer port and localhost-focused operator port.
- Audio input selection from the operator page.
- Local OpenAI Whisper transcription with rolling partial/final captions tuned for accuracy-first readable live subtitle pacing.
- Optional `faster-whisper` backend for installs that need lower latency.
- Glossary correction for church-specific words.
- Bad-word censor for likely speech-to-text mistakes.
- Sensitive blank/pause mode for private or pastoral moments.
- Transcript retention controls, encrypted local transcript cache, and operator-only current-session transcript export as `.txt`, `.vtt`, `.srt`, and `.json` with a privacy warning.
- OBS browser-source overlay and setup guide.
- Local Argos Translate support for experimental translated captions.
- Local HTTPS helper scripts for testing and managed-device deployments.
- macOS and Windows setup, start, permission repair/password reset, and macOS LaunchAgent helper scripts.

## Quick Start On Apple Silicon macOS

From the project folder:

```bash
bash setup-macos.sh
./start-macos.sh
```

Use `bash setup-macos.sh` for the first run because the setup script may not be executable yet after download or unzip. The setup script repairs permissions for the other Church Cap scripts, prepares a local `.venv`, installs the app dependencies, installs Argos Translate support and available language models, creates `.env` if needed, and can help set a friendly Bonjour hostname such as `church-cap.local`.

The normal start command opens the password setup page first. If a password already exists, Church Cap redirects you onward to the operator flow:

```text
http://localhost:9090/setup
```

Audience viewers use the public viewer port, normally:

```text
http://church-cap.local:8080/
```

On first run, create the operator password in the browser. Public caption viewers do not need the operator password.

## Quick Start On Windows

From PowerShell in the project folder:

```powershell
.\setup-windows.cmd
.\start-windows.cmd
```

Or run the PowerShell script directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
.\start-windows.ps1
```

The setup script prepares `.venv`, installs the app dependencies, checks CUDA/GPU support, installs Argos Translate support and available language models, and creates `.env` if needed. If Python is missing and `winget` is available, it can offer to install Python 3.12 first.

The normal start command opens the password setup page first. If a password already exists, Church Cap redirects you onward to the operator flow:

```text
http://localhost:9090/setup
```

Audience viewers normally use the IP address shown in the terminal or QR code, for example:

```text
http://192.168.1.50:8080/
```

The default `TRANSCRIBER_MODE=whisper` uses the standard local OpenAI Whisper package. It favours accuracy and consistency over raw speed and uses `WHISPER_BEAM_SIZE=5` by default. If you need lower latency, set `TRANSCRIBER_MODE=faster_whisper`; on Windows, that optional backend can use CUDA through CTranslate2 when the GPU, drivers, and required CUDA runtime DLLs are available. If `cublas64_12.dll` is missing, setup can offer to install local NVIDIA CUDA 12 runtime packages inside `.venv`, or you can run `.\install-cuda-runtime-windows.cmd` later. Argos Translate remains local and experimental.

The local CUDA runtime installer is usually easier than installing the full NVIDIA CUDA Toolkit. Advanced users can instead install CUDA 12.x and cuDNN system-wide from NVIDIA, then rerun `.\start-windows.cmd`.

## Normal Use

After the first setup, use:

```bash
./start-macos.sh
```

On Windows:

```powershell
.\start-windows.cmd
```

Do not recreate `.venv` or overwrite `.env` for normal Sunday use.

Operator passwords and runtime settings are stored outside the project folder so they survive app updates, Terminal restarts, and Mac restarts:

```text
~/Library/Application Support/Church Cap/data/
```

On Windows, the equivalent folder is:

```text
%APPDATA%\Church Cap\data\
```

The password is stored as a salted hash in `operator_auth.json`. Church Cap also keeps `operator_auth.backup.json` in the same folder and can restore from it if the primary auth file is lost or incomplete.

If login ever needs to be reset:

```bash
./reset-operator-password.sh
```

On Windows:

```powershell
.\reset-operator-password.cmd
```

If Windows shows `UnauthorizedAccess`, says scripts are disabled, or blocks the file because it came from another computer, run the `.cmd` launcher instead of double-clicking the `.ps1` file. If it is still blocked, right-click the downloaded zip or Church Cap folder, choose **Properties**, tick **Unblock** if shown, then try again.

If macOS says a script is not permitted or executable:

```bash
bash setup-macos.sh
```

If an old browser tab opens `localhost:8080/operator`, use the operator port instead:

```text
http://localhost:9090/operator
```

## Audio Setup

For best results:

```text
Church microphones -> sound desk aux/matrix/record output -> USB audio interface -> Church Cap computer
```

Avoid relying on the built-in laptop microphone for services.

Open `/operator`, then:

1. Stop captions if they are running.
2. Choose the church audio interface or mixer input.
3. Click **Save input**.
4. Click **Start captions**.

On macOS, if no audio devices are listed, make sure microphone permission is allowed in:

```text
System Settings -> Privacy & Security -> Microphone
```

## Main Pages

```text
/                  phone/tablet live captions
/display           large display page for screens
/obs               OBS browser-source overlay
/obs/help          OBS setup guide, operator login required
/operator          operator controls, login required
/feedback          feedback email guidance, login required
/account           change operator password, login required
/setup/network     local hostname/HTTPS/Wi-Fi guidance, login required
/qr.png            hostname QR code
/qr-ip.png         LAN IP fallback QR code
/health            basic health check
/transcript.txt    current-session transcript export, operator login required
/transcript.vtt    current-session WebVTT export, operator login required
/transcript.srt    current-session SRT export, operator login required
/transcript.json   current-session JSON export, operator login required
```

## Translation

Phone UI language selection is local and lightweight. Translated captions are separate, experimental, and resource-heavy.

Whisper performs speech-to-text. It does not translate one English caption stream into every viewer language by itself. Real translated captions require a translation provider such as Argos Translate.

The first-time macOS setup script installs Argos Translate support and available English-to-target models. To rerun that translation setup later:

```bash
./scripts/install-translation-models-argos.sh
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-translation-models-argos.ps1
```

Install and enable translated captions immediately:

```bash
./scripts/install-translation-models-argos.sh --enable
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-translation-models-argos.ps1 -Enable
```

Keep the active translated language limit low at first. Translation may be inaccurate for Scripture, names, theology, pastoral details, and safeguarding-sensitive content. Use a qualified human interpreter where accuracy matters.

More detail: [docs/translation.md](docs/translation.md).

## Security And Privacy

Church Cap is intended for local-network use. Do not port-forward it to the public internet without a full security review.

Recommended church setup:

- Run the caption computer on a trusted church/AV network.
- Let guests access only the public viewer port.
- Keep operator controls password-protected.
- Use the default dual-port start script.
- Keep operator access on localhost where possible.
- Use sensitive blank/pause mode for private prayer, testimony, safeguarding, or pastoral details.
- Set transcript retention appropriately for the service. Retained caption text is cached in the per-user Church Cap data folder and is deleted when the transcript is cleared or the retention window expires.
- Use clear notices so people know AI captions are being generated.

Read:

```text
docs/security_privacy_networking.md
docs/legal/PRIVACY.md
docs/legal/DISCLAIMER.md
docs/legal/NOTICE_TEMPLATE_FOR_CHURCHES.md
```

AI-generated captions may be inaccurate. For high-stakes, confidential, legal, safeguarding, or pastoral contexts, use qualified human support and appropriate church policies.

## HTTPS

Plain local HTTP is the simplest option for visitor phones on a church Wi-Fi network.

Local HTTPS is supported for testing and managed devices, but visitor phones will only trust the certificate if their device already trusts the issuing certificate authority.

Testing commands:

```bash
./scripts/generate-local-cert.sh
./start-macos-https.sh
```

For trusted local testing on a Mac with `mkcert`:

```bash
./scripts/generate-trusted-local-cert-macos.sh
./start-macos-https.sh
```

More detail: [docs/internal_https.md](docs/internal_https.md).

## Optional Auto-Start On macOS

Install a user LaunchAgent:

```bash
./scripts/install-macos-launchagent.sh
```

Remove it with:

```bash
./scripts/uninstall-macos-launchagent.sh
```

## Updates

The operator page includes an **Updates** section. It checks the latest version on GitHub, reports when Church Cap is already up to date, asks for confirmation before updating, replaces this folder in place, and restarts Church Cap.

The scripts below provide the same in-place update flow. They preserve `.env`, `.venv`, `data/`, `logs/`, `certs/`, `config/glossary.csv`, and `config/profanity_filter.txt`. The app-owned `APP_VERSION` and `FEEDBACK_EMAIL` values in `.env` are refreshed from the new release defaults.

Update resilience:

- The current app folder is not touched until the download completes, the ZIP passes an integrity test, required files are present, and the extracted version matches the version check.
- The updater stages the new release in a temporary folder and creates SHA-256 checksums before copying it into place.
- If the internet drops during download or dependency installation, the update stops before replacing app files.
- Before replacing files, the updater saves a rollback backup in `data/update-backups/`.
- After copying, the updater verifies installed file checksums. If replacement fails before completion, it restores the previous files automatically.

On macOS:

```bash
./update-macos.sh
```

On Windows:

```powershell
.\update-windows.cmd
```

## Docker

Docker is useful for the web app, but audio capture can be awkward on macOS. For Linux or server-style testing:

```bash
cp env.example .env
docker compose -f docker/docker-compose.yml up --build
```

## Development

Manual local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp env.example .env
./scripts/run-dev.sh
```

Recommended Python version: **3.12**. Python 3.10 or newer is required by the pinned dependency set.

Run checks:

```bash
python -m unittest discover -s tests
python -m compileall app tests
```

## Release Hygiene

Before publishing a release, confirm:

- `.env`, `data/`, `certs/`, `.venv/`, logs, and local runtime files are not committed.
- `LICENSE`, `.github/SECURITY.md`, `.github/CONTRIBUTING.md`, `.github/CODE_OF_CONDUCT.md`, and `docs/legal/THIRD_PARTY_NOTICES.md` are included.
- Third-party versions and licence notes are reviewed in `docs/legal/THIRD_PARTY_NOTICES.md`.
- Script permissions are executable, or users can run `bash setup-macos.sh` to repair them during setup.
- Windows PowerShell scripts are included for setup, start, password reset, GPU check, and Argos model installation.

GitHub community files live in the standard `.github/` folder:

```text
.github/CONTRIBUTING.md
.github/SECURITY.md
.github/CODE_OF_CONDUCT.md
```

Church Cap is released under the MIT License. Dependency and model licence notes are in [docs/legal/THIRD_PARTY_NOTICES.md](docs/legal/THIRD_PARTY_NOTICES.md).
