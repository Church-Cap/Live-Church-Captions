# Church Cap Quick Start Guide

Software described: v0.9.0

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

## Upgrading From v0.8.0

Mac and Windows: download and run the v0.9.0 DMG or Windows installer once, as described below. Do not use **Check for updates** in v0.8.0 for this upgrade; v0.8.0 cannot verify v0.9.0 because the updater signing key was replaced, so it will stop safely without changing your installation. Your operator password, settings, and local data are kept. Signed in-app updates work again from v0.9.0 onward.

Linux: run `./update-linux.sh` as usual; Linux uses its own checksum-verified update path and is not affected by the key change.

## First-Time Setup On Mac

1. Open the [Church Cap v0.9.0 release](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.9.0) and download `Church-Cap-v0.9.0-macOS-Apple-Silicon.dmg`.
2. Open the DMG and drag **Church Cap** to **Applications**.
3. Open Church Cap from Applications and allow microphone access when macOS asks.
4. Church Cap opens the existing browser setup page. Create the operator password there.

The Mac release is Developer-ID signed, notarized, and stapled. It does not require Terminal for normal use.

## First-Time Setup On Windows

1. Open the [Church Cap v0.9.0 release](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.9.0) and download the Church Cap Windows x64 setup executable.
2. Run setup. Windows may show a SmartScreen warning because the v0.9.0 Windows build is not Authenticode-signed; check that the file hash matches the SHA-256 value published with the release before continuing.
3. Leave optional NVIDIA CUDA unchecked unless this computer has a supported NVIDIA GPU. If selected, setup downloads verified per-user CUDA 12.4/cuDNN 9 runtime files. An interrupted download safely retries after first launch and can also be repaired later from **Operator → Performance**.
4. Open Church Cap from the Start menu. No Command Prompt window is required.

Church Cap keeps mutable application data under `%APPDATA%\Church Cap`. English captions work on CPU when CUDA is not installed or not ready.

The Windows installer keeps PyTorch translation as a CPU compatibility option. The optional CUDA checkbox downloads runtime files for Faster Whisper/CTranslate2; it does not make the PyTorch SMaLL-100 language pack GPU-enabled. Church Cap recommends the Broad language pack on a capable Windows computer, and the first-run screen reports the installed runtime's actual status.

If optional CUDA does not become ready, keep Church Cap open and review **Operator → Performance** for installation progress. The installer hand-off record is `%APPDATA%\Church Cap\logs\cuda-installer-handoff.log`; the background download record is `%APPDATA%\Church Cap\logs\cuda-runtime-install.log`. These logs contain no caption text.

## First-Time Setup On Linux

1. Open the [Church Cap v0.9.0 release](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.9.0) and download both `Church-Cap-Linux-CLI.tar.gz` and `Church-Cap-Linux-CLI.tar.gz.sha256`.
2. In a terminal, verify and extract the curated archive:

```bash
sha256sum -c Church-Cap-Linux-CLI.tar.gz.sha256
tar -xzf Church-Cap-Linux-CLI.tar.gz
cd Church-Cap-Linux-CLI
bash setup-linux.sh
```

3. Start Church Cap later with:

```bash
./start-linux.sh
```

The Linux download is a terminal-first source package rather than a desktop wrapper. It contains the shared Church Cap runtime without repository history, Mac/Windows artifacts, tests, or developer build caches. Setup detects `apt`, `dnf`, `yum`, `zypper`, `pacman`, or `apk`, installs only system prerequisites, and keeps Python packages inside this folder's `.venv`. It does not install NVIDIA drivers or enable extra repositories.

Allow at least 8 GiB free for the initial Python environment. Church Cap v0.9.0 uses Python 3.10-3.13. If Linux only provides Python 3.14 or newer, setup automatically downloads a pinned, SHA-256-verified bootstrap and keeps managed Python 3.12 in this Church Cap folder; it does not change the system Python. This supports the Python 3.14 supplied by Ubuntu 26.04 without asking the user to find a separate installer. Setup disables pip's persistent cache to reduce temporary storage. If it reports `Disk quota exceeded`, free space owned by that Linux user or ask the administrator to raise the account quota, then rerun setup. A partial incompatible Church Cap `.venv` can be removed and recreated from the setup prompt; no other folder is removed.

