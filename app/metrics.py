from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from app.paths import data_path

logger = logging.getLogger(__name__)

SERVICE_METRICS_SCHEMA_VERSION = 9
SERVICE_REPORT_SCHEMA_VERSION = 1
MAX_COMPLETED_SERVICES = 5
MAX_RESERVOIR_SAMPLES = 2048

_TRANSLATION_NOT_PUBLISHED_REASONS = {
    "stale_after_compute",
    "no_language_viewers_after_compute",
    "service_stopped",
    "send_failed",
    "unspecified",
}

_lock = Lock()
_storage_path = data_path("service_metrics.json")
_rng = random.Random()


@dataclass
class RuntimeMetrics:
    audio_rms: float = 0.0
    audio_peak: float = 0.0
    has_recent_voice: bool = False
    last_voice_age_seconds: float | None = None
    model_name: str = ""
    model_device: str = ""
    model_compute_type: str = ""
    model_loaded: bool = False
    model_load_seconds: float | None = None
    last_transcription_seconds: float | None = None
    last_update_at: float | None = None
    transcriptions_completed: int = 0
    last_transcription_pass_interval_seconds: float | None = None
    word_timestamps_enabled: bool = False
    word_timestamp_words: int = 0
    edge_words_withheld: int = 0
    edge_words_confirmed: int = 0
    last_translation_seconds: float | None = None
    last_translation_at: float | None = None
    translations_completed: int = 0
    audio_device: str | int | None = None
    sample_rate: int = 16000
    error: str | None = None


class _Series:
    """Streaming aggregates plus a bounded uniform reservoir for percentiles."""

    def __init__(self, capacity: int = MAX_RESERVOIR_SAMPLES):
        self.capacity = max(32, int(capacity))
        self.count = 0
        self.total = 0.0
        self.maximum: float | None = None
        self.samples: list[float] = []

    def add(self, value: float) -> None:
        value = max(0.0, float(value))
        self.count += 1
        self.total += value
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        if len(self.samples) < self.capacity:
            self.samples.append(value)
            return
        replacement = _rng.randrange(self.count)
        if replacement < self.capacity:
            self.samples[replacement] = value

    def summary(self) -> dict[str, Any]:
        if self.count <= 0:
            return {
                "samples": 0,
                "average_seconds": None,
                "p50_seconds": None,
                "p95_seconds": None,
                "maximum_seconds": None,
                "percentile_method": "bounded_reservoir",
            }
        return {
            "samples": self.count,
            "average_seconds": round(self.total / self.count, 4),
            "p50_seconds": _percentile(self.samples, 0.50),
            "p95_seconds": _percentile(self.samples, 0.95),
            "maximum_seconds": round(float(self.maximum or 0.0), 4),
            "percentile_method": "bounded_reservoir",
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 4)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 4)


def _resource_summary(series: _Series) -> dict[str, Any]:
    summary = series.summary()
    return {
        "samples": summary["samples"],
        "average": summary["average_seconds"],
        "p50": summary["p50_seconds"],
        "p95": summary["p95_seconds"],
        "peak": summary["maximum_seconds"],
        "percentile_method": summary["percentile_method"],
    }


def _stage_sum_seconds(
    transcription_value: float | None,
    refresh_seconds: float,
    publish_value: float | None,
) -> float | None:
    if transcription_value is None:
        return None
    return round(
        float(transcription_value)
        + max(0.0, float(refresh_seconds))
        + (0.0 if publish_value is None else float(publish_value)),
        4,
    )


def _operational_english_estimate(
    transcription: dict[str, Any],
    english_publish: dict[str, Any],
    refresh_seconds: float,
) -> dict[str, Any]:
    """Return a stage-sum responsiveness estimate, never a true end-to-end claim."""
    transcription_samples = max(0, int(transcription.get("samples") or 0))
    publish_samples = max(0, int(english_publish.get("samples") or 0))
    return {
        "samples": transcription_samples,
        "transcription_samples": transcription_samples,
        "english_publish_samples": publish_samples,
        "average_seconds": _stage_sum_seconds(
            transcription.get("average_seconds"),
            refresh_seconds,
            english_publish.get("average_seconds"),
        ),
        "p50_seconds": _stage_sum_seconds(
            transcription.get("p50_seconds"),
            refresh_seconds,
            english_publish.get("p50_seconds"),
        ),
        "p95_seconds": _stage_sum_seconds(
            transcription.get("p95_seconds"),
            refresh_seconds,
            english_publish.get("p95_seconds"),
        ),
        "maximum_seconds": _stage_sum_seconds(
            transcription.get("maximum_seconds"),
            refresh_seconds,
            english_publish.get("maximum_seconds"),
        ),
        "percentile_method": "sum_of_stage_percentiles",
        "estimate_method": "configured_refresh_plus_transcription_compute_plus_english_publish_when_available",
        "includes_english_publish_stage": publish_samples > 0,
        "interpretation": "Operational responsiveness estimate; not true microphone-to-browser end-to-end latency.",
    }


def _safe_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    return str(value)


_CONFIGURATION_FIELDS = {
    "transcriber_mode",
    "whisper_model",
    "whisper_device_requested",
    "whisper_compute_type_requested",
    "stream_update_interval_seconds",
    "stream_window_seconds",
    "word_timestamps_enabled",
    "edge_guard_seconds",
    "translation_enabled",
    "translation_provider",
    "translation_timing_mode",
    "translation_allowed_languages",
    "translation_max_active_languages",
    "translation_queue_capacity_per_language",
}

