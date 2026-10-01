# ADR 002: Serve the feed with direct SQL, not a materialized view

## Status

Accepted. Supersedes the "materialized view for feed" ADR the spec planned as
`002-materialized-view-for-feed.md`, which was never written.

## Context

The spec called for `GET /feed` to page through `upcoming_user_feed`, a materialized
view (migration `0009_views.sql`) holding one row per user and nearby upcoming headliner
show, with a precomputed `relevance_score`. The matcher was to refresh it with
`REFRESH MATERIALIZED VIEW CONCURRENTLY` every five minutes.

Phase 2 built `GET /feed` as a direct query on `users`, `venues`, `events`,
`event_artists`, and `artists` before the view was wired in, and the feed then grew
past what the view holds:

- Feed items carry venue coordinates (for the map) and headliner genres (for the genre
  filter); the view has neither.
- Dismissed events must disappear from the feed immediately; the view does not know
  about `dismissals` (added later in `0011_dismissals.sql`).
- Date, distance, price, and genre filters apply on top of the ranked set.
- The WebSocket push in `services/gateway/src/ws.py` reuses the same query base so a
  pushed item looks exactly like a feed item.

The matcher kept refreshing the view every five minutes, but nothing read it. Every
refresh recomputed the score for every user against every nearby show, for no reader.

## Decision

`GET /feed` queries the base tables directly: users joined to venues within their
travel radius (`ST_DWithin` on the GiST location indexes), their upcoming announced or
on-sale events and headliners, minus the user's dismissals, scored with
`relevance_score()` at request time, filtered, ordered by score, and paginated.

Migration `0015_drop_upcoming_user_feed.sql` drops the view and its indexes, and the
matcher no longer runs a refresh task.

## Consequences

- Results are always fresh. A new show, a status change to cancelled, a follow that
  shifts the taste embedding, a new home location or radius, or a dismissal shows up
  on the very next request instead of after the next refresh.
- Filters and dismissals live in one SQL statement next to the ranking, so there is no
  second copy of the feed's rules to keep in sync with a view definition, and adding a
  column to feed items is a query change, not a migration that rebuilds a view.
- Each request pays for the spatial join and scores every upcoming show within the
  user's radius before ordering and applying `LIMIT`/`OFFSET`, so cost per request grows
  with the number of nearby upcoming shows and with page depth. A view pays that cost
  once per refresh for all users instead, whether anyone reads the feed or not. At one
  metro's worth of shows per user, the per-request cost is the cheaper trade.
- The matcher has one less background task and one less failure mode.

Revisit this when a measurement shows a problem, for example the `GET /feed` p95 from
the planned k6 load test exceeding its latency budget, or `EXPLAIN ANALYZE` for a large
radius showing the score computation dominating. Options then include index or query
changes, or a per-user score table the matcher maintains as `events.enriched` and
`users.taste_updated` arrive, which stays fresh where a periodic refresh would not. The
k6 numbers will be recorded here once that test exists.
