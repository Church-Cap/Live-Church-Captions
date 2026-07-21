# Translation notes

Multilingual support has two separate parts:

1. **Phone/user-interface language** — local and lightweight. The visitor page changes labels such as “Live captions”, “Pause”, and “Session transcript” from static strings in `app/locales/client_ui.json` first. The file includes static strings for every supported caption language. If a selected language is not in that file, Church Cap asks the local Base / Argos provider to translate the small set of UI labels at runtime, then falls back to English if the needed Argos pack is not installed. This UI path is separate from live caption translation routing and does not require captions to be running.
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

### Base package: Argos Translate

Base package uses Argos Translate language packs. It can be useful as a fallback for installed packs, but it is usually more literal than the Recommended package. It runs locally after packs are installed, but package installation requires internet access.

The macOS, Windows, and Linux setup scripts offer to install common Base package / Argos packs, install all available English-to-target Base package / Argos packs, install common Base plus the Recommended package / CTranslate2 INT8, install common Base plus the Compatibility package / PyTorch SMaLL-100, or skip translation resources. Operators can also install common Base package / Argos packs or all Base package / Argos packs later from the **Languages** page.

To rerun common Base installation manually on macOS or Linux:

```bash
./scripts/install-translation-models-argos.sh
```

Install all available Base package / Argos packs:

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

### Recommended package: CTranslate2 INT8 SMaLL-100

Recommended package uses a converted `alirezamsh/small100` model through CTranslate2 with INT8 quantisation. It is the preferred efficient neural translation path for broad language coverage, lower memory use, and better multi-language throughput while keeping translation local and open-source.

The Recommended package is not installed by default. Non-technical operators can use **Improve translation performance** on the operator **Languages** page. The button runs the local installer in the background, shows progress, and then offers **Use faster translation** when the model is ready. Setup scripts can also install the Recommended package, and technical users can run it manually:

```bash
./scripts/install-small100-ct2-int8.sh
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-small100-ct2-int8.ps1
```

The Recommended package / CTranslate2 INT8 selects CUDA automatically when CTranslate2 can see a CUDA device, otherwise it uses CPU with INT8. Advanced users can override this with `CHURCHCAP_CT2_SMALL100_DEVICE=cpu|cuda|auto` and `CHURCHCAP_CT2_SMALL100_COMPUTE_TYPE`, but live services should rely on the default unless benchmarking shows a clear reason to change it.

### Compatibility package: PyTorch SMaLL-100

Compatibility package uses the optional `alirezamsh/small100` model through Transformers/PyTorch. The model card lists an MIT licence, 101 languages, and a 0.3B parameter model. It remains available for compatibility, but it may use more RAM and CPU/GPU than the Recommended or Base packages.

Core is not installed by default. Install it from the operator **Languages** page or manually:

```bash
./scripts/install-small100-core.sh
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-small100-core.ps1
```

### Auto: Recommended + Base + Compatibility

Auto mode shows languages from installed packages. Church Cap tries Recommended / CTranslate2 INT8 first, then Base / Argos, then Compatibility / PyTorch SMaLL-100 for languages earlier packages cannot translate. Use this when the computer has enough memory and the church wants the broadest language coverage while still using lighter Base package / Argos packs where useful.

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

- **Off** — source language captions only. The visitor picker shows a clear unavailable message instead of offering translated-caption choices.
- **Recommended** — SMaLL-100 supported languages when the CTranslate2/INT8 model is installed.
- **Base** — installed Argos target languages.
- **Compatibility** — SMaLL-100 supported languages when the legacy PyTorch model is installed.
- **Auto** — the union of installed Recommended, Base, and Compatibility package languages.

Chinese is presented as two separate audience choices:

- **Chinese (Simplified) — `zh-Hans`**: providers use their Chinese model target, then OpenCC `t2s` enforces Simplified output.
- **Chinese (Traditional, Hong Kong) — `zh-Hant`**: providers use their Chinese model target, then OpenCC `s2hk` enforces Hong Kong Traditional characters and regional variants.

SMaLL-100 itself has one generic `zh` target, so this is deterministic post-processing rather than a prompt. Argos can use either its `zh` or `zt` installed package before the same final conversion. Existing `zh` runtime settings migrate to `zh-Hans`; `zh-HK`, `zh-MO`, and `zh-TW` browser locales select `zh-Hant`. Rerun the selected translation-resource installer after upgrading so OpenCC is installed. OpenCC converts script and regional variants; it is not a Mandarin-to-Cantonese translator.