_SAFE_ENUMS = {
    "transcriber_mode": {"whisper", "faster_whisper"},
    "whisper_model": {"tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large", "large-v2", "large-v3"},
    "whisper_device_requested": {"auto", "cpu", "cuda", "mps"},
    "whisper_compute_type_requested": {"auto", "int8", "int8_float16", "float16", "float32", "fp16", "fp32"},
    "translation_provider": {"disabled", "argos", "both", "ct2small100", "small100", "demo"},
    "translation_timing_mode": {"live", "stable", "responsive"},
}
_PROVIDER_LABELS = {"disabled", "argos", "both", "ct2small100", "small100", "demo"}
_LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}$", re.IGNORECASE)


def _safe_configuration(configuration: dict[str, Any] | None) -> dict[str, Any]:
    source = configuration or {}
    result: dict[str, Any] = {}
    for key in sorted(_CONFIGURATION_FIELDS):
        if key not in source:
            continue
        value = source[key]
        if key in _SAFE_ENUMS:
            clean = str(value or "").lower()
            result[key] = clean if clean in _SAFE_ENUMS[key] else "custom"
        elif key == "translation_allowed_languages":
            result[key] = sorted({
                str(item).lower()
                for item in (value if isinstance(value, (list, tuple, set)) else [])
                if _LANGUAGE_CODE_RE.fullmatch(str(item))
            })
        elif key in {"translation_enabled", "word_timestamps_enabled"}:
            result[key] = bool(value)
        elif key in {"translation_max_active_languages", "translation_queue_capacity_per_language"}:
            try:
                result[key] = max(0, min(100, int(value or 0)))
            except (TypeError, ValueError):
                result[key] = 0
        elif key in {"stream_update_interval_seconds", "stream_window_seconds", "edge_guard_seconds"}:
            try:
                result[key] = round(max(0.0, min(300.0, float(value or 0.0))), 4)
            except (TypeError, ValueError):
                result[key] = 0.0
    return result


def _empty_summary(message: str | None = None) -> dict[str, Any]:
    return {
        "status": "not_started",
        "message": message or "No caption service measurements are available.",
        "availability_state": "no_service_in_this_process",
        "service_metrics_schema_version": SERVICE_METRICS_SCHEMA_VERSION,
        "run_id": None,
        "app_version": None,
        "diagnostics_schema_version": None,
        "started_at": None,
        "stopped_at": None,
        "duration_seconds": None,
        "stop_reason": None,
        "configuration": {},
        "load_identity": {},
        "transcription_latency": _Series().summary(),
        "transcription_streaming": {
            "scheduling_strategy": "deadline_start_to_start",
            "word_timestamp_passes": 0,
            "aligned_words": 0,
            "edge_words_withheld": 0,
            "edge_words_confirmed": 0,
            "pass_interval": _Series().summary(),
        },
        "english_publish_delay": _Series().summary(),
        "estimated_capture_to_english": {
            **_Series().summary(),
            "estimate_method": "oldest_audio_frame_to_english_send_complete",
            "interpretation": "Rolling-window upper bound; not perceived caption latency.",
        },
        "estimated_english_operational_response": _operational_english_estimate(
            _Series().summary(),
            _Series().summary(),
            0.0,
        ),
        "estimated_english_audience_delay": {
            **_operational_english_estimate(_Series().summary(), _Series().summary(), 0.0),
            "compatibility_alias_for": "estimated_english_operational_response",
        },
        "caption_counts": {"partial": 0, "final": 0, "transcript_commits": 0},
        "source_units": {
            "engine": "word_timestamp_local_agreement_v5",
            "interim_strategy": "immediate_stable_prefix_guarded_edge_tail",
            "draft_revisions": 0,
            "drafts_with_stable_prefix": 0,
            "final_units": 0,
            "maximum_revision": 0,
            "maximum_stable_prefix_words": 0,
            "maximum_mutable_tail_words": 0,
            "boundary_reasons": {},
            "processing_latency": _Series().summary(),
            "cue_lifetime": _Series().summary(),
        },
        "translation_languages": {},
        "translation_scheduler": {
            "scheduler_type": "bounded_fair_per_language",
            "queue_capacity_per_language": 0,
            "batches_queued": 0,
            "pending_batches_replaced": 0,
            "language_jobs_queued": 0,
            "language_jobs_started": 0,
            "language_jobs_completed": 0,
            "language_jobs_skipped_stale": 0,
            "language_jobs_skipped_no_viewers": 0,
            "partial_jobs_superseded": 0,
            "final_batches_replaced": 0,
            "final_jobs_superseded": 0,
            "draft_jobs_coalesced": 0,
            "draft_jobs_dropped_backpressure": 0,
            "draft_jobs_rejected_backpressure": 0,
            "final_jobs_preserved_over_capacity": 0,
            "degraded_events": 0,
            "recovery_events": 0,
            "max_queue_depth_by_language": {},
            "by_language": {},
            "shutdown": {
                "drain_timeout_seconds": None,
                "pending_at_stop": 0,
                "in_flight_at_stop": 0,
                "drained_after_stop": 0,
                "cancelled_at_stop": 0,
                "timed_out": False,
                "by_language": {},
            },
        },
        "viewer_counts_current": {},
        "viewer_counts_peak": {},
        "viewer_seconds": {},
        "resources": {},
        "system_samples": 0,
        "cpu_percent_peak": None,
        "memory_used_percent_peak": None,
        "errors": 0,
        "privacy": "Numeric service measurements only; no audio, captions, transcripts, translated text, glossary contents, device names, network identifiers, or operator data are retained.",
    }


