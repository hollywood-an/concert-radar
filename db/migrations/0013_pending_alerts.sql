-- Matches wait here until the daily digest emails them; alerts_sent records what went out.
CREATE TABLE pending_alerts (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    score DOUBLE PRECISION NOT NULL,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, event_id)
);

CREATE INDEX idx_pending_alerts_event ON pending_alerts (event_id);
