# Church Cap Quick Start Guide

Version: v0.7.0

This guide is for the person setting up Church Cap for a church service.

## What Church Cap Does

Church Cap listens to one audio input from the church sound desk or USB audio interface. It creates live captions locally on the caption computer and shares them over the church Wi-Fi.

Visitors do not install an app. They scan a QR code and read captions in their browser.

## What You Need

- An Apple Silicon Mac, Windows 10/11 computer, or modern 64-bit Linux computer. On Windows and Linux, setup can install or select a supported Python where the platform package manager provides one.
- Church Cap downloaded or copied to the caption computer.
- Internet access for first setup.
- A USB audio interface or mixer input from the sound desk.
- The caption computer and audience phones on a network where phones can reach Church Cap.

## Hardware Guidance

Minimum for testing: Apple Silicon Mac, Windows 10/11, or modern 64-bit Linux with a 4-core CPU and 8 GB RAM. Use **Fastest** or **Fast** if captions lag.

Recommended for live services: Apple Silicon Mac with 16 GB RAM, or Windows/Linux with a recent 6-8 core CPU and 16 GB RAM. NVIDIA GPU acceleration needs current drivers and CUDA runtime files that CTranslate2 can use.

Use **Benchmark** before selecting heavier models such as `small.en` or `medium.en`.

## First-Time Setup On Mac

1. Open Terminal.
2. Go to the Church Cap folder. This example assumes the downloaded and extracted folder has been moved into Documents.

```bash
cd "$HOME/Documents/Live-Church-Captions-0.7.0"
```

3. Run setup. Use `bash` for this first command because the setup script may not be executable yet. The setup script repairs permissions for the other Church Cap scripts automatically.

```bash
bash setup-macos.sh
```

4. Wait for setup to finish, then continue to **Start Church Cap** below.

The setup script installs the local Python environment and audio dependencies. It also offers translation-resource choices for common Base package / Argos packs, all Base package / Argos packs, optional Recommended package / CTranslate2 INT8, optional Compatibility package / PyTorch SMaLL-100, or skipping translation resources until later. It only installs Python packages inside the Church Cap folder's `.venv`.

If setup asks whether to set the Mac hostname to `church-cap.local`, choose yes if this Mac will normally run captions.

## First-Time Setup On Windows

1. Open PowerShell.
2. Go to the Church Cap folder. This example assumes the downloaded and extracted folder has been moved into Documents.

```powershell
cd "$HOME\Documents\Live-Church-Captions-0.7.0"
```

3. Run setup.

```powershell
.\setup-windows.cmd
```

4. Wait for setup to finish, then continue to **Start Church Cap** below.

The setup script installs the local Python environment and app dependencies, checks CUDA/GPU support, and offers translation-resource choices for common Base package / Argos packs, all Base package / Argos packs, optional Recommended package / CTranslate2 INT8, optional Compatibility package / PyTorch SMaLL-100, or skipping translation resources until later. v0.6.x starts the translation-performance track with the Recommended package / CTranslate2 INT8 for heavier translation paths, while Base package / Argos remains available as fallback. If Python is missing and Windows Package Manager is available, setup can offer to install Python 3.12 first. If an NVIDIA GPU is visible but CUDA is not ready for faster-whisper, setup can offer to install or force reinstall local CUDA 12 runtime packages into Church Cap's `.venv`. The force reinstall bypasses pip's cache and downloads fresh CUDA runtime wheels. If CUDA is not ready, Church Cap falls back to CPU.

You can also run the optional GPU runtime installer later:

```powershell
.\install-cuda-runtime-windows.cmd
```

If Windows says `UnauthorizedAccess`, scripts are disabled, or the file came from another computer, use `setup-windows.cmd`. If it is still blocked, right-click the downloaded zip or Church Cap folder, choose **Properties**, tick **Unblock** if shown, then try again.

## First-Time Setup On Linux

Open a terminal, then go to the Church Cap folder. This example assumes the downloaded and extracted folder has been moved into Documents.

```bash
cd "$HOME/Documents/Live-Church-Captions-0.7.0"
bash setup-linux.sh
```

The installer detects `apt`, `dnf`, `yum`, `zypper`, `pacman`, or `apk`. It installs only the system prerequisites and creates a project-local `.venv`. AlmaLinux and related RHEL-family systems use `dnf`/`yum`; the installer prefers Python 3.12 or 3.11 when available. It does not change repository configuration or install NVIDIA drivers/CUDA.

