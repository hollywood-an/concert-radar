"""Shared fixtures: the saved API payload and a Redpanda container for producer tests."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from testcontainers.kafka import RedpandaContainer

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ticketmaster_columbus.json"


@pytest.fixture
def payload() -> dict[str, Any]:
    """Load the saved Discovery API fixture page."""
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text())
    return data


@pytest.fixture(scope="session")
def kafka_bootstrap() -> Iterator[str]:
    """Start Redpanda in a container and yield its bootstrap server address."""
    with RedpandaContainer("docker.redpanda.com/redpandadata/redpanda:v24.1.1") as container:
        yield container.get_bootstrap_server()


@pytest.fixture(scope="session", autouse=True)
def _tracer_provider() -> None:
    """Install a real tracer provider so producer spans carry valid, injectable contexts."""
    trace.set_tracer_provider(TracerProvider())
