# Church Cap

Version: **v0.7.2**

![Church Cap logo](assets/branding/church-cap-wide-dark.png)

Church Cap is an open-source, local-first live caption app for churches.

Visitors scan a QR code, open a local web page on the church Wi-Fi, and read live captions on their phone. The app transcribes one audio feed from the church sound desk or audio interface, then broadcasts the captions to phones, room displays, and OBS browser sources over the local network.

For a non-technical setup guide, start with [START_HERE.md](START_HERE.md).

## Project Layout

- `START_HERE.md` — simplest setup guide for non-technical users.
- `setup-macos.sh`, `start-macos.sh`, `reset-operator-password.sh` — main Mac operator scripts.
- `setup-windows.cmd`, `start-windows.cmd`, `reset-operator-password.cmd` — easiest Windows operator launchers.
- `setup-linux.sh`, `start-linux.sh`, `update-linux.sh` — Linux setup, normal start, and updater scripts with package-manager detection.
- `install-cuda-runtime-windows.cmd` — optional Windows NVIDIA CUDA runtime force reinstall helper.
- `update-macos.sh`, `update-windows.cmd` — replace the current folder with the latest GitHub release tag after checking the remote version.
- `setup-windows.ps1`, `start-windows.ps1`, `reset-operator-password.ps1` — Windows PowerShell scripts used by the launchers.
- `app/` — Church Cap web app.
- `config/` — editable glossary and profanity-filter additions.
- `docs/` — user guides, legal notes, architecture, networking, and translation docs.
- `docs/project/ROADMAP_TO_V1.md` — staged route from the v0.6 preview architecture to v1.0.0.
- `docs/project/V0.7.2_IMPLEMENTATION.md` — v0.7.2 action-plan mapping, scope, and Linux acceptance gates.
- `docs/project/V0.7.2_RELEASE_NOTES.md` — commit summary and GitHub release wording for v0.7.2.
- `docs/project/Church_Cap_v0.7.2_Action_Plan.docx` — current pilot action plan and validation status.
- `docs/project/TRANSLATION_MODEL_RESEARCH.md` — commercial/open-source model and licence audit for contextual and Chinese translation.
- `.github/` — GitHub-standard contribution, security, code of conduct, issue, pull request, and CI files.
- `docker/` — optional Docker development files.
- `scripts/` — helper scripts used by setup, development, diagnostics, and maintenance.

## What It Includes

