from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import uuid4


class RecognitionSpan(BaseModel):
    """A Whisper segment or word relative to one rolling audio window."""

    text: str
    start_seconds: float
    end_seconds: float
    confidence: float | None = None
    word_aligned: bool = False


class CaptionSegment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    raw_text: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    is_final: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # v0.7 source-unit metadata. Raw English captions do not need these fields;
    # translated captions use them so draft revisions replace one another while
    # completed thoughts remain durable in the per-language queue.
    source_unit_id: str | None = None
    source_revision: int | None = None
    source_status: str | None = None
    source_started_at: datetime | None = None
    source_ended_at: datetime | None = None
    context_group_id: str | None = None
    source_boundary_reason: str | None = None
    translation_revision: int | None = None
    # v0.7 cue-ledger metadata. A cue remains addressable while its wording is
    # revised, then becomes immutable when it is sealed.
    cue_id: str | None = None
    cue_revision: int | None = None
    cue_status: str | None = None
    cue_operation: str | None = None
    # Streaming-caption stability boundary. Words before this count have
    # survived local agreement; only the newest tail remains mutable.
    cue_stable_word_count: int | None = None
    cue_mutable_word_count: int | None = None
    # Internal recogniser alignment data. These values are deliberately kept
    # out of WebSocket payloads, transcript exports, and diagnostics.
    recognition_spans: list[RecognitionSpan] = Field(default_factory=list, exclude=True)
    # Internal monotonic timing markers. They are excluded from every API,
    # WebSocket, transcript, and export representation.
    capture_started_monotonic: float | None = Field(default=None, exclude=True)
    source_ready_monotonic: float | None = Field(default=None, exclude=True)


class CaptionState(BaseModel):
    status: str = "idle"
    current: CaptionSegment | None = None
    history: list[CaptionSegment] = Field(default_factory=list)
    viewers: int = 0
    sensitive_mode: bool = False
    transcript_saving_enabled: bool = True
    transcript_retention_minutes: int = 120
