# Start Here: Church Cap

Church Cap is a local live-caption app for churches. It runs on the caption computer, listens to the church sound desk or USB audio interface, and gives visitors a QR code so they can read captions on their phones.

## First-Time Setup On Mac

Open Terminal, then go to this folder:

```bash
cd "$HOME/Documents/church_cap"
```

Run setup. Use `bash` for this first command because the setup script may not be executable yet. The setup script repairs permissions for the other Church Cap scripts automatically.

```bash
bash setup-macos.sh
```

Setup may take a while. It installs the local Python environment and audio dependencies. It can also install common Base Argos translation packs, all Base packs, optional Core / SMaLL-100, or skip translation resources until later.

## First-Time Setup On Windows

Open PowerShell, then go to this folder. This example assumes the folder has been moved into Documents.

```powershell
cd "$HOME\Documents\church_cap"
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

## Normal Sunday Start

After the first setup, start Church Cap on Mac with:

```bash
./start-macos.sh
```

On Windows:

```powershell
.\start-windows.cmd
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

- Open **System > Diagnostics** on the operator page and use **Download diagnostics** only if you are comfortable sharing the generated support file.
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

You can also use **Updates** on the operator page. Church Cap checks the latest GitHub release tag first, tells you if it is already up to date, asks before updating, checks the downloaded files, replaces this folder in place, and restarts the app.

If the internet drops or the download is damaged, the current app is left alone. During replacement, Church Cap keeps a rollback backup in `data/update-backups/` and restores it automatically if the copy or checksum check fails.
