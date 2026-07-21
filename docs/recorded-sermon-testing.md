# Recorded Sermon Translation Testing

Version: v0.7.1

Church Cap v0.7.1 retains up to five privacy-safe completed service summaries across app restarts. v0.7.0 advanced service-metrics to schema 9, which records word-alignment use, guarded-edge outcomes, actual recognition-pass cadence, cue latency, fair-queue and shutdown-drain evidence, translated draft/final publication counts, and first translated cue timing. Use the separate anonymised service report for comparisons; use the broader diagnostics export only when support also needs computer and log information.

## Prepare And Retain The Recording

Use a purpose-recorded or consented recording that the church is permitted to test. A 20–30 minute extract containing sermon speech, Bible references, names, prayers, notices, pauses, fast and slow speech, long clauses, and silence is more useful than a short microphone check.

Convert the extract to an uncompressed 8, 16, or 32-bit PCM WAV file. Store it in a local access-controlled test folder, do not commit it to the Church Cap repository, and agree a deletion date with the recording owner. Delete working copies and virtual-device recordings when the evaluation is complete.

The helper uses real-time external playback. Route its output into the same audio interface used by Church Cap, or use a virtual loopback device. This exercises the ordinary transcription, cleanup, source-unit builder, scheduler, translator, broadcast, and metrics paths, but device routing and audio-driver buffers can affect latency. It is not an internal file-source harness and does not support accelerated latency claims.

List playback outputs:

```bash
python3 scripts/play-recorded-sermon.py --list-devices
```

Validate a recording and create a settings-only manifest without opening audio:

```bash
python3 scripts/play-recorded-sermon.py "/path/to/sermon.wav" \
  --dry-run \
  --run-label "matrix-d-live-1" \
  --language fa --language zh-hant \
  --timing-mode live --provider both --repeat 1 \
  --manifest-out "/path/to/manifests/matrix-d-live-1.json"
```

Play the same file in real time by removing `--dry-run` and selecting an output:

```bash
python3 scripts/play-recorded-sermon.py "/path/to/sermon.wav" \
  --device 4 \
  --run-label "matrix-d-live-1" \
  --language fa --language zh-hant \
  --timing-mode live --provider both --repeat 1 \
  --manifest-out "/path/to/manifests/matrix-d-live-1.json"
```

The manifest contains settings, numeric WAV properties, a device index, labels, and limitations. It excludes the recording path and filename, device name, audio, captions, translations, transcripts, and glossary contents.

## Run A Test

1. Open **Operator → Diagnostics** and select **Reset test measurements** before the first comparison set.
2. Select the intended input or loopback device on the operator page.
3. Choose the provider, timing mode, and enabled languages recorded in the manifest.
4. Open one audience viewer for every translated language being measured. Work is viewer-demand driven.
5. Start captions, then start real-time playback.
6. Play the complete extract without changing performance, provider, timing, or language settings.
7. Stop captions after playback completes.
8. Download **Anonymised service report**. A new service may start safely because the previous five summaries are retained, but give each manifest and report matching external filenames.
9. Repeat each key input/settings combination at least three times.
10. Record human feedback separately and delete recordings according to the agreed retention date.

## Required Baseline Matrix

Use the same recording and representative audio level throughout. Run every row at least three times.

| Run | Audience viewers | Translation timing | Purpose |
| --- | --- | --- | --- |
| A | English only | Live | Protect source-caption latency |
| A2 | English only; include corrections and uninterrupted speech | Live | Confirm one cue is revised rather than repeated |
| B1 | Farsi | Live | Farsi live baseline |
| B2 | Farsi | More Stable | Farsi stability/readability comparison |
| B3 | Farsi | Responsive Context | Farsi first-cue latency, revision, and naturalness comparison |
| C1 | Simplified Chinese (`zh-Hans`) | Live | Simplified-script consistency baseline |
| C2 | Hong Kong Traditional Chinese (`zh-Hant`) | Live | Traditional-script and terminology baseline |
| C3 | Hong Kong Traditional Chinese (`zh-Hant`) | More Stable | Traditional stability/readability comparison |
| C4 | Hong Kong Traditional Chinese (`zh-Hant`) | Responsive Context | Traditional first-cue latency, revision, and naturalness comparison |
| D1 | Farsi and `zh-Hant` | Live | Queue and resource contention |
| D2 | Farsi and `zh-Hant` | More Stable | Stable-mode contention |
| D3 | Farsi and `zh-Hant` | Responsive Context | Responsive revision, queue contention, and delay |
| E1 | Farsi and `zh-Hant`, deliberately overloaded | Live | Backpressure and recovery evidence |
| E2 | Farsi and `zh-Hant`, deliberately overloaded | Responsive Context | Responsive coalescing, backpressure, and recovery evidence |

