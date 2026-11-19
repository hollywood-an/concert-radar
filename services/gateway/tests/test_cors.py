"""Tests for the configurable CORS policy."""

import httpx
import pytest
from fastapi import FastAPI

from src.config import Settings
from src.main import add_cors


async def test_preflight_allows_configured_origin(client: httpx.AsyncClient) -> None:
    """A preflight from an allowed origin (the default dev origin) is approved."""
    response = await client.options(
        "/feed",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_preflight_rejects_other_origin(client: httpx.AsyncClient) -> None:
    """A preflight from any other origin gets no allow-origin header."""
    response = await client.options(
        "/feed",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """CORS_ORIGINS is parsed as a JSON list, so production can allow its own host."""
    monkeypatch.setenv("CORS_ORIGINS", '["https://3-14-15-92.sslip.io"]')
    assert Settings().cors_origins == ["https://3-14-15-92.sslip.io"]


async def test_origin_regex_allows_only_whole_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    """CORS_ORIGIN_REGEX admits a hosted frontend and its previews, and nothing that
    merely contains an allowed origin."""
    monkeypatch.setenv(
        "CORS_ORIGIN_REGEX",
        r"https://demo\.vercel\.app|https://demo-[a-z0-9-]+-team\.vercel\.app",
    )
    application = FastAPI()
    add_cors(application, Settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for origin, allowed in [
            ("https://demo.vercel.app", True),
            ("https://demo-git-feature-team.vercel.app", True),
            ("https://demo.vercel.app.evil.example", False),
            ("https://demo-evil.vercel.app", False),
        ]:
            response = await client.options(
                "/feed", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
            )
            assert (response.headers.get("access-control-allow-origin") == origin) is allowed
