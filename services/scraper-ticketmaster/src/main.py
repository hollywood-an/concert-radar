"""CLI entrypoint: scrape Ticketmaster (or a saved fixture) and upsert into Postgres."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog
from opentelemetry import trace
from sqlalchemy.ext.asyncio import create_async_engine

from src.client import DiscoveryClient
from src.config import Settings
from src.db import IngestStats, ingest_payload
from src.telemetry import setup_telemetry

SERVICE_NAME = "scraper-ticketmaster"


def main() -> None:
    """Parse CLI arguments, configure telemetry, and run the scrape."""
    arg_parser = argparse.ArgumentParser(prog=SERVICE_NAME)
    arg_parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Path to a saved Discovery API response JSON to ingest instead of the network.",
    )
    args = arg_parser.parse_args()
    fixture_path: Path | None = args.fixture
    provider = setup_telemetry(SERVICE_NAME)
    try:
        exit_code = asyncio.run(run(fixture_path))
    finally:
        provider.shutdown()
    raise SystemExit(exit_code)


async def run(fixture_path: Path | None) -> int:
    """Ingest every page from the fixture or the live API; return the process exit code."""
    settings = Settings()
    logger = structlog.get_logger()
    if fixture_path is None and not settings.ticketmaster_api_key:
        logger.error("TICKETMASTER_API_KEY is empty and no --fixture was given; nothing to scrape")
        return 1

    engine = create_async_engine(settings.database_url)
    tracer = trace.get_tracer(SERVICE_NAME)
    stats = IngestStats()
    try:
        with tracer.start_as_current_span("scrape.run"):
            if fixture_path is not None:
                payload: dict[str, Any] = json.loads(fixture_path.read_text())
                with tracer.start_as_current_span("scrape.page", attributes={"page": 0}):
                    await ingest_payload(engine, payload, stats)
            else:
                client = DiscoveryClient(
                    settings.ticketmaster_api_key, settings.ticketmaster_dma_id
                )
                page_number = 0
                async for page_payload in client.fetch_pages():
                    with tracer.start_as_current_span(
                        "scrape.page", attributes={"page": page_number}
                    ):
                        await ingest_payload(engine, page_payload, stats)
                    page_number += 1
            logger.info("scrape complete", **asdict(stats))
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    main()