def _new_service(configuration: dict[str, Any] | None = None) -> dict[str, Any]:
    configuration = dict(configuration or {})
    raw_app_version = str(configuration.pop("app_version", ""))
    app_version = raw_app_version if re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?", raw_app_version) else "unknown"
    try:
        diagnostics_schema_version = max(0, int(configuration.pop("diagnostics_schema_version", 0)))
    except (TypeError, ValueError):
        diagnostics_schema_version = 0
    return {
        "status": "running",
        "message": "Caption service metrics are being collected.",
        "run_id": str(uuid4()),
        "app_version": app_version,
        "diagnostics_schema_version": diagnostics_schema_version,
        "service_metrics_schema_version": SERVICE_METRICS_SCHEMA_VERSION,
        "started_at": _utc_now(),
        "stopped_at": None,
        "duration_seconds": None,
        "stop_reason": None,
        "configuration": _safe_configuration(configuration),
        "load_identity": {},
        "series": {
            "transcription": _Series(),
            "transcription_pass_interval": _Series(),
            "english_publish": _Series(),
            "capture_to_english": _Series(),
            "cue_processing": _Series(),
            "cue_lifetime": _Series(),
        },
        "caption_counts": {"partial": 0, "final": 0, "transcript_commits": 0},
        "transcription_streaming": {
            "scheduling_strategy": "deadline_start_to_start",
            "word_timestamp_passes": 0,
            "aligned_words": 0,
            "edge_words_withheld": 0,
            "edge_words_confirmed": 0,
        },
        "source_units": {
            "engine": "word_timestamp_local_agreement_v5",
            "interim_strategy": "immediate_stable_prefix_guarded_edge_tail",
            "draft_revisions": 0,
            "drafts_with_stable_prefix": 0,
            "final_units": 0,
            "maximum_revision": 0,
            "maximum_stable_prefix_words": 0,
            "maximum_mutable_tail_words": 0,
            "boundary_reasons": {},
        },
        "translation_languages": {},
        "translation_scheduler": {
            "scheduler_type": "bounded_fair_per_language",
            "queue_capacity_per_language": int(
                _safe_configuration(configuration).get("translation_queue_capacity_per_language") or 0
            ),
            "batches_queued": 0,
            "pending_batches_replaced": 0,
            "language_jobs_queued": 0,
            "language_jobs_started": 0,
            "language_jobs_completed": 0,
            "language_jobs_skipped_stale": 0,
            "language_jobs_skipped_no_viewers": 0,
            "partial_jobs_superseded": 0,
            "final_batches_replaced": 0,
            "final_jobs_superseded": 0,
            "draft_jobs_coalesced": 0,
            "draft_jobs_dropped_backpressure": 0,
            "draft_jobs_rejected_backpressure": 0,
            "final_jobs_preserved_over_capacity": 0,
            "degraded_events": 0,
            "recovery_events": 0,
            "max_queue_depth_by_language": {},
            "by_language": {},
            "shutdown": {
                "drain_timeout_seconds": None,
                "pending_at_stop": 0,
                "in_flight_at_stop": 0,
                "drained_after_stop": 0,
                "cancelled_at_stop": 0,
                "timed_out": False,
                "by_language": {},
            },
        },
        "viewer_counts_current": {},
        "viewer_counts_peak": {},
        "viewer_seconds": {},
        "resources": {
            "system_cpu_percent": _Series(),
            "system_memory_used_percent": _Series(),
            "process_cpu_percent": _Series(),
            "process_rss_mib": _Series(),
        },
        "errors": 0,
    }


def _new_translation_entry() -> dict[str, Any]:
    return {
        "compute": _Series(),
        "queue_wait": _Series(),
        "source_to_publish": _Series(),
        "cue_first_publish": _Series(),
        "completed": 0,
        "started": 0,
        "published": 0,
        "drafts_published": 0,
        "finals_published": 0,
        "not_published": 0,
        "not_published_reasons": {},
        "applied": 0,
        "unchanged": 0,
        "failures": 0,
        "unavailable": 0,
        "source_fallbacks": 0,
        "provider_fallbacks": 0,
        "retries": 0,
        "requested_provider_counts": {},
        "actual_provider_counts": {},
    }


def _scheduler_language_entry(scheduler: dict[str, Any], language: str) -> dict[str, int]:
    return scheduler["by_language"].setdefault(language, {
        "queued": 0,
        "started": 0,
        "completed": 0,
        "partial_superseded": 0,
        "final_superseded": 0,
        "skipped_stale": 0,
        "skipped_no_viewers": 0,
        "draft_jobs_coalesced": 0,
        "draft_jobs_dropped_backpressure": 0,
        "draft_jobs_rejected_backpressure": 0,
        "final_jobs_preserved_over_capacity": 0,
        "degraded_events": 0,
        "recovery_events": 0,
    })


