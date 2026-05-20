from __future__ import annotations

import json
from datetime import datetime, timezone
from app.models import CaptionSegment


def _fmt_srt(seconds: float) -> str:
    seconds = max(float(seconds), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _fmt_vtt(seconds: float) -> str:
    return _fmt_srt(seconds).replace(',', '.')


def segments_to_srt(segments: list[CaptionSegment], default_duration: float = 3.0) -> str:
    lines: list[str] = []
    cursor = 0.0
    for i, seg in enumerate(segments, 1):
        start = seg.start_seconds if seg.start_seconds is not None else cursor
        end = seg.end_seconds if seg.end_seconds is not None else start + default_duration
        if end <= start:
            end = start + default_duration
        cursor = end
        lines.extend([str(i), f"{_fmt_srt(start)} --> {_fmt_srt(end)}", seg.text.strip(), ""])
    return "\n".join(lines).strip() + "\n"


def segments_to_vtt(segments: list[CaptionSegment], default_duration: float = 3.0) -> str:
    body: list[str] = ["WEBVTT", ""]
    cursor = 0.0
    for seg in segments:
        start = seg.start_seconds if seg.start_seconds is not None else cursor
        end = seg.end_seconds if seg.end_seconds is not None else start + default_duration
        if end <= start:
            end = start + default_duration
        cursor = end
        body.extend([f"{_fmt_vtt(start)} --> {_fmt_vtt(end)}", seg.text.strip(), ""])
    return "\n".join(body).strip() + "\n"


def segments_to_json(segments: list[CaptionSegment]) -> str:
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "segments": [seg.model_dump(mode="json") for seg in segments],
    }
    return json.dumps(payload, indent=2)
