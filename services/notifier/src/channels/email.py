"""Email channel. Dev mode only for now: log the message that would be sent.

Real delivery via AWS SES belongs to the production deploy phase; the call site and
message shape are final so swapping in SES later only touches this module.
"""

import structlog

log = structlog.get_logger()

CHANNEL = "email"


def send_email(to: str, subject: str, body: str) -> None:
    """Log the email that would be sent in production."""
    log.info("would send email", to=to, subject=subject, body=body)
