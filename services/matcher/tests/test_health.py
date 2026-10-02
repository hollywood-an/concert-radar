"""Health endpoint tests: liveness always, readiness only with a started consumer and live DB."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from src.health import start_health_server

OK = ("HTTP/1.1 200 OK", {"status": "ok"})
UNAVAILABLE = ("HTTP/1.1 503 Service Unavailable", {"status": "unavailable"})


@asynccontextmanager
async def serving(engine: AsyncEngine, consumer_started: asyncio.Event) -> AsyncIterator[int]:
    """Run the health server on an ephemeral port for the block; yield that port."""
    server = await start_health_server(0, engine, consumer_started)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


async def get(port: int, path: str) -> tuple[str, dict[str, str]]:
    """Send GET path over a raw connection; return the status line and the JSON body."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    response = await asyncio.wait_for(reader.read(), timeout=10)
    writer.close()
    await writer.wait_closed()
    head, _, body = response.partition(b"\r\n\r\n")
    return head.split(b"\r\n", 1)[0].decode(), json.loads(body)


async def test_healthz_reports_alive_before_the_consumer_starts(db_engine: AsyncEngine) -> None:
    """Liveness does not wait for the consumer."""
    async with serving(db_engine, asyncio.Event()) as port:
        assert await get(port, "/healthz") == OK


async def test_readyz_turns_ready_once_the_consumer_starts(db_engine: AsyncEngine) -> None:
    """Readiness is 503 until the consumer-started event is set, then 200."""
    consumer_started = asyncio.Event()
    async with serving(db_engine, consumer_started) as port:
        assert await get(port, "/readyz") == UNAVAILABLE
        consumer_started.set()
        assert await get(port, "/readyz") == OK


async def test_readyz_is_unavailable_when_the_database_is_unreachable() -> None:
    """A started consumer is not ready without its database; liveness is unaffected."""
    engine = create_async_engine(
        "postgresql+asyncpg://cr:cr_dev@127.0.0.1:1/concertradar", poolclass=NullPool
    )
    consumer_started = asyncio.Event()
    consumer_started.set()
    try:
        async with serving(engine, consumer_started) as port:
            assert await get(port, "/readyz") == UNAVAILABLE
            assert await get(port, "/healthz") == OK
    finally:
        await engine.dispose()


async def test_unknown_path_is_not_found(db_engine: AsyncEngine) -> None:
    """Anything but GET /healthz or /readyz is a 404."""
    async with serving(db_engine, asyncio.Event()) as port:
        assert await get(port, "/metrics") == ("HTTP/1.1 404 Not Found", {"detail": "Not Found"})
