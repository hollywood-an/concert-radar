"""Tests for the feed-ordering A/B test: assignment, exposure, activity, and the readout."""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.experiments import (
    CONTROL,
    FEED_RANKING,
    Experiment,
    compare_proportions,
    users_needed_per_variant,
)
from tests.conftest import auth_headers, create_event

RESULTS_URL = f"/experiments/{FEED_RANKING.key}/results"
TREATMENT = FEED_RANKING.treatment


def force_variant(monkeypatch: pytest.MonkeyPatch, variant: str) -> None:
    """Give every user `variant` until the next call, whatever their id hashes to."""
    monkeypatch.setattr(Experiment, "variant_for", lambda self, user_id: variant)


async def follow(
    client: httpx.AsyncClient, db: AsyncSession, headers: dict[str, str], artist: str
) -> None:
    """Follow a seeded artist by name."""
    artist_id = (
        await db.execute(text("SELECT id FROM artists WHERE name = :name"), {"name": artist})
    ).scalar_one()
    response = await client.post("/follows", json={"artist_id": str(artist_id)}, headers=headers)
    assert response.status_code == 201


async def exposed_user(client: httpx.AsyncClient, db: AsyncSession, email: str) -> dict[str, str]:
    """Sign in, follow an artist, and load the feed, which enters the user in the test."""
    headers = await auth_headers(client, email)
    await follow(client, db, headers, "The National")
    assert (await client.get("/feed", headers=headers)).status_code == 200
    return headers


async def record(
    client: httpx.AsyncClient, headers: dict[str, str], kind: str, event_id: uuid.UUID
) -> httpx.Response:
    """POST one activity row."""
    return await client.post(
        "/activity", json={"kind": kind, "event_id": str(event_id)}, headers=headers
    )


def test_variant_is_stable_and_splits_users_evenly() -> None:
    """The same user always gets the same variant, and the two halves are close to equal."""
    user_id = uuid.uuid4()
    assert len({FEED_RANKING.variant_for(user_id) for _ in range(10)}) == 1

    counts = Counter(FEED_RANKING.variant_for(uuid.uuid4()) for _ in range(10_000))
    assert set(counts) == {CONTROL, TREATMENT}
    # 10,000 fair coin flips land outside 4,800..5,200 about once in 16,000 runs.
    assert 4_800 <= counts[TREATMENT] <= 5_200


def test_variant_depends_on_the_experiment_key() -> None:
    """A second experiment splits the same users differently, so tests don't overlap."""
    other = Experiment(key="another_test", treatment="b", hypothesis="")
    users = [uuid.uuid4() for _ in range(2_000)]
    same = sum(
        (FEED_RANKING.variant_for(u) == CONTROL) == (other.variant_for(u) == CONTROL) for u in users
    )
    assert 800 <= same <= 1_200


def test_compare_proportions_matches_a_worked_example() -> None:
    """20 of 100 against 35 of 100: z = 2.375, p = 0.0175."""
    result = compare_proportions(20, 100, 35, 100)
    assert result.control_rate == pytest.approx(0.20)
    assert result.treatment_rate == pytest.approx(0.35)
    assert result.difference == pytest.approx(0.15)
    assert result.p_value == pytest.approx(0.0175, abs=0.0005)
    assert result.ci95_low == pytest.approx(0.028, abs=0.001)
    assert result.ci95_high == pytest.approx(0.272, abs=0.001)
    assert result.sample_ok


def test_compare_proportions_gives_no_verdict_on_thin_data() -> None:
    """An empty arm has no p-value; a tiny one has a p-value flagged as untrustworthy."""
    empty = compare_proportions(0, 0, 3, 4)
    assert empty.p_value is None
    assert empty.difference is None
    assert not empty.sample_ok

    tiny = compare_proportions(1, 6, 4, 6)
    assert tiny.p_value is not None
    assert not tiny.sample_ok

    nobody_converted = compare_proportions(0, 50, 0, 50)
    assert nobody_converted.p_value == 1.0


def test_users_needed_per_variant() -> None:
    """Detecting 20% -> 30% at 5% significance and 80% power takes 294 users per arm."""
    assert users_needed_per_variant(0.20, 0.10) == 294
    assert users_needed_per_variant(0.20, 0.05) > users_needed_per_variant(0.20, 0.10)


