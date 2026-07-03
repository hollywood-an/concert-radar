"""FastAPI application entrypoint for the Concert Radar gateway."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import text

from src.deps import get_sessionmaker
from src.routes import auth, events, feed
from src.telemetry import configure_telemetry

configure_telemetry("gateway")
logger = structlog.get_logger()

app = FastAPI(title="Concert Radar Gateway")
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
