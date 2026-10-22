"""Read the current cycle-goal source in one database statement snapshot.

Only structure, dates, title, legacy goal weights and athlete timezone are
planning inputs here. No load/fitness inference or period mutation is made.
The source read is not evidence of historical availability before capture.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.models.entities import TrainingPeriod, TrainingPeriodObjective, User

from ...domain.goals.protocol import (
    GoalPeriodType,
    LegacyObjectiveSnapshot,
    TrainingGoalSourceSnapshot,
    TrainingPeriodGoalSnapshot,
    validate_goal_sources,
)

TRAINING_GOAL_SOURCE_ROW_LIMIT = 5000


def _weight(value) -> str:
    if type(value) not in {float, int}:
        raise ValueError("Legacy objective weight is not numeric.")
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("Legacy objective weight is non-finite.")
    return format(decimal, "f").rstrip("0").rstrip(".") if decimal % 1 else str(int(decimal))


class SqlAlchemyTrainingGoalSource:
    def __init__(self, session):
        self.session = session

    async def capture(self, *, athlete_id: str, macrocycle_period_id: str):
        if (
            str(UUID(athlete_id)) != athlete_id
            or str(UUID(macrocycle_period_id)) != macrocycle_period_id
        ):
            raise ValueError("Goal source identifiers must be canonical UUIDs.")
        statement = (
            select(TrainingPeriod, TrainingPeriodObjective, User.timezone)
            .join(User, TrainingPeriod.user_id == User.id)
            .outerjoin(
                TrainingPeriodObjective, TrainingPeriodObjective.period_id == TrainingPeriod.id
            )
            .where(TrainingPeriod.user_id == UUID(athlete_id))
            .order_by(TrainingPeriod.id, TrainingPeriodObjective.objective_type)
            .limit(TRAINING_GOAL_SOURCE_ROW_LIMIT)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        rows = result.all()
        if len(rows) >= TRAINING_GOAL_SOURCE_ROW_LIMIT:
            raise ValueError("Goal hierarchy census completeness is unknown at the source limit.")
        periods, objectives, timezones = {}, {}, set()
        for period, objective, timezone_name in rows:
            identity = str(period.id)
            periods[identity] = period
            objectives.setdefault(identity, [])
            timezones.add(timezone_name)
            if objective is not None:
                objectives[identity].append(
                    LegacyObjectiveSnapshot(
                        objective.objective_type.value, _weight(objective.weight)
                    )
                )
        if len(timezones) != 1 or macrocycle_period_id not in periods:
            raise ValueError("Goal macrocycle or athlete timezone is unavailable.")

        def snapshot(identity):
            period = periods[identity]
            return TrainingPeriodGoalSnapshot(
                identity,
                str(period.user_id),
                str(period.parent_id) if period.parent_id else None,
                GoalPeriodType(period.period_type.value),
                period.title,
                period.start_date.isoformat(),
                period.end_date.isoformat(),
                tuple(sorted(objectives[identity], key=lambda item: item.objective_type)),
            )

        hierarchy, current = [], macrocycle_period_id
        while current is not None:
            if (
                current not in periods
                or current in {p.period_id for p in hierarchy}
                or len(hierarchy) >= 4
            ):
                raise ValueError("Goal source ancestor is missing, cyclic or unsupported.")
            node = snapshot(current)
            hierarchy.append(node)
            current = node.parent_id
        children = tuple(
            sorted(
                (
                    snapshot(identity)
                    for identity, period in periods.items()
                    if period.parent_id is not None
                    and str(period.parent_id) == macrocycle_period_id
                ),
                key=lambda item: (item.start_date, item.period_id),
            )
        )
        source = TrainingGoalSourceSnapshot(
            athlete_id,
            next(iter(timezones)),
            tuple(reversed(hierarchy)),
            children,
        )
        validate_goal_sources(source, macrocycle_period_id)
        return source
