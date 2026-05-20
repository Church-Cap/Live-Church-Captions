import asyncio
from collections.abc import AsyncIterator
from app.models import CaptionSegment


class Transcriber:
    async def stream(self) -> AsyncIterator[CaptionSegment]:
        raise NotImplementedError

    async def stop(self) -> None:
        pass


async def sleep_cancel_safe(seconds: float) -> None:
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        raise
