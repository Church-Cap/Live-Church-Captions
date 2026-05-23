# Start Here: Church Cap

Church Cap is a local live-caption app for churches. It runs on the caption Mac, listens to the church sound desk or USB audio interface, and gives visitors a QR code so they can read captions on their phones.

## First-Time Setup On Mac

Open Terminal, then go to this folder:

```bash
cd "$HOME/Documents/church_cap_v0.2.0"
```

Run setup. Use `bash` for this first command because the setup script may not be executable yet. The setup script repairs permissions for the other Church Cap scripts automatically.

```bash
bash setup-macos.sh
```

Setup may take a while. It installs the local Python environment, audio dependencies, and Argos translation support/models.

## First-Time Setup On Windows

Open PowerShell, then go to this folder. This example assumes the folder has been moved into Documents.

```powershell
cd "$HOME\Documents\church_cap_v0.2.0"
```

Run setup:

```powershell
.\setup-windows.cmd
```

If Python is missing and Windows Package Manager is available, setup can offer to install Python 3.12. Setup also checks for CUDA/GPU support. If an NVIDIA GPU is visible but CUDA runtime files are missing, setup can offer to install local CUDA 12 runtime packages into Church Cap's `.venv`. If CUDA is not ready, Church Cap falls back to CPU.

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
4. Click **Start captions**.
5. Show the audience QR code.
6. Use **Blank / pause** for private or sensitive moments.

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

The updater downloads the latest GitHub source into a new folder and keeps the current folder untouched.