Start later with:

```bash
./start-linux.sh
```

## Church Cap Box Profiles

Normal installs do not enter appliance mode automatically. A Church Cap Box uses an explicit identity file created by the appliance shell installer. CPU boxes use `appliance_cpu` for a simpler English-first workflow with Languages available as an advanced, warned option capped at three active translated languages. GPU boxes use `appliance_gpu` so multilingual controls are tied to NVIDIA/CUDA readiness.

The appliance path uses the local operator port `9090`; it does not fall back to `8000` or `8080`.

## Start Church Cap

For normal use after setup:

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

Wait while the app starts. The operator page should open automatically:

```text
http://localhost:9090/operator
```

On first Windows setup, Church Cap may open the password setup page first:

```text
http://localhost:9090/setup
```

The first time, create an operator password. Public caption viewers do not need this password.

## Know The Two Ports

Church Cap normally uses two local ports:

```text
Operator controls: http://localhost:9090/operator
Audience captions: http://church-cap.local:8080/
```

If you accidentally open `localhost:8080/operator`, use `localhost:9090/operator` instead.

On Windows, audience phones usually use the IP address shown by `start-windows.cmd` or the QR code on the operator page.

## Select The Audio Input

In the operator page:

1. Stop captions if they are running.
2. Find **Microphone / audio interface**.
3. Choose the USB audio interface or mixer input.
4. Click **Save input**.
5. Click **Start captions**.

Recommended audio route:

```text
Church microphones -> sound desk -> USB audio interface -> Church Cap Mac
```

Avoid using the built-in Mac microphone for a church service.

## Tune Caption Speed And Accuracy

In the operator page, use **Performance** on the dashboard.

- Move the slider toward **Fastest** if captions are too delayed or the computer is older.
- Move the slider toward **Most accurate** if the computer has enough headroom and better wording matters more than delay. The far-right setting uses `medium.en`, which may increase latency.
- Open **More settings** only when you need finer control. Easy mode shows platform, Whisper backend, model size, and CPU/GPU choice. Advanced mode adds caption refresh speed, listening window, and final-caption stability. The platform view normally auto-detects macOS, Windows, or Linux, but can be changed manually if needed. The top operator bar shows **English Delay** and **Translation Delay** so source-caption and translated-caption latency are visible without opening the benchmark panel.

Adjustments save automatically while captions are stopped. Stop captions before changing performance settings because Church Cap loads the AI model when captions start, and the Performance panel is locked during a live caption session to protect the audience feed. **Run 15s benchmark** and **Live monitor** begin only when the operator presses their buttons; they do not run automatically. Live-monitor samples are capped in memory. **Apply recommended** uses only local hardware/runtime information and does not need internet. It chooses a conservative live-service preset; select the medium model manually only after a successful benchmark. On Windows, choose Windows in the platform selector to reveal CUDA troubleshooting buttons for checking or force reinstalling the local CUDA runtime. Church Cap also trims obvious repeated word or phrase loops before they are shown to viewers or kept in the session transcript.

## Share Captions With Visitors

In the operator page, open **Audience & OBS**.

Use the main QR code first. If an Android phone or guest Wi-Fi cannot open the `.local` address, use the Android/IP fallback QR code. On an appliance, the Operator and Service Leader pages can create a temporary **Share QR** phone handoff so the QR image can be saved on a phone for printing or service slides.

The **Outputs** area is separate from audience phones. **Room display** is for a projector, TV, or confidence monitor. **OBS overlay** is for livestream software as a browser source. Both use the same smoother caption animation as the audience view. On a Church Cap Appliance, Church Cap warns before opening these clean output pages because they intentionally have no operator navigation and can cover the kiosk controls.

## Visitor Caption View

The phone caption page stays within the visible device screen instead of growing into a long page. Live captions use their own accumulated bottom-to-top scroll area in English and every translated language; visitors can scroll inside it to revisit recent live lines without moving the controls. The first English cue appears at the normal caption refresh speed, and corrected wording replaces that cue until it is sealed into the reader. Translated revisions use the same cue identity. The server-backed session transcript has a separate scroll area with timestamped captions and the newest entry at the top. It starts closed whenever the page is opened so Live receives the available space; select **Show transcript** to open it and **Hide transcript** to close it again.

