"""Asyncio event bus broadcasting system events to SSE subscribers."""

import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class EventBus:
    """Fan-out broadcast of JSON events to async subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def setup(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish_async(self, event_type: str, payload: dict | None = None) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            **(payload or {}),
        }
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Subscriber SSE lento, evento descartado (%s).", event_type)

    def publish_threadsafe(self, event_type: str, payload: dict | None = None) -> None:
        """Publish from worker threads onto the main event loop."""
        if self._loop is None or not self._loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.publish_async(event_type, payload), self._loop
            )
        except Exception as err:
            logger.debug("Falha ao publicar evento '%s': %s", event_type, err)

    @staticmethod
    def format_sse(event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def stream(self) -> AsyncGenerator[str, None]:
        """SSE generator yielding events for one subscriber."""
        queue = self.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield self.format_sse(event)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.unsubscribe(queue)


# Module-level singleton
event_bus = EventBus()
