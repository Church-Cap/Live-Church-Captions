# Start Here: Church Cap

Church Cap is a local live-caption app for churches. It runs on the caption computer, listens to the church sound desk or USB audio interface, and gives visitors a QR code so they can read captions on their phones.

Developers continuing the native desktop work should begin with [docs/project/CROSS_PLATFORM_ARCHITECTURE.md](docs/project/CROSS_PLATFORM_ARCHITECTURE.md), the [v0.8.0 implementation status](docs/project/V0.8.0_IMPLEMENTATION.md), and the [desktop update release runbook](docs/project/DESKTOP_UPDATE_RELEASE_RUNBOOK.md). The browser application has one shared source in `app/`; macOS, Windows, and Linux must not maintain separate copies of its pages or behaviour.

## Recommended Downloads

- [Mac — Apple Silicon](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.8.0): install the notarized DMG in Applications.
- [Windows — 64-bit](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.8.0): run the setup executable. The current Windows release is unsigned, so verify its published SHA-256 before accepting any SmartScreen warning.
- [Linux — 64-bit CLI](https://github.com/Church-Cap/Live-Church-Captions/releases/tag/v0.8.0): verify and extract `Church-Cap-Linux-CLI.tar.gz`, then run `bash setup-linux.sh`.

Mac, Windows, and Linux downloads are published as assets of the same versioned release.

The source-folder instructions below remain available for contributors and advanced installations. Mac and Windows users should normally use the native downloads above.

## First-Time Setup On Mac

Open Terminal, then go to the downloaded and extracted Church Cap folder. This example assumes the folder has been moved into Documents.

```bash
cd "$HOME/Documents/Live-Church-Captions-0.8.0"
```

Run setup. Use `bash` for this first command because the setup script may not be executable yet. The setup script repairs permissions for the other Church Cap scripts automatically.

```bash
bash setup-macos.sh
```

Setup may take a while. It installs the local Python environment and audio dependencies. It can also install common Base package / Argos packs, all Base packs, optional Recommended package / CTranslate2 INT8, optional Compatibility package / PyTorch SMaLL-100, or skip translation resources until later.

## First-Time Setup On Windows

Open PowerShell, then go to the downloaded and extracted Church Cap folder. This example assumes the folder has been moved into Documents.

```powershell
cd "$HOME\Documents\Live-Church-Captions-0.8.0"
```

Run setup:

```powershell
.\setup-windows.cmd
```

If Python is missing and Windows Package Manager is available, setup can offer to install Python 3.12. Setup also checks for CUDA/GPU support. If an NVIDIA GPU is visible but CUDA is not ready for faster-whisper, setup can offer to install or force reinstall local CUDA 12 runtime packages into Church Cap's `.venv`. The force reinstall bypasses pip's cache and downloads fresh CUDA runtime wheels. If CUDA is not ready, Church Cap falls back to CPU.

You can also run the optional GPU runtime installer later:

```powershell
.\install-cuda-runtime-windows.cmd
```

If Windows says `UnauthorizedAccess`, scripts are disabled, or the file came from another computer, use `setup-windows.cmd`. If it is still blocked, right-click the downloaded zip or Church Cap folder, choose **Properties**, tick **Unblock** if shown, then try again.

## First-Time Setup On Linux

Open a terminal, then go to the downloaded and extracted Church Cap folder. This example assumes the folder has been moved into Documents.

```bash
cd "$HOME/Documents/Live-Church-Captions-0.8.0"
bash setup-linux.sh
```

The script detects common Linux package managers and installs the required build, PortAudio, and download tools. It supports AlmaLinux/Rocky/RHEL/Fedora (`dnf`/`yum`), Ubuntu/Debian (`apt`), openSUSE (`zypper`), Arch (`pacman`), and Alpine (`apk`).

The installer keeps Python packages inside `.venv` and does not enable extra repositories or install NVIDIA drivers. If the distribution only provides Python 3.14 or newer, setup automatically downloads a pinned, SHA-256-verified bootstrap and installs Python 3.12 under the Church Cap folder's `.tools` directory without changing the system Python. On AlmaLinux and other systems using active `firewalld` or UFW, setup recommends allowing the public audience port and asks before making the change. Only TCP port 8080 (or your configured viewer port) is opened; operator port 9090 is not. Pressing Enter skips the firewall change. If a working NVIDIA driver is already present, setup also checks whether CTranslate2 can load its required CUDA 12 cuBLAS and cuDNN 9 libraries and offers to install missing runtime libraries inside `.venv`. The large optional download starts only if you explicitly answer `y` or `yes`; pressing Enter skips it. On AlmaLinux, if a system package is unavailable, check that AppStream and CRB are enabled according to your system policy.

Seeing a CUDA version in `nvidia-smi` is not enough by itself: that confirms the driver capability, not that `libcublas.so.12` and `libcudnn.so.9` are installed and visible to Church Cap. For an existing Linux install, repair the local runtime with:

```bash
./install-cuda-runtime-linux.sh
./start-linux.sh
```

## Normal Sunday Start

After the first setup, start Church Cap on Mac with:

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

Please wait while it starts. The operator page should open automatically:

```text
http://localhost:9090/operator
```

On first Windows setup, Church Cap may open the password setup page first:

```text
http://localhost:9090/setup
```

The audience caption page can use a configured local hostname:

```text
http://church-cap.local:8080/
```

On Linux, both QR codes remain available. Until local DNS or mDNS is configured, the hostname QR is labelled as requiring setup and the direct-IP QR is the recommended choice. If the IP QR does not work, allow the viewer port through the host firewall and check whether guest Wi-Fi isolates phones from wired/LAN devices.

## Operator Checklist

1. Create or enter the operator password.
2. Select the church audio interface or mixer input.
3. Click **Save input**.
4. Use **Performance** if captions are delayed or the computer needs a faster/lower-accuracy mode. Adjustments save automatically, then take effect after captions are stopped and started.
5. Click **Start captions**.
6. Show the audience QR code.
7. Use **Blank / pause** for private or sensitive moments.

The operator and Service Leader control buttons show a subtle active glow for the current state, and the pages show short status messages while captions start, stop, blank, resume, or send a test caption.

## Changing the spoken language

On the operator's **Live service** page, stop captions, choose **Spoken language**
under **Source captions**, then select **Save language**. Start captions again.
The choice is saved across restarts. English remains the default; Swedish and
nineteen other source languages are available. This is a fixed spoken-language
selection, not automatic language detection.

For non-English speech, Church Cap automatically uses the multilingual version
of the selected model size (for example, `base` instead of `base.en`). The first
start may need internet access to download that model. Changing source language
clears the current caption feed and reconnects viewers, room displays, and OBS.
Export any transcript you need before switching.

Translation still requires local models that support the selected source and
target languages. The English-to-Tigrinya model only supports English input.
English-specific glossary, Bible-reference, service-context corrections,
profanity filtering, and recognition prompts are not applied to other languages.

![Swedish source-language selection](docs/images/source-language-selector.png)

## Optional Service Leader Device

On the Church Cap computer, use either route:

1. Select **Connect a service leader device** on the operator login page and enter the operator password; or sign in and open **Service Leader** in the operator menu.
2. Generate the one-use QR code.
3. Let the service leader scan it.

Their phone/tablet receives a simpler page for start, stop, blank, resume, audio input, caption health, audience QR sharing, and Automatic/Manual translated-language control. The current action has a subtle glow and status messages explain when captions are starting, stopping, blanked, or resuming. It does not receive full operator access. Use a trusted staff/AV Wi-Fi network, especially when running over HTTP. The page includes dismissible local-HTTP and caption-preview notes so the service leader understands the network/security trade-off and knows that a delayed control-page preview does not necessarily mean the audience feed is delayed.

The service leader can share the audience QR code by generating a temporary phone-download QR, then save it for ProPresenter, EasyWorship, FreeShow, slides, or printed notices without opening the full operator page. On an appliance, **Operator → Congregation → Join Live Captions** uses the same handoff for its QR buttons.

## Optional Translated Audio Pilot

A visitor can select **Listen** after the church installs a reviewed voice pack. In **Operator → Languages → Spoken Translated Audio**, stop captions, choose only the language packs the church needs, review the estimated size, and select **Install selected languages**. Normal setup downloads no voice weights. The same section reports readiness and lets the operator make spoken audio available to visitors. English never shows the control, and ordinary text captions continue if speech generation is unavailable. Traditional Chinese currently uses Mandarin speech, not Cantonese. See [docs/translated-audio.md](docs/translated-audio.md) and the [voice-model notices](docs/legal/SPOKEN_LANGUAGE_MODELS.md) before live use.

## If Something Goes Wrong

Wrong page or port:

- Operator page: `http://localhost:9090/operator`
- Audience page: `http://church-cap.local:8080/`

Locked out:

```bash
./reset-operator-password.sh
```

On Windows:

```powershell
.\reset-operator-password.cmd
```

Then restart Church Cap and create a new operator password.

No microphone/audio input:

- Check the USB audio interface is connected.
- Watch the Operator microphone meter. If Church Cap opens the input but receives digital silence for three seconds, it shows a platform-specific warning without stopping captions.
- On macOS, the built-in MacBook microphone may be unavailable with the lid closed in clamshell mode. Open the lid or select an iPhone, USB, or other external input. Also allow the app used to start Church Cap (usually Terminal) in **System Settings > Privacy & Security > Microphone**, then fully restart Church Cap.
- On Windows, enable microphone access and desktop-app access in **Settings > Privacy & security > Microphone**.
- On Linux, check the selected PipeWire, PulseAudio, or ALSA capture source and confirm that it is not muted.
- Restart captions after changing the input.

Windows CUDA, performance, update, or setup problems:

- Open **System > Diagnostics** on the operator page and use **Download diagnostics** or, on an appliance, **Share diagnostics** only if you are comfortable sharing the generated support file.
- Review the file before attaching it to a GitHub issue or support email because system names, device names, error messages, and log details may still be sensitive. Do not post diagnostics publicly unless you are comfortable sharing the contents.

Stop Church Cap:

```text
Press Ctrl+C in the Terminal window running Church Cap.
```

For more detail, see [docs/user/quick-start.md](docs/user/quick-start.md).

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

If the internet drops or the download is damaged, the current app is left alone. During replacement, Church Cap keeps a rollback backup in `data/update-backups/` and restores it automatically if the copy or checksum check fails.
