"""Minimal HTTP /healthz and /readyz endpoints next to the gRPC server."""

import asyncio
import json
from asyncio import IncompleteReadError, LimitOverrunError
from http import HTTPStatus

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()

_TIMEOUT_SECONDS = 2.0


async def start_health_server(
    port: int, engine: AsyncEngine, serving: asyncio.Event
) -> asyncio.Server:
    """Serve /healthz and /readyz on all IPv4 interfaces; port 0 picks a free port."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Answer one request, then close the connection."""
        try:
            # Read the whole request head first: closing with unread bytes would make the
            # kernel reset the connection, and the client could lose the response.
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                request = await reader.readuntil(b"\r\n\r\n")
            status, body = await _route(request, engine, serving)
            payload = json.dumps(body).encode()
            head = (
                f"HTTP/1.1 {status.value} {status.phrase}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write(head.encode() + payload)
            await writer.drain()
        except (TimeoutError, ConnectionError, IncompleteReadError, LimitOverrunError):
            pass
        finally:
            writer.close()

    return await asyncio.start_server(handle, host="0.0.0.0", port=port)


async def _route(
    request: bytes, engine: AsyncEngine, serving: asyncio.Event
) -> tuple[HTTPStatus, dict[str, str]]:
    """Map a request to its status and JSON body."""
    if request.startswith(b"GET /healthz "):
        return HTTPStatus.OK, {"status": "ok"}
    if request.startswith(b"GET /readyz "):
        if serving.is_set() and await _database_reachable(engine):
            return HTTPStatus.OK, {"status": "ok"}
        return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unavailable"}
    return HTTPStatus.NOT_FOUND, {"detail": "Not Found"}


async def _database_reachable(engine: AsyncEngine) -> bool:
    """Return whether SELECT 1 succeeds within the timeout."""
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readyz database unreachable")
        return False
    return True