Linux keeps both QR codes visible. The direct-IP QR is recommended unless local DNS/mDNS is configured. If a working NVIDIA driver is present but CTranslate2 reports missing `libcublas.so.12` or `libcudnn.so.9`, run `./install-cuda-runtime-linux.sh` and restart with `./start-linux.sh`.

Contributors and advanced users can still use a source checkout and the platform setup scripts documented in the repository README.

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

In the operator page, open **Congregation → Join Live Captions**.

Use the configured-hostname QR first when local DNS/mDNS is working. On Linux without hostname setup—or whenever a phone cannot open the hostname—use the direct-IP QR. On an appliance, the Operator and Service Leader pages can create a temporary **Share QR** phone handoff so the QR image can be saved on a phone for printing or service slides.

The **Outputs** area is separate from audience phones. **Room display** is for a projector, TV, or confidence monitor. **OBS Live Stream** generates a one-language browser-source address for livestream software. **ProPresenter** creates a one-language local Web-object address and shows whether the active Prop has connected. Changing an output language updates its address; copy the new address into OBS or ProPresenter and refresh an already-open source. A translated presentation output requests that translation without appearing in the congregation viewer count. All three use the same smoother caption animation as the audience view. On a Church Cap Appliance, Church Cap warns before opening these clean output pages because they intentionally have no operator navigation and can cover the kiosk controls.

For ProPresenter, open **Congregation → ProPresenter**, choose English or an installed translated language, copy the address, and follow the six short Prop instructions. Enabling the Props layer in a Look and actually showing the Prop are separate actions. Start captions and rehearse with the real audio feed before the service; if ProPresenter's Web object is unreliable, use the documented OBS composite fallback.

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
- Watch the microphone level meter to confirm audio is coming in. If the selected input opens but supplies exact digital silence for three seconds, Church Cap shows a non-blocking warning with macOS, Windows, or Linux guidance. The warning clears when real samples arrive.
- If an audio driver leaves the input falsely marked open but stops sending audio callbacks, Church Cap automatically reopens only the input stream after three seconds. The loaded speech model and CUDA session stay in memory, and stale pre-pause audio is discarded. A recovery notice appears; if Windows cannot reopen the selected input immediately, Church Cap keeps retrying with bounded delays while you check the sound desk connection and Windows microphone access.
- Use the privacy controls to choose whether transcript history is saved and how long to keep it. A fresh app start begins with an empty visible session transcript; older saved transcript cache is pruned on startup using the retention window saved with that cache. **Open transcript folder** reveals the per-user local cache folder on the Church Cap computer. **Export TXT/VTT/SRT/JSON** downloads the current-session transcript only and asks the operator to confirm the privacy warning first. Clearing the transcript deletes the retained local transcript cache.

## Service Leader Controls

Smaller churches can pair a trusted phone or tablet without exposing the full operator dashboard:

1. On the Church Cap computer, use **Connect a service leader device** on the login page, or sign in and open **Service Leader** in the operator menu.
2. Generate the one-use QR code.
3. Scan it with the trusted device.

The simple page can start/stop captions, blank/resume for sensitive moments, change the audio input while captions are stopped, show microphone and caption-health status, share audience QR codes to a phone, and share the audience link through the device's normal share menu. On supported Apple devices that menu can include AirDrop; on Android it can include Quick Share, messages, WhatsApp and other installed apps. If local HTTP prevents the system share menu from opening, Copy link, Text message and Email remain available. Recipients still need access to the church network. The page can also export the current-session transcript, share redacted support logs after a warning, and enable translated captions in Automatic or Manual language mode. Language search matches native names, English names, and language codes. Its caption preview uses the same live feed as audience phones, but the page explains that a delayed control-device preview is not the main performance measure. It cannot access passwords, updates, performance settings, account/privacy settings, or translation installation.

The QR expires after 90 seconds and works once. The paired session lasts at most four hours and expires after two hours without activity. A warning offers to refresh the idle timer before it expires. The **Service Leader** operator section shows connected-device status and can replace or cancel an unused QR, open the restricted route, or disconnect all paired devices.

