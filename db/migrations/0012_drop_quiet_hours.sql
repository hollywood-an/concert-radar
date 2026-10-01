-- Alerts go out as one daily digest at a fixed time, so a per-user quiet window no
-- longer has anything to suppress.
ALTER TABLE users
    DROP COLUMN quiet_hours_start,
    DROP COLUMN quiet_hours_end;
