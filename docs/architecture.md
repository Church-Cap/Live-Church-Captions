# Architecture

```text
Sound desk / USB interface
        ↓
Audio capture service
        ↓
Local AI speech-to-text
        ↓
Timestamped local-agreement cue buffer
        ↓
Glossary/correction layer
        ↓
Bad-word censor
        ↓
Optional local translation
        ↓
Caption hub / broadcast manager
        ↓
WebSocket stream
        ↓
HTML5 caption pages on phones, tablets, side screens, and OBS browser sources
```

## Components

- `app/main.py` — FastAPI application, routes, start/stop controls, QR codes.
- `app/transcription/whisper_live.py` — local AI transcription from one audio input using standard OpenAI Whisper.
- `app/transcription/faster_whisper_live.py` — lower-latency transcription backend using faster-whisper/CTranslate2.
- `app/hardware.py` — CUDA/GPU detection and runtime resolution for faster-whisper.
- `app/runtime_config.py` — persisted operator choices for audio input, privacy, translation, security, and performance tuning.
- `app/service_leader_auth.py` — in-memory one-use pairing tokens and restricted service-leader sessions.
- `app/i18n.py` — supported language metadata and optional caption translation provider bridge.
- `app/localisation.py` and `app/locales/client_ui.json` — visitor page UI string loading and the single client UI catalogue.
- `app/glossary.py` — CSV-based Christian/church vocabulary correction.
- `app/profanity_filter.py` — bad-word censor for likely speech-to-text mistakes.
- `app/broadcast.py` — WebSocket broadcast hub, one-to-many client scaling.
- `app/source_units.py` — timestamp-aware local-agreement cue ledger derived from rolling Whisper hypotheses.
- `app/translation_scheduler.py` — bounded fair per-language translation queues and backpressure policy.
- `app/templates/*.html` — phone, display, and operator pages.
- `config/glossary.csv` — editable correction list.
- `config/profanity_filter.txt` — local censor additions.

## Privacy model

Church Cap is local-network first. Users scan a QR code and connect to the caption server over the church Wi-Fi. Captions are not sent to a cloud provider by the app's default workflow.

## Service leader security boundary

In dual-port mode, the operator listener binds to the configured host so paired church devices can reach `/service-leader`. When the localhost lock is enabled, middleware permits remote access only to `/service-leader` and static assets; `/operator` and all other operator routes remain blocked remotely.

Pairing tokens are random, single-use, short-lived, and carried in the QR URL fragment rather than the query string. They are exchanged for a separate server-side session cookie scoped to `/service-leader`. Mutating requests require both a session-specific CSRF token and a matching origin.

The local operator can create or replace a pending token through the dedicated dashboard section, cancel a pending token, inspect active-session counts, or revoke all sessions. Replacing a pending token does not revoke an established service-leader session.

The restricted language endpoint preserves the operator-selected provider, resource installation, priority policy, and active-language capacity. It can toggle translation and choose either automatic visitor language availability or a manual subset of languages already supported by installed resources. The page polls server state so operator-side language/resource changes and audio-device availability stay synchronized. Its source-caption preview connects as a non-counted observer to the same caption WebSocket used by audience clients, so it does not inflate viewer counts or influence automatic translated-language demand.

Caption health reuses the operator benchmark's live-delay calculation: latest transcription duration plus caption refresh interval. Health is green below 2.5 seconds, amber from 2.5–3.5 seconds, and red above 3.5 seconds.

## Scaling model

The server transcribes audio once, then broadcasts text to all connected browsers over WebSockets. It does not run one AI model per viewer.

## Language And Translation Model

Visitor UI language and translated captions are separate systems. UI labels come from static strings in `app/locales/client_ui.json` via `app/localisation.py`. The catalogue includes static strings for every supported caption language; missing future keys fall back to English per label. If a selected UI language is not in the catalogue, the `/api/client-ui/{language}` endpoint can translate the English UI strings locally at runtime using installed Base / Argos packs, then falls back to English if Argos cannot translate that language. This UI fallback does not require captions to be running and remains separate from live caption translation routing. Audience, operator, and Service Leader language lists render Unicode flag chips from the local language metadata, avoiding bundled image assets. Audience lists keep the code in the option text beside the language name; operator and Service Leader lists use visible flag/code chips for admin readability. Fallback code badges are used where a language has no flag metadata. Caption translation is optional and local. Recommended package uses a converted SMaLL-100 model through CTranslate2/INT8, Base package uses installed Argos Translate packs, Compatibility package uses the optional PyTorch SMaLL-100 model, and Auto mode exposes languages from installed packages while trying Recommended, then Base, then Compatibility. Simplified Chinese (`zh-Hans`) and Hong Kong Traditional Chinese (`zh-Hant`) are separate audience choices. Providers translate through their available Chinese target, then Apache-2.0 OpenCC applies `t2s` or `s2hk` so the displayed script is deterministic; this conversion does not turn Mandarin wording into Cantonese. Visitor caption-language requests are automatic by default: Church Cap translates the most-requested languages up to the operator's active limit, which defaults to 2 for fresh installs and can be raised on powerful hardware. In Manual / restricted language mode, installed but not enabled languages remain visible as requestable options on visitor and Service Leader pages; accepting a request adds the language to the restricted list while the active-language limit still controls live translation load. CPU appliance profiles keep the Languages page visible as an advanced option, but translated captions remain blocked until CPU language options are enabled from the appliance System menu. Once enabled, the operator warning and three-language cap are enforced server-side.

