# ADR 004: Treat listings as one show at trigram similarity > 0.6, same venue, ±20 minutes

## Status

Accepted.

## Context

The same concert appears in several places: a ticketing platform may list it twice, and the
system is designed for more scrapers than Ticketmaster. Counting one show twice would send
duplicate alerts and clutter the feed; merging two different shows would hide one. Exact
matches on title or time fail in practice: titles differ in punctuation and tour names
("Turnstile: Never Enough Tour" vs "Turnstile - Never Enough Tour"), and start times differ by
a few minutes between sources.

## Decision

Within one source, `(source, external_id)` is the identity and every message is an upsert.
Across sources, a newly discovered event is folded into an existing row when all three hold:

- it is at the same venue (venues are themselves matched by source id, then by name and city);
- it starts within 20 minutes of the existing event;
- `pg_trgm` `similarity(title, other_title) > 0.6`, taking the most similar match.

The first source wins: the merged listing links its lineup to the existing row but does not
overwrite its fields or prune its lineup. See `services/deduper/src/db.py`.

## Consequences

- Punctuation and small wording differences merge; different shows at the same venue on the
  same night (early and late sets) usually differ in time or title and stay separate.
- 0.6 was chosen from the examples in the tests, not tuned on a large labeled set. With a
  second real source, the threshold should be measured against its listings.
- A rescheduled show that moves more than 20 minutes and changes its title enough would be
  inserted as a new event; the status-change path covers the common case where the source
  keeps its id.
