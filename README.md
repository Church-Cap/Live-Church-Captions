# Church Cap

Version: **v0.9.0**

![Church Cap logo](assets/branding/church-cap-wide-dark.png)

Church Cap is an open-source, local-first live caption app for churches.

Visitors scan a QR code, open a local web page on the church Wi-Fi, and read live captions on their phone. The app transcribes one audio feed from the church sound desk or audio interface, then broadcasts the captions to phones, room displays, and OBS browser sources over the local network.

For a non-technical setup guide, start with [START_HERE.md](START_HERE.md).

## Download Church Cap

- [Mac — Apple Silicon](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.9.0): download the notarized DMG, drag Church Cap to Applications, then open it.
- [Windows — 64-bit](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.9.0): download and run the setup executable. The v0.9.0 Windows build is not Authenticode-signed, so Windows may show a SmartScreen warning.
- [Linux — 64-bit CLI](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.9.0): download `Church-Cap-Linux-CLI.tar.gz`, verify its published SHA-256 file, extract it, and run `bash setup-linux.sh`.

Upgrading a v0.8.0 Mac or Windows installation: download and run the v0.9.0 DMG or Windows installer once. v0.8.0 cannot install v0.9.0 through its in-app updater because v0.9.0 uses a replacement updater signing key; existing settings and local data are kept. Signed in-app updates resume from v0.9.0 onward. Linux updates are unaffected.

All platform downloads are published together under one semantic-version GitHub Release and use the single shared browser application in `app/`. Source checkout instructions remain below for contributors and advanced installations.

## Project Layout

Contributors: use the permanent `church-cap/` checkout and keep release installers
outside Git. See [development layout and repository safety](docs/project/DEVELOPMENT_AND_RELEASE_LAYOUT.md)
for local commit/push checks, platform handoffs and release storage.

