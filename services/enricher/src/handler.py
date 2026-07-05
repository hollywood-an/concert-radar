"""Core enrichment logic: resolve each artist on a deduped event and embed its genres."""

from dataclasses import dataclass, field
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from src.db import enrich_artist, fetch_artist, find_artist_by_mbid, merge_artist
from src.embeddings import embed_genres
from src.musicbrainz import MusicBrainzClient
from src.schemas import DedupedEvent
from src.spotify import SpotifyClient

log = structlog.get_logger()


@dataclass
class EnrichResult:
    """Outcome of processing one events.deduped message."""

    event_id: UUID
    artist_ids: list[UUID] = field(default_factory=list)
    enriched_artist_ids: list[UUID] = field(default_factory=list)


async def process_deduped(
    engine: AsyncEngine,
    mb: MusicBrainzClient,
    spotify: SpotifyClient,
    deduped: DedupedEvent,
) -> EnrichResult:
    """Enrich every artist on the event, resolving mbid merges to canonical ids."""
    result = EnrichResult(event_id=deduped.event_id)
    for artist_id in deduped.artist_ids:
        canonical_id, newly_enriched = await _enrich_artist(engine, mb, spotify, artist_id)
        if canonical_id is None:
            continue
        if canonical_id not in result.artist_ids:
            result.artist_ids.append(canonical_id)
        if newly_enriched:
            result.enriched_artist_ids.append(canonical_id)
    return result


async def _enrich_artist(
    engine: AsyncEngine,
    mb: MusicBrainzClient,
    spotify: SpotifyClient,
    artist_id: UUID,
) -> tuple[UUID | None, bool]:
    """Enrich one artist row; return (canonical artist id, whether it was newly enriched)."""
    async with engine.connect() as conn:
        row = await fetch_artist(conn, artist_id)
    if row is None:
        log.warning("artist row missing, skipping", artist_id=str(artist_id))
        return None, False
    if row.mbid is not None and row.has_embedding:
        return artist_id, False

    if row.mbid is not None:
        # Already resolved against MusicBrainz but never embedded: no network needed.
        embedding = embed_genres(list(row.genres or []))
        async with engine.begin() as conn:
            await enrich_artist(
                conn, artist_id, mbid=None, genres=list(row.genres or []), embedding=embedding
            )
        return artist_id, embedding is not None

    mb_artist = await mb.search_artist(row.name)
    spotify_artist = await spotify.search_artist(row.name)
    genres = _pick_genres(
        mb_tags=mb_artist.tags if mb_artist else [],
        spotify_genres=spotify_artist.genres if spotify_artist else [],
        existing=list(row.genres or []),
    )
    embedding = embed_genres(genres)

    async with engine.begin() as conn:
        if mb_artist is not None:
            canonical_id = await find_artist_by_mbid(conn, mb_artist.mbid, artist_id)
            if canonical_id is not None:
                # Another row already owns this mbid: this one is a duplicate spelling.
                await merge_artist(conn, artist_id, canonical_id)
                log.info(
                    "merged duplicate artist by mbid",
                    stub_id=str(artist_id),
                    canonical_id=str(canonical_id),
                    mbid=mb_artist.mbid,
                )
                return canonical_id, False
        await enrich_artist(
            conn,
            artist_id,
            mbid=mb_artist.mbid if mb_artist else None,
            genres=genres,
            embedding=embedding,
            spotify_id=spotify_artist.spotify_id if spotify_artist else None,
            popularity=spotify_artist.popularity if spotify_artist else None,
            image_url=spotify_artist.image_url if spotify_artist else None,
        )
    log.info(
        "artist enriched",
        artist_id=str(artist_id),
        name=row.name,
        mbid=mb_artist.mbid if mb_artist else None,
        genre_count=len(genres),
        embedded=embedding is not None,
    )
    return artist_id, True


def _pick_genres(mb_tags: list[str], spotify_genres: list[str], existing: list[str]) -> list[str]:
    """Prefer MusicBrainz tags, then Spotify genres, then whatever the scraper provided."""
    return mb_tags or spotify_genres or existing
