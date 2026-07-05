"""Periodic refresh of the upcoming_user_feed materialized view."""

import asyncio

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = structlog.get_logger()

# CONCURRENTLY cannot run inside a transaction, hence the autocommit connection.
_REFRESH = text("REFRESH MATERIALIZED VIEW CONCURRENTLY upcoming_user_feed")


async def refresh_feed_view(engine: AsyncEngine) -> None:
    """Refresh upcoming_user_feed without blocking concurrent readers."""
    async with engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(_REFRESH)
    log.info("feed view refreshed")


async def periodic_refresh(engine: AsyncEngine, interval_seconds: float) -> None:
    """Refresh the feed view every interval_seconds until cancelled."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await refresh_feed_view(engine)
        except Exception:
            log.exception("feed view refresh failed")
