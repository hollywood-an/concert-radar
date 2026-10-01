-- GET /feed queries the base tables directly (see docs/adr/002-direct-sql-feed.md), so
-- nothing reads this view; it also lacks the venue coordinates, genres, and dismissal
-- filtering the feed needs. Dropping it removes its indexes and the matcher's periodic
-- refresh along with it.
DROP MATERIALIZED VIEW upcoming_user_feed;
