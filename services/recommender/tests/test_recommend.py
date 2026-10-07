"""GetRecommendations over a real gRPC channel against a real Postgres."""

from typing import TYPE_CHECKING

import grpc
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.gen.recommender.v1 import recommender_pb2
from tests.conftest import (
    NEAR_VENUE,
    OTHER_NEAR_VENUE,
    create_artist,
    create_show,
    create_user,
    embedding,
)

if TYPE_CHECKING:
    from src.gen.recommender.v1.recommender_pb2_grpc import RecommenderServiceAsyncStub as Stub

CHICAGO = (-87.6298, 41.8781)


async def recommendations(
    stub: "Stub", user_id: object, limit: int = 0
) -> list[recommender_pb2.Recommendation]:
    request = recommender_pb2.GetRecommendationsRequest(user_id=str(user_id), limit=limit)
    response = await stub.GetRecommendations(request)
    return list(response.recommendations)


async def test_ranks_unfollowed_artists_by_similarity_to_taste(
    db_engine: AsyncEngine, stub: "Stub"
) -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    close = await create_artist(db_engine, "Close", ["indie pop"], embedding(x=0.9, y=0.1))
    middle = await create_artist(db_engine, "Middle", ["folk"], embedding(x=0.5, y=0.5))
    far = await create_artist(db_engine, "Far", ["metal"], embedding(y=1))
    for artist in (favorite, close, middle, far):
        await create_show(db_engine, artist)
    user = await create_user(db_engine, "fan@example.com", follows=[favorite])

    results = await recommendations(stub, user)

    assert [r.artist_name for r in results] == ["Close", "Middle", "Far"]
    assert results[0].similarity > results[1].similarity > results[2].similarity
    assert results[0].similarity == pytest.approx(0.9939, abs=1e-4)
    first = results[0]
    assert first.artist_id == str(close)
    assert first.genre == "indie pop"
    assert first.venue_name == NEAR_VENUE
    assert first.venue_city == "Columbus"
    assert first.distance_m > 0
    assert first.starts_at.seconds > 0
    assert not first.HasField("image_url")


async def test_each_artist_appears_once_with_their_soonest_show(
    db_engine: AsyncEngine, stub: "Stub"
) -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    touring = await create_artist(db_engine, "Touring", ["indie pop"], embedding(x=1, y=0.2))
    await create_show(db_engine, touring, days_out=60)
    soonest = await create_show(db_engine, touring, venue_name=OTHER_NEAR_VENUE, days_out=10)
    user = await create_user(db_engine, "fan@example.com", follows=[favorite])

    results = await recommendations(stub, user)

    assert [r.event_id for r in results] == [str(soonest)]
    assert results[0].venue_name == OTHER_NEAR_VENUE


async def test_skips_dismissed_past_cancelled_and_unembedded_shows(
    db_engine: AsyncEngine, stub: "Stub"
) -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    user = await create_user(db_engine, "fan@example.com", follows=[favorite])
    dismissed = await create_artist(db_engine, "Dismissed", ["pop"], embedding(x=1))
    past = await create_artist(db_engine, "Past", ["pop"], embedding(x=1))
    cancelled = await create_artist(db_engine, "Cancelled", ["pop"], embedding(x=1))
    unembedded = await create_artist(db_engine, "Unembedded", ["pop"], None)
    kept = await create_artist(db_engine, "Kept", ["pop"], embedding(x=1))
    dismissed_show = await create_show(db_engine, dismissed)
    await create_show(db_engine, past, days_out=-1)
    await create_show(db_engine, cancelled, status="cancelled")
    await create_show(db_engine, unembedded)
    await create_show(db_engine, kept, status="announced")
    async with db_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO dismissals (user_id, event_id) VALUES (:user_id, :event_id)"),
            {"user_id": user, "event_id": dismissed_show},
        )

    results = await recommendations(stub, user)

    assert [r.artist_name for r in results] == ["Kept"]


async def test_only_shows_within_the_travel_radius(db_engine: AsyncEngine, stub: "Stub") -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    other = await create_artist(db_engine, "Other", ["indie pop"], embedding(x=1))
    await create_show(db_engine, other)
    columbus_fan = await create_user(db_engine, "columbus@example.com", follows=[favorite])
    chicago_fan = await create_user(
        db_engine, "chicago@example.com", follows=[favorite], home=CHICAGO
    )

    assert [r.artist_name for r in await recommendations(stub, columbus_fan)] == ["Other"]
    assert await recommendations(stub, chicago_fan) == []


async def test_at_most_two_shows_per_genre_before_a_genre_repeats(
    db_engine: AsyncEngine, stub: "Stub"
) -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    rock_1 = await create_artist(db_engine, "Rock 1", ["rock"], embedding(x=1, y=0.05))
    rock_2 = await create_artist(db_engine, "Rock 2", ["rock", "pop"], embedding(x=1, y=0.1))
    # Genres compare case-insensitively, so "Rock" shares a cluster with "rock".
    rock_3 = await create_artist(db_engine, "Rock 3", ["Rock"], embedding(x=1, y=0.15))
    jazz = await create_artist(db_engine, "Jazz", ["jazz"], embedding(x=0.6, y=0.8))
    for artist in (rock_1, rock_2, rock_3, jazz):
        await create_show(db_engine, artist)
    user = await create_user(db_engine, "fan@example.com", follows=[favorite])

    top_three = await recommendations(stub, user, limit=3)
    all_four = await recommendations(stub, user, limit=4)

    assert [r.artist_name for r in top_three] == ["Rock 1", "Rock 2", "Jazz"]
    assert [r.artist_name for r in all_four] == ["Rock 1", "Rock 2", "Jazz", "Rock 3"]
    assert all_four[3].genre == "rock"


async def test_limit_defaults_to_ten(db_engine: AsyncEngine, stub: "Stub") -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    for n in range(12):
        artist = await create_artist(db_engine, f"Artist {n}", [f"genre {n}"], embedding(x=1))
        await create_show(db_engine, artist)
    user = await create_user(db_engine, "fan@example.com", follows=[favorite])

    assert len(await recommendations(stub, user)) == 10
    assert len(await recommendations(stub, user, limit=11)) == 11


async def test_users_without_taste_or_home_get_nothing(
    db_engine: AsyncEngine, stub: "Stub"
) -> None:
    favorite = await create_artist(db_engine, "Favorite", ["indie rock"], embedding(x=1))
    other = await create_artist(db_engine, "Other", ["indie pop"], embedding(x=1))
    await create_show(db_engine, other)
    no_follows = await create_user(db_engine, "new@example.com")
    no_home = await create_user(db_engine, "nohome@example.com", follows=[favorite], home=None)

    assert await recommendations(stub, no_follows) == []
    assert await recommendations(stub, no_home) == []


async def test_unknown_user_is_not_found(db_engine: AsyncEngine, stub: "Stub") -> None:
    with pytest.raises(grpc.aio.AioRpcError) as error:
        await recommendations(stub, "00000000-0000-0000-0000-000000000000")

    assert error.value.code() == grpc.StatusCode.NOT_FOUND


@pytest.mark.parametrize(
    ("user_id", "limit"), [("not-a-uuid", 0), ("00000000-0000-0000-0000-000000000000", -1)]
)
async def test_invalid_arguments_are_rejected(
    db_engine: AsyncEngine, stub: "Stub", user_id: str, limit: int
) -> None:
    with pytest.raises(grpc.aio.AioRpcError) as error:
        await recommendations(stub, user_id, limit=limit)

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
