"""WebSocket tests: a published match reaches the connected user over /ws/feed."""

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uvicorn
import websockets
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.ws import MATCHES_PROPOSED_TOPIC, consumer_ready
from tests.conftest import create_event

FUTURE = datetime.now(UTC) + timedelta(days=30)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
async def server(app: FastAPI) -> AsyncIterator[str]:
    """Serve the app with uvicorn in-process (lifespan runs the WS push loop)."""
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    instance = uvicorn.Server(config)
    task = asyncio.create_task(instance.serve())
    while not instance.started:
        await asyncio.sleep(0.05)
    await asyncio.wait_for(consumer_ready.wait(), timeout=30)
    yield f"127.0.0.1:{port}"
    instance.should_exit = True
    await asyncio.wait_for(task, timeout=15)


async def test_ws_rejects_bad_token(server: str) -> None:
    """A bogus token gets the socket closed with the unauthorized code."""
    async with websockets.connect(f"ws://{server}/ws/feed?token=bogus") as ws:
        with pytest.raises(websockets.ConnectionClosed):
            await ws.recv()
        assert ws.close_code == 4401


async def test_ws_pushes_match_to_connected_user(
    server: str, db: AsyncSession, kafka_bootstrap: str
) -> None:
    """Publishing a match for a connected user delivers the feed item over the socket."""
    event_id = await create_event(db, starts_at=FUTURE)
    async with httpx.AsyncClient(base_url=f"http://{server}") as http:
        login = await http.post("/auth/dev", json={"email": "socket@example.com"})
    token = login.json()["token"]
    user_id = login.json()["user"]["id"]

    async with websockets.connect(f"ws://{server}/ws/feed?token={token}") as ws:
        producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap)
        await producer.start()
        try:
            await producer.send_and_wait(
                MATCHES_PROPOSED_TOPIC,
                json.dumps({"user_id": user_id, "event_id": str(event_id), "score": 0.72}).encode(),
                key=f"{user_id}:{event_id}".encode(),
            )
        finally:
            await producer.stop()

        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))

    assert message["type"] == "match"
    item = message["item"]
    assert item["event_id"] == str(event_id)
    assert item["artist_name"] == "The National"
    assert item["venue_name"] == "Newport Music Hall"
    assert 0 <= item["score"] <= 1
