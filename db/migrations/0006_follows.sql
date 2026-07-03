CREATE TYPE follow_source AS ENUM ('manual', 'spotify_import', 'inferred');

CREATE TABLE follows (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artist_id UUID NOT NULL REFERENCES artists(id),
    source follow_source NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, artist_id)
);

CREATE INDEX idx_follows_artist ON follows (artist_id);
