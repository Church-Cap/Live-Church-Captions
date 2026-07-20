#!/usr/bin/env python3
"""Play a PCM WAV sermon into an output/loopback device for repeatable tests."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sounddevice():
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - depends on the installed audio runtime
        raise RuntimeError(
            "The sounddevice package is unavailable. Run Church Cap from its installed virtual environment."
        ) from exc
    return sd


def output_devices() -> list[tuple[int, str]]:
    sd = _sounddevice()
    devices: list[tuple[int, str]] = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_output_channels") or 0) > 0:
            devices.append((index, str(info.get("name") or f"Device {index}")))
    return devices


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Play a PCM WAV recording to a selected output or virtual-loopback device in real time.",
    )
    parser.add_argument("wav", nargs="?", type=Path, help="PCM WAV sermon recording")
    parser.add_argument("--device", type=int, help="PortAudio output device number")
    parser.add_argument("--list-devices", action="store_true", help="List usable output devices and exit")
    parser.add_argument("--block-frames", type=int, default=4096, help="Playback block size (default: 4096)")
    parser.add_argument("--run-label", default="recorded-sermon", help="Non-sensitive comparison label")
    parser.add_argument("--language", action="append", default=[], help="Expected audience language code; repeat as needed")
    parser.add_argument("--timing-mode", choices=("live", "stable", "contextual", "extended"), help="Church Cap translation timing selected for the run")
    parser.add_argument("--provider", help="Church Cap translation provider label selected for the run")
    parser.add_argument("--repeat", type=int, help="Repeat number for this settings/input combination")
    parser.add_argument("--manifest-out", type=Path, help="Write a privacy-safe JSON run manifest")
    parser.add_argument("--dry-run", action="store_true", help="Validate the WAV and write the manifest without opening audio")
    return parser.parse_args()


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except FileNotFoundError:
                pass
        raise


def _manifest(args: argparse.Namespace, recording: wave.Wave_read, *, status: str) -> dict[str, Any]:
    sample_rate = recording.getframerate()
    return {
        "manifest_schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_label": str(args.run_label),
        "repeat": args.repeat,
        "status": status,
        "playback": {
            "mode": "real_time_external_loopback",
            "duration_seconds": round(recording.getnframes() / max(1, sample_rate), 3),
            "sample_rate_hz": sample_rate,
            "channels": recording.getnchannels(),
            "sample_width_bytes": recording.getsampwidth(),
            "block_frames": max(256, int(args.block_frames)),
            "output_device_index": args.device,
        },
        "church_cap_settings": {
            "audience_languages": sorted(set(str(item).lower() for item in args.language if str(item).strip())),
            "translation_timing_mode": args.timing_mode,
            "translation_provider": args.provider,
        },
        "limitations": [
            "Playback uses an external or virtual loopback device rather than an internal file audio source.",
            "Device routing and audio-driver buffering can affect measured latency.",
            "The manifest contains settings and labels only; evaluator annotations belong in a separate file.",
        ],
        "privacy": "No recording path, filename, audio, transcript, caption, translation, glossary content, or device name is stored.",
    }


def main() -> int:
    args = parse_args()
    if args.list_devices:
        try:
            for index, name in output_devices():
                print(f"{index}: {name}")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    if args.wav is None:
        print("Provide a PCM WAV file, or use --list-devices.", file=sys.stderr)
        return 2
    if not args.wav.is_file():
        print("Recording not found.", file=sys.stderr)
        return 2

    with wave.open(str(args.wav), "rb") as recording:
        if recording.getcomptype() != "NONE":
            print("Only uncompressed PCM WAV recordings are supported.", file=sys.stderr)
            return 2
        sample_width = recording.getsampwidth()
        dtype = {1: "uint8", 2: "int16", 4: "int32"}.get(sample_width)
        if dtype is None:
            print("Supported WAV sample widths are 8, 16, and 32 bit PCM.", file=sys.stderr)
            return 2
        sample_rate = recording.getframerate()
        channels = recording.getnchannels()
        duration = recording.getnframes() / max(1, sample_rate)
        if args.manifest_out:
            _atomic_json_write(args.manifest_out, _manifest(args, recording, status="validated" if args.dry_run else "started"))
        if args.dry_run:
            print(f"Validated PCM WAV: {duration:.1f}s, {sample_rate} Hz, {channels} channel(s).")
            return 0

        print(
            f"Playing recording: {duration:.1f}s, {sample_rate} Hz, {channels} channel(s). "
            "Press Ctrl+C to stop."
        )
        try:
            sd = _sounddevice()
            with sd.RawOutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype=dtype,
                device=args.device,
                blocksize=max(256, int(args.block_frames)),
            ) as stream:
                while True:
                    block = recording.readframes(max(256, int(args.block_frames)))
                    if not block:
                        break
                    stream.write(block)
        except KeyboardInterrupt:
            if args.manifest_out:
                _atomic_json_write(args.manifest_out, _manifest(args, recording, status="stopped_early"))
            print("Playback stopped.")
            return 130
        except Exception as exc:
            if args.manifest_out:
                _atomic_json_write(args.manifest_out, _manifest(args, recording, status="playback_failed"))
            print(f"Playback failed: {exc}", file=sys.stderr)
            return 1
        if args.manifest_out:
            _atomic_json_write(args.manifest_out, _manifest(args, recording, status="completed"))
    print("Playback complete. Stop captions, then download the anonymised service report before the next run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
