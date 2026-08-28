"""Per-task event bus for SSE streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any


class EventBus:
    """Queues task events; `finish()` signals end of stream."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._done = False

    def emit(self, event: dict[str, Any]) -> None:
        if not self._done:
            self._queue.put_nowait(event)

    def finish(self) -> None:
        if not self._done:
            self._done = True
            self._queue.put_nowait(None)

    async def stream(self):
        """Async generator of SSE-formatted event lines."""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
