from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import uuid4


class CaptionSegment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    raw_text: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    is_final: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaptionState(BaseModel):
    status: str = "idle"
    current: CaptionSegment | None = None
    history: list[CaptionSegment] = Field(default_factory=list)
    viewers: int = 0
    sensitive_mode: bool = False
    transcript_saving_enabled: bool = True
    transcript_retention_minutes: int = 120
