# Translation notes

Multilingual support has two separate parts:

1. **Phone/user-interface language** — local and lightweight. The visitor page changes labels such as “Live captions”, “Pause”, and “Session transcript” from static strings in `app/locales/client_ui.json` first. The file includes manual fallback strings for languages Argos does not cover. If a selected language is not in that file, Church Cap asks the local Base / Argos provider to translate the small set of UI labels at runtime, then falls back to English if the needed Argos pack is not installed. This UI path is separate from live caption translation routing and does not require captions to be running.
2. **Translated captions** — experimental and resource-heavy. This takes the source caption text and translates it into audience languages using a local translation provider.

Whisper performs speech-to-text. It can transcribe several spoken languages when configured, but it does **not** translate one English caption stream into several audience languages by itself. Caption translation needs a separate translation provider.

## Visitor UI wording

`app/locales/client_ui.json` is the trusted static source for visitor-page UI labels. It can contain complete reviewed translations or partial manual fallback dictionaries. Missing keys fall back to English per label, so adding the most visible controls for a language is useful even before every notice sentence has been translated. This is the right place to add UI translations for languages Argos does not cover, or for languages where the Argos wording is too literal.

If a selected language is not in `client_ui.json`, Church Cap tries local Argos UI translation for the small set of page labels. If the English-to-target Argos pack is not installed or does not exist, the visitor page keeps English labels. Do not use SMaLL-100 for UI labels; it is reserved for caption translation because short interface text is easy for broad machine-translation models to mistranslate.

## Translation modes

### Off

Default for live caption translation. Viewers receive source captions. The phone UI language picker still works locally for interface labels.

```env
TRANSLATION_ENABLED=false
TRANSLATION_PROVIDER=argos
```

### Base: Argos Translate

Base mode uses Argos Translate language packs. It is usually more literal and lighter on system resources than Core mode. It runs locally after packs are installed, but package installation requires internet access.

The macOS and Windows setup scripts offer to install common Base packs, install all available English-to-target Base packs, install common Base packs plus Core, or skip translation resources. Operators can also install common Base packs or all Base packs later from the **Languages** page.

To rerun common Base installation manually on macOS:

```bash
./scripts/install-translation-models-argos.sh
```

Install all available Base packs:

```bash
./scripts/install-translation-models-argos.sh --all
```

Enable Base mode while installing:

```bash
./scripts/install-translation-models-argos.sh --enable
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-translation-models-argos.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install-translation-models-argos.ps1 -All
powershell -ExecutionPolicy Bypass -File .\scripts\install-translation-models-argos.ps1 -Enable
```

### Core: SMaLL-100

Core mode uses the optional `alirezamsh/small100` model. The model card lists an MIT licence, 101 languages, and a 0.3B parameter model. Core can cover more languages and may give better translations, but it uses more RAM and CPU/GPU than Base mode.

Core is not installed by default. Install it from the operator **Languages** page, from setup option 3, or manually:

```bash
./scripts/install-small100-core.sh
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-small100-core.ps1
```

### Auto: Base + Core

Auto mode shows languages from both installed providers. Church Cap tries Base first, then Core for languages Base cannot translate. Use this when the computer has enough memory and the church wants the broadest language coverage while still using lighter Base packs where possible.

### Demo

Testing only. This does not translate; it prefixes captions so you can test the routing, phone language selector, operator table, and resource safeguards.

```env
TRANSLATION_ENABLED=true
TRANSLATION_PROVIDER=demo
TRANSLATION_ALLOWED_LANGUAGES=en
TRANSLATION_MAX_ACTIVE_LANGUAGES=20
```

## Language selection

The visitor language picker is a custom searchable list. It shows the languages available for the current translation mode:

- **Off** — source language captions only, while UI labels can still change from bundled dictionaries.
- **Base** — installed Argos target languages.
- **Core** — SMaLL-100 supported languages when Core is installed.
- **Auto** — the union of installed Base languages and Core-supported languages.

By default, visitor language availability is **Automatic**. Visitors can request any language shown by the current mode, and Church Cap translates the most-requested languages up to the active limit. Advanced operators can switch to **Restricted** and select a smaller list, or prioritise selected languages first.

## Resource safeguard

Every active translated caption language adds CPU/RAM work. To protect the caption computer during a busy service, the operator can set **Maximum active translated languages**.

The default active limit is **20**. The control can be raised up to the full supported language catalogue on powerful hardware, or lowered for weaker systems and services where latency matters most.

Example:

```text
Max active translated languages: 2
Viewers request: Spanish, French, Ukrainian
Result: the two most-used languages are translated; the remaining language receives source captions and a help message.
```

This is intentional. It prevents one computer from trying to run too many translation streams on a Sunday morning.

## GPU note

The operator page **Performance** controls can switch between standard local OpenAI Whisper and the lower-latency `faster-whisper` backend without editing `.env`. The platform view auto-detects macOS or Windows and can be changed manually if needed. On Windows, faster-whisper/CTranslate2 uses the NVIDIA GPU automatically only when `WHISPER_DEVICE=auto` or the saved operator setting is `auto`, the GPU is visible, and required CUDA runtime DLLs such as `cublas64_12.dll` are available. Choosing **GPU / NVIDIA CUDA** forces a CUDA load attempt first, then falls back to CPU if the runtime cannot load it. On macOS, CUDA choices are hidden and OpenAI Whisper can attempt Apple Metal/MPS when PyTorch supports it. Setup can offer to install or force reinstall local CUDA 12 runtime packages into `.venv`; Windows users who already manage NVIDIA tooling can install CUDA 12.x and cuDNN system-wide from NVIDIA instead. Argos Translate is still treated as local experimental translation and may run on CPU even when Whisper uses GPU acceleration.

## Accuracy warning

AI translation is experimental and not verified. It can mistranslate Scripture, names, theological terms, pastoral details, and safeguarding-sensitive information.

Do not treat AI translation as a replacement for a qualified human interpreter where accuracy matters.
