CREATE TYPE alert_channel AS ENUM ('email', 'push', 'sms');

CREATE TABLE alerts_sent (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    channel alert_channel NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, event_id, channel)
);
