"""Address search for the home-location picker, proxied to Nominatim."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from src.deps import CurrentUser
from src.geocode import GeocoderUnavailable, get_geocoder
from src.schemas import GeocodeResult

router = APIRouter(tags=["geocode"])


@router.get("/geocode")
async def geocode(
    user: CurrentUser,
    q: Annotated[str, Query(min_length=3, max_length=200)],
) -> list[GeocodeResult]:
    """Return up to five places matching an address, city, or venue name.

    Signed-in users only, so the shared Nominatim quota isn't open to anonymous callers.
    """
    try:
        return await get_geocoder().search(q)
    except GeocoderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Address search is unavailable right now",
        ) from exc