def _summarise_service(service: dict[str, Any], *, now_monotonic: float | None = None) -> dict[str, Any]:
    summary = {
        "status": service["status"],
        "message": service["message"],
        "availability_state": "active_service" if service["status"] == "running" else "completed_service_available",
        "service_metrics_schema_version": SERVICE_METRICS_SCHEMA_VERSION,
        "run_id": service["run_id"],
        "app_version": service.get("app_version"),
        "diagnostics_schema_version": service.get("diagnostics_schema_version"),
        "started_at": service["started_at"],
        "stopped_at": service.get("stopped_at"),
        "duration_seconds": service.get("duration_seconds"),
        "stop_reason": service.get("stop_reason"),
        "configuration": dict(service["configuration"]),
        "load_identity": dict(service["load_identity"]),
        "transcription_latency": service["series"]["transcription"].summary(),
        "transcription_streaming": json.loads(json.dumps(service["transcription_streaming"])),
        "english_publish_delay": service["series"]["english_publish"].summary(),
        "estimated_capture_to_english": service["series"]["capture_to_english"].summary(),
        "caption_counts": dict(service["caption_counts"]),
        "source_units": json.loads(json.dumps(service["source_units"])),
        "translation_scheduler": json.loads(json.dumps(service["translation_scheduler"])),
        "viewer_counts_current": dict(service["viewer_counts_current"]),
        "viewer_counts_peak": dict(service["viewer_counts_peak"]),
        "viewer_seconds": {key: round(value, 2) for key, value in service["viewer_seconds"].items()},
        "errors": int(service["errors"]),
    }
    summary["source_units"]["processing_latency"] = service["series"]["cue_processing"].summary()
    summary["source_units"]["cue_lifetime"] = service["series"]["cue_lifetime"].summary()
    summary["transcription_streaming"]["pass_interval"] = service["series"]["transcription_pass_interval"].summary()
    if service["status"] == "running" and now_monotonic is not None and _service_started_monotonic is not None:
        summary["duration_seconds"] = round(max(0.0, now_monotonic - _service_started_monotonic), 2)

    capture_summary = summary["estimated_capture_to_english"]
    capture_summary["estimate_method"] = "oldest_audio_frame_to_english_send_complete"
    capture_summary["interpretation"] = "Rolling-window upper bound; not perceived caption latency."

    refresh = float(service["configuration"].get("stream_update_interval_seconds") or 0.0)
    operational_response = _operational_english_estimate(
        summary["transcription_latency"],
        summary["english_publish_delay"],
        refresh,
    )
    summary["estimated_english_operational_response"] = operational_response
    summary["estimated_english_audience_delay"] = {
        **operational_response,
        "compatibility_alias_for": "estimated_english_operational_response",
    }

    languages: dict[str, Any] = {}
    for language, entry in service["translation_languages"].items():
        source_to_publish = entry["source_to_publish"].summary()
        cue_first_publish = entry["cue_first_publish"].summary()
        cue_first_publish["measurement_method"] = "first_english_cue_update_to_first_translated_cue_send_complete"
        cue_first_publish["interpretation"] = "Includes stable-English accumulation, debounce, queue wait, provider compute, and publication for the first visible revision of each cue."
        audience_delay = cue_first_publish if cue_first_publish["samples"] else source_to_publish
        languages[language] = {
            "completed": entry["completed"],
            "started": entry["started"],
            "published": entry["published"],
            "drafts_published": entry["drafts_published"],
            "finals_published": entry["finals_published"],
            "not_published": entry["not_published"],
            "not_published_reasons": dict(entry["not_published_reasons"]),
            "applied": entry["applied"],
            "unchanged": entry["unchanged"],
            "failures": entry["failures"],
            "unavailable": entry["unavailable"],
            "source_fallbacks": entry["source_fallbacks"],
            "provider_fallbacks": entry["provider_fallbacks"],
            "retries": entry["retries"],
            "requested_provider_counts": dict(entry["requested_provider_counts"]),
            "actual_provider_counts": dict(entry["actual_provider_counts"]),
            "latency": entry["compute"].summary(),
            "queue_wait": entry["queue_wait"].summary(),
            "source_to_translated_publish": source_to_publish,
            "cue_first_translation_publish": cue_first_publish,
            "estimated_audience_delay": {
                **audience_delay,
                "compatibility_alias_for": "cue_first_translation_publish" if cue_first_publish["samples"] else "source_to_translated_publish",
            },
        }
    summary["translation_languages"] = languages

    resources = {
        key: _resource_summary(series)
        for key, series in service["resources"].items()
    }
    summary["resources"] = resources
    summary["system_samples"] = resources["system_cpu_percent"]["samples"]
    summary["cpu_percent_peak"] = resources["system_cpu_percent"]["peak"]
    summary["memory_used_percent_peak"] = resources["system_memory_used_percent"]["peak"]
    summary["privacy"] = "Numeric service measurements only; no audio, captions, transcripts, translated text, glossary contents, device names, network identifiers, or operator data are retained."
    return summary


_metrics = RuntimeMetrics()
_current_service: dict[str, Any] | None = None
_latest_completed_services: list[dict[str, Any]] = []
_interrupted_service: dict[str, Any] | None = None
_availability_state = "no_service_in_this_process"
_service_started_monotonic: float | None = None
_viewer_last_monotonic: float | None = None
_storage_initialised = False


def _store_payload_locked() -> dict[str, Any]:
    active_marker = None
    if _current_service is not None:
        active_marker = {
            key: _safe_json_value(_current_service.get(key))
            for key in (
                "run_id",
                "app_version",
                "diagnostics_schema_version",
                "service_metrics_schema_version",
                "started_at",
                "configuration",
                "load_identity",
            )
        }
    return {
        "service_metrics_schema_version": SERVICE_METRICS_SCHEMA_VERSION,
        "availability_state": _availability_state,
        "latest_completed_services": _latest_completed_services[:MAX_COMPLETED_SERVICES],
        "interrupted_service": _interrupted_service,
        "active_run": active_marker,
    }