- Local FastAPI web server.
- QR codes for audience access, including hostname and IP fallback links.
- Mobile caption page with a viewport-bounded, internally scrollable accumulated Live feed for English and every translated language, plus an optional independently scrollable session transcript that starts closed on each visit. A word-timestamp-aware cue ledger shows safe English words immediately, briefly guards only a weak word at the live audio edge, and updates corrected wording in place before sealing it into the shared reader. The page also includes newest-first timestamps, font size, automatic system light/dark theme with local override, comfort/compact, pause, and local clear controls. Dismissing viewer notices returns their space to the caption panels without making the page longer.
- Operator login, first-run password setup, and account/password page.
- Privacy-safe service measurements retained across restarts, with separate English operational-response and rolling-window estimates, stage timing, provider/scheduler outcomes, viewer-seconds, process/system resource aggregates, and a separate anonymised report.
- One-use QR pairing for a restricted service-leader page with start/stop, private-moment, status, and multi-language controls.
- Operator feedback page with version-aware email link, plus a dedicated Diagnostics menu for support exports and a Storage use view with opt-in cleanup of inactive model downloads and archived logs.
- Secure dual-port mode: public viewer port and localhost-focused operator port.
- Audio input selection from the operator page.
- Local OpenAI Whisper transcription with rolling partial/final captions tuned for accuracy-first readable live subtitle pacing.
- Optional `faster-whisper` backend with word-level alignment, guarded incomplete-edge words, sealed-audio buffer trimming, and start-to-start decode cadence for installs that need lower latency.
- Operator performance controls for switching between faster/lower-accuracy and slower/higher-accuracy presets, including model size, backend, CPU/GPU selection, and advanced latency tuning.
- Glossary correction for church-specific words.
- Bad-word censor for likely speech-to-text mistakes.
- Sensitive blank/pause mode for private or pastoral moments, with audience notices rendered through the selected client UI language where available.
- Transcript retention controls, encrypted local transcript cache, operator current-session transcript export as `.txt`, `.vtt`, `.srt`, and `.json`, plus restricted Service Leader TXT/VTT transcript export for appliance support after a privacy warning.
- OBS browser-source overlay and setup guide. The `/display` and `/obs` caption surfaces use the same subtle line glide and trailing-word entry animation as the phone viewer, with a stable two-line layout to reduce jumpy text on room screens and livestream overlays.
- On Church Cap appliances, local Display and OBS previews stay on the appliance shell origin so the persistent Home/System controls remain available and failed preview routes can return to the local recovery environment.
- Local multilingual support: phone UI labels use the lightweight catalogue in `app/locales/client_ui.json`, with Argos runtime fallback where needed. Experimental translated captions use package-style choices: **Recommended package** CTranslate2 INT8 / SMaLL-100, **Base package** Argos Translate, **Compatibility package** PyTorch SMaLL-100, or **Auto** mode across installed packages.
- v0.7.0 introduced real Faster-Whisper word timestamps and confidence, guarded weak words at the captured-audio edge, timestamp-driven removal of sealed audio, correction-in-place, and Responsive Context translation. v0.7.2 includes the locally prepared v0.7.1 operator-clarity work, repairs direct web updates from the public v0.7.0 release, pins the selected release, and reports updater failures in the operator interface.
- Local HTTPS helper scripts for testing and managed-device deployments.
- macOS, Windows, and Linux setup/start support, permission repair/password reset, and macOS LaunchAgent helper scripts.

## Deployment Profiles

Church Cap does not infer appliance mode from hardware alone. A normal Windows, Mac, or Linux computer always runs the full desktop profile unless an administrator explicitly sets `CHURCHCAP_DEPLOYMENT=appliance` or the appliance installer creates `/etc/churchcap-appliance/identity.json`.

Supported profiles are:

- `desktop` - full open-source app experience with all operator controls visible.
- `appliance_cpu` - streamlined Church Cap Box experience for English-first CPU hardware. Languages remain accessible as an advanced option, show a CPU warning first, and are capped at three active translated languages.
- `appliance_gpu` - streamlined Church Cap Box experience for multilingual GPU appliance builds. Translation controls are present, but translated captions stay blocked until CUDA is ready.

The appliance identity is intentionally separate from CUDA detection. CUDA decides what the machine can accelerate; the deployment identity decides which product experience to show. This prevents a user's own GPU computer from being mistaken for a Church Cap Box.

For the Church Cap Appliance, use the secure local operator port `9090` only. The shell installer no longer probes or falls back to `8000` or `8080` for the appliance path.

## Hardware Guidance

Minimum for testing and small services:

- Apple Silicon Mac, Windows 10/11, or a modern 64-bit Linux system with a 4-core CPU and 8 GB RAM.
- USB audio interface or sound desk feed.
- Use **Fastest** or **Fast** presets on lower-power systems.

Recommended for live church use:

- Apple Silicon Mac with 16 GB RAM, or Windows/Linux with a recent 6-8 core CPU and 16 GB RAM.
- For Windows GPU acceleration, use an NVIDIA GPU with current drivers and the local CUDA runtime packages installed by Church Cap.
- Use the built-in benchmark before selecting `small.en` or `medium.en`.

For Windows troubleshooting, the operator dashboard shows whether the NVIDIA driver is detected, whether CTranslate2 can use CUDA, whether CUDA runtime DLLs are ready, and which fallback mode Church Cap will use.

## Quick Start On Apple Silicon macOS

From the project folder:

```bash
bash setup-macos.sh
./start-macos.sh
```

