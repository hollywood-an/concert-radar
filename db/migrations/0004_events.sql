CREATE TYPE event_status AS ENUM ('announced', 'on_sale', 'sold_out', 'cancelled', 'rescheduled', 'postponed');

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id UUID NOT NULL REFERENCES venues(id),
    title TEXT,
    starts_at TIMESTAMPTZ NOT NULL,
    doors_at TIMESTAMPTZ,
    on_sale_at TIMESTAMPTZ,
    price_min_cents INT,
    price_max_cents INT,
    currency TEXT DEFAULT 'USD',
    status event_status NOT NULL DEFAULT 'announced',
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_url TEXT,
    image_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source, external_id)
);

CREATE TABLE event_artists (
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    artist_id UUID NOT NULL REFERENCES artists(id),
    billing INT NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, artist_id)
);

CREATE INDEX idx_events_starts_at ON events (starts_at);
CREATE INDEX idx_events_venue_id ON events (venue_id);
CREATE INDEX idx_events_status ON events (status);
CREATE INDEX idx_event_artists_artist ON event_artists (artist_id);