def _persist_store_locked() -> None:
    payload = json.dumps(_store_payload_locked(), indent=2, sort_keys=True).encode("utf-8")
    tmp_name: str | None = None
    try:
        _storage_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=_storage_path.parent,
            prefix=f"{_storage_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, _storage_path)
        try:
            _storage_path.chmod(0o600)
        except Exception:
            pass
    except Exception as exc:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except FileNotFoundError:
                pass
        logger.warning("Service metrics could not be persisted; live captions will continue: %s", exc)


def initialise_service_metrics_storage(path: str | Path | None = None) -> None:
    """Load retained summaries and convert any abandoned active marker to incomplete."""
    global _storage_path, _latest_completed_services, _interrupted_service
    global _availability_state, _storage_initialised, _current_service
    global _service_started_monotonic, _viewer_last_monotonic
    with _lock:
        if path is not None:
            _storage_path = Path(path)
        _latest_completed_services = []
        _interrupted_service = None
        _current_service = None
        _service_started_monotonic = None
        _viewer_last_monotonic = None
        stored_state = "no_service_in_this_process"
        active_marker = None
        try:
            payload = json.loads(_storage_path.read_text(encoding="utf-8")) if _storage_path.exists() else {}
            if int(payload.get("service_metrics_schema_version") or 0) in {3, 4, 5, 6, 7, 8, SERVICE_METRICS_SCHEMA_VERSION}:
                _latest_completed_services = [
                    item for item in payload.get("latest_completed_services", [])
                    if isinstance(item, dict)
                ][:MAX_COMPLETED_SERVICES]
                interrupted = payload.get("interrupted_service")
                _interrupted_service = interrupted if isinstance(interrupted, dict) else None
                active_marker = payload.get("active_run") if isinstance(payload.get("active_run"), dict) else None
                stored_state = str(payload.get("availability_state") or stored_state)
        except Exception as exc:
            logger.warning("Stored service metrics could not be read and were ignored: %s", exc)

        if active_marker:
            incomplete = _empty_summary("A caption service ended without a recorded Stop event. No missing latency values were invented.")
            incomplete.update({
                "status": "incomplete",
                "availability_state": "incomplete_after_restart",
                "run_id": active_marker.get("run_id"),
                "app_version": active_marker.get("app_version"),
                "diagnostics_schema_version": active_marker.get("diagnostics_schema_version"),
                "started_at": active_marker.get("started_at"),
                "configuration": active_marker.get("configuration") or {},
                "load_identity": active_marker.get("load_identity") or {},
                "stop_reason": "app_interrupted",
            })
            _interrupted_service = incomplete
            _availability_state = "incomplete_after_restart"
            _storage_initialised = True
            _persist_store_locked()
            return
        if _latest_completed_services:
            _availability_state = "completed_service_available"
        elif _interrupted_service:
            _availability_state = "incomplete_after_restart"
        elif stored_state == "reset_by_operator":
            _availability_state = "reset_by_operator"
        else:
            _availability_state = "no_service_in_this_process"
        _storage_initialised = True


def _ensure_storage_initialised_locked() -> None:
    global _storage_initialised
    if not _storage_initialised:
        # Production calls initialise from app lifespan. Tests may configure a path first.
        _storage_initialised = True


def start_service_metrics(configuration: dict[str, Any] | None = None) -> None:
    global _metrics, _current_service, _service_started_monotonic
    global _viewer_last_monotonic, _availability_state
    with _lock:
        _ensure_storage_initialised_locked()
        _metrics = RuntimeMetrics()
        _current_service = _new_service(configuration)
        _service_started_monotonic = time.monotonic()
        _viewer_last_monotonic = _service_started_monotonic
        _availability_state = "active_service"
        _persist_store_locked()


def _accumulate_viewer_seconds_locked(now: float) -> None:
    global _viewer_last_monotonic
    if _current_service is None or _viewer_last_monotonic is None:
        _viewer_last_monotonic = now
        return
    elapsed = max(0.0, now - _viewer_last_monotonic)
    for language, count in _current_service["viewer_counts_current"].items():
        _current_service["viewer_seconds"][language] = (
            float(_current_service["viewer_seconds"].get(language, 0.0)) + elapsed * int(count)
        )
    _viewer_last_monotonic = now


def finish_service_metrics(
    status: str = "completed",
    *,
    error: bool = False,
    stop_reason: str | None = None,
) -> None:
    global _current_service, _service_started_monotonic, _viewer_last_monotonic
    global _latest_completed_services, _availability_state
    with _lock:
        if _current_service is None:
            return
        now = time.monotonic()
        _accumulate_viewer_seconds_locked(now)
        _current_service["status"] = status
        _current_service["message"] = "The latest completed caption service is retained across app restarts."
        _current_service["stopped_at"] = _utc_now()
        _current_service["stop_reason"] = stop_reason or ("error" if error else "operator_stop")
        if _service_started_monotonic is not None:
            _current_service["duration_seconds"] = round(max(0.0, now - _service_started_monotonic), 2)
        if error:
            _current_service["errors"] += 1
        completed = _summarise_service(_current_service)
        completed["availability_state"] = "completed_service_available"
        _latest_completed_services = [completed, *_latest_completed_services][:MAX_COMPLETED_SERVICES]
        _current_service = None
        _service_started_monotonic = None
        _viewer_last_monotonic = None
        _availability_state = "completed_service_available"
        _persist_store_locked()


