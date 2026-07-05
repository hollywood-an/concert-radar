"""FastAPI application entrypoint for the Concert Radar gateway."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import text

from src import ws
from src.deps import get_sessionmaker
from src.kafka import get_taste_publisher
from src.routes import artists, auth, events, feed, follows, users
from src.telemetry import configure_telemetry

configure_telemetry("gateway")
logger = structlog.get_logger()


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the WebSocket push loop for the app's lifetime; flush Kafka on shutdown."""
    push_task = asyncio.create_task(ws.matches_push_loop())
    yield
    push_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await push_task
    await get_taste_publisher().stop()


app = FastAPI(title="Concert Radar Gateway", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(feed.router)
app.include_router(events.router)
app.include_router(artists.router)
app.include_router(follows.router)
app.include_router(users.router)
app.include_router(ws.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Report process liveness."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """Report readiness by executing a trivial query against the database."""
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readyz_database_unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ok"})


FastAPIInstrumentor.instrument_app(app)
