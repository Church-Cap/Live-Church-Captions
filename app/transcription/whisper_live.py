"""Local live transcription using the original OpenAI Whisper package.

This backend favours accuracy and consistency over lowest latency. It keeps the
same rolling-buffer contract as the faster-whisper backend, but uses standard
Whisper decoding with a modest beam search.
"""
from __future__ import annotations

import asyncio
import difflib
import platform
import re
import time
from collections import deque
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import numpy as np
import sounddevice as sd

from app.metrics import get_metrics, reset_metrics, update_metrics
from app.models import CaptionSegment
from app.text_cleanup import clean_caption_text, collapse_repeated_phrase
from app.transcription.base import Transcriber


class WhisperLiveTranscriber(Transcriber):
    def __init__(
        self,
        model_name: str = "base.en",
        device: str = "auto",
        language: str = "en",
        audio_device: str | int | None = None,
        sample_rate: int = 16000,
        chunk_seconds: int = 2,
        stream_window_seconds: float = 8.0,
        stream_update_interval_seconds: float = 1.2,
        stream_silence_finalise_seconds: float = 1.45,
        stream_min_rms: float = 0.006,
        stream_stability_passes: int = 2,
        initial_prompt: str | None = None,
        beam_size: int = 5,
    ):
        self.model_name = model_name
        self.requested_device = device
        self.device = self._resolve_device(device)
        self.language = language
        self.audio_device = audio_device if audio_device not in {"", "none", "None"} else None
        self.sample_rate = int(sample_rate)
        self.chunk_seconds = max(float(chunk_seconds), 0.5)
        self.window_seconds = max(float(stream_window_seconds), self.chunk_seconds)
        self.update_interval = max(float(stream_update_interval_seconds), 0.35)
        self.silence_finalise_seconds = max(float(stream_silence_finalise_seconds), 0.3)
        self.min_rms = max(float(stream_min_rms), 0.0)
        self.stability_passes = max(int(stream_stability_passes), 1)
        self.initial_prompt = " ".join(str(initial_prompt or "").split()).strip() or None
        self.beam_size = max(1, int(beam_size))

        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._model = None
        self._audio_lock = Lock()
        self._audio_buffer: deque[np.ndarray] = deque()
        self._max_buffer_samples = int(self.sample_rate * max(self.window_seconds + 2.0, 10.0))
        self._buffered_samples = 0
        self._last_voice_at = 0.0
        self._last_partial = ""
        self._last_final = ""
        self._stream: sd.InputStream | None = None
        self._stable_candidate = ""
        self._stable_count = 0
        reset_metrics()
        update_metrics(
            model_name=self.model_name,
            model_device=self.device,
            model_compute_type="fp16" if self.device == "cuda" else "fp32",
            audio_device=self.audio_device,
            sample_rate=self.sample_rate,
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        requested = (device or "auto").lower().strip()
        if requested == "cpu":
            return "cpu"
        if requested == "cuda":
            return "cuda"
        if requested == "mps":
            return "mps"
        if requested in {"cuda", "auto"}:
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
                if requested == "auto" and platform.system() == "Darwin" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                    return "mps"
            except Exception:
                pass
        return "cpu"

    def _load_model(self):
        if self._model is None:
            started = time.monotonic()
            try:
                import whisper
                self._model = whisper.load_model(self.model_name, device=self.device)
            except Exception as exc:
                if self.device not in {"cuda", "mps"}:
                    raise
                failed_device = self.device
                self.device = "cpu"
                update_metrics(
                    model_device=self.device,
                    model_compute_type="fp32",
                    error=f"{failed_device.upper()} model load failed; fell back to CPU: {exc}",
                )
                import whisper
                self._model = whisper.load_model(self.model_name, device=self.device)
            update_metrics(model_loaded=True, model_load_seconds=time.monotonic() - started)
        return self._model

    def _audio_callback(self, indata, frames, time_info, status):  # pragma: no cover - needs audio hardware
        audio = np.asarray(indata, dtype=np.float32).reshape(-1).copy()
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        now = time.monotonic()
        has_voice = rms >= self.min_rms
        if has_voice:
            self._last_voice_at = now
        voice_age = None if self._last_voice_at <= 0 else now - self._last_voice_at
        update_metrics(
            audio_rms=rms,
            audio_peak=peak,
            has_recent_voice=has_voice or self._has_recent_voice(),
            last_voice_age_seconds=voice_age,
            last_update_at=now,
        )
        with self._audio_lock:
            self._audio_buffer.append(audio)
            self._buffered_samples += audio.size
            while self._buffered_samples > self._max_buffer_samples and self._audio_buffer:
                removed = self._audio_buffer.popleft()
                self._buffered_samples -= removed.size

    def _start_audio_stream(self) -> None:
        def open_stream(device):
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                blocksize=max(512, int(self.sample_rate * 0.1)),
                callback=self._audio_callback,
            )
            stream.start()
            return stream

        try:
            self._stream = open_stream(self.audio_device)
        except Exception as exc:
            if self.audio_device is None:
                raise RuntimeError(
                    "Could not open the system default audio input. Check microphone permissions, "
                    "connect the USB audio interface, then refresh and choose an input on the operator page."
                ) from exc
            update_metrics(
                error=f"Selected audio input could not be opened; falling back to system default: {exc}",
                audio_device=None,
            )
            self.audio_device = None
            try:
                self._stream = open_stream(None)
            except Exception as fallback_exc:
                raise RuntimeError(
                    "Could not open the selected audio input or the system default input. "
                    "Refresh the audio device list, choose a valid microphone/audio interface, save it, "
                    "then start captions again."
                ) from fallback_exc

    def _latest_audio(self, seconds: float | None = None) -> np.ndarray:
        seconds = seconds or self.window_seconds
        wanted = int(self.sample_rate * seconds)
        with self._audio_lock:
            if not self._audio_buffer:
                return np.zeros(0, dtype=np.float32)
            parts = list(self._audio_buffer)
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        if audio.size > wanted:
            audio = audio[-wanted:]
        return audio.astype(np.float32, copy=False)

    def _has_recent_voice(self) -> bool:
        return (time.monotonic() - self._last_voice_at) <= self.silence_finalise_seconds

    def reset_buffer(self) -> None:
        with self._audio_lock:
            self._audio_buffer.clear()
            self._buffered_samples = 0
        self._last_voice_at = 0.0
        self._last_partial = ""
        self._stable_candidate = ""
        self._stable_count = 0


    def _transcribe_text(self, audio: np.ndarray) -> str:
        if audio.size < int(self.sample_rate * 0.5):
            return ""
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        if rms < self.min_rms / 2:
            return ""

        model = self._load_model()
        started = time.monotonic()
        result = model.transcribe(
            audio,
            language=self.language or None,
            task="transcribe",
            fp16=self.device == "cuda",
            beam_size=self.beam_size,
            patience=1.0,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.55,
            initial_prompt=self.initial_prompt,
            condition_on_previous_text=False,
            verbose=False,
        )
        text = " ".join(str(result.get("text") or "").split()).strip()
        text = clean_caption_text(collapse_repeated_phrase(text))
        if self._looks_unreliable_result(text, result):
            text = ""
        update_metrics(
            last_transcription_seconds=time.monotonic() - started,
            transcriptions_completed=int(get_metrics().get("transcriptions_completed") or 0) + 1,
        )
        return text

    @staticmethod
    def _looks_unreliable_result(text: str, result: dict) -> bool:
        if not text:
            return False
        segments = result.get("segments") or []
        if segments:
            no_speech = [float(seg.get("no_speech_prob") or 0.0) for seg in segments]
            avg_logprob = [float(seg.get("avg_logprob") or 0.0) for seg in segments if seg.get("avg_logprob") is not None]
            if no_speech and min(no_speech) >= 0.72:
                return True
            if avg_logprob and sum(avg_logprob) / len(avg_logprob) < -1.15:
                return True
        compact = re.sub(r"\s+", "", text)
        if re.search(r"(.)\1{7,}", compact):
            return True
        words = re.findall(r"[A-Za-z']+", text.lower())
        repeated = 1
        for previous, current in zip(words, words[1:]):
            repeated = repeated + 1 if current == previous else 1
            if repeated >= 6:
                return True
        if len(text) >= 80:
            non_word = sum(1 for char in text if not (char.isalnum() or char.isspace() or char in ".,;:!?'-\"()"))
            if non_word / max(len(text), 1) > 0.18:
                return True
        return False

    @staticmethod
    def _dedupe_against_previous(text: str, previous: str) -> str:
        text = " ".join(text.split()).strip()
        previous = " ".join(previous.split()).strip()
        if not text or not previous:
            return text
        if text == previous or text in previous:
            return ""
        if text.startswith(previous):
            return text[len(previous):].strip(" ,.;:-")
        prev_words = previous.split()
        text_words = text.split()
        max_overlap = min(len(prev_words), len(text_words), 12)
        for n in range(max_overlap, 0, -1):
            if [w.lower().strip(",.;:") for w in prev_words[-n:]] == [w.lower().strip(",.;:") for w in text_words[:n]]:
                return " ".join(text_words[n:]).strip()
        return text

    @staticmethod
    def _normalise_text(text: str) -> str:
        return " ".join(text.lower().replace("…", " ").replace(".", " ").replace(",", " ").replace(";", " ").replace(":", " ").split())

    def _is_stable_enough(self, text: str) -> bool:
        norm = self._normalise_text(text)
        if not norm:
            return False
        previous = self._normalise_text(self._stable_candidate)
        if previous and difflib.SequenceMatcher(None, previous, norm).ratio() >= 0.88:
            self._stable_count += 1
            if len(text) >= len(self._stable_candidate):
                self._stable_candidate = text
        else:
            self._stable_candidate = text
            self._stable_count = 1
        return self._stable_count >= self.stability_passes

    async def stream(self) -> AsyncIterator[CaptionSegment]:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._load_model)
        self._start_audio_stream()
        pending_final_text = ""
        last_publish = 0.0

        while self._running:
            await asyncio.sleep(self.update_interval)
            now = time.monotonic()
            audio = self._latest_audio(self.window_seconds)
            text = await loop.run_in_executor(self._executor, self._transcribe_text, audio)
            text = " ".join(text.split()).strip()
            if not text:
                if pending_final_text and not self._has_recent_voice() and self._is_stable_enough(pending_final_text):
                    final_text = self._dedupe_against_previous(self._stable_candidate or pending_final_text, self._last_final)
                    if final_text and len(final_text.split()) >= 2:
                        self._last_final = (self._last_final + " " + final_text).strip()[-1200:]
                        yield CaptionSegment(text=final_text, raw_text=pending_final_text, is_final=True)
                    pending_final_text = ""
                    self._last_partial = ""
                    self._stable_candidate = ""
                    self._stable_count = 0
                continue

            pending_final_text = text
            if text != self._last_partial and (now - last_publish) >= self.update_interval:
                self._last_partial = text
                last_publish = now
                yield CaptionSegment(text=text, raw_text=text, is_final=False)

            if pending_final_text and not self._has_recent_voice() and self._is_stable_enough(pending_final_text):
                final_text = self._dedupe_against_previous(self._stable_candidate or pending_final_text, self._last_final)
                if final_text and len(final_text.split()) >= 2:
                    self._last_final = (self._last_final + " " + final_text).strip()[-1200:]
                    yield CaptionSegment(text=final_text, raw_text=pending_final_text, is_final=True)
                pending_final_text = ""
                self._last_partial = ""
                self._stable_candidate = ""
                self._stable_count = 0

    async def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._executor.shutdown(wait=False, cancel_futures=True)
