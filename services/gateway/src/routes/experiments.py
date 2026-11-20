"""Activity logging and the readout of A/B experiments."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import text

from src.config import get_settings
from src.deps import CurrentUser, DbSession
from src.experiments import (
    CONTROL,
    EXPERIMENTS,
    compare_proportions,
    users_needed_per_variant,
)
from src.models import Event
from src.schemas import ActivityRequest, ExperimentResults, MetricComparison, VariantCounts

router = APIRouter(tags=["experiments"])

# The smallest improvement worth acting on: ten more users in a hundred opening a show.
_MINIMUM_LIFT = 0.10
# Used to size the experiment before control has any users of its own.
_ASSUMED_BASELINE = 0.20

_INSERT_ACTIVITY = text(
    "INSERT INTO user_activity (user_id, kind, event_id) VALUES (:user_id, :kind, :event_id)"
)

# One row per variant. A user counts toward a metric if they did the thing at least once
# after first being shown their variant; repeat actions do not count twice.
_RESULTS_SQL = text(
    """
    SELECT
        x.variant,
        count(*) AS users,
        count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM user_activity a
            WHERE a.user_id = x.user_id AND a.kind = 'show_opened'
              AND a.created_at >= x.exposed_at
        )) AS opened_show,
        count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM user_activity a
            WHERE a.user_id = x.user_id AND a.kind = 'ticket_click'
              AND a.created_at >= x.exposed_at
        )) AS clicked_tickets
    FROM experiment_exposures x
    JOIN users u ON u.id = x.user_id
    WHERE x.experiment = :experiment
      AND (CAST(:excluded_suffix AS text) = ''
           OR right(lower(u.email), char_length(CAST(:excluded_suffix AS text)))
              <> CAST(:excluded_suffix AS text))
    GROUP BY x.variant
    """
)


@router.post("/activity", status_code=status.HTTP_204_NO_CONTENT)
async def record_activity(body: ActivityRequest, user: CurrentUser, session: DbSession) -> Response:
    """Record that the user opened a show's page or followed its ticket link."""
    if await session.get(Event, body.event_id) is None:
        raise HTTPException(status_code=404, detail="event not found")
    await session.execute(
        _INSERT_ACTIVITY, {"user_id": user.id, "kind": body.kind, "event_id": body.event_id}
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/experiments/{key}/results")
async def experiment_results(key: str, _: CurrentUser, session: DbSession) -> ExperimentResults:
    """Return per-variant counts and a significance test for each metric.

    Only totals are returned, never who did what. `conclusive` is true when the primary
    metric (opening a show) has enough users for the test to be trusted and differs at the
    5% level.
    """
    experiment = EXPERIMENTS.get(key)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    result = await session.execute(
        _RESULTS_SQL,
        {
            "experiment": experiment.key,
            "excluded_suffix": get_settings().experiment_excluded_email_suffix.lower(),
        },
    )
    by_variant = {row["variant"]: dict(row) for row in result.mappings()}

    def counts(variant: str) -> VariantCounts:
        row = by_variant.get(variant, {})
        return VariantCounts(
            variant=variant,
            users=row.get("users", 0),
            opened_show=row.get("opened_show", 0),
            clicked_tickets=row.get("clicked_tickets", 0),
        )

    control = counts(CONTROL)
    treatment = counts(experiment.treatment)
    opened = compare_proportions(
        control.opened_show, control.users, treatment.opened_show, treatment.users
    )
    clicked = compare_proportions(
        control.clicked_tickets, control.users, treatment.clicked_tickets, treatment.users
    )
    return ExperimentResults(
        experiment=experiment.key,
        hypothesis=experiment.hypothesis,
        control=control,
        treatment=treatment,
        metrics=[
            MetricComparison(metric="opened_show", **asdict(opened)),
            MetricComparison(metric="clicked_tickets", **asdict(clicked)),
        ],
        users_needed_per_variant=users_needed_per_variant(
            opened.control_rate or _ASSUMED_BASELINE, _MINIMUM_LIFT
        ),
        conclusive=opened.sample_ok and opened.p_value is not None and opened.p_value < 0.05,
    )
