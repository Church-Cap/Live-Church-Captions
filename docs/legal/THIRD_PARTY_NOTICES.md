# Third-Party Notices

Last reviewed: 2026-05-19

Church Cap is released under the MIT License. This file records the direct third-party packages and model/tooling notes for the first public preview.

The repository does not vendor Python packages, Whisper model weights, Argos model packages, Homebrew packages, certificates, or a prebuilt `.venv`. Installers download dependencies into the user's local environment.

## Direct Python Dependencies

These are the direct dependencies pinned in `requirements.txt` and `requirements-translation.txt`.

| Component | Version | Purpose | Licence / notice |
|---|---:|---|---|
| FastAPI | 0.115.6 | Web application/API framework | MIT |
| Uvicorn | 0.34.0 | ASGI web server | BSD |
| Jinja2 | 3.1.5 | HTML templating | BSD-3-Clause |
| qrcode | 8.0 | QR code generation | BSD |
| Pillow | resolved by `qrcode[pil]` | Image handling for QR codes | HPND-style Pillow licence; exact installed version should be recorded if bundling wheels or a packaged environment |
| python-multipart | 0.0.27 | Form parsing for FastAPI routes | Apache-2.0 |
| pydantic-settings | 2.7.1 | Environment/settings loading | MIT |
| NumPy | 2.2.1 | Numerical/audio processing support | BSD-3-Clause; binary wheels may include additional notices such as OpenBLAS/LAPACK/GCC runtime components |
| sounddevice | 0.5.1 | Audio input capture | MIT; uses the system PortAudio library |
| faster-whisper | 1.2.1 | Local Whisper transcription backend | MIT |
| requests | 2.33.0 | Optional installer/model-download HTTP requests | Apache-2.0 |
| argostranslate | 1.9.6 | Local translation provider installed by the Argos setup script | MIT or CC0, per Argos Translate project metadata |

## Important Transitive Dependencies

The exact transitive dependency set is resolved by `pip` for the user's platform and Python version. Important runtime dependencies include:

| Component | Used by | Notice |
|---|---|---|
| Starlette | FastAPI | ASGI/web framework dependency. |
| Pydantic / pydantic-core | FastAPI and pydantic-settings | Data validation/settings dependencies. |
| python-dotenv | pydantic-settings | `.env` loading support. |
| CTranslate2 | faster-whisper and Argos Translate | Local inference runtime. On Windows, Church Cap can use CUDA through CTranslate2 when the installed runtime, NVIDIA drivers, and required CUDA runtime DLLs expose it. |
| Hugging Face Hub | faster-whisper | Model download/cache helper. |
| tokenizers | faster-whisper | Text tokenization. |
| onnxruntime | faster-whisper | Runtime dependency. |
| PyAV | faster-whisper | Audio decoding dependency. |
| tqdm | faster-whisper | Progress display dependency. |
| sentencepiece, stanza, sacremoses, packaging | Argos Translate | Optional translation dependencies. |
| NVIDIA CUDA Python wheel packages | Optional Windows GPU acceleration | Optional local `.venv` packages such as `nvidia-cuda-runtime-cu12`, `nvidia-cublas-cu12`, and `nvidia-cudnn-cu12`; installed only if the Windows operator chooses GPU runtime setup. |
| PortAudio | sounddevice | System audio library installed through Homebrew on macOS. |

If you distribute a packaged app, wheels, a frozen environment, or a Docker image, generate a full software bill of materials from that exact artifact and include all transitive package versions and licences.

## Model And Data Notices

Church Cap does not commit or redistribute model weights in this repository.

- `faster-whisper` downloads or loads Whisper-compatible model weights at runtime according to `WHISPER_MODEL`.
- The default model setting is `base.en`.
- Confirm the licence for every speech-to-text model you ship, cache, mirror, or bundle.
- Argos Translate language packages are downloaded by `scripts/install-translation-models-argos.sh` on macOS or `scripts/install-translation-models-argos.ps1` on Windows during setup or when the translation installer is rerun.
- Confirm the licence for every Argos language package you redistribute or preinstall.

Do not assume every model hosted online is safe to redistribute or use commercially. Model code, model weights, training data, and conversion scripts may have different licences.

If you add Christian-context features, prefer user-provided glossary terms, public-domain vocabulary, and church-owned sermon notes. Avoid training or fine-tuning on copyrighted Bible translations, worship lyrics, sermon libraries, or liturgical material unless you have the right to do so.

## Release Checklist

Before publishing a public release:

1. Confirm direct dependency versions are pinned in `requirements.txt` and `requirements-translation.txt`.
2. Run a dependency vulnerability check against the exact versions being released.
3. Generate a full SBOM/licence report if distributing anything beyond source code, such as wheels, a Docker image, a bundled `.venv`, or an app package.
4. Confirm speech-to-text and translation model licences for any model weights you distribute or preinstall.
5. Include this file, root `LICENSE`, `docs/legal/PRIVACY.md`, `docs/legal/DISCLAIMER.md`, `.github/SECURITY.md`, and `.github/CONTRIBUTING.md`.
6. Confirm `.env`, `data/`, `certs/`, `.venv/`, logs, and local runtime files are excluded from GitHub.