def update_metrics(**kwargs) -> None:
    with _lock:
        for key, value in kwargs.items():
            if hasattr(_metrics, key):
                setattr(_metrics, key, value)
        if _current_service is not None:
            identity_mapping = {
                "model_name": "actual_model",
                "model_device": "actual_device",
                "model_compute_type": "actual_compute_type",
                "model_loaded": "model_loaded",
                "model_load_seconds": "model_load_seconds",
            }
            for source, target in identity_mapping.items():
                if source in kwargs and kwargs[source] not in {None, ""}:
                    value = kwargs[source]
                    if target == "actual_model":
                        allowed = _SAFE_ENUMS["whisper_model"]
                        clean = str(value).lower()
                        value = clean if clean in allowed else "custom"
                    elif target == "actual_device":
                        allowed = _SAFE_ENUMS["whisper_device_requested"]
                        clean = str(value).lower()
                        value = clean if clean in allowed else "custom"
                    elif target == "actual_compute_type":
                        allowed = _SAFE_ENUMS["whisper_compute_type_requested"]
                        clean = str(value).lower()
                        value = clean if clean in allowed else "custom"
                    _current_service["load_identity"][target] = _safe_json_value(value)


def reset_metrics() -> None:
    """Reset live counters without discarding retained service summaries."""
    global _metrics
    with _lock:
        _metrics = RuntimeMetrics()


def clear_service_metrics() -> bool:
    global _latest_completed_services, _interrupted_service, _availability_state
    with _lock:
        if _current_service is not None:
            return False
        _latest_completed_services = []
        _interrupted_service = None
        _availability_state = "reset_by_operator"
        _persist_store_locked()
        return True


def record_transcription(
    seconds: float,
    *,
    word_timestamps_used: bool = False,
    aligned_words: int = 0,
    edge_words_withheld: int = 0,
    edge_words_confirmed: int = 0,
) -> None:
    elapsed = max(0.0, float(seconds))
    aligned = max(0, int(aligned_words))
    withheld = max(0, int(edge_words_withheld))
    confirmed = max(0, int(edge_words_confirmed))
    with _lock:
        _metrics.last_transcription_seconds = elapsed
        _metrics.transcriptions_completed += 1
        _metrics.word_timestamps_enabled = _metrics.word_timestamps_enabled or bool(word_timestamps_used)
        _metrics.word_timestamp_words += aligned
        _metrics.edge_words_withheld += withheld
        _metrics.edge_words_confirmed += confirmed
        if _current_service is not None:
            _current_service["series"]["transcription"].add(elapsed)
            streaming = _current_service["transcription_streaming"]
            streaming["word_timestamp_passes"] += 1 if word_timestamps_used else 0
            streaming["aligned_words"] += aligned
            streaming["edge_words_withheld"] += withheld
            streaming["edge_words_confirmed"] += confirmed


def record_transcription_pass_interval(seconds: float) -> None:
    elapsed = max(0.0, float(seconds))
    with _lock:
        _metrics.last_transcription_pass_interval_seconds = elapsed
        if _current_service is not None:
            _current_service["series"]["transcription_pass_interval"].add(elapsed)


def record_caption(*, is_final: bool, transcript_commits: int = 0) -> None:
    with _lock:
        if _current_service is None:
            return
        key = "final" if is_final else "partial"
        _current_service["caption_counts"][key] += 1
        _current_service["caption_counts"]["transcript_commits"] += max(0, int(transcript_commits))


def record_source_unit(
    *,
    is_final: bool,
    revision: int,
    boundary_reason: str | None = None,
    cue_lifetime_seconds: float | None = None,
    stable_word_count: int = 0,
    mutable_word_count: int = 0,
) -> None:
    with _lock:
        if _current_service is None:
            return
        source_units = _current_service["source_units"]
        source_units["final_units" if is_final else "draft_revisions"] += 1
        source_units["maximum_revision"] = max(source_units["maximum_revision"], max(1, int(revision)))
        stable_words = max(0, int(stable_word_count))
        mutable_words = max(0, int(mutable_word_count))
        source_units["maximum_stable_prefix_words"] = max(
            source_units["maximum_stable_prefix_words"],
            stable_words,
        )
        source_units["maximum_mutable_tail_words"] = max(
            source_units["maximum_mutable_tail_words"],
            mutable_words,
        )
        if not is_final and stable_words:
            source_units["drafts_with_stable_prefix"] += 1
        if is_final:
            reason = str(boundary_reason or "unspecified")
            reasons = source_units["boundary_reasons"]
            reasons[reason] = int(reasons.get(reason, 0)) + 1
            if cue_lifetime_seconds is not None:
                _current_service["series"]["cue_lifetime"].add(cue_lifetime_seconds)

def record_cue_processing(seconds: float) -> None:
    """Record text-free server alignment overhead for latency validation."""
    elapsed = max(0.0, float(seconds))
    with _lock:
        if _current_service is not None:
            _current_service["series"]["cue_processing"].add(elapsed)


def record_english_publish(
    source_ready_to_publish_seconds: float,
    *,
    estimated_capture_to_publish_seconds: float | None = None,
) -> None:
    with _lock:
        if _current_service is None:
            return
        _current_service["series"]["english_publish"].add(source_ready_to_publish_seconds)
        if estimated_capture_to_publish_seconds is not None:
            _current_service["series"]["capture_to_english"].add(estimated_capture_to_publish_seconds)


def _count_key(mapping: dict[str, int], key: str | None, amount: int = 1) -> None:
    if not key:
        return
    raw = str(key).lower()
    clean = raw if raw in _PROVIDER_LABELS else "custom"
    mapping[clean] = int(mapping.get(clean, 0)) + amount


