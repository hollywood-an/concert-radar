# ADR 008: A/B test the feed order before changing it

## Status

Accepted. The experiment `feed_ranking_v1` is running; it has no result yet.

## Context

The feed ranks by `0.7 × taste similarity + 0.3 × recency`. Testing the live site showed a
side effect: a show by an artist the user follows, ten months out, ranks below shows next week
by artists who are only similar, because the recency term has decayed to nothing. Listing
followed artists' shows first looks like an obvious fix. It is also a guess. It pushes the
"discover something new this week" shows down, and whether users prefer that is a question
about behaviour, not about code.

## Decision

Run both orders side by side and measure.

- **Variants.** `control` is the current order. `followed_first` lists shows headlined by a
  followed artist first, then everything else, each group ranked by the same score. The score
  shown on each ticket is unchanged; only the order differs.
- **Assignment.** `sha256("feed_ranking_v1:" + user id)` decides the variant, half and half.
  It is a pure function, so a user gets the same order on every request and every device
  with nothing to look up, and a later experiment with a different key splits users
  independently of this one.
- **Who is in the experiment.** The two orders are identical for a user who follows nobody, so
  a user enters (one row in `experiment_exposures`) on their first feed load after following
  someone. Counting the others would only dilute the comparison.
- **Metrics.** The web app reports two actions to `POST /activity`: opening a show's page and
  following a ticket link. The primary metric is the share of users who open at least one
  show after entering the experiment; ticket clicks are secondary. Each user counts once, so
  one enthusiastic user cannot carry a variant.
- **Readout.** `GET /experiments/feed_ranking_v1/results` returns the counts per variant and,
  for each metric, both rates, the difference with a 95% confidence interval, and the p-value
  of a two-proportion z-test. It reports `conclusive` only when the primary metric differs at
  the 5% level *and* each variant has at least five users who did and five who did not (the
  condition for the test's normal approximation).
- **Sample size.** Detecting a rise from 20% to 30% of users opening a show, at 5%
  significance and 80% power, takes 294 users per variant. The readout recomputes this from
  the observed control rate.
- **Test accounts.** Accounts at `example.com`, a domain reserved for testing, are assigned a
  variant like anyone else but are left out of the readout.

## Consequences

- The demo has far fewer than 588 users, so this experiment will not reach a verdict soon,
  and the readout says so instead of printing a p-value that looks like one. What exists today
  is the mechanism, tested end to end; a result needs real traffic.
- Show opens and ticket clicks are counted wherever they happen (feed, map, Discover strip),
  not only from the feed. Users are randomized, so the comparison is still fair, but actions
  the feed order cannot influence add noise.
- `GET /feed` now writes one row the first time an eligible user loads it. Later loads hit
  the primary key and write nothing.
- The readout is visible to any signed-in user. It holds totals only, never who did what.
- Ending the experiment means deleting the losing branch of the `ORDER BY` and the
  `FEED_RANKING` entry; the activity table stays useful for the next question.