## Performance model

The operator dashboard exposes a performance slider, an Easy settings view, and an Advanced settings view. Presets switch between faster/lower-accuracy and slower/higher-accuracy combinations of backend, model size, caption refresh interval, listening window, silence finalise timing, stability checks, and beam size. The far-right preset uses the medium Whisper model and warns operators to benchmark it because it can increase latency. Controls can choose an automatic macOS, Windows, or Linux platform view so processor options match the supported computer. Windows and Linux expose NVIDIA CUDA choices; macOS exposes Apple Metal/MPS for OpenAI Whisper.

The top operator bar includes live **English Delay** and **Translation Delay** tiles. English Delay is based on the latest transcription pass plus the configured caption refresh interval; Translation Delay adds the latest local translation pass when translated captions are active. The Performance panel also includes a lightweight 15-second benchmark and live monitor that sample runtime metrics from `/api/status`, including transcription time, estimated live/final caption delay, audio level, model load time, runtime, and available system load. Recommendations are generated locally from OS, CPU count, CUDA readiness, and current runtime state; applying them does not require internet access and favours conservative live-service presets over the medium model. These settings are saved in the per-user `runtime_config.json` file and override matching `.env` defaults. They apply when captions next start because the transcription backend loads its model and opens the audio stream at session start. Performance settings are locked while captions are running, including the speed/accuracy slider, backend, model size, processor, and advanced timing controls. On macOS, hardware reporting includes Apple chip/GPU details and unified-memory totals where available. On Windows, automatic CUDA use depends on CTranslate2 seeing the GPU and the required CUDA runtime DLLs; if a forced CUDA load fails, Church Cap reports the issue and falls back to CPU. The Windows CUDA troubleshooting controls can refresh local detection and launch the local CUDA runtime force reinstall in the background, writing to `logs/cuda-runtime-install.log`; diagnostics and UI status use this relative log label rather than a full local file path. Windows CUDA recommendations use Faster Whisper because the bundled CUDA runtime path is for CTranslate2 rather than CUDA-enabled PyTorch.

v0.6.1 added the typed service-run layer in `app/metrics.py`. v0.7.0 retains that lifecycle and advances the service-metrics schema to 9. In addition to stage timing and provider outcomes, it identifies word-timestamp cue-engine v5 and its immediate stable-prefix/guarded-edge-tail strategy. It reports text-free word-alignment passes and counts, weak edge words withheld or confirmed, actual start-to-start decode intervals, cue-processing latency, stable/mutable word counts, cue lifetime, translated draft/final publications, first translated-cue timing, queue pressure, and shutdown outcomes. The privacy boundary is unchanged: no audio, timestamps, confidence values, caption wording, or translation wording is retained in a service report.

The English and translation paths intentionally separate after cleanup. Faster-Whisper requests real per-word start/end alignment and confidence. A high-confidence edge word remains immediate; only a weak final word within the configured live-edge margin waits for a second matching decode. `SourceUnitBuilder` combines these private timings with consecutive-hypothesis agreement, so shared words form a stable prefix while only the newest tail remains mutable. Confirmed cues seal at punctuation, 14 words, five seconds, audio-window advancement, or a real Whisper final. The newest sealed audio boundary is fed back to Faster-Whisper so later rolling windows omit immutable audio while retaining a one-second overlap. Decode passes follow a start-to-start deadline: model compute consumes the configured interval instead of being followed by another full interval sleep. Standard OpenAI Whisper uses the same corrected cadence with segment-level alignment. The client applies cue IDs and monotonically increasing revisions, so a correction replaces the live cue instead of appending another guessed line. Its persistent line ledger and measured-width wrapping remain unchanged. The same cue stream drives transcript and translation jobs. Responsive Context retranslates only the stable prefix of the current English cue after meaningful growth, coalesces obsolete revisions in the bounded fair queue, and publishes the final refinement under the same cue identity. Privacy resets and the bounded Stop drain remain unchanged.

Storage accounting is calculated on demand from Operator → Diagnostics rather than on every status poll. The cleanup API accepts only server-generated candidate identifiers and recomputes the allow-list immediately before deletion. It protects active models and does not expose local paths. Church Cap-owned logs rotate at 5 MB with two backups, diagnostics tail reads are byte-bounded, and routine Uvicorn request access logs are disabled.

