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

The prototype includes retention controls. When transcript saving is enabled, retained caption text is cached locally in the per-user Church Cap data folder for the configured retention window. The transcript cache is encrypted at rest when the installed Python environment includes the `cryptography` dependency. Operator-only export can download the current-session transcript as text, subtitle, or JSON files after a privacy warning. Sensitive moment mode suppresses visible captions, retained transcript entries, and transcript export content for that period. Exported files are outside Church Cap retention controls once saved elsewhere, so churches should only export where they have a clear reason and policy basis to keep or share the transcript. Clearing the transcript, disabling transcript saving, or setting retention to no history deletes the retained transcript cache.

The safest default for sensitive environments is to retain as little as possible.

## Cloud services

If cloud transcription, translation, remote diagnostics, analytics, or public livestream integrations are added later, they should be clearly documented and disabled by default unless the church intentionally enables them.
