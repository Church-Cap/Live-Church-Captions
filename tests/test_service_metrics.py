import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.metrics as metrics
from app.models import CaptionSegment


class ServiceMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.metrics_path = Path(self.tempdir.name) / "service_metrics.json"
        metrics.initialise_service_metrics_storage(self.metrics_path)
        metrics.clear_service_metrics()

    def tearDown(self):
        metrics.finish_service_metrics()
        metrics.clear_service_metrics()
        self.tempdir.cleanup()

    def test_completed_summary_contains_stage_metrics_and_outcomes(self):
        metrics.start_service_metrics({
            "app_version": "0.7.2",
            "diagnostics_schema_version": 2,
            "translation_provider": "both",
            "translation_allowed_languages": ["fa", "zh"],
            "stream_update_interval_seconds": 1.0,
        })
        for seconds in (0.5, 1.0, 1.5):
            metrics.record_transcription(seconds)
        metrics.update_metrics(
            model_name="base.en",
            model_device="cpu",
            model_compute_type="int8",
            model_loaded=True,
            model_load_seconds=1.25,
        )
        metrics.record_english_publish(0.08, estimated_capture_to_publish_seconds=1.8)
        metrics.record_caption(is_final=False)
        metrics.record_caption(is_final=True, transcript_commits=1)
        metrics.record_translation_started("fa", 0.2)
        metrics.record_translation(
            "fa",
            0.4,
            applied=True,
            outcome="applied",
            requested_provider="both",
            actual_provider="argos",
            fallback_chain=("ct2small100", "argos"),
            retry_count=1,
            source_to_publish_seconds=0.75,
            cue_first_publish_seconds=2.25,
            is_final=False,
        )
        metrics.record_translation_started("zh", 0.3)
        metrics.record_translation(
            "zh",
            1.2,
            applied=False,
            failed=True,
            fallback=True,
            outcome="failed",
            requested_provider="both",
            actual_provider="small100",
            fallback_chain=("ct2small100", "argos", "small100"),
            retry_count=2,
            source_to_publish_seconds=1.7,
        )
        metrics.record_system_sample({
            "cpu_percent": 31.5,
            "memory_used_percent": 42.0,
            "process_cpu_percent": 18.0,
            "process_rss_mib": 512.0,
        })
        metrics.finish_service_metrics("completed", stop_reason="operator_stop")

        summary = metrics.get_service_metrics()

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["app_version"], "0.7.2")
        self.assertEqual(summary["service_metrics_schema_version"], 9)
        self.assertTrue(summary["run_id"])
        self.assertEqual(summary["load_identity"]["actual_model"], "base.en")
        self.assertEqual(summary["load_identity"]["model_load_seconds"], 1.25)
        self.assertEqual(summary["transcription_latency"]["samples"], 3)
        self.assertEqual(summary["transcription_latency"]["p50_seconds"], 1.0)
        self.assertEqual(summary["english_publish_delay"]["samples"], 1)
        self.assertEqual(summary["estimated_capture_to_english"]["p50_seconds"], 1.8)
        self.assertEqual(
            summary["estimated_capture_to_english"]["estimate_method"],
            "oldest_audio_frame_to_english_send_complete",
        )
        self.assertEqual(summary["estimated_english_operational_response"]["p50_seconds"], 2.08)
        self.assertEqual(summary["estimated_english_operational_response"]["p95_seconds"], 2.53)
        self.assertEqual(summary["estimated_english_operational_response"]["maximum_seconds"], 2.58)
        self.assertTrue(summary["estimated_english_operational_response"]["includes_english_publish_stage"])
        self.assertEqual(
            summary["estimated_english_audience_delay"]["compatibility_alias_for"],
            "estimated_english_operational_response",
        )
        self.assertEqual(summary["caption_counts"], {"partial": 1, "final": 1, "transcript_commits": 1})
        self.assertEqual(summary["translation_languages"]["fa"]["actual_provider_counts"], {"argos": 1})
        self.assertEqual(summary["translation_languages"]["fa"]["provider_fallbacks"], 1)
        self.assertEqual(summary["translation_languages"]["fa"]["queue_wait"]["p50_seconds"], 0.2)
        self.assertEqual(summary["translation_languages"]["fa"]["cue_first_translation_publish"]["p50_seconds"], 2.25)
        self.assertEqual(
            summary["translation_languages"]["fa"]["estimated_audience_delay"]["compatibility_alias_for"],
            "cue_first_translation_publish",
        )
        self.assertEqual(summary["translation_languages"]["fa"]["drafts_published"], 1)
        self.assertEqual(summary["translation_languages"]["zh"]["failures"], 1)
        self.assertEqual(summary["resources"]["process_rss_mib"]["peak"], 512.0)
        self.assertNotIn("samples", json.dumps(summary["translation_languages"]["fa"]).split('"latency"')[0])

    def test_latest_five_completed_summaries_survive_storage_reload(self):
        run_ids = []
        for index in range(6):
            metrics.start_service_metrics({"app_version": "0.7.2", "performance_label": f"preset-{index}"})
            metrics.record_transcription(0.1 + index)
            metrics.finish_service_metrics()
            run_ids.append(metrics.get_service_metrics()["run_id"])

        metrics.initialise_service_metrics_storage(self.metrics_path)
        report = metrics.get_service_metrics_report()

        self.assertEqual(report["availability_state"], "completed_service_available")
        self.assertEqual(len(report["completed_services"]), 5)
        self.assertEqual(report["latest_completed_service"]["run_id"], run_ids[-1])
        self.assertNotIn(run_ids[0], [item["run_id"] for item in report["completed_services"]])

    def test_report_exposes_current_and_latest_completed_separately(self):
        metrics.start_service_metrics({"app_version": "0.7.2"})
        metrics.finish_service_metrics()
        completed_id = metrics.get_service_metrics()["run_id"]
        metrics.start_service_metrics({"app_version": "0.7.2"})

        report = metrics.get_service_metrics_report()
        self.assertEqual(report["availability_state"], "active_service")
        self.assertNotEqual(report["current_service"]["run_id"], completed_id)
        self.assertEqual(report["latest_completed_service"]["run_id"], completed_id)

    def test_abandoned_active_marker_is_reported_incomplete_after_restart(self):
        metrics.start_service_metrics({"app_version": "0.7.2"})
        active_id = metrics.get_service_metrics()["run_id"]

        metrics.initialise_service_metrics_storage(self.metrics_path)
        report = metrics.get_service_metrics_report()

        self.assertEqual(report["availability_state"], "incomplete_after_restart")
        self.assertEqual(report["interrupted_service"]["run_id"], active_id)
        self.assertEqual(report["interrupted_service"]["stop_reason"], "app_interrupted")
        self.assertEqual(report["interrupted_service"]["transcription_latency"]["samples"], 0)

    def test_reset_state_persists_and_cannot_clear_an_active_run(self):
        metrics.start_service_metrics()
        self.assertFalse(metrics.clear_service_metrics())
        self.assertEqual(metrics.get_service_metrics()["status"], "running")
        metrics.finish_service_metrics()
        self.assertTrue(metrics.clear_service_metrics())

        metrics.initialise_service_metrics_storage(self.metrics_path)
        self.assertEqual(metrics.get_service_metrics_report()["availability_state"], "reset_by_operator")

    def test_reservoir_is_bounded_while_full_count_is_retained(self):
        metrics.start_service_metrics()
        for index in range(metrics.MAX_RESERVOIR_SAMPLES + 500):
            metrics.record_transcription(index / 1000)

        summary = metrics.get_service_metrics()
        self.assertEqual(summary["transcription_latency"]["samples"], metrics.MAX_RESERVOIR_SAMPLES + 500)
        self.assertLessEqual(
            len(metrics._current_service["series"]["transcription"].samples),
            metrics.MAX_RESERVOIR_SAMPLES,
        )

    def test_viewer_seconds_use_time_between_demand_changes(self):
        with patch("app.metrics.time.monotonic", return_value=100.0):
            metrics.start_service_metrics()
            metrics.record_viewer_counts({"en": 1, "fa": 2})
        with patch("app.metrics.time.monotonic", return_value=110.0):
            metrics.record_viewer_counts({})
        with patch("app.metrics.time.monotonic", return_value=112.0):
            metrics.finish_service_metrics()

        summary = metrics.get_service_metrics()
        self.assertEqual(summary["viewer_counts_peak"], {"en": 1, "fa": 2})
        self.assertEqual(summary["viewer_seconds"], {"en": 10.0, "fa": 20.0})

    def test_scheduler_replacements_and_skips_are_counted_by_language(self):
        metrics.start_service_metrics()
        metrics.record_translation_batch(
            languages=["fa", "zh"],
            replaced_pending=False,
            replaced_final_pending=False,
            is_final=True,
        )
        metrics.record_translation_batch(
            languages=["fa", "zh"],
            replaced_pending=True,
            replaced_final_pending=True,
            replaced_languages=["fa", "zh"],
            is_final=False,
        )
        metrics.record_translation_skip("stale", language="fa", is_final=False)
        metrics.record_translation_skip("no_viewers", language="zh")

        scheduler = metrics.get_service_metrics()["translation_scheduler"]
        self.assertEqual(scheduler["batches_queued"], 2)
        self.assertEqual(scheduler["language_jobs_queued"], 4)
        self.assertEqual(scheduler["pending_batches_replaced"], 1)
        self.assertEqual(scheduler["final_batches_replaced"], 1)
        self.assertEqual(scheduler["final_jobs_superseded"], 2)
        self.assertEqual(scheduler["by_language"]["fa"]["queued"], 2)
        self.assertEqual(scheduler["by_language"]["zh"]["skipped_no_viewers"], 1)

    def test_schema_nine_records_streaming_stability_backpressure_and_recovery(self):
        metrics.start_service_metrics({"translation_queue_capacity_per_language": 4})
        metrics.record_transcription(
            0.2,
            word_timestamps_used=True,
            aligned_words=7,
            edge_words_withheld=1,
            edge_words_confirmed=1,
        )
        metrics.record_transcription_pass_interval(0.95)
        metrics.record_cue_processing(0.001)
        metrics.record_cue_processing(0.002)
        metrics.record_source_unit(is_final=False, revision=1, stable_word_count=0, mutable_word_count=5)
        metrics.record_source_unit(is_final=False, revision=2, stable_word_count=4, mutable_word_count=3)
        metrics.record_source_unit(
            is_final=True,
            revision=3,
            boundary_reason="whisper_final",
            cue_lifetime_seconds=4.2,
            stable_word_count=7,
            mutable_word_count=0,
        )
        metrics.record_translation_queue_event("queue_depth", language="fa", depth=4)
        metrics.record_translation_queue_event("draft_coalesced", language="fa", depth=4)
        metrics.record_translation_queue_event("final_revision_coalesced", language="fa", depth=4)
        metrics.record_translation_queue_event("draft_dropped_backpressure", language="fa", depth=4)
        metrics.record_translation_queue_event("degraded", language="fa", depth=4)
        metrics.record_translation_queue_event("recovered", language="fa", depth=1)

        summary = metrics.get_service_metrics()

        self.assertEqual(summary["service_metrics_schema_version"], 9)
        self.assertEqual(summary["transcription_streaming"]["word_timestamp_passes"], 1)
        self.assertEqual(summary["transcription_streaming"]["aligned_words"], 7)
        self.assertEqual(summary["transcription_streaming"]["edge_words_withheld"], 1)
        self.assertEqual(summary["transcription_streaming"]["edge_words_confirmed"], 1)
        self.assertEqual(summary["transcription_streaming"]["pass_interval"]["samples"], 1)
        self.assertEqual(summary["source_units"]["engine"], "word_timestamp_local_agreement_v5")
        self.assertEqual(
            summary["source_units"]["interim_strategy"],
            "immediate_stable_prefix_guarded_edge_tail",
        )
        self.assertEqual(summary["source_units"]["processing_latency"]["samples"], 2)
        self.assertEqual(summary["source_units"]["draft_revisions"], 2)
        self.assertEqual(summary["source_units"]["final_units"], 1)
        self.assertEqual(summary["translation_scheduler"]["final_jobs_superseded"], 1)
        self.assertEqual(summary["translation_scheduler"]["by_language"]["fa"]["final_superseded"], 1)
        self.assertEqual(summary["source_units"]["maximum_revision"], 3)
        self.assertEqual(summary["source_units"]["boundary_reasons"], {"whisper_final": 1})
        self.assertEqual(summary["source_units"]["drafts_with_stable_prefix"], 1)
        self.assertEqual(summary["source_units"]["maximum_stable_prefix_words"], 7)
        self.assertEqual(summary["source_units"]["maximum_mutable_tail_words"], 5)
        self.assertEqual(summary["source_units"]["cue_lifetime"]["p50_seconds"], 4.2)
        scheduler = summary["translation_scheduler"]
        self.assertEqual(scheduler["queue_capacity_per_language"], 4)
        self.assertEqual(scheduler["draft_jobs_coalesced"], 1)
        self.assertEqual(scheduler["draft_jobs_dropped_backpressure"], 1)
        self.assertEqual(scheduler["degraded_events"], 1)
        self.assertEqual(scheduler["recovery_events"], 1)
        self.assertEqual(scheduler["max_queue_depth_by_language"], {"fa": 4})

    def test_schema_seven_records_translation_shutdown_disposition(self):
        metrics.start_service_metrics({"translation_queue_capacity_per_language": 8})
        metrics.record_translation_shutdown(
            drain_timeout_seconds=2.0,
            pending_at_stop={"fa": 1, "zh-hant": 2},
            in_flight_at_stop={"zh-hant": 1},
            cancelled_at_stop={"zh-hant": 1},
            timed_out=True,
        )

        shutdown = metrics.get_service_metrics()["translation_scheduler"]["shutdown"]
        self.assertEqual(shutdown["pending_at_stop"], 3)
        self.assertEqual(shutdown["in_flight_at_stop"], 1)
        self.assertEqual(shutdown["drained_after_stop"], 3)
        self.assertEqual(shutdown["cancelled_at_stop"], 1)
        self.assertTrue(shutdown["timed_out"])
        self.assertEqual(shutdown["by_language"]["fa"]["drained_after_stop"], 1)
        self.assertEqual(shutdown["by_language"]["zh-hant"]["cancelled_at_stop"], 1)

    def test_translation_non_publication_reasons_are_counted(self):
        metrics.start_service_metrics()
        metrics.record_translation_started("fa", 0.1)
        metrics.record_translation(
            "fa",
            0.2,
            applied=True,
            outcome="applied",
            published=False,
            not_published_reason="stale_after_compute",
        )
        metrics.record_translation_started("fa", 0.1)
        metrics.record_translation(
            "fa",
            0.2,
            applied=True,
            outcome="applied",
            published=False,
            not_published_reason="no_language_viewers_after_compute",
        )

        language = metrics.get_service_metrics()["translation_languages"]["fa"]
        self.assertEqual(language["completed"], 2)
        self.assertEqual(language["published"], 0)
        self.assertEqual(language["not_published"], 2)
        self.assertEqual(
            language["not_published_reasons"],
            {"stale_after_compute": 1, "no_language_viewers_after_compute": 1},
        )

    def test_anonymised_report_rejects_content_sentinels(self):
        sentinel = "PRIVATE_SERMON_GLOSSARY_SENTINEL_91QX"
        metrics.start_service_metrics({
            "app_version": sentinel,
            "replay_label": sentinel,
            "unknown_content_field": sentinel,
            "translation_provider": sentinel,
        })
        metrics.record_transcription(0.5)
        metrics.record_translation(
            "fa",
            0.3,
            applied=True,
            outcome="applied",
            requested_provider=sentinel,
            actual_provider=sentinel,
        )
        metrics.finish_service_metrics()

        report_json = json.dumps(metrics.service_report_payload())
        self.assertNotIn(sentinel, report_json)
        for forbidden_key in ("audio_device", "caption", "transcript", "glossary", "local_path", "network"):
            self.assertNotIn(f'"{forbidden_key}"', report_json.lower())

        public_segment = CaptionSegment(
            text=sentinel,
            capture_started_monotonic=123.0,
            source_ready_monotonic=124.0,
        ).model_dump(mode="json")
        self.assertNotIn("capture_started_monotonic", public_segment)
        self.assertNotIn("source_ready_monotonic", public_segment)


if __name__ == "__main__":
    unittest.main()