async def test_treatment_lists_followed_artists_first(
    client: httpx.AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control ranks two similar artists' shows this week above a followed artist's show
    ten months out; the treatment puts the followed artist's show on top."""
    now = datetime.now(UTC)
    await create_event(
        db, starts_at=now + timedelta(days=300), lineup=(("The National", 0),), title="Followed"
    )
    await create_event(
        db, starts_at=now + timedelta(days=2), lineup=(("Mannequin Pussy", 0),), title="Closest"
    )
    await create_event(
        db, starts_at=now + timedelta(days=2), lineup=(("Japanese Breakfast", 0),), title="Close"
    )
    headers = await auth_headers(client, "order@example.com")
    await follow(client, db, headers, "The National")

    force_variant(monkeypatch, CONTROL)
    control = (await client.get("/feed", headers=headers)).json()["items"]
    force_variant(monkeypatch, TREATMENT)
    treatment = (await client.get("/feed", headers=headers)).json()["items"]

    assert [item["title"] for item in control] == ["Closest", "Close", "Followed"]
    assert [item["title"] for item in treatment] == ["Followed", "Closest", "Close"]
    # Only the order changes; the scores shown to the user are the same. (Approximately:
    # recency is measured from now(), which moves between the two requests.)
    control_scores = {item["title"]: item["score"] for item in control}
    treatment_scores = {item["title"]: item["score"] for item in treatment}
    assert control_scores == pytest.approx(treatment_scores, abs=1e-6)


async def test_exposure_is_recorded_once_and_only_for_users_with_follows(
    client: httpx.AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user enters the experiment on their first feed load after following somebody,
    and keeps that first variant and timestamp."""
    count = text("SELECT count(*) FROM experiment_exposures")
    headers = await auth_headers(client, "exposure@example.com")

    force_variant(monkeypatch, TREATMENT)
    await client.get("/feed", headers=headers)
    assert (await db.execute(count)).scalar_one() == 0

    await follow(client, db, headers, "The National")
    await client.get("/feed", headers=headers)
    force_variant(monkeypatch, CONTROL)
    await client.get("/feed", headers=headers)

    rows = (await db.execute(text("SELECT experiment, variant FROM experiment_exposures"))).all()
    assert [tuple(row) for row in rows] == [(FEED_RANKING.key, TREATMENT)]


async def test_activity_requires_auth(client: httpx.AsyncClient) -> None:
    """POST /activity without a Bearer token is rejected with 401."""
    response = await client.post(
        "/activity", json={"kind": "show_opened", "event_id": str(uuid.uuid4())}
    )
    assert response.status_code == 401


async def test_activity_rejects_unknown_events_and_kinds(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """An event that doesn't exist is a 404; an action the API doesn't track is a 422."""
    event_id = await create_event(db, starts_at=datetime.now(UTC) + timedelta(days=30))
    headers = await auth_headers(client, "activity@example.com")
    assert (await record(client, headers, "show_opened", uuid.uuid4())).status_code == 404
    assert (await record(client, headers, "scrolled", event_id)).status_code == 422
    assert (await record(client, headers, "show_opened", event_id)).status_code == 204
    assert (await db.execute(text("SELECT count(*) FROM user_activity"))).scalar_one() == 1


async def test_results_require_auth_and_a_known_experiment(client: httpx.AsyncClient) -> None:
    """The readout needs a signed-in user, and an unknown key is a 404."""
    assert (await client.get(RESULTS_URL)).status_code == 401
    headers = await auth_headers(client, "reader@example.com")
    response = await client.get("/experiments/no_such_test/results", headers=headers)
    assert response.status_code == 404


async def test_results_before_anyone_is_exposed(client: httpx.AsyncClient) -> None:
    """With no users the readout is all zeros, has no p-value, and is not conclusive."""
    headers = await auth_headers(client, "early@example.com")
    body = (await client.get(RESULTS_URL, headers=headers)).json()
    assert body["control"] == {
        "variant": CONTROL,
        "users": 0,
        "opened_show": 0,
        "clicked_tickets": 0,
    }
    assert body["treatment"]["variant"] == TREATMENT
    assert [m["metric"] for m in body["metrics"]] == ["opened_show", "clicked_tickets"]
    assert all(m["p_value"] is None and not m["sample_ok"] for m in body["metrics"])
    assert body["users_needed_per_variant"] == 294
    assert body["conclusive"] is False


async def test_results_count_each_user_once_for_what_they_did_after_exposure(
    client: httpx.AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per variant: users exposed, and how many opened a show or clicked tickets at least
    once afterwards. Earlier activity, repeats, and test accounts don't count."""
    event_id = await create_event(db, starts_at=datetime.now(UTC) + timedelta(days=30))

    force_variant(monkeypatch, CONTROL)
    control_a = await exposed_user(client, db, "control-a@fans.test")
    await exposed_user(client, db, "control-b@fans.test")
    # Opened a show before entering the experiment, and never again.
    early = await auth_headers(client, "control-c@fans.test")
    await record(client, early, "show_opened", event_id)
    await follow(client, db, early, "The National")
    await client.get("/feed", headers=early)

    force_variant(monkeypatch, TREATMENT)
    treatment_a = await exposed_user(client, db, "treatment-a@fans.test")
    treatment_b = await exposed_user(client, db, "treatment-b@fans.test")
    # example.com accounts are test accounts and stay out of the readout.
    tester = await exposed_user(client, db, "qa@example.com")

    await record(client, control_a, "show_opened", event_id)
    await record(client, treatment_a, "show_opened", event_id)
    await record(client, treatment_a, "show_opened", event_id)
    await record(client, treatment_a, "ticket_click", event_id)
    await record(client, treatment_b, "show_opened", event_id)
    await record(client, tester, "ticket_click", event_id)

    body = (await client.get(RESULTS_URL, headers=control_a)).json()
    assert body["control"] == {
        "variant": CONTROL,
        "users": 3,
        "opened_show": 1,
        "clicked_tickets": 0,
    }
    assert body["treatment"] == {
        "variant": TREATMENT,
        "users": 2,
        "opened_show": 2,
        "clicked_tickets": 1,
    }
    opened = body["metrics"][0]
    assert opened["control_rate"] == pytest.approx(1 / 3)
    assert opened["treatment_rate"] == pytest.approx(1.0)
    assert opened["difference"] == pytest.approx(2 / 3)
    # Five users cannot settle anything, whatever the p-value says.
    assert opened["sample_ok"] is False
    assert body["conclusive"] is False
