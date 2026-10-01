from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    PlannedWorkout,
    TrainingPeriod,
    TrainingPeriodObjective,
    User,
    WorkoutSession,
)


def serialize_plan_objective(
    objective: TrainingPeriodObjective,
) -> dict:
    return {
        "id": str(objective.id),
        "objective_type": (
            objective.objective_type.value
        ),
        "weight": objective.weight,
    }


def serialize_active_period(
    period: TrainingPeriod,
    objectives: list[TrainingPeriodObjective],
) -> dict:
    return {
        "id": str(period.id),
        "parent_id": (
            str(period.parent_id)
            if period.parent_id
            else None
        ),
        "period_type": period.period_type.value,
        "title": period.title,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "description": period.description,
        "target_load": period.target_load,
        "load_method": period.load_method,
        "target_duration_sec": (
            period.target_duration_sec
        ),
        "extra_data": period.extra_data,
        "objectives": [
            serialize_plan_objective(item)
            for item in objectives
        ],
    }


async def get_plan_context(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
) -> dict:
    week_start = (
            as_of_date
            - timedelta(
        days=as_of_date.weekday()
    )
    )

    week_end = (
            week_start
            + timedelta(days=6)
    )

    workout_result = await db.scalars(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.user_id == user.id,
            PlannedWorkout.date >= week_start,
            PlannedWorkout.date <= week_end,
        )
        .order_by(
            PlannedWorkout.date.asc(),
            PlannedWorkout.planned_start_time.asc(),
        )
    )

    planned_workouts = list(workout_result)

    local_timezone = ZoneInfo(
        timezone_name
    )

    snapshot_day_end = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    workout_ids = [
        workout.id
        for workout in planned_workouts
    ]

    linked_sessions_by_workout = {}

    if workout_ids:
        session_result = await db.scalars(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id
                == user.id,
                WorkoutSession.planned_workout_id.in_(
                    workout_ids
                ),
                WorkoutSession.started_at
                < snapshot_day_end,
            )
            .order_by(
                WorkoutSession.started_at.asc()
            )
        )

        for session in session_result:
            if session.started_at >= snapshot_day_end:
                continue

            if (
                    session.planned_workout_id
                    is None
            ):
                continue

            linked_sessions_by_workout.setdefault(
                session.planned_workout_id,
                [],
            ).append(session)

    period_result = await db.scalars(
        select(TrainingPeriod)
        .where(
            TrainingPeriod.user_id == user.id,
            TrainingPeriod.start_date <= as_of_date,
            TrainingPeriod.end_date >= as_of_date,
        )
        .order_by(
            TrainingPeriod.start_date.asc(),
            TrainingPeriod.end_date.desc(),
        )
    )

    periods = list(period_result)

    if not periods:
        return {
            "as_of_date": as_of_date,
            "active_periods": [],
            "current_week": {
                "week_start": week_start,
                "week_end": week_end,
                "planned_workouts": [
                    serialize_planned_workout(
                        workout,
                        linked_sessions_by_workout.get(
                            workout.id,
                            [],
                        ),
                    )
                    for workout in planned_workouts
                ],
            },
        }

    period_ids = [
        period.id
        for period in periods
    ]

    objective_result = await db.scalars(
        select(TrainingPeriodObjective)
        .where(
            TrainingPeriodObjective.period_id.in_(
                period_ids
            )
        )
        .order_by(
            TrainingPeriodObjective.objective_type
        )
    )

    objectives_by_period = {
        period_id: []
        for period_id in period_ids
    }

    for objective in objective_result:
        objectives_by_period[
            objective.period_id
        ].append(objective)

    return {
        "as_of_date": as_of_date,
        "active_periods": [
            serialize_active_period(
                period,
                objectives_by_period[
                    period.id
                ],
            )
            for period in periods
        ],
        "current_week": {
            "week_start": week_start,
            "week_end": week_end,
            "planned_workouts": [
                serialize_planned_workout(
                    workout,
                    linked_sessions_by_workout.get(
                        workout.id,
                        [],
                    ),
                )
                for workout in planned_workouts
            ],
        },
    }


def serialize_planned_workout(
    workout: PlannedWorkout,
    linked_sessions: list[WorkoutSession] | None = None,
) -> dict:
    sessions = linked_sessions or []

    primary_session = (
        max(
            sessions,
            key=lambda session: session.started_at,
        )
        if sessions
        else None
    )

    return {
        "id": str(workout.id),
        "training_period_id": (
            str(workout.training_period_id)
            if workout.training_period_id
            else None
        ),
        "date": workout.date,
        "planned_start_time": (
            workout.planned_start_time
        ),
        "sport": workout.sport.value,
        "title": workout.title,
        "status": workout.status.value,
        "duration_sec": workout.duration_sec,
        "distance_m": workout.distance_m,
        "intensity_type": workout.intensity_type,
        "execution": {
            "has_actual": (
                primary_session is not None
            ),
            "actual_session_count": len(
                sessions
            ),
            "session_id": (
                str(primary_session.id)
                if primary_session
                else None
            ),
            "link_source": (
                primary_session
                .planned_workout_link_source.value
                if (
                    primary_session
                    and primary_session
                    .planned_workout_link_source
                )
                else None
            ),
            "actual_started_at": (
                primary_session.started_at
                if primary_session
                else None
            ),
            "actual_duration_sec": (
                primary_session.duration_sec
                if primary_session
                else None
            ),
            "actual_distance_m": (
                primary_session.distance_m
                if primary_session
                else None
            ),
            "actual_cardio_load": (
                primary_session.cardio_load
                if primary_session
                else None
            ),
        },
    }