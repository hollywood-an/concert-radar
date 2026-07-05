"""CLI entrypoint: scrape Ticketmaster (or a saved fixture) and publish events.discovered."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import structlog
from opentelemetry import trace

from src.client import DiscoveryClient
from src.config import Settings
from src.parser import extract_raw_events, parse_page
from src.producer import DiscoveredEventProducer
from src.telemetry import setup_telemetry

SERVICE_NAME = "scraper-ticketmaster"


def main() -> None:
    """Parse CLI arguments, configure telemetry, and run the scrape."""
    arg_parser = argparse.ArgumentParser(prog=SERVICE_NAME)
    arg_parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Path to a saved Discovery API response JSON to publish instead of the network.",
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
    """Publish every event from the fixture or the live API; return the process exit code."""
    settings = Settings()
    logger = structlog.get_logger()
    if fixture_path is None and not settings.ticketmaster_api_key:
        logger.error("TICKETMASTER_API_KEY is empty and no --fixture was given; nothing to scrape")
        return 1

    tracer = trace.get_tracer(SERVICE_NAME)
    producer = DiscoveredEventProducer(settings.kafka_bootstrap_servers)
    await producer.start()
    events_seen = 0
    events_published = 0
    try:
        with tracer.start_as_current_span("scrape.run"):
            page_number = 0
            async for payload in _pages(fixture_path, settings):
                with tracer.start_as_current_span("scrape.page", attributes={"page": page_number}):
                    events_seen += len(extract_raw_events(payload))
                    for event in parse_page(payload):
                        await producer.publish(event)
                        events_published += 1
                page_number += 1
            logger.info(
                "scrape complete",
                events_seen=events_seen,
                events_published=events_published,
                pages=page_number,
            )
    finally:
        await producer.stop()
    return 0


async def _pages(fixture_path: Path | None, settings: Settings) -> Any:
    """Yield Discovery API pages from the fixture file or the live API."""
    if fixture_path is not None:
        yield json.loads(fixture_path.read_text())
        return
    client = DiscoveryClient(settings.ticketmaster_api_key, settings.ticketmaster_dma_id)
    async for payload in client.fetch_pages():
        yield payload


if __name__ == "__main__":
    main()