While reminder or accuracy/translation notices are visible, a subtle hint beside **Live** explains that closing them creates more caption space. Closing a notice keeps the overall page the same height and automatically expands the Live and transcript panels into the released space. On short phones, spacing becomes denser and the product footer yields space while the full safety notice wording remains available.

When captions are already visible and a visitor changes language, the phone page may briefly show a small loading notice inside the live caption card while the new language stream catches up. The notice overlays the card so the controls and transcript do not jump. If translated captions are disabled for the service, the language menu explains that translated captions are unavailable and keeps the source-caption option visible. The visitor page requests the browser's native screen wake lock where supported so the phone is less likely to sleep during a service; it releases when the page is hidden or the browser revokes it. This keeps the implementation light, although any always-on screen will still use normal display battery power.

In landscape orientation on phones and tablets, the viewer uses a compact side-by-side layout: live captions take about 75% of the width and the transcript takes the remaining space when enabled. The live caption and transcript panels stay within the visible screen; longer transcript history scrolls inside the transcript panel. If a visitor hides the transcript, the live caption view expands to use the full width.

Visitors automatically get the light or dark theme from their device settings. They can still use the theme button to set a local override, and can change text size, comfort/compact spacing, pause their local view, or clear their local screen without affecting anyone else. On a Church Cap Appliance, the operator/appliance theme is remembered by the appliance shell rather than relying on a desktop light/dark setting, so it comes back in the chosen mode after the kiosk restarts.

## During A Service

- Use **Start captions** when ready.
- If the speech model or audio input takes a moment to load, the operator page shows a polished status notice until captions are live. Start, Stop, Blank / pause, and Resume also show short action messages and a subtle active glow so the current caption state is visible at a glance.
- Use **Stop** when captions should stop.
- Use **Blank / pause** before private prayer, pastoral details, testimony, safeguarding, or anything sensitive. While blanked, captions are not shown, retained in the session transcript, or included in transcript exports; Church Cap also flushes the live transcription buffer and drops a short buffered-audio window when captions resume. Audience phones show the blanked/resumed notice in the selected caption UI language where a local UI string or runtime UI translation is available.
- Use **Resume** when public captions should continue.
- Watch the microphone level meter to confirm audio is coming in.
- Use the privacy controls to choose whether transcript history is saved and how long to keep it. A fresh app start begins with an empty visible session transcript; older saved transcript cache is pruned on startup using the retention window saved with that cache. **Open transcript folder** reveals the per-user local cache folder on the Church Cap computer. **Export TXT/VTT/SRT/JSON** downloads the current-session transcript only and asks the operator to confirm the privacy warning first. Clearing the transcript deletes the retained local transcript cache.

## Service Leader Controls

Smaller churches can pair a trusted phone or tablet without exposing the full operator dashboard:

1. On the Church Cap computer, use **Connect a service leader device** on the login page, or sign in and open **Service Leader** in the operator menu.
2. Generate the one-use QR code.
3. Scan it with the trusted device.

The simple page can start/stop captions, blank/resume for sensitive moments, change the audio input while captions are stopped, show microphone and caption-health status, share audience QR codes to a phone, export the current-session transcript, share redacted support logs after a warning, and enable translated captions in Automatic or Manual language mode. Language search matches native names, English names, and language codes. Its caption preview uses the same live feed as audience phones, but the page explains that a delayed control-device preview is not the main performance measure. It cannot access passwords, updates, performance settings, account/privacy settings, or translation installation.

The QR expires after 90 seconds and works once. The paired session lasts at most four hours and expires after two hours without activity. A warning offers to refresh the idle timer before it expires. The **Service Leader** operator section shows connected-device status and can replace or cancel an unused QR, open the restricted route, or disconnect all paired devices.

For HTTP, use a private staff/AV Wi-Fi network rather than open or congregation guest Wi-Fi. HTTPS is preferred for a managed church phone or tablet.

## Translation

Phone UI language selection is local and lightweight. It uses bundled interface labels and falls back to English for labels that have not been translated yet.

Translated captions stay off until the operator enables them. The **Languages** page lets the operator choose Off, Recommended package / CTranslate2 INT8 SMaLL-100, Base package / Argos, Compatibility package / PyTorch SMaLL-100, or Auto / Recommended + Base + Compatibility mode, install language resources, and set how many translated languages can be active at once. Visitor languages are automatic by default; Church Cap prioritises the most-requested languages up to the active limit. The default active limit is 2 for fresh installs. Keep CPU-only systems at 1-2 active translated languages for live services, and raise the limit only after benchmarking stronger hardware.

