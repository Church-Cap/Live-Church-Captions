# Privacy and Data Protection Notes

This project is designed to be local-first. By default, the intended deployment is:

- audio enters the caption computer from the church sound desk or audio interface;
- speech is processed on the local caption computer;
- live captions are served on the local network;
- no public internet access is required for normal caption viewing.

Churches should still treat live captions and transcripts as potentially sensitive personal data.

## Recommended church practice

Before using this in a public or semi-public service, meeting, or group, consider:

- displaying a clear notice that live AI captions are in use;
- explaining whether transcripts are retained, for how long, and who can access them;
- using the operator blank/pause controls during sensitive pastoral moments;
- disabling transcript retention where appropriate;
- deleting transcripts that are no longer needed;
- avoiding use for confidential pastoral counselling or safeguarding disclosures unless there is an appropriate policy and consent process;
- protecting the operator page with a strong password;
- limiting access to transcript download and admin controls;
- keeping the caption server on a trusted local network where possible.

## Transcript retention

Church Cap includes retention controls. When transcript saving is enabled, retained caption text is cached locally in the per-user Church Cap data folder for the configured retention window. The transcript cache is encrypted at rest when the installed Python environment includes the `cryptography` dependency. Operator export can download the current-session transcript as text, subtitle, or JSON files after a privacy warning. A paired Service Leader device can export limited TXT/VTT current-session transcripts for appliance support after a separate warning. Sensitive moment mode suppresses visible captions, retained transcript entries, and transcript export content for that period. Exported files are outside Church Cap retention controls once saved elsewhere, so churches should only export where they have a clear reason and policy basis to keep or share the transcript. Clearing the transcript, disabling transcript saving, or setting retention to no history deletes the retained transcript cache. If the local cache cannot be written because of a storage or permissions issue, live captions continue and the current browser session can keep showing captions, but retained transcript history may not be saved until the storage issue is fixed.

The safest default for sensitive environments is to retain as little as possible.

## Cloud services

If cloud transcription, translation, remote diagnostics, analytics, or public livestream integrations are added later, they should be clearly documented and disabled by default unless the church intentionally enables them.


## Diagnostics exports

The operator can download two different JSON files. **Anonymised service report** is allow-listed and contains only numeric service measurements, non-identifying settings, random run IDs, and schema/version fields. It excludes speech, captions, translations, audio and audio-device metadata, glossary contents, paths, network identifiers, operator data, and logs. The broader **Diagnostics** file is for support and can include Church Cap version, operating system version, CPU details, memory size, project drive capacity/free space, Python version, performance settings, CUDA/Apple runtime status, the same privacy-safe service measurements, and recent updater/CUDA log lines with local paths redacted. Diagnostics do not include audio, transcripts, captions, translated wording, operator passwords, session secrets, or `.env` contents. Operators should still review diagnostics before sharing because computer details, error messages, and logs may be sensitive. Do not post diagnostics publicly unless the file has been reviewed and the operator is comfortable sharing its contents.
