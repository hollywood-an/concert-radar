# ADR 006: Alert only on followed artists, once a day

## Status

Accepted. Replaces the spec's "relevance score above 0.3" matching and per-user quiet hours.

## Context

The first end-to-end test followed one artist and produced 64 alert emails at once. The cause
was the rule itself: the relevance score is 0.7 × taste similarity + 0.3 × recency, and genre
embeddings are similar enough that nearly every show scored above 0.3; users with no follows
score 0.5 on everything, so every new user would be emailed about every show near them.
Quiet hours only delayed the flood.

## Decision

- **What alerts:** a show alerts a user only when an artist they follow is on its lineup
  (any billing), the show is upcoming, announced or on sale, inside their travel radius, and
  not dismissed. Similar-artist discovery stays in the ranked feed, which still uses the score.
- **When:** a newly announced show alerts its nearby followers; re-scrapes of known shows do
  not. Following an artist (or importing follows from Spotify) alerts that artist's existing
  nearby shows once; moving home or changing the radius re-matches all followed artists.
- **Delivery:** one digest per user per day at 14:00 UTC (10am US Eastern in summer; users
  have no time zone), soonest show first. Alerts that went stale while queued (show started,
  cancelled, dismissed, out of range, or alerts turned off) are dropped at send time.
- **Changes:** users already emailed about a show get a notice in the next digest if it is
  cancelled, postponed, or rescheduled, using its status at send time.
- The in-app "New match" push follows the same rule, so the feed and the inbox agree.
- Quiet hours were removed (migration 0012): a single daily email has nothing to suppress.

## Consequences

- One follow now produces at most a handful of alerts (the artist's own nearby shows), and a
  user can predict exactly why each alert arrived.
- Users discover new artists through the feed and artist pages rather than email.
- A digest is up to a day late; a time-sensitive channel (push) would need its own rule.
- `alerts_sent` makes every alert one-time per user, show, and channel.
