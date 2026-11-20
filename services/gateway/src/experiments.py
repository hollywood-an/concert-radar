"""A/B experiments: who gets which variant, and whether the difference is real.

Assignment is a pure function of the experiment key and the user id, so a user sees the
same variant on every request and every replica without a lookup. The statistics are a
two-proportion z-test, written out here because it is twenty lines and the alternative
is a SciPy dependency in the API image.
"""

import hashlib
import math
from dataclasses import dataclass
from uuid import UUID

CONTROL = "control"

# Standard normal quantiles for a two-sided 5% test and 80% power.
_Z_ALPHA = 1.959964
_Z_POWER = 0.841621


@dataclass(frozen=True)
class Experiment:
    """One experiment: its key, the treatment's name, and what it is testing."""

    key: str
    treatment: str
    hypothesis: str
    treatment_share: float = 0.5

    def variant_for(self, user_id: UUID) -> str:
        """Return the variant this user always gets."""
        digest = hashlib.sha256(f"{self.key}:{user_id}".encode()).digest()
        bucket = int.from_bytes(digest[:8], "big") / 2**64
        return self.treatment if bucket < self.treatment_share else CONTROL


# Control ranks by the blended score alone, so a followed artist's show months away can sit
# below a merely similar artist's show next week. The treatment lists followed artists'
# shows first and ranks within each group by the same score.
FEED_RANKING = Experiment(
    key="feed_ranking_v1",
    treatment="followed_first",
    hypothesis=(
        "Listing shows by artists the user follows ahead of everything else makes users "
        "more likely to open a show."
    ),
)

EXPERIMENTS = {FEED_RANKING.key: FEED_RANKING}


@dataclass(frozen=True)
class Comparison:
    """Treatment against control on one yes/no outcome per user."""

    control_rate: float | None
    treatment_rate: float | None
    difference: float | None
    ci95_low: float | None
    ci95_high: float | None
    p_value: float | None
    sample_ok: bool


def compare_proportions(
    control_hits: int, control_users: int, treatment_hits: int, treatment_users: int
) -> Comparison:
    """Compare two conversion rates with a pooled two-proportion z-test.

    The interval is for treatment minus control and uses each arm's own variance.
    `sample_ok` is the usual condition for the normal approximation: at least five users
    who did and five who did not in each arm. Below that, treat the p-value as noise.
    """
    if control_users == 0 or treatment_users == 0:
        return Comparison(
            control_rate=control_hits / control_users if control_users else None,
            treatment_rate=treatment_hits / treatment_users if treatment_users else None,
            difference=None,
            ci95_low=None,
            ci95_high=None,
            p_value=None,
            sample_ok=False,
        )
    control_rate = control_hits / control_users
    treatment_rate = treatment_hits / treatment_users
    difference = treatment_rate - control_rate

    pooled = (control_hits + treatment_hits) / (control_users + treatment_users)
    pooled_se = math.sqrt(pooled * (1 - pooled) * (1 / control_users + 1 / treatment_users))
    # Every user converted, or none did: the arms are identical and there is nothing to test.
    p_value = math.erfc(abs(difference) / pooled_se / math.sqrt(2)) if pooled_se > 0 else 1.0

    se = math.sqrt(
        control_rate * (1 - control_rate) / control_users
        + treatment_rate * (1 - treatment_rate) / treatment_users
    )
    sample_ok = all(
        count >= 5
        for count in (
            control_hits,
            control_users - control_hits,
            treatment_hits,
            treatment_users - treatment_hits,
        )
    )
    return Comparison(
        control_rate=control_rate,
        treatment_rate=treatment_rate,
        difference=difference,
        ci95_low=difference - _Z_ALPHA * se,
        ci95_high=difference + _Z_ALPHA * se,
        p_value=p_value,
        sample_ok=sample_ok,
    )


def users_needed_per_variant(baseline_rate: float, lift: float) -> int:
    """Users each variant needs to detect `lift` (absolute) over `baseline_rate`.

    Two-sided test at 5% significance with 80% power.
    """
    p1 = min(max(baseline_rate, 0.01), 0.98)
    p2 = min(p1 + lift, 0.99)
    mean = (p1 + p2) / 2
    numerator = (
        _Z_ALPHA * math.sqrt(2 * mean * (1 - mean))
        + _Z_POWER * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    return math.ceil(numerator / (p2 - p1) ** 2)
