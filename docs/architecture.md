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
- `app/transcription/faster_whisper_live.py` — local AI transcription from one audio input.
- `app/hardware.py` — CUDA/GPU detection and automatic faster-whisper runtime selection.
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