Use `bash setup-macos.sh` for the first run because the setup script may not be executable yet after download or unzip. The setup script repairs permissions for the other Church Cap scripts, prepares a local `.venv`, installs the app dependencies, creates `.env` if needed, can help set a friendly Bonjour hostname such as `church-cap.local`, and offers translation-resource choices for common Base package / Argos packs, all Base package / Argos packs, optional Recommended package / CTranslate2 INT8, optional Compatibility package / PyTorch SMaLL-100, or skipping translation resources until later.

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

The setup script prepares `.venv`, installs the app dependencies, checks CUDA/GPU support, creates `.env` if needed, and offers translation-resource choices for common Base package / Argos packs, all Base package / Argos packs, optional Recommended package / CTranslate2 INT8, optional Compatibility package / PyTorch SMaLL-100, or skipping translation resources until later. If Python is missing and `winget` is available, it can offer to install Python 3.12 first.

The normal start command opens the password setup page first. If a password already exists, Church Cap redirects you onward to the operator flow:

```text
http://localhost:9090/setup
```

Audience viewers normally use the IP address shown in the terminal or QR code, for example:

```text
http://192.168.1.50:8080/
```

Church Cap can use either the standard OpenAI Whisper backend or the lower-latency `faster-whisper` backend. The operator page includes a **Performance** section with a speed/accuracy slider and advanced controls for platform view, backend, model size, processor, compute type, caption refresh, listening window, silence timing, and stability checks. These settings are saved automatically in the per-user runtime config and apply the next time captions are started. To protect the live audience feed, performance controls are locked while captions are running.

The **Performance platform** setting defaults to auto-detect. On Windows, `faster-whisper` can use CUDA through CTranslate2 when the GPU, drivers, and required CUDA runtime DLLs are available. If CUDA is not ready, setup can offer to install or force reinstall local NVIDIA CUDA 12 runtime packages inside `.venv`, or you can run `.\install-cuda-runtime-windows.cmd` later. The force reinstall clears pip's CUDA wheel cache and downloads fresh local runtime wheels. The operator Performance panel also shows a Windows CUDA troubleshooting area when Windows is selected, with **Check CUDA** and **Force reinstall CUDA runtime** buttons. Selecting **GPU / NVIDIA CUDA** forces a CUDA load attempt first for Faster Whisper; if the runtime cannot load CUDA, Church Cap falls back to CPU and reports the reason in the operator status. The built-in CUDA runtime installer targets Faster Whisper/CTranslate2 rather than PyTorch/OpenAI Whisper, so Windows CUDA recommendations stay on Faster Whisper. On macOS, the processor choices hide CUDA and can show Apple GPU / Metal for OpenAI Whisper when PyTorch supports MPS; diagnostics and the operator strip report Apple chip/GPU information and unified memory more clearly. Argos Translate remains local and experimental and may still run on CPU. Recommended package uses a converted SMaLL-100 model through CTranslate2/INT8 and can use CUDA where CTranslate2 supports it. Compatibility package still uses PyTorch and may use CUDA if PyTorch sees it.

The local CUDA runtime installer is usually easier than installing the full NVIDIA CUDA Toolkit. Windows users who already manage NVIDIA tooling can instead install CUDA 12.x and cuDNN system-wide from NVIDIA, then rerun `.\start-windows.cmd`.

## Quick Start On Linux

From the project folder:

```bash
bash setup-linux.sh
./start-linux.sh
```

The setup script detects `apt`, `dnf`, `yum`, `zypper`, `pacman`, or `apk`, installs Python/build/audio prerequisites through that package manager, and keeps all Python packages inside `.venv`. It is intended for AlmaLinux, Rocky Linux, RHEL-family systems, Fedora, Ubuntu, Debian, openSUSE, Arch Linux, Alpine Linux, and close derivatives.

On AlmaLinux, Church Cap prefers an available Python 3.12 or 3.11 because the operating system's default `python3` may be too old. The installer does not enable extra repositories automatically. If `dnf` cannot find PortAudio development packages, enable the normal AppStream/CRB repositories according to your system policy and rerun setup.

Linux NVIDIA acceleration uses the system-managed driver/CUDA runtime. Church Cap detects CUDA through CTranslate2 and falls back to CPU safely; it does not install NVIDIA drivers or CUDA on Linux.

