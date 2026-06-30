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

The macOS, Windows, and Linux setup scripts offer to install common Base packs, install all available English-to-target Base packs, install common Base packs plus Core, or skip translation resources. Operators can also install common Base packs or all Base packs later from the **Languages** page.

To rerun common Base installation manually on macOS or Linux:

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
TRANSLATION_MAX_ACTIVE_LANGUAGES=2
```

## Language selection

The visitor language picker is a custom searchable list. It shows the languages available for the current translation mode. Language options use compact Unicode flag chips; the language code remains in the option text beside the language name instead of inside the flag chip. If a language has no flag metadata, Church Cap shows a compact code badge:

- **Off** — source language captions only, while UI labels can still change from bundled dictionaries.
- **Base** — installed Argos target languages.
- **Core** — SMaLL-100 supported languages when Core is installed.
- **Auto** — the union of installed Base languages and Core-supported languages.

By default, visitor language availability is **Automatic**. Visitors can request any language shown by the current mode, and Church Cap translates the most-requested languages up to the active limit. Advanced operators can switch to **Restricted** and select a smaller list, or prioritise selected languages first. In Restricted mode, the audience language picker and paired Service Leader language list show only the selected languages plus English. Open audience phones refresh this language list from `/api/languages` when the picker opens, so operator changes appear without a full page reload. The operator and Service Leader lists search language codes, English names, native names, and accented names. The operator list includes **Select all** and **Clear all** controls for quicker setup.

## Resource safeguard

Every active translated caption language adds CPU/RAM work. To protect the caption computer during a busy service, the operator can set **Maximum active translated languages**.

The default active limit is **2** for fresh installs. The control can be raised up to the full supported language catalogue on powerful hardware, but CPU-only systems should usually stay at 1-2 active translated languages for live services.

Example:

```text
Max active translated languages: 2
Viewers request: Spanish, French, Ukrainian
Result: the two most-used languages are translated; the remaining language receives source captions and a help message.
```

This is intentional. It prevents one computer from trying to run too many translation streams on a Sunday morning.

The restricted service-leader page can enable or disable translated captions and choose Automatic or Manual language availability from resources already installed by the operator. If the operator has already restricted availability, the Service Leader can only choose from that approved list. Its search results follow the same language availability rules and include flag/code chips, native names, English names, and language codes. It cannot change the provider, install models, or exceed the operator-configured active-language limit. Manual mode saves a restricted language list containing English plus the selected languages; Automatic mode lets visitor demand choose languages up to the active limit. Changes made on either page are reflected on the other page during its normal live-status refresh.

## Appliance profiles

The open-source desktop app keeps the full Languages page available because the operator may be testing or preparing a powerful machine. The Church Cap Appliance is stricter:

- `appliance_cpu` keeps the main operator experience English-first but leaves **Languages** accessible as an advanced option. The first visit shows a CPU translation warning, and Church Cap enforces a hard limit of three active translated languages even if a stale browser or direct API request tries to exceed it.
- `appliance_gpu` shows multilingual controls in the main run-service area, but translated captions remain blocked until CUDA is ready.

The appliance profile comes from `/etc/churchcap-appliance/identity.json` or explicit environment variables. It is never inferred from hardware alone.

## CPU-only live-service guidance

CPU-only translation is viable, but it is not the same workload as English captions. Whisper, text cleanup, WebSocket delivery, and every active translated language all compete for the same CPU. On CPU-only or mid-range mobile systems, start with **1-2 active translated languages** for live services and raise the limit only after testing with normal speech.

Church Cap protects the live source caption feed by scheduling translated-caption work through a latest-wins queue. If speech produces a newer caption while an older caption is still being translated, stale translation work can be skipped so translated captions do not arrive as a delayed backlog. This keeps translation useful without letting it starve live English captions.

For 3 or more simultaneous neural translations, use a stronger desktop CPU, NVIDIA CUDA acceleration, or a separate translation-capable machine. AMD integrated graphics / ROCm may become useful for Linux power users in the future, but it is not a supported Church Cap acceleration path in this release.

## GPU note

The operator page **Performance** controls can switch between standard local OpenAI Whisper and the lower-latency `faster-whisper` backend without editing `.env`. The platform view auto-detects macOS, Windows, or Linux and can be changed manually if needed. Windows and Linux can use NVIDIA CUDA when CTranslate2 sees a working runtime; Windows includes an optional local runtime installer, while Linux leaves drivers and CUDA under the system administrator's package policy. On macOS, CUDA choices are hidden and OpenAI Whisper can attempt Apple Metal/MPS when PyTorch supports it. Argos Translate may still run on CPU even when Whisper uses GPU acceleration.

## Accuracy warning

AI translation is experimental and not verified. It can mistranslate Scripture, names, theological terms, pastoral details, and safeguarding-sensitive information.

Do not treat AI translation as a replacement for a qualified human interpreter where accuracy matters.
