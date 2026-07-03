CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    spotify_id TEXT UNIQUE,
    spotify_access_token TEXT,
    spotify_refresh_token TEXT,
    home_location GEOGRAPHY(Point, 4326),
    travel_radius_m INT NOT NULL DEFAULT 80467,
    taste_embedding vector(384),
    alert_email BOOLEAN NOT NULL DEFAULT true,
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_home_location ON users USING gist (home_location);
