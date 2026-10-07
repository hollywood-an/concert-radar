"""Health endpoint tests: liveness always, readiness only while serving gRPC with a live DB."""

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
async def health_server(engine: AsyncEngine, serving: asyncio.Event) -> AsyncIterator[int]:
    """Run the health server on an ephemeral port for the block; yield that port."""
    server = await start_health_server(0, engine, serving)
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


async def test_healthz_reports_alive_before_the_server_starts(db_engine: AsyncEngine) -> None:
    """Liveness does not wait for the gRPC server."""
    async with health_server(db_engine, asyncio.Event()) as port:
        assert await get(port, "/healthz") == OK


async def test_readyz_turns_ready_once_the_server_is_serving(db_engine: AsyncEngine) -> None:
    """Readiness is 503 until the serving event is set, then 200."""
    serving = asyncio.Event()
    async with health_server(db_engine, serving) as port:
        assert await get(port, "/readyz") == UNAVAILABLE
        serving.set()
        assert await get(port, "/readyz") == OK


async def test_readyz_is_unavailable_when_the_database_is_unreachable() -> None:
    """A serving server is not ready without its database; liveness is unaffected."""
    engine = create_async_engine(
        "postgresql+asyncpg://cr:cr_dev@127.0.0.1:1/concertradar", poolclass=NullPool
    )
    serving = asyncio.Event()
    serving.set()
    try:
        async with health_server(engine, serving) as port:
            assert await get(port, "/readyz") == UNAVAILABLE
            assert await get(port, "/healthz") == OK
    finally:
        await engine.dispose()


async def test_unknown_path_is_not_found(db_engine: AsyncEngine) -> None:
    """Anything but GET /healthz or /readyz is a 404."""
    async with health_server(db_engine, asyncio.Event()) as port:
        assert await get(port, "/metrics") == ("HTTP/1.1 404 Not Found", {"detail": "Not Found"})
