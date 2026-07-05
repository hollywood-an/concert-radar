"""Message contracts for the topics the notifier consumes and produces."""

from uuid import UUID

from pydantic import BaseModel


class MatchProposed(BaseModel):
    """Payload of matches.proposed, as published by the matcher."""

    user_id: UUID
    event_id: UUID
    score: float


class NotificationSent(BaseModel):
    """Payload of notifications.sent."""

    user_id: UUID
    event_id: UUID
    channel: str
    score: float
