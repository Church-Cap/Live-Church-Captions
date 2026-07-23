"""Lower-latency local microphone/audio-interface transcription using faster-whisper.

This version uses a rolling audio buffer instead of waiting for a single large
recording chunk. It emits fast partial captions and only stores final captions
when speech pauses. This path is actively tuned for real live-caption
behaviour while keeping the standard transcription path available as a fallback.
"""
from __future__ import annotations

import asyncio
import time
import difflib
from collections import deque
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from app.models import CaptionSegment, RecognitionSpan
from app.metrics import (
    record_transcription,
    record_transcription_guard_event,
    record_transcription_input_trim,
    record_transcription_pass_interval,
    update_metrics,
)
from app.text_cleanup import clean_caption_text, collapse_repeated_phrase
from app.transcription.base import Transcriber
from app.transcription.audio_input import input_default_sample_rate, resample_mono
from app.hardware import detect_hardware_acceleration, resolve_whisper_runtime
from app.transcription.streaming_words import (
    IncompleteEdgeGuard,
    cadence_delay_seconds,
    looks_unreliable_hypothesis,
    speech_bounded_audio_range,
    should_suppress_silence_hypothesis,
)


class FasterWhisperTranscriber(Transcriber):
    def __init__(
        self,
        model_name: str = "base.en",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "en",
        audio_device: str | int | None = None,
        sample_rate: int = 16000,
        chunk_seconds: int = 2,
        stream_window_seconds: float = 6.0,
        stream_update_interval_seconds: float = 1.0,
        stream_silence_finalise_seconds: float = 1.35,
        stream_min_rms: float = 0.006,
        stream_stability_passes: int = 2,
        initial_prompt: str | None = None,
        word_timestamps_enabled: bool = True,
        edge_guard_seconds: float = 0.32,
        edge_confidence_threshold: float = 0.65,
        committed_audio_overlap_seconds: float = 1.0,
    ):
        self.model_name = model_name
        self.requested_device = device
        self.requested_compute_type = compute_type
        self.hardware_status = detect_hardware_acceleration()
        self.device, self.compute_type = resolve_whisper_runtime(device, compute_type, self.hardware_status)
        self.language = language
        self.audio_device = audio_device if audio_device not in {"", "none", "None"} else None
        self.sample_rate = int(sample_rate)
        self.input_sample_rate = self.sample_rate
        self.chunk_seconds = max(float(chunk_seconds), 0.5)
        self.window_seconds = max(float(stream_window_seconds), self.chunk_seconds)
        self.update_interval = max(float(stream_update_interval_seconds), 0.25)
        self.silence_finalise_seconds = max(float(stream_silence_finalise_seconds), 0.3)
        self.min_rms = max(float(stream_min_rms), 0.0)
        self.stability_passes = max(int(stream_stability_passes), 1)
        self.initial_prompt = " ".join(str(initial_prompt or "").split()).strip() or None
        self.word_timestamps_enabled = bool(word_timestamps_enabled)
        self.edge_guard_seconds = max(0.0, float(edge_guard_seconds))
        self.edge_confidence_threshold = min(1.0, max(0.0, float(edge_confidence_threshold)))
        self.committed_audio_overlap_seconds = max(0.5, float(committed_audio_overlap_seconds))
        # Keep enough post-speech audio for Silero to close its endpoint, then
        # let its short speech padding—not a long raw-silence tail—reach Whisper.
        self.speech_tail_padding_seconds = 0.35
        self._edge_guard = IncompleteEdgeGuard(
            margin_seconds=self.edge_guard_seconds,
            confidence_threshold=self.edge_confidence_threshold,
        )

        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._model: WhisperModel | None = None
        self._audio_lock = Lock()
        self._audio_buffer: deque[np.ndarray] = deque()
        self._max_buffer_samples = int(self.sample_rate * max(self.window_seconds + 2.0, 8.0))
        self._buffered_samples = 0
        self._audio_end_monotonic = 0.0
        self._trim_before_monotonic = 0.0
        self._last_voice_at = 0.0
        self._last_partial = ""
        self._last_final = ""
        self._stream: sd.InputStream | None = None
        self._stable_candidate = ""
        self._stable_count = 0
        update_metrics(model_name=self.model_name, model_device=self.device, model_compute_type=self.compute_type, audio_device=self.audio_device, sample_rate=self.sample_rate)

    def _load_model(self) -> WhisperModel:
        if self._model is None:
            started = time.monotonic()
            try:
                self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            except Exception as exc:
                if self.device != "cuda":
                    raise
                self.device = "cpu"
                self.compute_type = "int8"
                update_metrics(
                    model_device=self.device,
                    model_compute_type=self.compute_type,
                    error=f"CUDA model load failed; fell back to CPU: {exc}",
                )
                self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            update_metrics(model_loaded=True, model_load_seconds=time.monotonic() - started)
        return self._model

    def _audio_callback(self, indata, frames, time_info, status):  # pragma: no cover - needs audio hardware
        audio = np.asarray(indata, dtype=np.float32).reshape(-1).copy()
        if self.input_sample_rate != self.sample_rate:
            audio = resample_mono(audio, self.input_sample_rate, self.sample_rate)
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        now = time.monotonic()
        has_voice = rms >= self.min_rms
        if has_voice:
            self._last_voice_at = now
        voice_age = None if self._last_voice_at <= 0 else now - self._last_voice_at
        update_metrics(audio_rms=rms, audio_peak=peak, has_recent_voice=has_voice or self._has_recent_voice(), last_voice_age_seconds=voice_age, last_update_at=now)
        with self._audio_lock:
            self._audio_buffer.append(audio)
            self._buffered_samples += audio.size
            self._audio_end_monotonic = now
            while self._buffered_samples > self._max_buffer_samples and self._audio_buffer:
                removed = self._audio_buffer.popleft()
                self._buffered_samples -= removed.size

    def _start_audio_stream(self) -> None:
        def open_stream(device, samplerate: int):
            self.input_sample_rate = int(samplerate)
            stream = sd.InputStream(
                samplerate=self.input_sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                blocksize=max(512, int(self.input_sample_rate * 0.1)),
                callback=self._audio_callback,
            )
            stream.start()
            update_metrics(audio_device=device, sample_rate=self.sample_rate)
            return stream

        def open_with_native_rate(device, original_error: Exception):
            native_rate = input_default_sample_rate(device, self.sample_rate)
            if native_rate == self.sample_rate:
                raise original_error
            stream = open_stream(device, native_rate)
            update_metrics(
                error=(
                    f"Audio input opened at native {native_rate} Hz and is being resampled "
                    f"to {self.sample_rate} Hz for Faster Whisper. Original {self.sample_rate} Hz open failed: {original_error}"
                )
            )
            return stream

        try:
            self._stream = open_stream(self.audio_device, self.sample_rate)
        except Exception as exc:
            try:
                self._stream = open_with_native_rate(self.audio_device, exc)
                return
            except Exception as native_exc:
                if self.audio_device is None:
                    raise RuntimeError(
                        "Could not open the system default audio input. Check operating-system microphone/audio permissions, "
                        f"connect the USB audio interface, then refresh and choose an input on the operator page. Detail: {native_exc}"
                    ) from native_exc
            update_metrics(
                error=f"Selected audio input could not be opened; falling back to system default: {exc}",
                audio_device=None,
            )
            self.audio_device = None
            try:
                self._stream = open_stream(None, self.sample_rate)
            except Exception as fallback_exc:
                try:
                    self._stream = open_with_native_rate(None, fallback_exc)
                except Exception as native_default_exc:
                    raise RuntimeError(
                        "Could not open the selected audio input or the system default input. "
                        "Refresh the audio device list, choose a valid microphone/audio interface, save it, "
                        f"then start captions again. Detail: {native_default_exc}"
                    ) from native_default_exc

    def _latest_audio(self, seconds: float | None = None) -> tuple[np.ndarray, float]:
        seconds = seconds or self.window_seconds
        wanted = int(self.sample_rate * seconds)
        with self._audio_lock:
            if not self._audio_buffer:
                return np.zeros(0, dtype=np.float32), time.monotonic()
            parts = list(self._audio_buffer)
            audio_end = self._audio_end_monotonic or time.monotonic()
            trim_before = self._trim_before_monotonic
            last_voice_at = self._last_voice_at
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        selected = speech_bounded_audio_range(
            total_samples=audio.size,
            sample_rate=self.sample_rate,
            audio_end_monotonic=audio_end,
            last_voice_at=last_voice_at,
            window_seconds=seconds,
            tail_padding_seconds=self.speech_tail_padding_seconds,
            trim_before_monotonic=trim_before,
            committed_overlap_seconds=self.committed_audio_overlap_seconds,
        )
        record_transcription_input_trim(selected.trailing_silence_trimmed_seconds)
        audio = audio[selected.start_sample:selected.end_sample]
        capture_started = selected.capture_started_monotonic
        if audio.size > wanted:  # Defensive rounding bound.
            audio = audio[-wanted:]
            capture_started = (audio_end - selected.trailing_silence_trimmed_seconds) - (
                audio.size / max(1, self.sample_rate)
            )
        return audio.astype(np.float32, copy=False), capture_started

    def acknowledge_audio_until(self, end_monotonic: float | None) -> None:
        """Allow sealed audio to leave future rolling windows, keeping overlap."""
        if end_monotonic is None:
            return
        with self._audio_lock:
            self._trim_before_monotonic = max(self._trim_before_monotonic, float(end_monotonic))

    def _has_recent_voice(self) -> bool:
        return (time.monotonic() - self._last_voice_at) <= self.silence_finalise_seconds

    def reset_buffer(self) -> None:
        with self._audio_lock:
            self._audio_buffer.clear()
            self._buffered_samples = 0
            self._audio_end_monotonic = 0.0
            self._trim_before_monotonic = 0.0
        self._last_voice_at = 0.0
        self._last_partial = ""
        self._stable_candidate = ""
        self._stable_count = 0
        self._edge_guard.reset()


    def _transcribe_text(
        self,
        audio: np.ndarray,
        had_recent_voice_at_capture: bool = True,
        speech_progress_seconds: float | None = None,
    ) -> tuple[str, list[RecognitionSpan]]:
        if audio.size < int(self.sample_rate * 0.4):
            return "", []
        # Skip clear silence/noise. This keeps the model from inventing captions.
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        if rms < self.min_rms / 2:
            return "", []

        model = self._load_model()
        started = time.monotonic()
        segments, _info = model.transcribe(
            audio,
            language=self.language or None,
            beam_size=1,
            best_of=1,
            vad_filter=True,
            vad_parameters={
                "threshold": 0.5,
                "neg_threshold": 0.35,
                "min_speech_duration_ms": 100,
                "min_silence_duration_ms": 160,
                "speech_pad_ms": 100,
            },
            temperature=0.0,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.55,
            initial_prompt=self.initial_prompt,
            condition_on_previous_text=False,
            without_timestamps=False,
            word_timestamps=self.word_timestamps_enabled,
            hallucination_silence_threshold=(0.5 if self.word_timestamps_enabled else None),
        )
        materialised = list(segments)
        raw_words: list[str] = []
        word_spans: list[RecognitionSpan] = []
        if self.word_timestamps_enabled:
            for segment in materialised:
                for word in (getattr(segment, "words", None) or []):
                    raw_word = str(word.word or "")
                    clean_word = raw_word.strip()
                    if not clean_word:
                        continue
                    raw_words.append(raw_word)
                    word_spans.append(RecognitionSpan(
                        text=clean_word,
                        start_seconds=max(0.0, float(word.start)),
                        end_seconds=max(float(word.start), float(word.end)),
                        confidence=(
                            None
                            if getattr(word, "probability", None) is None
                            else float(word.probability)
                        ),
                        word_aligned=True,
                    ))

        full_text = (
            "".join(raw_words).strip()
            if raw_words
            else " ".join(" ".join(str(segment.text or "").split()) for segment in materialised).strip()
        )
        full_text = clean_caption_text(collapse_repeated_phrase(full_text))
        unreliable = looks_unreliable_hypothesis(
            full_text,
            no_speech_probabilities=tuple(
                float(segment.no_speech_prob)
                for segment in materialised
                if getattr(segment, "no_speech_prob", None) is not None
            ),
            average_log_probabilities=tuple(
                float(segment.avg_logprob)
                for segment in materialised
                if getattr(segment, "avg_logprob", None) is not None
            ),
        )
        if unreliable:
            self._edge_guard.reset()
            record_transcription(
                time.monotonic() - started,
                word_timestamps_used=bool(word_spans),
                aligned_words=len(word_spans),
            )
            record_transcription_guard_event(
                "unreliable_metadata",
                suppressed_words=len(full_text.split()),
            )
            return "", []

        edge_result = self._edge_guard.filter(
            word_spans,
            audio_duration_seconds=audio.size / max(1, self.sample_rate),
            protect_live_edge=had_recent_voice_at_capture,
            speech_progress_seconds=speech_progress_seconds,
        ) if word_spans else None
        if edge_result is not None:
            spans = list(edge_result.spans)
            text = "".join(raw_words[:len(spans)]).strip()
            withheld_words = edge_result.withheld_words
            confirmed_edge_words = edge_result.confirmed_edge_words
        else:
            spans = [
                RecognitionSpan(
                    text=" ".join(segment.text.split()),
                    start_seconds=max(0.0, float(segment.start)),
                    end_seconds=max(float(segment.start), float(segment.end)),
                )
                for segment in materialised
                if " ".join(segment.text.split())
            ]
            text = " ".join(span.text for span in spans).strip()
            withheld_words = 0
            confirmed_edge_words = 0
        text = clean_caption_text(collapse_repeated_phrase(text))
        record_transcription(
            time.monotonic() - started,
            word_timestamps_used=bool(word_spans),
            aligned_words=len(word_spans),
            edge_words_withheld=withheld_words,
            edge_words_confirmed=confirmed_edge_words,
        )
        return text, spans

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
        # Find a simple word overlap between the end of previous and start of text.
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
        """Require repeated agreement before committing final text.

        This reduces repeated or jumpy final captions from rolling windows while
        still allowing fast partial captions to appear immediately.
        """
        norm = self._normalise_text(text)
        if not norm:
            return False
        previous = self._normalise_text(self._stable_candidate)
        if previous and difflib.SequenceMatcher(None, previous, norm).ratio() >= 0.88:
            self._stable_count += 1
            # Keep the newest/fullest wording as the candidate.
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
        pending_final_spans: list[RecognitionSpan] = []
        pending_capture_started: float | None = None
        last_publish = 0.0
        next_pass_due = time.monotonic() + self.update_interval
        previous_pass_started: float | None = None

        while self._running:
            await asyncio.sleep(cadence_delay_seconds(
                pass_started=next_pass_due - self.update_interval,
                now=time.monotonic(),
                interval_seconds=self.update_interval,
            ))
            now = time.monotonic()
            if previous_pass_started is not None:
                record_transcription_pass_interval(now - previous_pass_started)
            previous_pass_started = now
            next_pass_due = now + self.update_interval
            audio, capture_started = self._latest_audio(self.window_seconds)
            had_recent_voice_at_capture = self._has_recent_voice()
            with self._audio_lock:
                last_voice_at_capture = self._last_voice_at
            speech_progress_seconds = max(0.0, last_voice_at_capture - capture_started)
            text, spans = await loop.run_in_executor(
                self._executor,
                self._transcribe_text,
                audio,
                had_recent_voice_at_capture,
                speech_progress_seconds,
            )
            source_ready = time.monotonic()
            text = " ".join(text.split()).strip()
            if should_suppress_silence_hypothesis(
                text,
                had_recent_voice_at_capture=had_recent_voice_at_capture,
            ):
                record_transcription_guard_event(
                    "silence_after_voice_grace",
                    suppressed_words=len(text.split()),
                )
                text = ""
                spans = []
            if not text:
                # Finalise whatever was last visible after a short silence.
                if pending_final_text and not self._has_recent_voice() and self._is_stable_enough(pending_final_text):
                    final_text = self._dedupe_against_previous(self._stable_candidate or pending_final_text, self._last_final)
                    if final_text and len(final_text.split()) >= 2:
                        self._last_final = (self._last_final + " " + final_text).strip()[-1200:]
                        yield CaptionSegment(
                            text=final_text,
                            raw_text=pending_final_text,
                            is_final=True,
                            capture_started_monotonic=pending_capture_started,
                            source_ready_monotonic=time.monotonic(),
                            recognition_spans=pending_final_spans,
                        )
                    pending_final_text = ""
                    pending_final_spans = []
                    pending_capture_started = None
                    self._last_partial = ""
                    self._stable_candidate = ""
                    self._stable_count = 0
                    self._edge_guard.reset()
                continue

            pending_final_text = text
            pending_final_spans = spans
            pending_capture_started = capture_started
            if text != self._last_partial and (now - last_publish) >= self.update_interval:
                self._last_partial = text
                last_publish = now
                yield CaptionSegment(
                    text=text,
                    raw_text=text,
                    is_final=False,
                    capture_started_monotonic=capture_started,
                    source_ready_monotonic=source_ready,
                    recognition_spans=spans,
                )

            if pending_final_text and not self._has_recent_voice() and self._is_stable_enough(pending_final_text):
                final_text = self._dedupe_against_previous(self._stable_candidate or pending_final_text, self._last_final)
                if final_text and len(final_text.split()) >= 2:
                    self._last_final = (self._last_final + " " + final_text).strip()[-1200:]
                    yield CaptionSegment(
                        text=final_text,
                        raw_text=pending_final_text,
                        is_final=True,
                        capture_started_monotonic=pending_capture_started,
                        source_ready_monotonic=time.monotonic(),
                        recognition_spans=pending_final_spans,
                    )
                pending_final_text = ""
                pending_final_spans = []
                pending_capture_started = None
                self._last_partial = ""
                self._stable_candidate = ""
                self._stable_count = 0
                self._edge_guard.reset()

    async def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._executor.shutdown(wait=False, cancel_futures=True)
