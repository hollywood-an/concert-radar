-- composite indexes for common query patterns
-- Note: the original spec called for a partial index with predicate `starts_at > now()`,
-- but Postgres requires index predicates to be IMMUTABLE and now() is STABLE, so the
-- predicate is dropped and the composite index covers all rows.
CREATE INDEX idx_events_future_status ON events (starts_at, status);
CREATE INDEX idx_follows_user_source ON follows (user_id, source);
CREATE INDEX idx_alerts_sent_user_recent ON alerts_sent (user_id, sent_at DESC);