By default, visitor language availability is **Automatic**. Visitors can request any language shown by the current mode, and Church Cap translates the most-requested languages up to the active limit. Advanced operators can switch to **Restricted** and select a smaller list, or prioritise selected languages first. In Restricted mode, the audience language picker and paired Service Leader language list show selected languages plus English as available, and can also show installed-but-disabled languages as requestable. Open audience phones refresh this language list from `/api/languages` when the picker opens, so operator changes appear without a full page reload. If translated captions are turned off, or an appliance System menu profile disables CPU languages, the picker limits caption choices to the source language and tells visitors that translated captions are unavailable for the service. In Restricted mode, installed but not enabled languages are shown as requestable on visitor and Service Leader pages; accepting a request adds the language to the restricted list while the active-language limit still controls how many languages are translated at once. The operator and Service Leader lists search language codes, English names, native names, and accented names. The operator list includes **Select all** and **Clear all** controls for quicker setup.

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

Church Cap protects the live source caption feed by keeping English publication outside the translation worker. Translated captions use bounded queues per language. New revisions of the same draft coalesce, and overload removes replaceable drafts before completed units. Final source units remain queued even when that temporarily exceeds the normal queue capacity. Languages rotate fairly instead of one language consuming every available turn.

For 3 or more simultaneous neural translations, use a stronger desktop CPU, NVIDIA CUDA acceleration, or a separate translation-capable machine.

## Efficient translation-performance direction

v0.6.1 starts the translation-performance track. The immediate goal is to keep the user-facing translation workflow stable while preparing the heavier translation path for CTranslate2/INT8 where practical.

Current runtime reality:

- **Recommended / CTranslate2 INT8 SMaLL-100** is the preferred broad-language package. It can use CPU/int8 or CUDA-backed CTranslate2 compute types where supported.
- **Base / Argos** stays available as a local fallback for installed language packs and generally runs on CPU.
- **Compatibility / PyTorch SMaLL-100** remains available for comparison and fallback. It may use CUDA when PyTorch sees CUDA, but it is not the preferred performance path.
- **Faster Whisper** already uses CTranslate2 and can use CPU/int8 or NVIDIA CUDA for speech-to-text. That acceleration does not automatically accelerate Argos translation.
- **AMD ROCm** is a future experimental Linux research path. Church Cap should not advertise ROCm as supported until setup, detection, fallback, and model/runtime tests are repeatable on real AMD hardware.

The Recommended package is intentionally behind provider/status checks. Keep Base and Compatibility fallbacks available, benchmark every active-language count, and only increase appliance limits when the operator can see measured English Delay and Translation Delay staying healthy.

## v0.7.0 Word Timing, Source Units, Context, And Scheduling, Retained In v0.7.2

The v0.7.0 Faster-Whisper path requests per-word timestamps and confidence; v0.7.2 retains this behavior unchanged. Safe words and forward extensions remain immediate. Only a weak final word within the 0.32-second captured-audio edge is hidden until a second decode agrees or the word moves away from the edge. The cue ledger still revises one stable `cue_id`; confirmed text seals at punctuation, 14 words, five seconds, audio-window advancement, or a real final. The sealed word-time boundary trims immutable audio from later rolling windows while retaining one second of overlap. Draft revisions replace one live line and unrelated sealed cues remain durable. Standard OpenAI Whisper keeps segment alignment but uses the same corrected start-to-start cadence.

The normal per-language queue capacity is eight. Church Cap coalesces every older queued revision for the same cue, including a stale final revision, then drops the oldest remaining draft if space is needed. If a queue contains only unrelated sealed cues, another sealed cue is accepted over capacity; a new draft is rejected until the queue drains. In-flight output is published only when its cue revision is still current. Round-robin selection prevents a busy language from starving another language. Sensitive mode and Clear erase cue and scheduler state.

Service-metrics schema 9 reports this behaviour with numeric counts only. It records word-timestamp passes, aligned-word totals, guarded edge words withheld/confirmed, actual recognition-pass intervals, cue processing, stable/mutable counts, cue lifetime, queue and Stop outcomes, translated draft/final publication counts, and first translated publication time measured from the first English cue update. Recognition words, times, confidence values, captions, and translations remain excluded.