Linux setup keeps distro-specific package names in `scripts/linux-system-packages.sh`. `setup-linux.sh` detects the package manager, installs system prerequisites, then follows the same `.venv` workflow as the other platforms. Linux CUDA remains system-managed: Church Cap detects it through CTranslate2 but does not install drivers or alter CUDA repositories.

## Caption pacing model

The audience viewer treats captions as one bottom-to-top caption stream. The phone shell is bounded to the dynamic viewport, so caption growth never turns it into an indefinitely long document. Live and Session transcript are independent scroll containers; Live retains a bounded three-screen line buffer, follows new text only while the reader is already near the bottom, and preserves the reader's position after they scroll back. English and translated clients both render the server-owned cue ledger. A draft `upsert` changes the existing cue; only a `seal` creates durable history. Forward-only draft growth keeps existing line breaks and wraps from the final line, reducing vertical jumps while retaining the subtle new-word animation. An accepted rewrite may reflow once, without animating the old lines across the card. Line wrapping is presentation-only and never changes cue identity. The optional Session transcript starts closed on every page visit and its button state is synchronized with the panel. Lines use logical start alignment, so English and other left-to-right languages begin at the left edge while right-to-left languages can follow their own direction. Dismissing notices releases flex space to the caption panels and a localized hint explains that behavior while notices remain. The `/display` and `/obs` pages keep the separate stable two-line presentation layout.

If Whisper has not produced any confirmed caption yet, the phone viewer may show the current live draft so viewers are not left on the waiting screen during continuous speech. Once confirmed captions are available, the phone viewer prefers the calmer confirmed stream so already-read words do not keep changing. Both live Whisper paths and the server-side transcript assembly collapse obvious repeated word or phrase loops, and Faster Whisper avoids conditioning each rolling-window decode on previous text so a bad phrase is less likely to keep feeding itself.

Language switches during an active viewer session use a small absolute-positioned notice inside the live caption card. The live caption card also allows fresh partial speech to appear even when older final captions remain in the stream, so speech after a quiet gap does not wait for the next final caption before becoming visible. The notice only appears when caption content is already present, so an empty waiting screen stays still, and it does not affect card height or the position of controls and transcript history. When translated captions are disabled, the viewer language picker limits caption choices to the source language and shows a clear unavailable message. Visitor and Service Leader pages use the browser Screen Wake Lock API where available; the lock is visibility-bound and releases when the page is hidden or the browser revokes it. Church Cap does not run hidden media keep-awake fallbacks; if a mobile browser rejects wake lock, the device's normal auto-lock setting still applies.

The session transcript is server-backed rather than browser-only. `app/broadcast.py` turns rolling partial captions into retained transcript sections, stores them through `app/transcript_store.py`, and sends small transcript updates to connected clients over the existing WebSocket. The phone transcript panel shows timestamped captions with the newest entry first when transcript/history retention is enabled, lets visitors scroll back through the current app session, and shows a simple disabled state when retention is off. Operator-only export routes download the current-session transcript as TXT, VTT, SRT, or JSON after a browser confirmation warning. Sensitive moment mode creates a transcript privacy barrier: captions received while blanked are discarded, the active transcript draft is dropped, live transcription buffers are reset when blanking/resuming, and a short resume drain window prevents buffered private speech from entering history or export. The WebSocket event sends a stable UI message key so audience phones can show the blanked/resumed notice in the viewer's selected UI language, falling back to English when no local string is available. Visitors can hide or show the transcript locally without changing the server history or other viewers. The client and operator pages default to the device light/dark setting via `prefers-color-scheme`, while manual theme toggles are stored locally per device. On the Church Cap Appliance, the injected shell stores the chosen kiosk/operator theme in `/etc/churchcap-appliance/shell-state.json` so startup does not depend on a desktop environment exposing a colour-scheme preference. A fresh app start begins with an empty visible session transcript rather than hydrating old captions into the client view. The local transcript cache is encrypted at rest when `cryptography` is installed, records the retention window that applied when it was saved, and is pruned on startup. It is written through unique temporary files so overlapping caption updates cannot collide during the atomic save. If the cache cannot be written because of a storage or permissions problem, Church Cap logs a warning and keeps live captions running rather than showing the storage error to audience devices. The cache is deleted when the operator clears the transcript, disables retention, or the saved retention window removes all retained captions. The operator privacy panel can reveal the per-user transcript cache folder on the Church Cap computer for troubleshooting.

On phone and tablet landscape viewports, the client switches to a compact two-column layout when enough width is available: live captions use roughly 75% of the width and the optional transcript uses the remaining space. The landscape shell is constrained to the viewport height so transcript growth scrolls inside the transcript panel instead of pushing the live caption feed down the page. If a visitor hides the transcript, the live caption area expands to the full width while preserving spacing around the controls and footer.