def record_translation_started(language: str, queue_wait_seconds: float) -> None:
    language = str(language or "unknown").lower()
    with _lock:
        if _current_service is None:
            return
        entry = _current_service["translation_languages"].setdefault(language, _new_translation_entry())
        entry["started"] += 1
        entry["queue_wait"].add(queue_wait_seconds)
        scheduler = _current_service["translation_scheduler"]
        scheduler["language_jobs_started"] += 1
        _scheduler_language_entry(scheduler, language)["started"] += 1


def record_translation(
    language: str,
    seconds: float,
    *,
    applied: bool,
    failed: bool = False,
    fallback: bool = False,
    outcome: str | None = None,
    requested_provider: str | None = None,
    actual_provider: str | None = None,
    fallback_chain: list[str] | tuple[str, ...] | None = None,
    retry_count: int = 0,
    source_to_publish_seconds: float | None = None,
    cue_first_publish_seconds: float | None = None,
    is_final: bool = False,
    published: bool = True,
    not_published_reason: str | None = None,
) -> None:
    elapsed = max(0.0, float(seconds))
    language = str(language or "unknown").lower()
    outcome = str(outcome or ("applied" if applied else "failed" if failed else "source_shown"))
    chain = [str(item) for item in (fallback_chain or []) if str(item)]
    with _lock:
        _metrics.last_translation_seconds = elapsed
        _metrics.last_translation_at = time.monotonic()
        _metrics.translations_completed += 1
        if _current_service is None:
            return
        entry = _current_service["translation_languages"].setdefault(language, _new_translation_entry())
        entry["compute"].add(elapsed)
        if source_to_publish_seconds is not None:
            entry["source_to_publish"].add(source_to_publish_seconds)
        if cue_first_publish_seconds is not None:
            entry["cue_first_publish"].add(cue_first_publish_seconds)
        entry["completed"] += 1
        entry["published"] += int(published)
        entry["drafts_published"] += int(published and not is_final)
        entry["finals_published"] += int(published and is_final)
        if not published:
            entry["not_published"] += 1
            clean_reason = str(not_published_reason or "unspecified").lower()
            if clean_reason not in _TRANSLATION_NOT_PUBLISHED_REASONS:
                clean_reason = "unspecified"
            reasons = entry["not_published_reasons"]
            reasons[clean_reason] = int(reasons.get(clean_reason, 0)) + 1
        entry["applied"] += int(applied)
        entry["unchanged"] += int(outcome == "unchanged")
        entry["failures"] += int(failed or outcome == "failed")
        entry["unavailable"] += int(outcome in {"unavailable", "disabled"})
        entry["source_fallbacks"] += int(fallback or outcome in {"source_shown", "failed", "unavailable", "disabled"})
        entry["provider_fallbacks"] += int(len(chain) > 1)
        entry["retries"] += max(0, int(retry_count))
        _count_key(entry["requested_provider_counts"], requested_provider)
        _count_key(entry["actual_provider_counts"], actual_provider)
        scheduler = _current_service["translation_scheduler"]
        scheduler["language_jobs_completed"] += 1
        _scheduler_language_entry(scheduler, language)["completed"] += 1


def record_translation_batch(
    *,
    languages: list[str],
    replaced_pending: bool,
    replaced_final_pending: bool,
    is_final: bool = False,
    replaced_languages: list[str] | None = None,
) -> None:
    with _lock:
        if _current_service is None:
            return
        scheduler = _current_service["translation_scheduler"]
        scheduler["batches_queued"] += 1
        scheduler["language_jobs_queued"] += len(languages)
        for language in languages:
            _scheduler_language_entry(scheduler, str(language))["queued"] += 1
        if replaced_pending:
            scheduler["pending_batches_replaced"] += 1
            scheduler["final_batches_replaced"] += int(replaced_final_pending)
            superseded = replaced_languages or []
            key = "final_jobs_superseded" if replaced_final_pending else "partial_jobs_superseded"
            scheduler[key] += len(superseded) or 1
            language_key = "final_superseded" if replaced_final_pending else "partial_superseded"
            for language in superseded:
                _scheduler_language_entry(scheduler, str(language))[language_key] += 1


def record_translation_queue_event(
    event: str,
    *,
    language: str,
    depth: int | None = None,
) -> None:
    final_revision = str(event) == "final_revision_coalesced"
    key = {
        "draft_coalesced": "draft_jobs_coalesced",
        "draft_dropped_backpressure": "draft_jobs_dropped_backpressure",
        "draft_rejected_backpressure": "draft_jobs_rejected_backpressure",
        "final_preserved_over_capacity": "final_jobs_preserved_over_capacity",
        "degraded": "degraded_events",
        "recovered": "recovery_events",
    }.get(str(event))
    if not key and event != "queue_depth" and not final_revision:
        return
    language = str(language or "unknown").lower()
    with _lock:
        if _current_service is None:
            return
        scheduler = _current_service["translation_scheduler"]
        language_entry = _scheduler_language_entry(scheduler, language)
        if final_revision:
            scheduler["final_jobs_superseded"] += 1
            language_entry["final_superseded"] += 1
        if key:
            scheduler[key] += 1
            language_entry[key] += 1
        if depth is not None:
            depths = scheduler["max_queue_depth_by_language"]
            depths[language] = max(int(depth), int(depths.get(language, 0)))


