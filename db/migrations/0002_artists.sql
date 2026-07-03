CREATE TABLE artists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    mbid TEXT UNIQUE,
    spotify_id TEXT UNIQUE,
    genres TEXT[] DEFAULT '{}',
    embedding vector(384),
    popularity INT,
    image_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_artists_name_trgm ON artists USING gin (name gin_trgm_ops);
CREATE INDEX idx_artists_embedding ON artists USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
