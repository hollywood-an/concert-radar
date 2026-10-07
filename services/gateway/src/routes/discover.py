"""Discovery: nearby shows by artists the user doesn't follow yet, from the recommender."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from src.deps import CurrentUser
from src.recommender import RecommenderUnavailable, get_recommender
from src.schemas import DiscoverItem

router = APIRouter(tags=["discover"])


@router.get("/discover")
async def discover(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[DiscoverItem]:
    """Return up to `limit` shows ranked by taste and spread across genres.

    Answers 503 when the recommender is down or slower than its deadline, so the feed
    page can hide the strip instead of waiting on it.
    """
    try:
        return await get_recommender().recommendations(user.id, limit)
    except RecommenderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendations are unavailable right now",
        ) from exc
