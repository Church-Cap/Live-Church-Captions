# Third-Party Notices

Last reviewed: 2026-07-15

Church Cap is released under the MIT License. This file records the direct third-party packages, optional model/tooling notes, appliance-shell system package notes, and release hygiene reminders for v0.7.0.

The repository does not vendor Python packages, Whisper model weights, Argos model packages, Homebrew packages, operating-system packages, font files, browser packages, certificates, or a prebuilt `.venv`. Installers download dependencies into the user's local environment or ask the operating system package manager to install them. If you distribute a packaged app, appliance image, wheelhouse, Docker image, or prebuilt virtual environment, generate notices from that exact artifact.

## Direct Python Dependencies

These are the direct dependencies pinned in `requirements.txt` and `requirements-translation.txt`.

| Component | Version | Purpose | Licence / notice |
|---|---:|---|---|
| FastAPI | 0.139.2 | Web application/API framework | MIT |
| Uvicorn | 0.34.0 | ASGI web server | BSD |
| Jinja2 | 3.1.6 | HTML templating | BSD-3-Clause |
| qrcode | 8.0 | QR code generation | BSD |
| Pillow | resolved by `qrcode[pil]` | Image handling for QR codes | HPND-style Pillow licence; exact installed version should be recorded if bundling wheels or a packaged environment |
| python-multipart | 0.0.32 | Form parsing for FastAPI routes | Apache-2.0 |
| pydantic-settings | 2.7.1 | Environment/settings loading | MIT |
| NumPy | 2.2.1 | Numerical/audio processing support | BSD-3-Clause; binary wheels may include additional notices such as OpenBLAS/LAPACK/GCC runtime components |
| sounddevice | 0.5.1 | Audio input capture | MIT; uses the system PortAudio library |
| openai-whisper | 20250625 | Default local Whisper transcription backend | MIT |
| faster-whisper | 1.2.1 | Optional lower-latency Whisper transcription backend | MIT |
| requests | 2.33.0 | Optional installer/model-download HTTP requests | Apache-2.0 |
| standard-library `http.server`, `http.client`, `subprocess`, `json`, `hashlib`, `hmac`, `secrets` | Python bundled | Appliance shell/proxy, PIN hashing, and local system commands | Python Software Foundation License; no extra package installed |
| cryptography | >=42.0.0 | Local transcript cache encryption | Apache-2.0 or BSD-3-Clause |
| argostranslate | 1.9.6 | Optional local Base translation provider installed by setup or the operator language-resource installer | MIT or CC0, per Argos Translate project metadata |
| OpenCC | 1.4.1 | Deterministic Simplified and Hong Kong Traditional Chinese script/phrase conversion after local translation | Apache-2.0 |
| ctranslate2, transformers, sentencepiece, safetensors | installed only by optional Fast Core / Core translation setup | Optional SMaLL-100 conversion and translation runtime | MIT / Apache-2.0 / BSD-style / Apache-2.0, confirm exact resolved versions if distributing a packaged build |

## Important Transitive Dependencies

The exact transitive dependency set is resolved by `pip` for the user's platform and Python version. Important runtime dependencies include:

| Component | Used by | Notice |
|---|---|---|
| Starlette | FastAPI | ASGI/web framework dependency. |
| Pydantic / pydantic-core | FastAPI and pydantic-settings | Data validation/settings dependencies. |
| python-dotenv | pydantic-settings | `.env` loading support. |
| CTranslate2 | faster-whisper and optional Fast Core translation | Local inference runtime. On Windows, Church Cap can use CUDA through CTranslate2 for Faster Whisper when the installed runtime, NVIDIA drivers, and required CUDA runtime DLLs expose it. Fast Core converts SMaLL-100 into a local CTranslate2 INT8 model when the optional installer is run. Confirm model licences and converted model distribution terms before shipping prebuilt weights. |
| PyTorch | openai-whisper | Local model runtime dependency; binary wheels may include platform-specific notices and accelerator libraries. |
| tiktoken | openai-whisper | Tokenization dependency. |
| numba / llvmlite | openai-whisper | Audio preprocessing dependencies. |
| Hugging Face Hub | faster-whisper | Model download/cache helper. |
| tokenizers | faster-whisper | Text tokenization. |
| onnxruntime | faster-whisper | Runtime dependency. |
| PyAV | faster-whisper | Audio decoding dependency. |
| tqdm | faster-whisper | Progress display dependency. |
| sentencepiece, stanza, sacremoses, packaging | Argos Translate | Optional translation dependencies. |
| NVIDIA CUDA Python wheel packages | Optional Windows GPU acceleration | Optional local `.venv` packages such as `nvidia-cuda-runtime-cu12`, `nvidia-cublas-cu12`, and `nvidia-cudnn-cu12`; installed only if the Windows operator chooses GPU runtime setup. |
| PortAudio | sounddevice | System audio library installed through Homebrew on macOS or the detected Linux package manager. |

If you distribute a packaged app, wheels, a frozen environment, or a Docker image, generate a full software bill of materials from that exact artifact and include all transitive package versions and licences.

## Appliance Shell And Operating-System Packages

The AlmaLinux appliance shell is source code in this project and is covered by the Church Cap MIT License unless a file says otherwise. The shell installer does not vendor operating-system packages. It asks `dnf` to install packages from the configured AlmaLinux/EPEL/third-party repositories on the appliance.

Package names and licences can vary slightly by distribution version and repository. For a redistributed appliance image, confirm the exact RPM metadata with `rpm -qi <package>` and include the generated notices for the image you ship.

| Component / package family | Installed by | Purpose | Licence / notice |
|---|---|---|---|
| AlmaLinux packages | Appliance setup | Base operating-system packages used by the kiosk appliance | AlmaLinux is a rebuild of Red Hat Enterprise Linux sources and contains many open-source licences; include distribution notices if shipping an image |
| NetworkManager, NetworkManager-wifi, wpa_supplicant | Appliance setup | Wi-Fi scanning, connection, DHCP, and network status | Open-source system networking packages; commonly GPL/LGPL/BSD-family depending on component |
| OpenSSH server | Appliance setup | Optional PIN-gated support/admin SSH access | OpenSSH uses BSD/ISC-style open-source licences |
| Cage, Wayland stack, Firefox or Chromium | Appliance setup / kiosk launcher | Minimal kiosk browser environment | Cage is open-source; Firefox is MPL-2.0; Chromium is BSD-style plus third-party notices; browser binaries bring their own notices |
| systemd unit files | Appliance setup | Service supervision and kiosk startup | Project unit files are covered by Church Cap MIT; systemd itself is LGPL-2.1-or-later with additional notices |
| ALSA utilities, usbutils, pciutils, psmisc, acl, libinput | Appliance setup | Audio/device diagnostics, process control, permissions, and touch/input support | Open-source Linux utility packages; licences vary by package and distro build |
| Python `evdev` / `python3-evdev` | Optional appliance diagnostics | Touch/input diagnostics when standalone `evtest` is unavailable | Open-source Python package; confirm exact distro or pip metadata if bundled |
| `wvkbd`, `wvkbd-mobintl`, `squeekboard` | Optional, only if already installed | Native Wayland on-screen keyboard outside the browser | Open-source keyboard projects; not bundled by Church Cap |
| Noto Sans families including Arabic, Hebrew, Indic scripts, Thai/Lao/Khmer/Myanmar/Sinhala/Ethiopic/Armenian/Georgian, and CJK | Optional appliance setup | Better multilingual text rendering on the kiosk display | SIL Open Font License 1.1 |
| Noto Emoji / Noto Color Emoji | Optional appliance setup | Emoji/flag glyph rendering where the OS package is available | Noto emoji fonts are SIL Open Font License 1.1; related tools/resources may use Apache-2.0 or public-domain/copyright-exempt notices |