Most users should install Church Cap from the [latest GitHub release](https://github.com/Church-Cap/Live-Church-Captions/releases). The files below are primarily for contributors and source-based installations.

- `app/` — shared Church Cap web application used across macOS, Windows, and Linux.
- `engine/` — packaged web-server entry point and lifecycle protocol.
- `desktop/` — native macOS and Windows supervisor, system tray integration, and updater.
- `config/` — local glossary overrides and caption-filter additions.
- `scripts/` — setup, build, release, diagnostic, and maintenance tools.
- `packaging/` — platform-specific installer, signing, and packaging configuration.
- `docs/` — user guides, architecture, legal information, translation documentation, and maintained project references.
- `docker/` — optional Docker development environment.
- `.github/` — contribution templates, security information, and automated checks.

### Source Setup Scripts

- `setup-macos.sh`, `start-macos.sh` — macOS source setup and startup.
- `setup-windows.cmd`, `start-windows.cmd` — Windows source setup and startup.
- `setup-linux.sh`, `start-linux.sh`, `update-linux.sh` — Linux CLI setup, startup, and updates.
- `reset-operator-password.*` — operator password and security-mode recovery tools.
- `install-cuda-runtime-*` — optional NVIDIA CUDA runtime installation helpers.

For source installation, see [START_HERE.md](START_HERE.md). Maintainers should also read the [cross-platform architecture](docs/project/CROSS_PLATFORM_ARCHITECTURE.md) and [desktop update release runbook](docs/project/DESKTOP_UPDATE_RELEASE_RUNBOOK.md).

## What It Includes

- Local FastAPI web server.
- QR codes for audience access, including hostname and IP fallback links.
- Mobile caption page with a viewport-bounded, internally scrollable accumulated Live feed for English and every translated language, plus an optional independently scrollable session transcript that starts closed on each visit. A word-timestamp-aware cue ledger shows safe English words immediately, briefly guards only a weak word at the live audio edge, and updates corrected wording in place before sealing it into the shared reader. The page also includes newest-first timestamps, font size, automatic system light/dark theme with local override, comfort/compact, pause, and local clear controls. Dismissing viewer notices returns their space to the caption panels without making the page longer.
- Operator login, operating-system-style first-run setup for security, hardware-aware caption performance and optional languages, plus the account/password page.
- Same-origin request tokens for first-run setup, login, pairing, operator forms, and operator API changes, plus bounded password-attempt pauses with a clear operator-facing explanation.
- Privacy-safe service measurements retained across restarts, with separate English operational-response and rolling-window estimates, stage timing, provider/scheduler outcomes, viewer-seconds, process/system resource aggregates, and a separate anonymised report.
- One-use QR pairing for a restricted service-leader page with start/stop, private-moment, status, and multi-language controls.
- Operator feedback page with a version-aware email link, plus **Diagnostics → Support** for privacy-aware exports and **Diagnostics → Application Storage** for opt-in cleanup of inactive model downloads and archived logs.
- Secure dual-port mode: public viewer port and localhost-focused operator port.
- Audio input selection from the operator page.
- Local OpenAI Whisper transcription with rolling partial/final captions tuned for accuracy-first readable live subtitle pacing.
- Optional `faster-whisper` backend with word-level alignment, guarded incomplete-edge words, sealed-audio buffer trimming, and start-to-start decode cadence for installs that need lower latency.
- Operator performance controls for switching between faster/lower-accuracy and slower/higher-accuracy presets, including model size, backend, CPU/GPU selection, and advanced latency tuning.
- Glossary correction for church-specific words.
- Bad-word censor for likely speech-to-text mistakes.
- Sensitive blank/pause mode for private or pastoral moments, with audience notices rendered through the selected client UI language where available.
- Transcript retention controls, encrypted local transcript cache, operator current-session transcript export as `.txt`, `.vtt`, `.srt`, and `.json`, plus restricted Service Leader TXT/VTT transcript export for appliance support after a privacy warning.
- OBS and ProPresenter presentation overlays with an operator-only setup guide. Each OBS browser source or ProPresenter Prop can use a generated one-language address (`/obs?integration=obs&lang=…` for OBS, `/propresenter?lang=…` for ProPresenter; older `/obs?integration=propresenter` Props keep working), report its connection state on the dashboard, and request translated captions without inflating the congregation viewer count. The `/display` and `/obs` surfaces share one polished two-line presentation policy: finalized cues remain immediate, live English drafts expose only the server-confirmed prefix, unstable revisions retain the last good wording, and both outputs use the same line-planning policy and subtle motion while preserving their surface-specific styling.
- On Church Cap appliances, local Display and OBS previews stay on the appliance shell origin so the persistent Home/System controls remain available and failed preview routes can return to the local recovery environment.
- Local multilingual support: phone UI labels use the lightweight catalogue in `app/locales/client_ui.json`, with Argos runtime fallback where needed. Experimental translated captions use package-style choices: **Recommended package** CTranslate2 INT8 / SMaLL-100, **Base package** Argos Translate, **Compatibility package** PyTorch SMaLL-100, or **Auto** mode across installed packages.
- Optional local translated audio for installed and independently reviewed Sherpa-ONNX voice packs. If translated captions are selected during first-run setup, a separate optional step can install one, several or all spoken-language packs; **Skip for now** remains the default, and English-only setup never asks. **Languages → Spoken translated audio** keeps later installation, estimated download/storage use, readiness and the visitor on/off control together. The catalogue covers Catalan, Spanish, French, Kazakh, Latvian, Nepali, Dutch, Slovenian, Swedish, Ukrainian and Mandarin for both Chinese caption scripts. A viewer can select **Listen** to hear finalized translated cues; one generated cue is shared by every listener using that language. English, unavailable voices, invalid/silent output and sensitive/private moments do not produce translated audio. See [spoken-language model notices](docs/legal/SPOKEN_LANGUAGE_MODELS.md).
- Optional Service Context preparation with deterministic temporary corrections, independent Bible-reference formatting, and an explicitly enabled experimental Whisper-assistance mode limited to two selected terms.
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

Use `bash setup-macos.sh` for the first run because the setup script may not be executable yet after download or unzip. The setup script repairs permissions for the other Church Cap scripts, prepares a local `.venv`, installs the app dependencies, creates `.env` if needed, and can help set a friendly Bonjour hostname such as `church-cap.local`. Optional caption languages are then explained in the browser setup assistant. It recommends English-only or the Broad language pack from local processor/CUDA checks and can install the selected open-source local runtime; additional Base and compatibility controls remain available later from **Languages**.

The normal start command opens the password setup page first. If a password already exists, Church Cap redirects you onward to the operator flow:

```text
http://localhost:9090/setup
```

Audience viewers use the public viewer port, normally:

```text
http://church-cap.local:8080/
```

On first run, the browser assistant creates the operator password, recommends suitable caption performance, and offers optional translated-caption setup. Choosing a translated-caption pack reveals a separate, skippable spoken-audio step; choosing English-only proceeds directly to Review. Public caption viewers do not need the operator password.

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

The setup script prepares `.venv`, installs the app dependencies, checks CUDA/GPU support, and creates `.env` if needed. If Python is missing and `winget` is available, it can offer to install Python 3.12 first. The browser assistant then recommends suitable caption performance and a friendly language pack using only local hardware information; additional Base and compatibility controls remain available later from **Languages**.

The normal start command opens the password setup page first. If a password already exists, Church Cap redirects you onward to the operator flow:

```text
http://localhost:9090/setup
```

Audience viewers normally use the IP address shown in the terminal or QR code, for example:

```text
http://192.168.1.50:8080/
```

Church Cap can use either the standard OpenAI Whisper backend or the lower-latency `faster-whisper` backend. The operator page includes a **Performance** section with a speed/accuracy slider and advanced controls for platform view, backend, model size, processor, compute type, caption refresh, listening window, silence timing, and stability checks. These settings are saved automatically in the per-user runtime config and apply the next time captions are started. To protect the live audience feed, performance controls are locked while captions are running.

The **Performance platform** setting defaults to auto-detect. On Windows, `faster-whisper` can use CUDA through CTranslate2 when the GPU, drivers, and required CUDA runtime DLLs are available. Source setup can offer to install or force reinstall exact CUDA 12.4 runtime/cuBLAS and cuDNN 9 packages inside `.venv`, or you can run `.\install-cuda-runtime-windows.cmd` later. The packaged Windows application instead verifies the exact allow-listed wheels and installs only their required DLL/licence files beneath per-user Church Cap application data; it does not need a source checkout or `.venv`. The operator Performance panel shows **Check CUDA** and **Install / repair CUDA runtime** controls, and the Windows installer offers the same approximately 1.1 GB runtime as an explicit unchecked option. Selecting **GPU / NVIDIA CUDA** forces a CUDA load attempt first for Faster Whisper; if the runtime cannot load CUDA, Church Cap falls back to CPU and reports the reason in the operator status. The built-in CUDA runtime installer targets Faster Whisper/CTranslate2 rather than PyTorch/OpenAI Whisper, so CUDA recommendations stay on Faster Whisper. On macOS, the processor choices hide CUDA and can show Apple GPU / Metal for OpenAI Whisper when PyTorch supports MPS; diagnostics and the operator strip report Apple chip/GPU information and unified memory more clearly. Argos Translate remains local and experimental and may still run on CPU. Recommended package uses a converted SMaLL-100 model through CTranslate2/INT8 and can use CUDA where CTranslate2 supports it. Compatibility package still uses PyTorch and may use CUDA if PyTorch sees it.

The local CUDA runtime installer is usually easier than installing the full NVIDIA CUDA Toolkit. Windows users who already manage NVIDIA tooling can instead install CUDA 12.x and cuDNN system-wide from NVIDIA, then rerun `.\start-windows.cmd`.

## Quick Start On Linux

From the project folder:

```bash
bash setup-linux.sh
./start-linux.sh
```

The setup script detects `apt`, `dnf`, `yum`, `zypper`, `pacman`, or `apk`, installs build/audio prerequisites through that package manager, and keeps all Python packages inside `.venv`. The browser assistant handles optional language setup after the first start. It is intended for AlmaLinux, Rocky Linux, RHEL-family systems, Fedora, Ubuntu, Debian, openSUSE, Arch Linux, Alpine Linux, and close derivatives.

The current pinned runtime requires Python 3.10-3.13 and at least 8 GiB of installation headroom. Setup prefers a compatible installed Python. If the distribution only supplies Python 3.14 or newer—as Ubuntu 26.04 does—it downloads a pinned `uv` bootstrap for the detected x86_64/ARM64 and glibc/musl platform, verifies its SHA-256, and installs Python 3.12 under Church Cap's own `.tools` directory. It does not replace or reconfigure the system Python. Pip's persistent cache is disabled to reduce temporary disk usage. If setup reports `Disk quota exceeded`, free space for the current Linux account or ask the administrator to raise its quota, then rerun setup; it can offer to recreate only an incompatible partial Church Cap `.venv`.

On AlmaLinux, Church Cap prefers an available Python 3.12 or 3.11 because the operating system's default `python3` may be too old. The installer does not enable extra repositories automatically. If `dnf` cannot find PortAudio development packages, enable the normal AppStream/CRB repositories according to your system policy and rerun setup. When active `firewalld` or UFW is detected, setup recommends an audience-only TCP rule and requires explicit confirmation before adding it. The rule uses the configured viewer port, normally 8080, and never opens operator port 9090.

Linux always shows both audience QR choices. Unless `CAPTION_LOCAL_HOSTNAME` or `PUBLIC_BASE_URL` explicitly supplies a working DNS/mDNS name, the hostname QR is labelled as requiring setup and the direct-IP QR is recommended. A computer name alone does not guarantee that `<name>.local` is published through mDNS. If the direct-IP QR still fails after the host firewall is open, check the router for guest-Wi-Fi or client isolation between the phone and caption computer.

Linux NVIDIA acceleration still requires a working system NVIDIA driver. When `nvidia-smi` detects that driver, setup checks separately for the CUDA 12 cuBLAS and cuDNN 9 libraries required by current CTranslate2. If they are missing, setup can install them as Python wheels inside Church Cap's `.venv`; it does not change the driver, enable repositories, or install the full CUDA Toolkit. `start-linux.sh` automatically exposes those project-local library directories before Python starts. To repair an existing installation manually, run `./install-cuda-runtime-linux.sh`, then always launch with `./start-linux.sh`. If the runtime remains unavailable, automatic mode uses CPU/int8 instead of treating device enumeration alone as proof that CUDA is ready.

More detail: [docs/linux.md](docs/linux.md).

## Recorded Sermon Testing

Church Cap uses service-metrics schema 13. It records privacy-safe Service Context counts alongside text-free audio-callback recovery, word-timestamp, edge-guard, cadence, translation, cue, queue, shutdown, and resource measurements. Authenticated diagnostics also show text-free translated-audio availability, listener, queue, drop, and synthesis timing information. The downloadable service report retains no audio, recognition timestamps, confidence values, caption text, translation text, generated speech, sermon notes, or context terms. Follow [docs/recorded-sermon-testing.md](docs/recorded-sermon-testing.md).

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

The permission belongs to the app that launches Church Cap, which is usually Terminal for `start-macos.sh`. Fully restart Church Cap after changing it. The built-in MacBook microphone may be unavailable with the lid closed in clamshell mode; open the lid or select an iPhone, USB, or other external input. On Windows, enable both microphone and desktop-app access. On Linux, check the selected PipeWire, PulseAudio, or ALSA capture source and mute state. Church Cap opens the audio input before loading the speech model. If the stream opens but supplies exact digital silence for three seconds, the Operator page shows a non-blocking platform-specific warning; it clears as soon as real samples arrive. This health check does not record or retain audio.

## Performance Tuning

Open `/operator`, then use **Performance** on the dashboard.

- Move the slider toward **Fastest** for older CPUs or lower delay.
- Move the slider toward **Most accurate** when the computer has enough CPU/GPU headroom and wording matters more than delay. The far-right setting uses `medium.en` and can noticeably increase latency, so check it with the benchmark before a service.
- Use **More settings** for deeper tuning. Easy mode shows platform, backend, model size, and processor. Advanced mode adds compute type, caption refresh, listening window, silence finalise timing, stability checks, and OpenAI Whisper beam size. The platform view is automatic by default, but can be set to macOS, Windows, or Linux if detection is wrong.

Performance adjustments save automatically when captions are stopped. Stop captions before changing the model, backend, processor, or other performance settings because the model and audio stream are loaded when captions start. The top operator bar includes **English Delay** and **Translation Delay** tiles so the operator can distinguish source English caption latency from translated-caption latency during a service. The Performance panel includes an operator-started 15-second benchmark and live monitor; neither runs automatically. Live-monitor samples are capped in memory. It can recommend conservative live-service settings from local hardware/runtime information and apply them offline without any internet access. The medium model stays available on the slider, but it should be selected manually only after a successful benchmark. The live transcribers and session transcript include a repetition guard that trims obvious stuck word or phrase loops before they reach the audience captions or retained transcript.

**Diagnostics → Application Storage** shows the application, local data, Hugging Face downloads, OpenAI Whisper downloads, optional spoken-audio models, and bounded log use. Church Cap rotates its own diagnostic logs at 5 MB with two backups and disables routine HTTP access logging. Cleanup is never automatic: the operator must review and confirm exact inactive downloads or archived logs, and Church Cap protects the active model, current logs, settings, transcripts, and current service data.

## Main Pages

```text
/                  phone/tablet live captions
/display           large display page for screens, using the smooth audience-caption renderer
/obs               transparent OBS overlay; fixed language with ?lang=code
/propresenter      the same overlay for ProPresenter Web objects; fixed language with ?lang=code
/obs/help          OBS setup guide, operator login required
/propresenter/help ProPresenter setup guide, operator login required
/operator          operator controls, login required
/service-leader    restricted service-leader controls, one-use pairing required
/feedback          feedback email guidance, login required
/account           change operator password, login required
/setup/network     local hostname/HTTPS/Wi-Fi guidance, login required
/qr.png            hostname QR code
/qr-ip.png         LAN IP fallback QR code
/health            minimal public readiness, service status, and version check
/transcript.txt    current-session transcript export, operator login required
/transcript.vtt    current-session WebVTT export, operator login required
/transcript.srt    current-session SRT export, operator login required
/transcript.json   current-session JSON export, operator login required
/api/diagnostics/export  local diagnostics JSON export, operator login and local computer required
/api/diagnostics/download-handoff  temporary appliance diagnostics handoff QR, operator login and local computer required
```

## Translation

Phone UI language selection is local and lightweight. In Manual / restricted language mode, visitor and Service Leader language pickers can show installed languages that are not currently enabled and let someone request them; the Operator and paired Service Leader receive floating request cards and can accept or reject a language without changing the active translation capacity limit. The Service Leader card drops over the top section of the page and also shows current translation-slot use and read-only viewer demand. The visitor page uses static strings from `app/locales/client_ui.json` first, including manual fallback strings for languages Argos does not cover. If a selected language is not in that file, Church Cap asks the local Base / Argos provider to translate the small set of UI labels at runtime, then falls back to English if the needed Argos pack is not installed. This UI path is separate from live caption translation routing and does not require captions to be running. Audience language lists show compact Unicode flag chips and keep the language code in the language text. Operator and Service Leader lists keep compact flag/code chips for admin readability. Search matches language codes, English names, native names, and accented names. When a platform does not render emoji flags reliably, Church Cap still shows the language code in the option text or fallback badge.

Tigrinya text captions are included in the optional Recommended language package using the Apache-2.0 Helsinki-NLP OPUS-MT model. New Recommended installs include it automatically; an upgraded installation that already has SMaLL-100 can use **Repair Recommended package** to add and locally verify the missing Tigrinya files. It remains separate from spoken translated audio and is not downloaded during normal Church Cap setup. Reviewed spoken-audio voice models can be removed individually from Languages or Diagnostics while captions are stopped; Diagnostics reports their actual per-pack and combined storage use, while text translation and the shared speech runtime are preserved.

The operator dashboard shows a steady loading notice while captions start and the local audio input/speech model are being prepared. Audio capture opens first so permission or routing problems are visible on the microphone meter while the model loads. If an open stream supplies exact digital silence for three seconds, the Operator page shows a non-blocking platform-specific warning. On Linux, Church Cap first tries the configured 16 kHz capture rate and, if a USB audio interface only opens at its native rate such as 48 kHz, captures at that native rate and resamples internally for Whisper. Audio input saves prefer the device name rather than the volatile PortAudio index, so USB devices are less likely to break after reboot or re-enumeration. On visitor phones, changing language during an active caption stream shows a small in-card loading notice that does not move the caption layout; it is not shown on an empty waiting screen. When translated captions are disabled, the visitor language menu clearly explains that translated captions are unavailable and keeps the source-caption option available. Visitor and Service Leader pages request the browser's native screen wake lock where supported and release it when the page is hidden. Some mobile browsers may still dim or sleep the device when wake lock is unavailable or rejected, especially over plain local HTTP. The display and OBS pages share the phone caption renderer so new words ease in and existing lines glide instead of the whole overlay snapping on every update.

Translated captions are separate, experimental, and resource-heavy. Whisper performs speech-to-text; it does not translate one English caption stream into every viewer language by itself. Real translated captions require a translation provider. Church Cap supports **Recommended package / CTranslate2 INT8 SMaLL-100**, **Base package / Argos Translate**, **Compatibility package / PyTorch SMaLL-100**, and **Auto / Recommended + Base + Compatibility** modes.

First-time terminal setup installs no optional translation model. The browser assistant offers **English captions only**, **Broad language pack**, and an Advanced **PyTorch SMaLL-100 language pack** fallback, with a local hardware-based recommendation and conservative active-language limit. Broad and PyTorch may be selected together; **Select all packs** enables Automatic provider mode and installs the selected model packs sequentially with combined progress. A plain-language information dialog explains the storage, performance and compatibility tradeoffs. If translation is selected, a separate optional page can install selected spoken-audio voices; **Skip for now** is the default. Voice installation waits until caption-language installation has completed so the large installers do not compete. On NVIDIA systems the PyTorch option is promoted into view, but it is labelled CUDA-verified only when the locally installed open-source PyTorch runtime reports that CUDA is available; a Windows installer CUDA selection is shown as pending until runtime verification succeeds. The operator **Languages** page can additionally install common Base package / Argos packs, install all Base package / Argos packs, or repair the broad and compatibility runtimes. Normal desktop installs keep the full Languages page available. On `appliance_cpu`, the page is available as an advanced option with a confirmation warning and a hard cap of three active translated languages. On `appliance_gpu`, translated captions require the GPU/CUDA runtime to be ready. To rerun common Base setup manually:

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

The paired page can start, stop, blank, resume, change the audio input while captions are stopped, monitor caption health, share audience QR codes through a temporary phone-download QR, export the current-session transcript, share redacted support logs after an explicit warning, and manage translated captions in Automatic or Manual language mode. It receives incoming audience language requests in a top-down Accept/Reject card and shows active translation slots and viewer-language demand without exposing performance or model controls. Its microphone monitor also shows the Operator's digital-silence troubleshooting warning when an open input supplies no signal. On appliance profiles, the Operator **Congregation → Join Live Captions** QR buttons use the same temporary phone-download handoff instead of saving files to the kiosk. When the operator sets Manual / restricted availability, the Service Leader and audience language pickers only show the selected languages. Its searchable language list matches native names, English names, language codes, and uses the same flag/code chips as the operator language page. Language and audio choices stay synchronised with the operator page. The operator and Service Leader controls show a subtle active-state glow, and short action messages explain when captions are starting, stopping, blanked, resuming, or sending a test caption. The caption preview uses the same live feed as audience phones, but the page warns that a control-device delay is not the main performance measure. It cannot access updates, passwords, performance settings, account/privacy settings, or model installation. Pairing expires after 90 seconds and the restricted session expires after four hours or two hours of inactivity, with an on-device warning before the inactivity timer runs out.

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

The operator page includes an **Updates** section. **Check for updates** works differently on each platform:

- **Installed Mac and Windows app:** Church Cap brings the desktop app forward on its **Settings** tab and runs its signed-updater **Check for updates**. Review and install the update there. The operator page never installs desktop updates itself.
- **Linux:** Church Cap runs `./update-linux.sh --check`, reports the result, and asks for confirmation before running the same script to replace this folder in place and restart.
- **Mac and Windows source folders:** Church Cap checks the latest GitHub release tag and asks for confirmation before running the update script below.

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

## Factory Reset

The installed macOS and Windows application has **Settings → Updates and recovery → Factory reset Church Cap**. This separate, strongly confirmed action stops the local server, removes the operator account, settings, transcripts, service measurements, logs, in-app exports, and downloaded caption/voice models, then restarts into the complete first-time setup. It does not uninstall Church Cap. The existing password-reset action remains available when settings and models should be preserved.

Linux has the same reset boundary without a native application shell. Stop Church Cap, run the following command from its folder, type `RESET`, and then start Church Cap again:

```bash
./factory-reset-linux.sh
```

Factory reset is intentionally not exposed as an ordinary browser-dashboard button: stopping the engine before deleting model and data files is safer and more reliable on Windows, macOS and Linux.

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
python -m pip install --upgrade "pip==26.1.2" "setuptools<82" wheel
python -m pip install -r requirements.txt
cp env.example .env
./scripts/run-dev.sh
```

Recommended Python version: **3.12**. The current pinned dependency set supports Python 3.10 through 3.13.

Run the core checks:

```bash
python -m unittest discover -s tests
python -m compileall app tests
```

GitHub CI installs the security tools separately. To run the same security gates locally:

```bash
python -m pip install "bandit==1.9.4" "pip-audit==2.10.1"
bandit --quiet --recursive --severity-level high app
pip-audit --requirement requirements.txt
```

## Release Hygiene

Before publishing a release, confirm:

- `.env`, `data/`, `certs/`, `.venv/`, logs, diagnostics exports, and local runtime files are not committed.
- Diagnostics wording is current and the export still excludes transcripts, passwords, secrets, `.env` contents, and unredacted local paths while clearly naming included system specs and warning against public sharing without review.
- `LICENSE`, `.github/SECURITY.md`, `.github/CONTRIBUTING.md`, `.github/CODE_OF_CONDUCT.md`, `docs/legal/THIRD_PARTY_NOTICES.md`, and `docs/legal/SPOKEN_LANGUAGE_MODELS.md` are included.
- Third-party versions and licence notes are reviewed in `docs/legal/THIRD_PARTY_NOTICES.md`; optional voice-specific sources and obligations are reviewed in `docs/legal/SPOKEN_LANGUAGE_MODELS.md`.
- Script permissions are executable, or users can run `bash setup-macos.sh` to repair them during setup.
- Windows scripts are included for setup, start, password reset, update, optional CUDA runtime force reinstall, Base package / Argos model installation, optional Recommended package / CTranslate2 INT8 conversion, and optional Compatibility package / PyTorch SMaLL-100 installation.
- Linux scripts are included for package-manager-aware setup, start, update, password reset, optional project-local CUDA runtime installation, Base package / Argos model installation, optional Recommended package / CTranslate2 INT8 conversion, and optional Compatibility package / PyTorch SMaLL-100 installation.

GitHub community files live in the standard `.github/` folder:

```text
.github/CONTRIBUTING.md
.github/SECURITY.md
.github/CODE_OF_CONDUCT.md
```

Church Cap is released under the MIT License. Dependency and model licence notes are in [Third-Party Notices](docs/legal/THIRD_PARTY_NOTICES.md) and [Optional Spoken-Language Model Notices](docs/legal/SPOKEN_LANGUAGE_MODELS.md).