def record_translation_shutdown(
    *,
    drain_timeout_seconds: float,
    pending_at_stop: dict[str, int],
    in_flight_at_stop: dict[str, int],
    cancelled_at_stop: dict[str, int],
    timed_out: bool,
) -> None:
    """Record queue disposition at Stop without retaining any caption content."""

    def clean_counts(values: dict[str, int]) -> dict[str, int]:
        return {
            str(language or "unknown").lower(): max(0, int(count))
            for language, count in values.items()
            if int(count) > 0
        }

    pending = clean_counts(pending_at_stop)
    in_flight = clean_counts(in_flight_at_stop)
    cancelled = clean_counts(cancelled_at_stop)
    languages = sorted(set(pending) | set(in_flight) | set(cancelled))
    by_language: dict[str, dict[str, int]] = {}
    for language in languages:
        initial = pending.get(language, 0) + in_flight.get(language, 0)
        cancelled_count = min(initial, cancelled.get(language, 0))
        by_language[language] = {
            "pending_at_stop": pending.get(language, 0),
            "in_flight_at_stop": in_flight.get(language, 0),
            "drained_after_stop": max(0, initial - cancelled_count),
            "cancelled_at_stop": cancelled_count,
        }

    with _lock:
        if _current_service is None:
            return
        shutdown = _current_service["translation_scheduler"]["shutdown"]
        shutdown.update({
            "drain_timeout_seconds": round(max(0.0, float(drain_timeout_seconds)), 3),
            "pending_at_stop": sum(pending.values()),
            "in_flight_at_stop": sum(in_flight.values()),
            "drained_after_stop": sum(item["drained_after_stop"] for item in by_language.values()),
            "cancelled_at_stop": sum(item["cancelled_at_stop"] for item in by_language.values()),
            "timed_out": bool(timed_out),
            "by_language": by_language,
        })


def record_translation_skip(reason: str, *, language: str | None = None, is_final: bool = False) -> None:
    key = {
        "stale": "language_jobs_skipped_stale",
        "no_viewers": "language_jobs_skipped_no_viewers",
    }.get(reason)
    if not key:
        return
    with _lock:
        if _current_service is None:
            return
        scheduler = _current_service["translation_scheduler"]
        scheduler[key] += 1
        if language:
            language_entry = _scheduler_language_entry(scheduler, str(language))
            language_entry["skipped_stale" if reason == "stale" else "skipped_no_viewers"] += 1
            if reason == "stale":
                superseded_key = "final_jobs_superseded" if is_final else "partial_jobs_superseded"
                scheduler[superseded_key] += 1
                language_entry["final_superseded" if is_final else "partial_superseded"] += 1


def record_viewer_counts(counts: dict[str, int]) -> None:
    clean = {str(language): max(0, int(count)) for language, count in counts.items() if int(count) > 0}
    now = time.monotonic()
    with _lock:
        if _current_service is None:
            return
        _accumulate_viewer_seconds_locked(now)
        _current_service["viewer_counts_current"] = clean
        for language, count in clean.items():
            _current_service["viewer_counts_peak"][language] = max(
                count,
                int(_current_service["viewer_counts_peak"].get(language, 0)),
            )


def record_system_sample(snapshot: dict[str, Any]) -> None:
    mapping = {
        "cpu_percent": "system_cpu_percent",
        "memory_used_percent": "system_memory_used_percent",
        "process_cpu_percent": "process_cpu_percent",
        "process_rss_mib": "process_rss_mib",
    }
    with _lock:
        if _current_service is None:
            return
        for source, target in mapping.items():
            value = snapshot.get(source)
            if isinstance(value, (int, float)):
                _current_service["resources"][target].add(float(value))


def get_metrics() -> dict:
    with _lock:
        data = asdict(_metrics)
    if data.get("last_update_at"):
        data["last_update_age_seconds"] = max(0.0, time.monotonic() - float(data["last_update_at"]))
    else:
        data["last_update_age_seconds"] = None
    return data


def get_service_metrics_report() -> dict[str, Any]:
    with _lock:
        current = _summarise_service(_current_service, now_monotonic=time.monotonic()) if _current_service else None
        return {
            "service_metrics_schema_version": SERVICE_METRICS_SCHEMA_VERSION,
            "availability_state": _availability_state,
            "current_service": current,
            "latest_completed_service": json.loads(json.dumps(_latest_completed_services[0])) if _latest_completed_services else None,
            "completed_services": json.loads(json.dumps(_latest_completed_services[:MAX_COMPLETED_SERVICES])),
            "interrupted_service": json.loads(json.dumps(_interrupted_service)) if _interrupted_service else None,
            "retention_limit": MAX_COMPLETED_SERVICES,
            "privacy": "Allow-listed numeric measurements and non-identifying configuration only. No speech, captions, translations, audio metadata, glossary contents, paths, network identifiers, or operator data.",
        }


def get_service_metrics() -> dict[str, Any]:
    report = get_service_metrics_report()
    selected = report["current_service"] or report["latest_completed_service"] or report["interrupted_service"]
    if selected is None:
        message = (
            "Test measurements were reset by the operator. Start captions to create a new run."
            if report["availability_state"] == "reset_by_operator"
            else "No caption service has been measured in this app process or retained from an earlier run."
        )
        selected = _empty_summary(message)
    selected = json.loads(json.dumps(selected))
    selected["availability_state"] = report["availability_state"]
    return selected


def service_report_payload() -> dict[str, Any]:
    return {
        "service_report_schema_version": SERVICE_REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "service_metrics": get_service_metrics_report(),
        "privacy": "This anonymised report is allow-listed and contains no speech, captions, translated text, audio or audio-device metadata, glossary contents, paths, network identifiers, operator data, or logs.",
    }
