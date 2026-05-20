from collections.abc import AsyncIterator
from app.models import CaptionSegment
from app.transcription.base import Transcriber, sleep_cancel_safe


class MockTranscriber(Transcriber):
    def __init__(self):
        self._running = True
        self._lines = [
            "Good morning everyone, and welcome to church.",
            "Today we are reading from Ephesians chapter two.",
            "Let us fix our eyes on Jesus Christ and listen to the Word of God.",
            "For by grace you have been saved through faith.",
            "This is not your own doing; it is the gift of God.",
            "Let us pray together and ask the Holy Spirit to speak to us.",
        ]

    async def stream(self) -> AsyncIterator[CaptionSegment]:
        i = 0
        while self._running:
            await sleep_cancel_safe(2.5)
            text = self._lines[i % len(self._lines)]
            yield CaptionSegment(text=text, raw_text=text, start_seconds=None, end_seconds=None, is_final=True)
            i += 1

    async def stop(self) -> None:
        self._running = False
