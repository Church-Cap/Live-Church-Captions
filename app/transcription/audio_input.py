"""Audio-device helpers for local live transcription.

Linux USB audio interfaces often expose capture at a native rate such as
48 kHz. Whisper still wants 16 kHz audio, so the transcribers try the requested
rate first and fall back to opening the device at its native rate when needed.
"""
from __future__ import annotations

import numpy as np
import sounddevice as sd


def input_default_sample_rate(device: str | int | None, fallback: int) -> int:
    """Return the default input sample rate for a PortAudio device."""
    try:
        info = sd.query_devices(device, "input")
    except Exception:
        try:
            info = sd.query_devices(device)
        except Exception:
            return int(fallback)
    try:
        rate = int(round(float(info.get("default_samplerate") or 0)))
    except Exception:
        rate = 0
    return rate if rate > 0 else int(fallback)


def resample_mono(audio: np.ndarray, input_rate: int, output_rate: int) -> np.ndarray:
    """Small NumPy linear resampler for mono speech audio."""
    input_rate = int(input_rate)
    output_rate = int(output_rate)
    if input_rate <= 0 or output_rate <= 0 or input_rate == output_rate or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    output_size = max(1, int(round(audio.size * (output_rate / input_rate))))
    if output_size == audio.size:
        return audio.astype(np.float32, copy=False)
    source_positions = np.linspace(0.0, 1.0, num=audio.size, endpoint=False, dtype=np.float64)
    target_positions = np.linspace(0.0, 1.0, num=output_size, endpoint=False, dtype=np.float64)
    return np.interp(target_positions, source_positions, audio).astype(np.float32, copy=False)
