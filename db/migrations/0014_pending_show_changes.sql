-- Users already emailed about a show that was later cancelled, postponed, or rescheduled
-- wait here until the daily digest tells them about the change.
CREATE TABLE pending_show_changes (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, event_id)
);

CREATE INDEX idx_pending_show_changes_event ON pending_show_changes (event_id);
