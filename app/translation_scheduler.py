from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from app.models import CaptionSegment


@dataclass(frozen=True)
class TranslationJob:
    language: str
    segment: CaptionSegment
    sequence: int
    enqueued_monotonic: float
    source_ready_monotonic: float
    generation: int
    cue_first_seen_monotonic: float = 0.0

    @property
    def unit_id(self) -> str:
        return self.segment.cue_id or self.segment.source_unit_id or self.segment.id

    @property
    def revision(self) -> int:
        return int(self.segment.cue_revision or self.segment.source_revision or 1)

    @property
    def is_final(self) -> bool:
        return bool(self.segment.is_final or self.segment.source_status == "final")


@dataclass(frozen=True)
class EnqueueResult:
    accepted: bool
    events: tuple[str, ...]
    depth: int


class BoundedFairTranslationScheduler:
    """Per-language queues with draft coalescing and durable final jobs."""

    def __init__(self, capacity_per_language: int = 8) -> None:
        self.capacity_per_language = max(2, int(capacity_per_language))
        self._queues: dict[str, deque[TranslationJob]] = {}
        self._round_robin: deque[str] = deque()
        self._latest: dict[tuple[str, str], tuple[int, bool]] = {}
        self._degraded_languages: set[str] = set()
        self._recovery_events: deque[str] = deque()
        self._generation = 0

    def _activate(self, language: str) -> None:
        if language not in self._round_robin and self._queues.get(language):
            self._round_robin.append(language)

    def enqueue(self, job: TranslationJob) -> EnqueueResult:
        queue = self._queues.setdefault(job.language, deque())
        events: list[str] = []
        was_degraded = job.language in self._degraded_languages

        matching_indexes = [
            index
            for index, queued in enumerate(queue)
            if queued.unit_id == job.unit_id and queued.revision <= job.revision
        ]
        replaced_final = any(queue[index].is_final for index in matching_indexes)
        for index in reversed(matching_indexes):
            del queue[index]
        if matching_indexes:
            events.append("final_revision_coalesced" if replaced_final else "draft_coalesced")

        if len(queue) >= self.capacity_per_language:
            draft_index = next((index for index, queued in enumerate(queue) if not queued.is_final), None)
            if draft_index is not None:
                del queue[draft_index]
                events.append("draft_dropped_backpressure")
            elif not job.is_final:
                self._degraded_languages.add(job.language)
                rejected_events = ["draft_rejected_backpressure"]
                if not was_degraded:
                    rejected_events.append("degraded")
                return EnqueueResult(False, tuple(rejected_events), len(queue))
            else:
                events.append("final_preserved_over_capacity")

        queue.append(job)
        self._latest[(job.language, job.unit_id)] = (job.revision, job.is_final)
        self._activate(job.language)
        if any(event.endswith("backpressure") or event == "final_preserved_over_capacity" for event in events):
            self._degraded_languages.add(job.language)
        if not was_degraded and job.language in self._degraded_languages:
            events.append("degraded")
        return EnqueueResult(True, tuple(events), len(queue))

    def pop_next(self) -> TranslationJob | None:
        while self._round_robin:
            language = self._round_robin.popleft()
            queue = self._queues.get(language)
            if not queue:
                continue
            job = queue.popleft()
            if queue:
                self._round_robin.append(language)
            if language in self._degraded_languages and len(queue) < self.capacity_per_language:
                self._degraded_languages.remove(language)
                self._recovery_events.append(language)
            return job
        return None

    def is_current(self, job: TranslationJob) -> bool:
        if job.generation != self._generation:
            return False
        return self._latest.get((job.language, job.unit_id)) == (job.revision, job.is_final)

    def take_recovery_events(self) -> list[str]:
        recovered = list(self._recovery_events)
        self._recovery_events.clear()
        return recovered

    def has_jobs(self) -> bool:
        return any(self._queues.values())

    def pending_counts(self) -> dict[str, int]:
        """Return privacy-safe queue depths for service shutdown accounting."""
        return {
            language: len(queue)
            for language, queue in self._queues.items()
            if queue
        }

    def clear(self) -> None:
        self._queues.clear()
        self._round_robin.clear()
        self._latest.clear()
        self._degraded_languages.clear()
        self._recovery_events.clear()
        self._generation += 1

    @property
    def generation(self) -> int:
        return self._generation

    def snapshot(self, *, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else float(now)
        depths = {language: len(queue) for language, queue in self._queues.items() if queue}
        oldest_final_age: dict[str, float] = {}
        for language, queue in self._queues.items():
            finals = [job for job in queue if job.is_final]
            if finals:
                oldest_final_age[language] = round(max(0.0, now - finals[0].enqueued_monotonic), 3)
        return {
            "scheduler_type": "bounded_fair_per_language",
            "queue_capacity_per_language": self.capacity_per_language,
            "queue_depths": depths,
            "oldest_final_age_seconds": oldest_final_age,
            "degraded_languages": sorted(self._degraded_languages),
        }