Faster-Whisper derives word alignment from cross-attention and dynamic time warping; this improves boundary evidence but does not make Whisper a native streaming recogniser. Church Cap therefore combines alignment with local agreement and the edge guard. This follows the published Whisper-Streaming pattern of word timestamps, repeated-prefix agreement, and timestamp-driven buffer trimming without adding another model or network service. See the [Faster-Whisper word-timestamp documentation](https://github.com/SYSTRAN/faster-whisper#word-level-timestamps) and [Whisper-Streaming design](https://github.com/ufal/whisper_streaming).

The operator timing menu now offers three modes:

- **Responsive Context** is recommended. It translates the stable English prefix once at least three words are stable, waits at least 1.5 seconds and normally three additional stable words before another revision, and refines the same translated cue when English becomes final.
- **Live** translates eligible drafts and completed units for the lowest delay.
- **More Stable** updates less frequently from corrected English.

Responsive Context works with Argos, CTranslate2 SMaLL-100, and PyTorch SMaLL-100 because it changes translation scheduling rather than sending an instruction prompt. These models do not offer a reliable instruction channel. The responsive path uses accumulating context inside the current English cue, never waits for earlier completed thoughts, and never stores context in diagnostics. Legacy saved `contextual` or `extended` choices migrate to `responsive`. Sensitive mode, Clear, and timing-mode changes erase its in-memory timing and cue state.

This first responsive implementation deliberately does not prepend previous sentences. SMaLL-100 and typical Argos packages are sentence-level systems; concatenating earlier cues can translate or reorder the complete block without a dependable boundary for the newest target wording. Previous-sentence context remains a measured follow-up experiment rather than a source of hidden latency or repeated text.

See [TRANSLATION_MODEL_RESEARCH.md](project/TRANSLATION_MODEL_RESEARCH.md) for the current licence and model audit. In short, SMaLL-100 is listed as MIT and OpenCC as Apache-2.0; Argos application code is MIT/CC0 but every separately downloaded Argos model package still needs package-level licence verification. NLLB-200 and SeamlessM4T published weights are not candidates for commercially usable Church Cap distributions because their model cards use CC-BY-NC-4.0.

## GPU note

The operator page **Performance** controls can switch between standard local OpenAI Whisper and the lower-latency `faster-whisper` backend without editing `.env`. The platform view auto-detects macOS, Windows, or Linux and can be changed manually if needed. Windows and Linux can use NVIDIA CUDA for Faster Whisper when CTranslate2 sees a working runtime; Windows includes an optional local runtime installer, while Linux leaves drivers and CUDA under the system administrator's package policy. On macOS, CUDA choices are hidden and OpenAI Whisper can attempt Apple Metal/MPS when PyTorch supports it. Argos Translate may still run on CPU even when Whisper uses GPU acceleration. Recommended package / CTranslate2 INT8 translation remains optional and should be validated with real speech before live use.

## Measuring Translation In v0.7.2

Church Cap records privacy-safe numeric measurements for every translated language requested by a connected viewer. The current service and latest five completed summaries distinguish queue wait, provider compute, source-to-publish timing, outcomes, source-unit boundaries, draft coalescing/backpressure, durable finals, maximum queue depth, recovery, viewer-seconds, and resource pressure. Viewer counts are seeded when captions start so phones that joined beforehand are included. The implementation is not limited to Farsi or Chinese; those are the first languages being assessed with native readers.

The separate anonymised service report contains only allow-listed numeric measurements and non-identifying run/configuration fields. It excludes source speech, captions, translated wording, audio and device metadata, glossary content, paths, network identifiers, operator data, and logs. The broader diagnostics file also excludes caption content but remains support-sensitive because it includes computer information and redacted logs. Follow [recorded-sermon-testing.md](recorded-sermon-testing.md) to compare repeated runs with the same recording and audience-language viewers.

## Accuracy warning

AI translation is experimental and not verified. It can mistranslate Scripture, names, theological terms, pastoral details, and safeguarding-sensitive information.

Do not treat AI translation as a replacement for a qualified human interpreter where accuracy matters.

## Operator controls
Translation timing has three modes. **Responsive Context** is the recommended default for new configurations and retranslates the growing stable English cue without waiting for completed paragraphs. **Live** translates eligible partial captions quickly as the lowest-delay control. **More Stable** uses corrected English partials at a slower, steadier pace and also translates final captions. Context and naturalness must still be validated by native readers rather than assumed from model output.

Language requests are enabled by default. In Restricted mode, visitors and service leaders can ask for an installed language that is not currently enabled; the operator must accept it before it appears for the audience. If requests become distracting or disruptive, turn off **Visitor language requests** in **Languages → Advanced language controls**. Existing requests are cleared when the switch is saved off, and new requests are rejected until it is turned on again.
