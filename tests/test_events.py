import asyncio

import pytest

from app.events import EventBroker


@pytest.mark.asyncio
async def test_broker_delivers_to_subscriber():
    broker = EventBroker()
    async with broker.subscribe() as queue:
        await broker.publish("songs_changed")
        message = await asyncio.wait_for(queue.get(), timeout=0.5)
        assert message == "songs_changed"


@pytest.mark.asyncio
async def test_broker_delivers_to_multiple_subscribers():
    broker = EventBroker()
    async with broker.subscribe() as q1, broker.subscribe() as q2:
        await broker.publish("songs_changed")
        m1 = await asyncio.wait_for(q1.get(), timeout=0.5)
        m2 = await asyncio.wait_for(q2.get(), timeout=0.5)
        assert m1 == m2 == "songs_changed"
