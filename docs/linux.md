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
3. Installs build tools, PortAudio headers, libsndfile, curl, `tar`, CA certificates, and the distribution's normal Python support packages.
4. Selects a compatible Python 3.10-3.13 interpreter, preferring Python 3.12. When only an incompatible system Python is available, setup downloads pinned `uv` 0.12.3 for the detected x86_64/ARM64 and glibc/musl platform, verifies its published SHA-256, and installs managed Python 3.12 beneath `.tools`. The system Python is left unchanged.
5. Requires at least 8 GiB of filesystem headroom, creates `.venv` from that interpreter, disables pip's persistent download cache, and installs Church Cap there. If a managed account quota is smaller than the filesystem's free-space report, setup prints quota diagnostics after a failure.
6. Detects active `firewalld` or UFW and offers the recommended audience-viewer rule after explaining its scope.
7. If an NVIDIA driver is detected, verifies the CUDA 12 cuBLAS and cuDNN 9 libraries and offers a project-local runtime install when needed.

Distro package mappings live only in `scripts/linux-system-packages.sh`. Keep new distro work in that file rather than adding branches throughout the application.

Ubuntu 26.04's Python 3.14 is deliberately not used because every pinned Church Cap ML wheel is not yet available for it. No separate Python installation step is required: the verified managed Python 3.12 path handles this automatically and stays local to Church Cap. The updater preserves `.tools` along with `.venv` and user data.

If setup reports `Disk quota exceeded`, free space owned by the current Linux account or ask its administrator to raise the quota. A failed attempt may leave a partial `.venv`. Rerun `bash setup-linux.sh`; when that environment is partial or incompatible, setup offers to remove only the Church Cap `.venv` and recreate it after explicit confirmation.

## AlmaLinux

Use a maintained AlmaLinux release with the standard BaseOS/AppStream repositories. Some development packages may require CRB according to the system's repository policy.

Church Cap does not enable repositories automatically. If `dnf` cannot find Python 3.11+ or `portaudio-devel`, enable the appropriate official repository and rerun setup.

AlmaLinux Desktop normally uses `firewalld`. Setup detects the zone associated with the default network route and recommends allowing the configured viewer port, normally TCP 8080, in both the current and permanent firewalld configurations. It asks first and proceeds only for an explicit `y` or `yes`. The rule does not open operator port 9090.

## Audience QR, firewall and hostname

On Linux, an operating-system computer name does not automatically create a working `<name>.local` address. Church Cap keeps the hostname QR visible, but labels it as requiring setup unless `CAPTION_LOCAL_HOSTNAME` or `PUBLIC_BASE_URL` explicitly configures a hostname. The LAN IP QR is the recommended target until DNS or mDNS is working.

If `firewalld` or UFW is active, setup recommends opening only the configured viewer TCP port. Rerun `bash setup-linux.sh` to receive that prompt. A host-firewall rule cannot override router isolation: guest Wi-Fi must also be allowed to reach the caption computer's LAN IP and viewer port. Do not expose the viewer directly to the public internet.

## Audio permissions

Run Church Cap as a normal user that can access the selected ALSA/PulseAudio/PipeWire input. Do not run the web application as root. On a dedicated server without a desktop session, verify the USB interface is visible to the service user before starting captions.

## NVIDIA CUDA

The Linux NVIDIA driver remains system-managed; Church Cap does not install or modify it and does not enable NVIDIA repositories. `nvidia-smi` proves that the driver can see the GPU, but its displayed CUDA version does not prove that the user-space libraries required by CTranslate2 are installed.

Current Faster Whisper/CTranslate2 needs CUDA 12 cuBLAS (`libcublas.so.12`) and cuDNN 9 (`libcudnn.so.9`). Setup tests whether those libraries can actually be loaded. If they are missing, the Linux setup flow explains the download and asks whether to install `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` inside `.venv`. Installation proceeds only after an explicit `y` or `yes`; pressing Enter skips it. `start-linux.sh` adds the wheel library directories to `LD_LIBRARY_PATH` before Python starts.

For an existing installation:

```bash
./install-cuda-runtime-linux.sh
./start-linux.sh
```

Always use `start-linux.sh` when relying on the project-local runtime. If CUDA is incomplete, automatic mode selects CPU/int8 and diagnostics name the missing libraries rather than reporting a false-ready CUDA state.

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
