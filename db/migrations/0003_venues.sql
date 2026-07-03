CREATE TABLE venues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    location GEOGRAPHY(Point, 4326) NOT NULL,
    address JSONB,
    city TEXT,
    state TEXT,
    country TEXT DEFAULT 'US',
    capacity INT,
    source_ids JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_venues_location ON venues USING gist (location);
CREATE INDEX idx_venues_name_trgm ON venues USING gin (name gin_trgm_ops);
