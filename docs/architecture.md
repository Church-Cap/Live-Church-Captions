# Architecture

```text
Sound desk / USB interface
        ↓
Audio capture service
        ↓
Local AI speech-to-text
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
- `app/transcription/whisper_live.py` — default local AI transcription from one audio input using standard OpenAI Whisper.
- `app/transcription/faster_whisper_live.py` — optional lower-latency transcription backend.
- `app/hardware.py` — CUDA/GPU detection for the optional faster-whisper runtime.
- `app/glossary.py` — CSV-based Christian/church vocabulary correction.
- `app/profanity_filter.py` — bad-word censor for likely speech-to-text mistakes.
- `app/broadcast.py` — WebSocket broadcast hub, one-to-many client scaling.
- `app/templates/*.html` — phone, display, and operator pages.
- `config/glossary.csv` — editable correction list.
- `config/profanity_filter.txt` — local censor additions.

## Privacy model

The prototype is local-network first. Users scan a QR code and connect to the caption server over the church Wi-Fi. Captions are not sent to a cloud provider by the app's default workflow.

## Scaling model

The server transcribes audio once, then broadcasts text to all connected browsers over WebSockets. It does not run one AI model per viewer.

## Caption pacing model

The audience viewer treats captions as one bottom-to-top caption stream. Lines use logical start alignment, so English and other left-to-right languages begin at the left edge while right-to-left languages can follow their own direction. Lines use the available caption box from the bottom upward, existing lines glide upward when new text arrives, and only the newest trailing word receives a subtle entry animation. This makes the phone view behave more like a live transcript surface than a centered video subtitle box.

If Whisper has not produced any confirmed caption yet, the phone viewer may show the current live draft so viewers are not left on the waiting screen during continuous speech. Once confirmed captions are available, the phone viewer prefers the calmer confirmed stream so already-read words do not keep changing.

The session transcript is server-backed rather than browser-only. `app/broadcast.py` turns rolling partial captions into retained transcript sections, stores them through `app/transcript_store.py`, and sends small transcript updates to connected clients over the existing WebSocket. The phone transcript panel shows timestamped captions with the newest entry first when transcript/history retention is enabled, lets visitors scroll back through the current app session, and shows a simple disabled state when retention is off. Operator-only export routes download the current-session transcript as TXT, VTT, SRT, or JSON after a browser confirmation warning. Sensitive moment mode creates a transcript privacy barrier: captions received while blanked are discarded, the active transcript draft is dropped, live transcription buffers are reset when blanking/resuming, and a short resume drain window prevents buffered private speech from entering history or export. Visitors can hide or show the transcript locally without changing the server history or other viewers. The client and operator pages default to the device light/dark setting via `prefers-color-scheme`, while manual theme toggles are stored locally per device. A fresh app start begins with an empty visible session transcript rather than hydrating old captions into the client view. The local transcript cache is encrypted at rest when `cryptography` is installed, records the retention window that applied when it was saved, and is pruned on startup. It is deleted when the operator clears the transcript, disables retention, or the saved retention window removes all retained captions. The operator privacy panel can reveal the per-user transcript cache folder on the Church Cap computer for troubleshooting.

On phone and tablet landscape viewports, the client switches to a compact two-column layout when enough width is available: live captions use roughly 75% of the width and the optional transcript uses the remaining space. The landscape shell is constrained to the viewport height so transcript growth scrolls inside the transcript panel instead of pushing the live caption feed down the page. If a visitor hides the transcript, the live caption area expands to the full width while preserving spacing around the controls and footer.
