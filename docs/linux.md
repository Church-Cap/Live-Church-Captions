# Linux support

Church Cap supports native Linux audio/caption operation through the same Python application used on macOS and Windows.

## Recommended distributions

The primary Linux setup targets are:

- AlmaLinux, Rocky Linux, RHEL-family systems, and Fedora through `dnf`/`yum`
- Ubuntu, Debian, and derivatives through `apt`

The setup helper also recognises:

- openSUSE through `zypper`
- Arch Linux and derivatives through `pacman`
- Alpine Linux through `apk`

Python and machine-learning wheel availability can vary on rolling, very old, or musl-based distributions. AlmaLinux and Ubuntu are the preferred release-test platforms.

## Setup

```bash
bash setup-linux.sh
./start-linux.sh
```

`setup-linux.sh`:

1. Reads `/etc/os-release` for a friendly distro name.
2. Detects the installed package manager.
3. Installs Python, venv/pip support, build tools, PortAudio headers, libsndfile, curl, and unzip.
4. Selects Python 3.12, 3.11, 3.10, or a supported `python3`, in that order.
5. Creates `.venv` and installs Church Cap there.

Distro package mappings live only in `scripts/linux-system-packages.sh`. Keep new distro work in that file rather than adding branches throughout the application.

## AlmaLinux

Use a maintained AlmaLinux release with the standard BaseOS/AppStream repositories. Some development packages may require CRB according to the system's repository policy.

Church Cap does not enable repositories automatically. If `dnf` cannot find Python 3.11+ or `portaudio-devel`, enable the appropriate official repository and rerun setup.

## Audio permissions

Run Church Cap as a normal user that can access the selected ALSA/PulseAudio/PipeWire input. Do not run the web application as root. On a dedicated server without a desktop session, verify the USB interface is visible to the service user before starting captions.

## NVIDIA CUDA

Linux NVIDIA drivers and CUDA are system-managed. Church Cap does not install or modify them. If CTranslate2 can use the GPU, Auto mode selects CUDA; otherwise Church Cap falls back to CPU/int8.

## Runtime data

Linux uses:

```text
${XDG_DATA_HOME:-~/.local/share}/church-cap/
```

Set `CHURCH_CAP_DATA_DIR` to override this location.

## Updating

```bash
./update-linux.sh
```

The Linux updater uses the shared Unix update implementation, preserves local configuration/data, verifies release files and checksums, and restarts with `start-linux.sh`.