The language selectors use Unicode flag characters plus visible language-code text or fallback badges. Church Cap does not bundle flag image assets.


## Project Assets And UI Language Data

- Church Cap branding images in `assets/branding/` are project assets. Unless separately stated, they are distributed with the project under the root MIT License. If you create a trademark policy later, document any trademark restrictions separately from the source-code licence.
- The client UI language catalogue in `app/locales/client_ui.json` is project-maintained interface text. It is not a model and does not contain bundled machine-translation data.
- Unicode emoji/flag rendering comes from the user's operating system or optional font packages; Church Cap does not bundle commercial flag assets.

## Model And Data Notices

Church Cap does not commit or redistribute model weights in this repository.

- `openai-whisper` downloads or loads Whisper model weights at runtime according to `WHISPER_MODEL`.
- `faster-whisper` is retained as an optional lower-latency backend and downloads or loads Whisper-compatible model weights at runtime according to `WHISPER_MODEL`.
- The default model setting is `base.en`.
- Confirm the licence for every speech-to-text model you ship, cache, mirror, or bundle.
- Argos Translate language packages are downloaded by `scripts/install-translation-models-argos.sh` on macOS/Linux or `scripts/install-translation-models-argos.ps1` on Windows during setup, from the operator **Languages** page, or when the translation installer is rerun manually.
- Confirm the licence for every Argos language package you use, redistribute, or preinstall. The Argos application code is MIT/CC0, but model packages are separate artifacts and some package metadata has historically omitted an explicit licence. Do not assume the library licence automatically covers every downloaded model.
- Church Cap disables Argos's optional Stanza sentence-boundary pipeline before importing Argos. Church Cap translates short bounded cues, so this avoids loading packaged Stanza model files and avoids service-time Stanza resource checks. Argos 1.9.6 still pins older Stanza and SentencePiece packages; treat Argos model packages as trusted local resources, install them only through the documented operator/setup flow, and reassess the pin when Argos publishes a compatible fixed dependency set.
- Optional Fast Core translation downloads and converts `alirezamsh/small100` when `scripts/install-small100-ct2-int8.sh` or `scripts/install-small100-ct2-int8.ps1` is run. Optional legacy Core translation downloads the same model when `scripts/install-small100-core.sh` or `scripts/install-small100-core.ps1` is run. The Hugging Face model card lists SMaLL-100 as MIT licensed and covering 101 languages. Confirm the licence again before redistributing model weights or converted CTranslate2 files.
- OpenCC is installed by the translation installers and is used only for deterministic Chinese script and regional-phrase conversion. Its official project and PyPI metadata list Apache-2.0.

Do not assume every model hosted online is safe to redistribute or use commercially. Model code, model weights, training data, and conversion scripts may have different licences.

If you add Christian-context features, prefer user-provided glossary terms, public-domain vocabulary, and church-owned sermon notes. Avoid training or fine-tuning on copyrighted Bible translations, worship lyrics, sermon libraries, or liturgical material unless you have the right to do so.

## Release Checklist

Before publishing a public release:

1. Confirm direct dependency versions are pinned in `requirements.txt` and `requirements-translation.txt`.
2. Run a dependency vulnerability check against the exact versions being released.
3. Generate a full SBOM/licence report if distributing anything beyond source code, such as wheels, a Docker image, a bundled `.venv`, an app package, a wheelhouse, or an appliance disk image.
4. Confirm speech-to-text and translation model licences for any model weights you distribute, mirror, cache, or preinstall.
5. If publishing the appliance shell separately, include its `LICENSE` and `THIRD_PARTY_NOTICES.md` files as well as the main app legal docs.
6. Include this file, root `LICENSE`, `docs/legal/PRIVACY.md`, `docs/legal/DISCLAIMER.md`, `.github/SECURITY.md`, and `.github/CONTRIBUTING.md`.
7. Confirm `.env`, `data/`, `certs/`, `.venv/`, logs, diagnostics exports, and local runtime files are excluded from GitHub.