For HTTP, use a private staff/AV Wi-Fi network rather than open or congregation guest Wi-Fi. HTTPS is preferred for a managed church phone or tablet.

## Translation

Phone UI language selection is local and lightweight. It uses bundled interface labels and falls back to English for labels that have not been translated yet.

Translated captions stay off until the operator enables them. The **Languages** page lets the operator choose Off, Recommended package / CTranslate2 INT8 SMaLL-100, Base package / Argos, Compatibility package / PyTorch SMaLL-100, or Auto / Recommended + Base + Compatibility mode, install language resources, and set how many translated languages can be active at once. Visitor languages are automatic by default; Church Cap prioritises the most-requested languages up to the active limit. The default active limit is 2 for fresh installs. Keep CPU-only systems at 1-2 active translated languages for live services, and raise the limit only after benchmarking stronger hardware.

On Church Cap Appliance CPU boxes, the **Languages** page remains available but opens with a CPU warning and cannot exceed three active translated languages. On Church Cap Appliance GPU boxes, translated captions are available only when the box is installed with the GPU appliance profile and CUDA is ready. Normal desktop installs keep the full Languages page visible without the appliance cap.

Translation is experimental and may be inaccurate. Start with the default active translated language limit, then keep it low if the computer struggles or captions begin to lag. Use a qualified human interpreter where accuracy matters.

### Optional Translated Audio

Church Cap can speak finalized translated captions to a visitor who selects **Listen**, without translating the text again. Stop captions, then use **Operator → Languages → Spoken Translated Audio** to choose the required packs, review their estimated size, and select **Install selected languages**. Installation, readiness and the visitor on/off control are kept together on that card. Normal setup and the source repository contain no voice weights. English never offers translated audio; Traditional Chinese currently uses Mandarin speech, not Cantonese.

Run the optional installer only after normal setup, then follow the manifest, licence and live-test guidance in [Local Translated Audio](../translated-audio.md) and [Optional Spoken-Language Model Notices](../legal/SPOKEN_LANGUAGE_MODELS.md). Keep the feature off for a live service until a native listener has checked the exact voice and the target computer has passed the caption-latency, sensitive-mode, headphone and backlog tests.

While text-translation or spoken-language resources are installing, keep the Operator page open to see the overall percentage and current phase. Spoken-language installs also show one circle for each selected voice package. Download byte percentages are measured directly where the package size is known; dependency installation and AI model conversion use labelled stage estimates and may remain at one percentage for several minutes.

### Optional Service Context (before the service)

If a sermon contains unusual names, places, organisations or difficult theological terms, open **Operator → Dashboard → Service Context** while captions are stopped. Paste the notes or choose a UTF-8 `.txt`/`.md` file (maximum 512 KiB), then select **Analyse notes locally**. Suggestions do not change Whisper in the safe default mode. After a short rehearsal, add an explicit “heard as → replace with” correction only for a consistent mistake, then select **Use for this service**.

This step is optional. Church Cap discards the original notes after local analysis and keeps only the reviewed candidates in memory. The notes are not a script or teleprompter and cannot create captions without matching microphone audio. Approved context locks when captions start, becomes inactive when captions stop, and is not reused unless an operator explicitly re-arms it. Inactive candidates clear automatically after four hours or immediately when **Clear** is selected.

Service Context is marked **Beta** as well as **Optional**. Direct **Experimental recognition assistance** is off by default. Enable it only for a particularly difficult proper name, select no more than two terms, and rehearse with the intended speech model, computer and audio route. This option supplies terms to every Whisper pass and may increase processing load, caption latency, false insertions or unstable wording. Compare it with the option switched off and do not make the first test during a production service.

Bible-reference formatting does not require sermon notes. During every English caption run, explicit wording such as “first Corinthians chapter thirteen verse four” is formatted locally as `1 Corinthians 13:4`. Full passages are not placed in Whisper's prompt and Church Cap does not retrieve or insert verse text.

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

Use the direct-IP QR code on the operator page. On Linux, rerun `bash setup-linux.sh` and accept the recommended audience firewall rule if it was previously skipped. Also check that the phone is on the same network and that guest Wi-Fi/client isolation allows it to reach the caption computer. A working host firewall rule cannot override isolation enforced by the router or wireless access point.

