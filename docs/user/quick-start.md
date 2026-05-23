# Church Cap Quick Start Guide

Version: 0.2.0 public preview

This guide is for the person setting up Church Cap for a church service.

## What Church Cap Does

Church Cap listens to one audio input from the church sound desk or USB audio interface. It creates live captions locally on the Mac and shares them over the church Wi-Fi.

Visitors do not install an app. They scan a QR code and read captions in their browser.

## What You Need

- An Apple Silicon Mac, or a Windows 10/11 computer. On Windows, setup can offer to install Python 3.12 if Windows Package Manager is available.
- Church Cap downloaded or copied to the Mac.
- Internet access for first setup.
- A USB audio interface or mixer input from the sound desk.
- The Mac and audience phones on a network where phones can reach the caption Mac.

## First-Time Setup On Mac

1. Open Terminal.
2. Go to the Church Cap folder. This example assumes the folder has been moved into Documents.

```bash
cd "$HOME/Documents/church_cap_v0.2.0"
```

3. Run setup. Use `bash` for this first command because the setup script may not be executable yet. The setup script repairs permissions for the other Church Cap scripts automatically.

```bash
bash setup-macos.sh
```

4. Wait for setup to finish, then continue to **Start Church Cap** below.

The setup script installs the local Python environment, audio dependencies, and Argos translation support/models. It only installs Python packages inside the Church Cap folder's `.venv`.

If setup asks whether to set the Mac hostname to `church-cap.local`, choose yes if this Mac will normally run captions.

## First-Time Setup On Windows

1. Open PowerShell.
2. Go to the Church Cap folder. This example assumes the folder has been moved into Documents.

```powershell
cd "$HOME\Documents\church_cap_v0.2.0"
```

3. Run setup.

```powershell
.\setup-windows.cmd
```

4. Wait for setup to finish, then continue to **Start Church Cap** below.

The setup script installs the local Python environment, app dependencies, Argos translation support/models, and checks CUDA/GPU support. If Python is missing and Windows Package Manager is available, setup can offer to install Python 3.12 first. If an NVIDIA GPU is visible but CUDA runtime files are missing, setup can offer to install local CUDA 12 runtime packages into Church Cap's `.venv`. If CUDA is not ready, Church Cap falls back to CPU.

You can also run the optional GPU runtime installer later:

```powershell
.\install-cuda-runtime-windows.cmd
```

If Windows says `UnauthorizedAccess`, scripts are disabled, or the file came from another computer, use `setup-windows.cmd`. If it is still blocked, right-click the downloaded zip or Church Cap folder, choose **Properties**, tick **Unblock** if shown, then try again.

## Start Church Cap

For normal use after setup:

```bash
./start-macos.sh
```

On Windows:

```powershell
.\start-windows.cmd
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

## Share Captions With Visitors

In the operator page, open **Audience & OBS**.

Use the main QR code first. If an Android phone or guest Wi-Fi cannot open the `.local` address, use the Android/IP fallback QR code.

## Visitor Caption View

The phone caption page shows live captions as a bottom-to-top reading stream. Captions start at the left edge in English, wrap naturally, and move upward as new captions arrive. A server-backed session transcript below the controls shows timestamped captions from the current app session with the newest entry at the top when history is enabled, and visitors can scroll back through earlier captions. Visitors can use **Hide transcript** or **Show transcript** to choose whether that scrollback panel appears on their own device.

In landscape orientation on phones and tablets, the viewer uses a compact side-by-side layout: live captions take about 75% of the width and the transcript takes the remaining space when enabled. The live caption and transcript panels stay within the visible screen; longer transcript history scrolls inside the transcript panel. If a visitor hides the transcript, the live caption view expands to use the full width.

Visitors automatically get the light or dark theme from their device settings. They can still use the theme button to set a local override, and can change text size, comfort/compact spacing, pause their local view, or clear their local screen without affecting anyone else.

## During A Service

- Use **Start captions** when ready.
- Use **Stop** when captions should stop.
- Use **Blank / pause** before private prayer, pastoral details, testimony, safeguarding, or anything sensitive. While blanked, captions are not shown, retained in the session transcript, or included in transcript exports; Church Cap also flushes the live transcription buffer and drops a short buffered-audio window when captions resume.
- Use **Resume** when public captions should continue.
- Watch the microphone level meter to confirm audio is coming in.
- Use the privacy controls to choose whether transcript history is saved and how long to keep it. A fresh app start begins with an empty visible session transcript; older saved transcript cache is pruned on startup using the retention window saved with that cache. **Open transcript folder** reveals the per-user local cache folder on the Church Cap computer. **Export TXT/VTT/SRT/JSON** downloads the current-session transcript only and asks the operator to confirm the privacy warning first. Clearing the transcript deletes the retained local transcript cache.

## Translation

Argos Translate support is installed during setup, but translated captions stay off until the operator enables them.

Translation is experimental and may be inaccurate. Keep the active translated language limit low at first. Use a qualified human interpreter where accuracy matters.

## Passwords

The operator password is stored outside the Church Cap folder in:

```text
~/Library/Application Support/Church Cap/data/
```

On Windows, it is stored in:

```text
%APPDATA%\Church Cap\data\
```

It should survive Terminal restarts, Mac restarts, and app folder updates.

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

Use the Android/IP fallback QR code on the operator page. Also check that the phone is on the same network and that guest Wi-Fi is allowed to reach the caption Mac.

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

The operator page includes a **Feedback** link. Use it for feature ideas, issues, setup confusion, accessibility feedback, and caption or translation notes. Please include the Church Cap version number and any useful computer, operating system, audio interface, or error details.

## Updating Church Cap

Mac:

```bash
./update-macos.sh
```

Windows:

```powershell
.\update-windows.cmd
```

The updater downloads the latest GitHub source into a new folder and keeps the current folder untouched. It copies `.env`, `config/glossary.csv`, and `config/profanity_filter.txt` into the update folder when present.
