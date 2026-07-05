"""WebSocket live feed: push a user's new matches as the matcher proposes them.

Clients connect to /ws/feed?token=<jwt>. A background task consumes matches.proposed
(from offset latest — history is served by GET /feed) and pushes the corresponding
feed item to any open sockets for that user.
"""

import asyncio
import uuid
from collections import defaultdict
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError
from sqlalchemy import text

from src.config import get_settings
from src.deps import get_sessionmaker
from src.models import User
from src.routes.feed import FEED_ITEM_BASE
from src.schemas import FeedItem

MATCHES_PROPOSED_TOPIC = "matches.proposed"
_UNAUTHORIZED_CLOSE_CODE = 4401

router = APIRouter()
logger = structlog.get_logger()

consumer_ready = asyncio.Event()

_ITEM_SQL = text(FEED_ITEM_BASE + " AND e.id = :event_id")


class _MatchProposed(BaseModel):
    """Payload of matches.proposed, as published by the matcher."""

    user_id: uuid.UUID
    event_id: uuid.UUID
    score: float


class ConnectionManager:
    """Open feed sockets grouped by user id."""

    def __init__(self) -> None:
        self._sockets: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    def register(self, user_id: uuid.UUID, socket: WebSocket) -> None:
        """Track an accepted socket for a user."""
        self._sockets[user_id].add(socket)

    def unregister(self, user_id: uuid.UUID, socket: WebSocket) -> None:
        """Stop tracking a socket."""
        self._sockets[user_id].discard(socket)
        if not self._sockets[user_id]:
            del self._sockets[user_id]

    def is_connected(self, user_id: uuid.UUID) -> bool:
        """Whether the user has at least one open socket."""
        return user_id in self._sockets

    async def send_to_user(self, user_id: uuid.UUID, message: dict[str, Any]) -> None:
        """Send a JSON message to every open socket for the user, dropping dead ones."""
        for socket in list(self._sockets.get(user_id, ())):
            try:
                await socket.send_json(message)
            except Exception:
                self.unregister(user_id, socket)


manager = ConnectionManager()


async def _authenticate(token: str) -> User | None:
    """Resolve the user for a raw JWT, or None when it is invalid."""
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = uuid.UUID(claims["sub"])
    except (JWTError, KeyError, ValueError):
        return None
    async with get_sessionmaker()() as session:
        return await session.get(User, user_id)


@router.websocket("/ws/feed")
async def feed_socket(websocket: WebSocket, token: str = Query(default="")) -> None:
    """Hold a live-feed connection open until the client disconnects."""
    user = await _authenticate(token)
    if user is None:
        # Accept first so the client sees a proper close code instead of an HTTP 403.
        await websocket.accept()
        await websocket.close(code=_UNAUTHORIZED_CLOSE_CODE)
        return
    await websocket.accept()
    manager.register(user.id, websocket)
    logger.info("ws_connected", user_id=str(user.id))
    try:
        while True:
            # The stream is push-only; inbound frames are keepalives and are ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(user.id, websocket)
        logger.info("ws_disconnected", user_id=str(user.id))


async def push_match(match: _MatchProposed) -> None:
    """Push the feed item for a proposed match to the user's open sockets, if visible."""
    async with get_sessionmaker()() as session:
        row = (
            (
                await session.execute(
                    _ITEM_SQL, {"user_id": match.user_id, "event_id": match.event_id}
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        return
    item = FeedItem.model_validate(dict(row))
    await manager.send_to_user(
        match.user_id, {"type": "match", "item": item.model_dump(mode="json")}
    )


async def matches_push_loop() -> None:
    """Consume matches.proposed and push matches to connected users. Runs until cancelled."""
    settings = get_settings()
    consumer = AIOKafkaConsumer(
        MATCHES_PROPOSED_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="gateway-ws",
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    try:
        await consumer.start()
    except Exception:
        logger.exception("ws push loop disabled: cannot reach Kafka")
        return
    consumer_ready.set()
    logger.info("ws push loop consuming", topic=MATCHES_PROPOSED_TOPIC)
    try:
        async for message in consumer:
            try:
                match = _MatchProposed.model_validate_json(message.value)
            except ValidationError:
                logger.exception("skipping malformed match", offset=message.offset)
                continue
            if manager.is_connected(match.user_id):
                await push_match(match)
    finally:
        consumer_ready.clear()
        await consumer.stop()