More detail: [docs/linux.md](docs/linux.md).

## Recorded Sermon Testing

v0.7.2 keeps the v0.6.1 service-run measurements and service-metrics schema 9. Reports identify cue-engine v5 and its immediate stable-prefix/guarded-edge-tail strategy. They include word-timestamp pass and aligned-word counts, weak edge words withheld or confirmed, actual start-to-start recognition-pass intervals, translated draft/final counts, and first translated-cue timing alongside cue, queue, shutdown, and resource measurements. The report retains no audio, recognition timestamps, confidence values, caption text, or translation text. Download the separate anonymised service report and follow [docs/recorded-sermon-testing.md](docs/recorded-sermon-testing.md).

## Normal Use

After the first setup, use:

```bash
./start-macos.sh
```

On Windows:

```powershell
.\start-windows.cmd
```

On Linux:

```bash
./start-linux.sh
```

Do not recreate `.venv` or overwrite `.env` for normal Sunday use.

Operator passwords and runtime settings are stored outside the project folder so they survive app updates, terminal restarts, and computer restarts:

```text
~/Library/Application Support/Church Cap/data/
```

On Windows, the equivalent folder is:

```text
%APPDATA%\Church Cap\data\
```

On Linux, the default is:

```text
~/.local/share/church-cap/data/
```

`XDG_DATA_HOME` and `CHURCH_CAP_DATA_DIR` are respected.

The password is stored as a salted hash in `operator_auth.json`. Church Cap also keeps `operator_auth.backup.json` in the same folder and can restore from it if the primary auth file is lost or incomplete.

Runtime settings include audio input, transcript/privacy options, translation options, bad-word censor state, security mode, and performance tuning. Values saved on the operator page override the matching `.env` defaults until changed again from the operator page.

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

## Performance Tuning

Open `/operator`, then use **Performance** on the dashboard.

- Move the slider toward **Fastest** for older CPUs or lower delay.
- Move the slider toward **Most accurate** when the computer has enough CPU/GPU headroom and wording matters more than delay. The far-right setting uses `medium.en` and can noticeably increase latency, so check it with the benchmark before a service.
- Use **More settings** for deeper tuning. Easy mode shows platform, backend, model size, and processor. Advanced mode adds compute type, caption refresh, listening window, silence finalise timing, stability checks, and OpenAI Whisper beam size. The platform view is automatic by default, but can be set to macOS, Windows, or Linux if detection is wrong.

Performance adjustments save automatically when captions are stopped. Stop captions before changing the model, backend, processor, or other performance settings because the model and audio stream are loaded when captions start. The top operator bar includes **English Delay** and **Translation Delay** tiles so the operator can distinguish source English caption latency from translated-caption latency during a service. The Performance panel includes an operator-started 15-second benchmark and live monitor; neither runs automatically. Live-monitor samples are capped in memory. It can recommend conservative live-service settings from local hardware/runtime information and apply them offline without any internet access. The medium model stays available on the slider, but it should be selected manually only after a successful benchmark. The live transcribers and session transcript include a repetition guard that trims obvious stuck word or phrase loops before they reach the audience captions or retained transcript.

Operator → **Diagnostics → Storage use** shows the application, local data, Hugging Face downloads, OpenAI Whisper downloads, and bounded log use. Church Cap rotates its own diagnostic logs at 5 MB with two backups and disables routine HTTP access logging. Cleanup is never automatic: the operator must review and confirm exact inactive downloads or archived logs, and Church Cap protects the active model, current logs, settings, transcripts, and current service data.

## Main Pages

```text
/                  phone/tablet live captions
/display           large display page for screens, using the smooth audience-caption renderer
/obs               OBS browser-source overlay, using the same smoother caption pacing
/obs/help          OBS setup guide, operator login required
/operator          operator controls, login required
/service-leader    restricted service-leader controls, one-use pairing required
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
/api/diagnostics/export  local diagnostics JSON export, operator login and local computer required
/api/diagnostics/download-handoff  temporary appliance diagnostics handoff QR, operator login and local computer required
```

## Translation