Also run the key matrix on one lower-powered reference machine when available. Disconnect network access for at least one installed-model service and replay run to prove the offline path.

## What The Service Report Measures

- run ID, app/schema versions, service start, stop, duration, and stop reason
- requested and actual transcription model/device/compute identity and load duration
- transcription compute, English source-ready-to-publish, the operational refresh/transcription/publication response estimate, and the separately labelled oldest-audio-frame rolling-window upper bound
- per-language first translated cue publication from the first English cue update, translated draft/final publication counts, and source-ready-to-translated-publish delay
- Faster-Whisper word-timestamp passes, aligned-word count, weak edge words withheld/confirmed, and actual start-to-start pass interval
- partial/final source counts and transcript-commit counts
- source-unit draft revisions, drafts with a stable prefix, maximum stable-prefix and mutable-tail word counts, final units, maximum revision, final boundary reasons, and cue lifetime
- per-language enqueue/start/completion, queue wait, provider compute, and source-to-translated-publish timing
- applied, unchanged, failed, unavailable, retry, provider-fallback, source-shown, and completed-but-not-published outcomes with allow-listed reasons
- requested/actual provider counts and fallback attempts
- draft coalescing, draft-first backpressure, durable-final overflow, maximum queue depth, stale/no-viewer outcomes, and degraded/recovery events by language and total
- pending and in-flight work at Stop, work drained within two seconds, explicit cancellations, and whether the bounded drain timed out
- current/peak viewers and viewer-seconds by language, including viewers connected before captions start
- Church Cap process CPU/RSS and system CPU/memory average, p95, peak, and sample count

Percentiles use a bounded reservoir while counts, averages, and peaks cover the complete run. `estimated_capture_to_english` uses the oldest audio frame in the rolling transcription window and is labelled as a rolling-window upper bound rather than perceived caption latency. `estimated_english_operational_response` adds the configured refresh interval to transcription and English publication stage percentiles. It is more useful for same-hardware responsiveness comparisons, but it is still not true microphone-to-browser latency because browser transport and rendering are not measured.

The anonymised report contains no audio, audio-device metadata, source or translated captions, transcripts, glossary contents, paths, network identifiers, operator data, or logs. The broader diagnostics file remains support-sensitive because it includes computer details and redacted logs.

## Human Review Notes

Keep evaluator annotations separate from manifests, service reports, and diagnostics. A safe structure records only timecodes, categories, scores, and non-content issue labels:

```json
{
  "evaluation_schema_version": 1,
  "run_label": "matrix-d-live-1",
  "language": "fa",
  "ratings": {
    "naturalness": 4,
    "meaning_preserved": 4,
    "church_terminology": 3,
    "completeness": 4,
    "reading_comfort": 4
  },
  "issues": [
    {"timecode_seconds": 315, "category": "terminology", "severity": 2}
  ]
}
```

For both Chinese choices, also record `script_consistency` and classify mixed-script issues without copying sermon wording into a public report. Hong Kong reviewers should separately score Traditional-character consistency, regional wording, naturalness, and whether the Mandarin translation itself preserves meaning; OpenCC guarantees the selected script profile but does not translate Mandarin into Cantonese.

## Cue Engine Acceptance Checks

Run A/A2 on v0.7.1 before the multilingual matrix. If a release-to-release baseline is useful, compare against the published v0.6.0 release using the same recording, audio route, Faster-Whisper model, device, and timing preset. Confirm that safe words remain prompt while weak, incomplete edge guesses appear less often. `source_units.engine` must be `word_timestamp_local_agreement_v5` and `interim_strategy` must be `immediate_stable_prefix_guarded_edge_tail`; Faster-Whisper runs must show non-zero `word_timestamp_passes` and `aligned_words`. If transcription compute p95 is below the configured update interval, `transcription_streaming.pass_interval` p95 should remain close to that interval instead of interval plus compute time. Review `edge_words_withheld` and `edge_words_confirmed` alongside the viewer: zero is valid for a high-confidence passage, but sustained withholding without confirmation suggests thresholds are too strict. Cue-processing p95 should remain at or below 0.010 seconds and maximum below 0.025 seconds on the appliance. A correction may still change the newest mutable wording, but completed lines must keep position, the correction must not append a duplicate, and sealing must not move the lines. Check stable/mutable word counts, cue lifetime, final units, boundary reasons, queue pressure, recovery, and Stop accounting as before. The report proves scheduling behaviour, not caption or translation quality.

Record passage-level preferences between Responsive Context, Live, and More Stable, not only one overall score. Responsive Context should remain recommended only if Farsi and Hong Kong Traditional reviewers find its meaning and reading experience at least as good as the controls while first translated cue p50 remains at or below 3 seconds and p95 at or below 5 seconds on the reference appliance. Check that revisions replace one cue and that completed translations neither change nor reappear. Do not publish private sermon wording in issues or attach the recording to a public bug report.
