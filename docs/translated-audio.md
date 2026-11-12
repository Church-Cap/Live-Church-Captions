# Local Translated Audio

Version: v0.9.0

Church Cap can optionally read completed translated captions through a local Sherpa-ONNX voice. The client language search shows a small headphone marker beside each language whose local voice is ready, so visitors can see listening availability before selecting it. Every translated-language audience page still shows **Listen** so the feature is discoverable. If that language does not yet have a verified, installed voice pack, selecting the control displays a clear unavailable message; it never pretends audio has started. English does not offer translated audio. Voice gender and model names are deliberately not shown to listeners; Church Cap uses one operator-approved voice per language, selected for intelligibility before gender.

The operator can switch this feature on or off from **Languages → Spoken translation for visitors**. It is on by default for existing installations and saves immediately. Switching it off hides the headphone markers and **Listen** control from audience pages, clears pending speech and prevents in-progress speech from being delivered. Translated text captions continue normally, and the choice is retained after Church Cap restarts.

## Reliability boundary

- Caption and translation publication never waits for TTS.
- Only completed translated cues are spoken. Draft corrections are not read aloud.
- A cue is synthesised once per language and shared with every opted-in listener using that language.
- No synthesis occurs when a language has no audio listeners.
- Each language has a two-cue bounded queue. An older pending cue is discarded when necessary so audio cannot fall continually behind.
- The browser also abandons an audio backlog above 4.5 seconds and resumes from the newest completed cue.
- Generated audio and translated text remain in memory. Church Cap does not write them to transcripts, service reports, diagnostics, or logs.
- Caption viewing continues normally if Sherpa-ONNX, a voice pack, browser audio, or the audio WebSocket fails.
- The audience page preserves voice readiness across normal caption/viewer metadata updates and rechecks the server when **Listen** is selected. This prevents a page opened before installation, or a routine live-state update, from incorrectly leaving a ready voice marked unavailable.
- Audience playback uses one user-activated HTML audio element rather than Web Audio buffers. A silent waiting track preserves mobile Safari's explicit-tap permission, and the same element plays each completed cue so supported phones can expose native media controls. The page distinguishes **Connected — waiting** from **Playing translated audio**.
- Voice output is checked for finite, audible samples before it is sent. A small number of invalid model samples is repaired; substantially invalid or silent output is rejected and reported instead of sending a silent WAV.

## Installation

The easiest route is **Operator → Languages → Spoken translated audio**. Stop captions first, select only the voice packs the church needs, review the displayed download/storage estimate, and select **Install selected languages**. Connect the Church Cap computer to the internet and allow several minutes. The installer adds the optional runtime and downloads checksum-verified voices into Church Cap's persistent application-data folder; normal setup downloads no voice weights and upgrades do not need to download installed packs again. The same card reports readiness and controls whether visitors see headphone markers and the **Listen** button. For every reviewed spoken-language pack, the audience Listen/Stop label and connection, waiting, playing, unavailable and error status use the currently selected caption language rather than English fallback text.

The reviewed optional catalogue retained by v0.7.6 covers Catalan, Spanish, French, Kazakh, Latvian, Nepali, Dutch, Slovenian, Swedish, Ukrainian, Simplified Chinese and Traditional Chinese. The two Chinese caption routes share one Kokoro Mandarin download.

Traditional Chinese describes the writing system, not the spoken language. This starter voice is Mandarin, not Cantonese. Churches that need Cantonese speech should leave audio off until a separately reviewed Cantonese pack is configured and tested with native listeners.

Installing every pack is approximately 716 MB of downloads and may use roughly 1.6 GB after extraction, plus optional runtime dependencies. Church Cap calculates the estimate for the current selection in the GUI. See [Optional Spoken-Language Model Notices](legal/SPOKEN_LANGUAGE_MODELS.md) for the model-by-model table and obligations. The review conclusion for included packs is: **No obvious commercial prohibition; comply with attribution, notice or share-alike requirements.** It is not a legal guarantee.

The former Farsi Amir pack is retired because its model card records a Lessac base checkpoint whose terms do not meet Church Cap's commercial-use requirement. Farsi translated text continues to work; optional Farsi speech remains unavailable until a cleaner pack passes review.

The same installer can be run manually after normal Church Cap setup:

macOS or Linux:

```bash
./scripts/install-tts.sh --packages zh,es,fr
```

Windows PowerShell:

```powershell
.\scripts\install-tts.ps1 -Packages "zh,es,fr"
```

Omitting `--packages` / `-Packages` installs the complete optional catalogue. The GUI is preferred because it shows individual packs and the estimated size before installation.

The installer downloads official Sherpa-ONNX release archives, verifies pinned SHA-256 checksums before extraction, rejects unsafe archive paths and links, installs the files below the platform-specific Church Cap `tts` data folder, and writes `voices.json` atomically. It preserves unrelated custom voice entries, except for the specifically retired Amir source. No voice weights are committed to the Church Cap source repository.

Installed reviewed voice models can be removed from **Operator → Languages → Spoken translated audio → Remove installed languages** while captions are stopped. Church Cap shows a themed confirmation menu with only the installed catalogue packs and an estimated storage saving. Removal deletes only the selected reviewed model folders and their matching manifest entries; it preserves other voices, unrelated custom voice entries, the shared Sherpa-ONNX runtime, licence notices and all text-caption translation resources. The removed Listen options disappear from audience devices and can be restored later by downloading those packs again.

**Operator → Diagnostics → Application Storage → Spoken audio models** reports the actual space used by each installed reviewed voice pack and their combined total. It offers the same removal menu, while keeping the broader Church Cap data figure intact because voice packs live inside the persistent application-data folder. Storage is calculated only when Application Storage is opened or refreshed, so normal caption-status polling does not repeatedly scan large model folders.

The manifest deliberately rejects:

- paths outside the Church Cap TTS folder;
- missing model resources;
- unsupported engines;
- models without a licence identifier and official source URL; and
- voices that have not explicitly been marked `commercial_use_approved` after review.

The Sherpa-ONNX framework licence does not grant rights to third-party voice weights. Recheck every voice model and training-data/model-card licence before redistribution. Keep the source URL and SPDX-style licence identifier in `voices.json` and in `docs/legal/THIRD_PARTY_NOTICES.md` when a voice ships with Church Cap.

## Supported engines

The v0.7.6 provider supports Sherpa-ONNX VITS/Piper-compatible and Kokoro voice packs. A maintained Piper executable is not bundled. This keeps the optional runtime permissively licensed while allowing separately reviewed compatible ONNX voices.

Advanced operators can use `config/tts_voices.example.json` as a starting point for additional voices. Record the real spoken locale in the manifest and pilot every new pack with native listeners before enabling it.

## Operator checks

Diagnostics reports the framework, installed language codes, spoken locale, model engine, licence identifier, listener count, queue depth, generated/dropped cue counts, synthesis time and last error. It never reports the spoken text or audio.

Before a live service:

1. Confirm **Spoken translation for visitors** is on in Languages.
2. Confirm Diagnostics shows **Ready** and lists the intended language.
3. Enable that translated language in **Languages** and open its audience page.
4. Test the exact computer and each enabled voice with a recorded sermon.
5. Have a native listener check names, Scripture references and church terminology.
6. Confirm headphones work after selecting **Listen** on an audience device.
7. Confirm switching translated speech off hides its client controls without stopping translated text.
8. Confirm Stop audio immediately silences scheduled speech.
9. Confirm captions continue when the TTS dependency or voice model is deliberately unavailable.
