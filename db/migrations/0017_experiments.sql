-- A/B experiments. A user enters an experiment the first time a request serves them a
-- variant that could differ from control; the row fixes which variant they were shown and
-- when, so results only count what a user did after that moment.
CREATE TABLE experiment_exposures (
    experiment TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    variant TEXT NOT NULL,
    exposed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (experiment, user_id)
);

-- What users do with shows, reported by the web app. Experiments read their outcome
-- metrics from here; rows are append-only and one user may repeat an action.
CREATE TABLE user_activity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('show_opened', 'ticket_click')),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_activity_user ON user_activity (user_id, kind, created_at);
CREATE INDEX idx_user_activity_event ON user_activity (event_id);
