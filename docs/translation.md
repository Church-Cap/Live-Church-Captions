# Translation notes

Multilingual support has two separate parts:

1. **Phone/user-interface language** — local and lightweight. This changes labels such as “Live captions”, “Pause”, and “Recent captions”.
2. **Translated captions** — experimental and resource-heavy. This takes the source caption text and translates it into selected audience languages.

Whisper performs speech-to-text. It can transcribe several spoken languages when configured, but it does **not** translate one English caption stream into several audience languages by itself. Caption translation needs a separate translation provider.

## Current providers

### argos disabled at runtime

Default. Argos is the configured local provider after setup, but translated captions remain off until the operator enables them. Viewers receive source captions.

```env
TRANSLATION_ENABLED=false
TRANSLATION_PROVIDER=argos
```

### demo

Testing only. This does not translate; it prefixes captions so you can test the routing, phone language selector, operator table, and resource safeguards.

```env
TRANSLATION_ENABLED=true
TRANSLATION_PROVIDER=demo
TRANSLATION_ALLOWED_LANGUAGES=en
TRANSLATION_MAX_ACTIVE_LANGUAGES=1
```

### argos

Local translation using Argos Translate models. This runs locally after the models are installed, but model installation requires internet access.

The macOS and Windows setup scripts run the Argos installer. To rerun it later on macOS:

```bash
./scripts/install-translation-models-argos.sh
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-translation-models-argos.ps1
```

Then set:

```env
TRANSLATION_ENABLED=true
TRANSLATION_PROVIDER=argos
TRANSLATION_ALLOWED_LANGUAGES=en
TRANSLATION_MAX_ACTIVE_LANGUAGES=1
```

Restart the app.

## GPU note

The operator page **Performance** controls can switch between standard local OpenAI Whisper and the lower-latency `faster-whisper` backend without editing `.env`. The platform view auto-detects macOS or Windows and can be changed manually if needed. On Windows, faster-whisper/CTranslate2 uses the NVIDIA GPU automatically only when `WHISPER_DEVICE=auto` or the saved operator setting is `auto`, the GPU is visible, and required CUDA runtime DLLs such as `cublas64_12.dll` are available. Choosing **GPU / NVIDIA CUDA** forces a CUDA load attempt first, then falls back to CPU if the runtime cannot load it. On macOS, CUDA choices are hidden and OpenAI Whisper can attempt Apple Metal/MPS when PyTorch supports it. Setup can offer to install or force reinstall local CUDA 12 runtime packages into `.venv`; Windows users who already manage NVIDIA tooling can install CUDA 12.x and cuDNN system-wide from NVIDIA instead. Argos Translate is still treated as local experimental translation and may run on CPU even when Whisper uses GPU acceleration.

## Resource safeguard

Every active translated language adds CPU/RAM work. To protect the caption computer during a busy service, the operator can set **Maximum active translated languages**.

Example:

```text
Max active translated languages: 1
Viewers request: Spanish, French, Ukrainian
Result: only the most-used language is translated; the others receive source captions with a warning.
```

This is intentional. It prevents one computer from trying to run too many translation streams on a Sunday morning.

## Accuracy warning

AI translation is experimental and not verified. It can mistranslate Scripture, names, theological terms, pastoral details, and safeguarding-sensitive information.

Do not treat AI translation as a replacement for a qualified human interpreter where accuracy matters.
