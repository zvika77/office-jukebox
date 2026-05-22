import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class EventBroker:
    """Tiny in-process pub/sub for SSE."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event: str) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


broker = EventBroker()


def publish_sync(event: str) -> None:
    """Call from sync code (FastAPI route handlers) — schedules on the running loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop.is_running():
        loop.create_task(broker.publish(event))
    else:
        loop.run_until_complete(broker.publish(event))