If Safari reports that the server stopped responding after the page has been open or translated audio has been used, first reopen the current QR link. Church Cap refreshes stale viewer assets and recreates caption/audio connections when Safari restores a suspended page. If Safari alone still fails while another phone can reach Church Cap, try the direct-IP QR; success there points to cached local-hostname/mDNS resolution rather than the Church Cap server.

### No audio devices appear

- Check the USB audio interface is connected.
- On macOS, the built-in MacBook microphone may be unavailable with the lid closed in clamshell mode. Open the lid or select an iPhone, USB, or other external input. Also allow the launching app (usually Terminal) in **System Settings > Privacy & Security > Microphone**, then fully restart Church Cap.
- On Windows, enable microphone and desktop-app access in **Settings > Privacy & security > Microphone**.
- On Linux, check the selected PipeWire, PulseAudio, or ALSA capture source and mute state.
- Run setup again if PortAudio was not installed.

If the device is listed but the microphone meter remains at 0%, follow the same checks. Church Cap may be able to open a device even when the operating system or mixer supplies digital silence.

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

The operator page includes **Open feedback page** under **Diagnostics → Support**. Use it for feature ideas, issues, setup confusion, accessibility feedback, and caption or translation notes. Please include the Church Cap version number and any useful computer, operating system, audio interface, or error details. For recorded-sermon comparisons, use **Diagnostics → Support → Download anonymised service report**; this allow-listed file contains no speech, captions, rejected wording, translations, audio metadata, recognition timestamps, glossary content, paths, network identifiers, operator data, or logs. Church Cap retains the latest five completed summaries across restarts and reports timestamped cue-engine processing latency, cue/queue health, and text-free end-of-speech guard counts. Select **Reset test measurements** before a new comparison set.

Open **Diagnostics → Application Storage** to see the application, Church Cap data, Hugging Face model downloads, OpenAI Whisper downloads, optional spoken-audio models, and current log use. Storage is calculated only when this page is opened or refreshed. **Review unused downloads** opens a Church Cap-themed confirmation menu; nothing is removed automatically. The active model, settings, transcripts, measurements, and current logs are protected. An inactive model offered for cleanup must download again if you select it later. Church Cap limits each of its diagnostic logs to 5 MB plus two archived copies.

On Windows, translation installer output is stored in `%APPDATA%\Church Cap\logs\translation-install.log`, not in the downloaded Church Cap folder. Enter `%APPDATA%\Church Cap\logs` in the Run dialog or File Explorer to open it. The authenticated diagnostics download also includes the recent installer output with local paths redacted.

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

You can also use **Updates** on the operator page. Source installations check their platform release channel, tell you if the current version is up to date, ask before updating, check the downloaded files, replace the application files in place, and restart the app. The native Mac/Windows applications use their separately signed desktop update channels after those channels are published.

The updater preserves `.env`, `.venv`, `data/`, `logs/`, `certs/`, `config/glossary.csv`, and `config/profanity_filter.txt`. The displayed app version is code-owned so a stale `APP_VERSION` in `.env` cannot keep Windows showing an older release after an update.

The source updater checks its downloaded release archive, required release files, release version, staged Python syntax, and SHA-256 file checksums before and after copying. Linux selects the curated `Church-Cap-Linux-CLI.tar.gz` asset and verifies its separately published SHA-256 before extraction. If the internet drops during download or dependency installation, the current app is left alone. During replacement, Church Cap keeps a rollback backup in `data/update-backups/` and restores it automatically if the copy or checksum check fails.

## Returning to first-time setup

On the installed Mac or Windows application, open **Settings → Updates and recovery → Factory reset Church Cap**. Read the removal list and type `RESET`. Church Cap stops its server before removing local credentials, configuration, transcripts, measurements, logs, in-app exports and downloaded caption/voice models. It then restarts and opens the complete first-time setup. The application itself remains installed.

On Linux, stop the running Church Cap process first, then run `./factory-reset-linux.sh` from the Church Cap folder and type `RESET`. Start Church Cap normally afterward. Use the separate password-reset option or `scripts/reset-operator-password.sh` when you only need a new password and want to keep settings and downloads.
