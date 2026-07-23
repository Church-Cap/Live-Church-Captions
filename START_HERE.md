# Start Here: Church Cap

Church Cap is a local live-caption app for churches. It runs on the caption computer, listens to the church sound desk or USB audio interface, and gives visitors a QR code so they can read captions on their phones.

## First-Time Setup On Mac

Open Terminal, then go to the downloaded and extracted Church Cap folder. This example assumes the folder has been moved into Documents.

```bash
cd "$HOME/Documents/Live-Church-Captions-0.7.3"
```

Run setup. Use `bash` for this first command because the setup script may not be executable yet. The setup script repairs permissions for the other Church Cap scripts automatically.

```bash
bash setup-macos.sh
```

Setup may take a while. It installs the local Python environment and audio dependencies. It can also install common Base package / Argos packs, all Base packs, optional Recommended package / CTranslate2 INT8, optional Compatibility package / PyTorch SMaLL-100, or skip translation resources until later.

## First-Time Setup On Windows

Open PowerShell, then go to the downloaded and extracted Church Cap folder. This example assumes the folder has been moved into Documents.

```powershell
cd "$HOME\Documents\Live-Church-Captions-0.7.3"
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
cd "$HOME/Documents/Live-Church-Captions-0.7.3"
bash setup-linux.sh
```

The script detects common Linux package managers and installs the required Python, build, PortAudio, and download tools. It supports AlmaLinux/Rocky/RHEL/Fedora (`dnf`/`yum`), Ubuntu/Debian (`apt`), openSUSE (`zypper`), Arch (`pacman`), and Alpine (`apk`).

The installer keeps Python packages inside `.venv` and does not enable extra repositories or install NVIDIA drivers. On AlmaLinux, if a package is unavailable, check that AppStream and CRB are enabled according to your system policy.

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

The audience caption page normally uses:

```text
http://church-cap.local:8080/
```

If that does not work on a phone, use the Android/IP fallback QR code shown on the operator page.

## Operator Checklist

1. Create or enter the operator password.
2. Select the church audio interface or mixer input.
3. Click **Save input**.
4. Use **Performance** if captions are delayed or the computer needs a faster/lower-accuracy mode. Adjustments save automatically, then take effect after captions are stopped and started.
5. Click **Start captions**.
6. Show the audience QR code.
7. Use **Blank / pause** for private or sensitive moments.

The operator and Service Leader control buttons show a subtle active glow for the current state, and the pages show short status messages while captions start, stop, blank, resume, or send a test caption.

## Optional Service Leader Device

On the Church Cap computer, use either route:

1. Select **Connect a service leader device** on the operator login page and enter the operator password; or sign in and open **Service Leader** in the operator menu.
2. Generate the one-use QR code.
3. Let the service leader scan it.

Their phone/tablet receives a simpler page for start, stop, blank, resume, audio input, caption health, audience QR sharing, and Automatic/Manual translated-language control. The current action has a subtle glow and status messages explain when captions are starting, stopping, blanked, or resuming. It does not receive full operator access. Use a trusted staff/AV Wi-Fi network, especially when running over HTTP. The page includes dismissible local-HTTP and caption-preview notes so the service leader understands the network/security trade-off and knows that a delayed control-page preview does not necessarily mean the audience feed is delayed.

The service leader can share the audience QR code by generating a temporary phone-download QR, then save it for ProPresenter, EasyWorship, FreeShow, slides, or printed notices without opening the full operator page. On an appliance, the Operator Audience & OBS page uses the same handoff for its QR buttons.

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
- Check macOS microphone permissions in System Settings.
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