Phone UI language selection is local and lightweight. In Manual / restricted language mode, visitor and Service Leader language pickers can show installed languages that are not currently enabled and let someone request them; the operator receives a floating request card and can accept or reject the language without changing the active translation capacity limit. The visitor page uses static strings from `app/locales/client_ui.json` first, including manual fallback strings for languages Argos does not cover. If a selected language is not in that file, Church Cap asks the local Base / Argos provider to translate the small set of UI labels at runtime, then falls back to English if the needed Argos pack is not installed. This UI path is separate from live caption translation routing and does not require captions to be running. Audience language lists show compact Unicode flag chips and keep the language code in the language text. Operator and Service Leader lists keep compact flag/code chips for admin readability. Search matches language codes, English names, native names, and accented names. When a platform does not render emoji flags reliably, Church Cap still shows the language code in the option text or fallback badge.

The operator dashboard shows a steady loading notice while captions start and the local speech model/audio input are being prepared. On Linux, Church Cap first tries the configured 16 kHz capture rate and, if a USB audio interface only opens at its native rate such as 48 kHz, captures at that native rate and resamples internally for Whisper. Audio input saves prefer the device name rather than the volatile PortAudio index, so USB devices are less likely to break after reboot or re-enumeration. On visitor phones, changing language during an active caption stream shows a small in-card loading notice that does not move the caption layout; it is not shown on an empty waiting screen. When translated captions are disabled, the visitor language menu clearly explains that translated captions are unavailable and keeps the source-caption option available. Visitor and Service Leader pages request the browser's native screen wake lock where supported and release it when the page is hidden. Some mobile browsers may still dim or sleep the device when wake lock is unavailable or rejected, especially over plain local HTTP. The display and OBS pages share the phone caption renderer so new words ease in and existing lines glide instead of the whole overlay snapping on every update.

Translated captions are separate, experimental, and resource-heavy. Whisper performs speech-to-text; it does not translate one English caption stream into every viewer language by itself. Real translated captions require a translation provider. Church Cap supports **Recommended package / CTranslate2 INT8 SMaLL-100**, **Base package / Argos Translate**, **Compatibility package / PyTorch SMaLL-100**, and **Auto / Recommended + Base + Compatibility** modes.

The first-time setup scripts can install common Base package / Argos packs, all available Base package / Argos packs, Base plus the Recommended package / CTranslate2 INT8, or Base plus the Compatibility package / PyTorch SMaLL-100. The operator **Languages** page can also install common Base package / Argos packs, install all Base package / Argos packs, or use **Improve translation performance** to install the faster local translation engine without running commands. The Compatibility package / PyTorch SMaLL-100 remains available as a fallback option. Normal desktop installs keep the full Languages page available. On `appliance_cpu`, the page is available as an advanced option with a confirmation warning and a hard cap of three active translated languages. On `appliance_gpu`, translated captions require the GPU/CUDA runtime to be ready. To rerun common Base setup manually:

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

Install optional Recommended package / CTranslate2 INT8 SMaLL-100 support:

```bash
./scripts/install-small100-ct2-int8.sh
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-small100-ct2-int8.ps1
```

By default, translated-caption language availability is automatic: visitors can request any supported language shown by the selected provider, and Church Cap translates the most-requested languages up to the operator's active limit. The default active limit is 2 for fresh installs. The control can be raised on powerful hardware, but CPU-only systems should usually stay at 1-2 active translated languages when latency matters.

Translation may be inaccurate for Scripture, names, theology, pastoral details, and safeguarding-sensitive content. Use a qualified human interpreter where accuracy matters.

More detail: [docs/translation.md](docs/translation.md).

## Security And Privacy

Church Cap is intended for local-network use. Do not port-forward it to the public internet without a full security review.

Recommended church setup:

- Run the caption computer on a trusted church/AV network.
- Let guests access only the public viewer port.
- Keep operator controls password-protected.
- Use the default dual-port start script.
- Keep operator access on localhost where possible.
- Pair a church-managed service-leader device from the local operator login page or the operator dashboard's **Service Leader** section instead of sharing the full operator login over HTTP.
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

