CREATE MATERIALIZED VIEW upcoming_user_feed AS
SELECT
    u.id AS user_id,
    e.id AS event_id,
    e.starts_at,
    e.title,
    e.price_min_cents,
    e.price_max_cents,
    e.status,
    e.source_url,
    e.image_url,
    v.name AS venue_name,
    v.city AS venue_city,
    ST_Distance(u.home_location, v.location) AS distance_m,
    a.id AS artist_id,
    a.name AS artist_name,
    a.image_url AS artist_image_url,
    relevance_score(u.taste_embedding, a.embedding, e.starts_at) AS score
FROM users u
CROSS JOIN LATERAL (
    SELECT e2.*
    FROM events e2
    JOIN venues v2 ON v2.id = e2.venue_id
    WHERE e2.starts_at > now()
      AND e2.status IN ('announced', 'on_sale')
      AND ST_DWithin(u.home_location, v2.location, u.travel_radius_m)
) e
JOIN venues v ON v.id = e.venue_id
JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
JOIN artists a ON a.id = ea.artist_id
WHERE u.home_location IS NOT NULL;

CREATE UNIQUE INDEX idx_upcoming_feed_user_event ON upcoming_user_feed (user_id, event_id);
CREATE INDEX idx_upcoming_feed_score ON upcoming_user_feed (user_id, score DESC);