On Church Cap Appliance CPU boxes, the **Languages** page remains available but opens with a CPU warning and cannot exceed three active translated languages. On Church Cap Appliance GPU boxes, translated captions are available only when the box is installed with the GPU appliance profile and CUDA is ready. Normal desktop installs keep the full Languages page visible without the appliance cap.

Translation is experimental and may be inaccurate. Start with the default active translated language limit, then keep it low if the computer struggles or captions begin to lag. Use a qualified human interpreter where accuracy matters.

## Passwords

The operator password is stored outside the Church Cap folder in:

```text
~/Library/Application Support/Church Cap/data/
```

On Windows, it is stored in:

```text
%APPDATA%\Church Cap\data\
```

On Linux, it is stored in:

```text
~/.local/share/church-cap/data/
```

It should survive terminal restarts, computer restarts, and app folder updates.

If the operator is locked out:

```bash
./reset-operator-password.sh
```

On Windows:

```powershell
.\reset-operator-password.cmd
```

Then restart Church Cap and create a new password.

## Common Problems

### The operator page does not open

Use:

```text
http://localhost:9090/operator
```

Wait a few seconds after running `./start-macos.sh`.

### The audience QR code does not open on a phone

Use the Android/IP fallback QR code on the operator page. Also check that the phone is on the same network and that guest Wi-Fi is allowed to reach the caption computer.

### No audio devices appear

- Check the USB audio interface is connected.
- Check macOS microphone permissions.
- Run setup again if PortAudio was not installed.

### Captions are inaccurate

- Use a direct feed from the sound desk rather than the built-in microphone.
- Check audio level.
- Add common corrections to `config/glossary.csv`.
- Use the bad-word censor for likely speech-to-text mistakes.

### You need to stop Church Cap

Press `Ctrl+C` in the Terminal window running Church Cap.

## Privacy Reminder

AI-generated captions can contain mistakes. Use the sensitive blank/pause mode for private or pastoral moments. Churches should use clear notices and follow their own safeguarding, privacy, and data protection policies.

## Feedback

The operator page includes a **Feedback** link. Use it for feature ideas, issues, setup confusion, accessibility feedback, and caption or translation notes. Please include the Church Cap version number and any useful computer, operating system, audio interface, or error details. For recorded-sermon comparisons, use **Diagnostics > Download anonymised service report**; this allow-listed file contains no speech, captions, translations, audio metadata, recognition timestamps, glossary content, paths, network identifiers, operator data, or logs. v0.7.0 retains the latest five completed summaries across restarts and reports timestamped cue-engine processing latency plus cue/queue health. Select **Reset test measurements** before a new comparison set.

Open **Diagnostics → Storage use** to see the application, Church Cap data, Hugging Face model downloads, OpenAI Whisper downloads, and current log use. Storage is calculated only when this page is opened or refreshed. **Review unused downloads** opens a Church Cap-themed confirmation menu; nothing is removed automatically. The active model, settings, transcripts, measurements, and current logs are protected. An inactive model offered for cleanup must download again if you select it later. Church Cap limits each of its diagnostic logs to 5 MB plus two archived copies.

For technical troubleshooting, use the broader **Download diagnostics** file, or **Share diagnostics** on an appliance. Attach diagnostics only if you are comfortable sharing system specs, OS version, performance settings, hardware status, measurements, storage category sizes, and redacted updater/CUDA logs. Do not post diagnostics publicly unless you have reviewed the file.

## Updating Church Cap

Mac:

```bash
./update-macos.sh
```

Windows:

```powershell
.\update-windows.cmd
```

Linux:

```bash
./update-linux.sh
```

You can also use **Updates** on the operator page. Church Cap checks the latest GitHub release tag first, tells you if it is already up to date, asks before updating, checks the downloaded files, replaces this folder in place, and restarts the app.

The updater preserves `.env`, `.venv`, `data/`, `logs/`, `certs/`, `config/glossary.csv`, and `config/profanity_filter.txt`. The displayed app version is code-owned so a stale `APP_VERSION` in `.env` cannot keep Windows showing an older release after an update.

The updater checks the ZIP, required release files, release version, staged Python syntax, and SHA-256 file checksums before and after copying. If the internet drops during download or dependency installation, the current app is left alone. During replacement, Church Cap keeps a rollback backup in `data/update-backups/` and restores it automatically if the copy or checksum check fails.