## Service Leader Controls

On the Church Cap computer, either select **Connect a service leader device** on the operator login page or open **Service Leader** in the operator menu. Generate a one-use QR code, then scan it with the church phone or tablet. The operator section can replace or cancel an unused QR, show connected-device status, and disconnect all paired devices.

The paired page can start, stop, blank, resume, change the audio input while captions are stopped, monitor caption health, share audience QR codes through a temporary phone-download QR, export the current-session transcript, share redacted support logs after an explicit warning, and manage translated captions in Automatic or Manual language mode. On appliance profiles, the Operator Audience & OBS QR buttons use the same temporary phone-download handoff instead of saving files to the kiosk. When the operator sets Manual / restricted availability, the Service Leader and audience language pickers only show the selected languages. Its searchable language list matches native names, English names, language codes, and uses the same flag/code chips as the operator language page. Language and audio choices stay synchronised with the operator page. The operator and Service Leader controls show a subtle active-state glow, and short action messages explain when captions are starting, stopping, blanked, resuming, or sending a test caption. The caption preview uses the same live feed as audience phones, but the page warns that a control-device delay is not the main performance measure. It cannot access updates, passwords, performance settings, account/privacy settings, or model installation. Pairing expires after 90 seconds and the restricted session expires after four hours or two hours of inactivity, with an on-device warning before the inactivity timer runs out.

The page uses the configured operator port, normally `9090`. In secure operator mode, full operator routes remain localhost-only while `/service-leader` is available to paired devices. On HTTP, use a trusted staff/AV network; HTTPS is preferred for managed church devices.

More detail: [docs/service_leader_controls.md](docs/service_leader_controls.md).

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

The operator page includes an **Updates** section. It checks the latest GitHub release tag, reports when Church Cap is already up to date, asks for confirmation before updating, replaces this folder in place, and restarts Church Cap.

The scripts below provide the same in-place update flow. They preserve `.env`, `.venv`, `data/`, `logs/`, `certs/`, `config/glossary.csv`, and `config/profanity_filter.txt`. The displayed version is code-owned so a stale `APP_VERSION` in `.env` cannot keep Windows showing an older release. Legacy update scripts may still refresh `APP_VERSION` for compatibility, and app-owned defaults such as `FEEDBACK_EMAIL` are refreshed where appropriate.

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

On Linux:

```bash
./update-linux.sh
```

## Docker

Docker is useful for web-only server-style testing. Native audio operation is supported on macOS, Windows, and common Linux distributions. For a container smoke test:

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

- `.env`, `data/`, `certs/`, `.venv/`, logs, diagnostics exports, and local runtime files are not committed.
- Diagnostics wording is current and the export still excludes transcripts, passwords, secrets, `.env` contents, and unredacted local paths while clearly naming included system specs and warning against public sharing without review.
- `LICENSE`, `.github/SECURITY.md`, `.github/CONTRIBUTING.md`, `.github/CODE_OF_CONDUCT.md`, and `docs/legal/THIRD_PARTY_NOTICES.md` are included.
- Third-party versions and licence notes are reviewed in `docs/legal/THIRD_PARTY_NOTICES.md`.
- Script permissions are executable, or users can run `bash setup-macos.sh` to repair them during setup.
- Windows scripts are included for setup, start, password reset, update, optional CUDA runtime force reinstall, Base package / Argos model installation, optional Recommended package / CTranslate2 INT8 conversion, and optional Compatibility package / PyTorch SMaLL-100 installation.
- Linux scripts are included for package-manager-aware setup, start, update, password reset, Base package / Argos model installation, optional Recommended package / CTranslate2 INT8 conversion, and optional Compatibility package / PyTorch SMaLL-100 installation.

GitHub community files live in the standard `.github/` folder:

```text
.github/CONTRIBUTING.md
.github/SECURITY.md
.github/CODE_OF_CONDUCT.md
```

Church Cap is released under the MIT License. Dependency and model licence notes are in [docs/legal/THIRD_PARTY_NOTICES.md](docs/legal/THIRD_PARTY_NOTICES.md).
