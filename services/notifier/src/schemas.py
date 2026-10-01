"""Message contracts for the topics the notifier consumes and produces."""

from uuid import UUID

from pydantic import BaseModel


class MatchProposed(BaseModel):
    """Payload of matches.proposed, as published by the matcher."""

    user_id: UUID
    event_id: UUID
    score: float


class StatusChange(BaseModel):
    """Payload of events.status_changed, as published by the deduper."""

    event_id: UUID
    source: str
    external_id: str
    old_status: str
    new_status: str


class NotificationSent(BaseModel):
    """Payload of notifications.sent: a new-show alert or a change notice that went out."""

    user_id: UUID
    event_id: UUID
    channel: str
    kind: str
    score: float | None
