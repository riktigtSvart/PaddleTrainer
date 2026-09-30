from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import (
    ObjectiveType,
    PeriodType,
    PlannedWorkout,
    TrainingPeriod,
    TrainingPeriodObjective,
    WorkoutLinkSource,
    WorkoutSession,
)
from app.services.users import get_or_create_demo_user
from app.services.training_load import (
    get_current_load_state,
    get_training_load_proxies,
    get_training_load_series,
    get_weekly_cardio_load_series,
)

router = APIRouter(
    prefix="/training-periods",
    tags=["training-periods"],
)


class TrainingPeriodObjectiveCreate(BaseModel):
    objective_type: ObjectiveType
    weight: float = Field(
        ge=0.0,
        le=1.0,
    )


class TrainingPeriodCreate(BaseModel):
    parent_id: UUID | None = None
    period_type: PeriodType

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    start_date: date
    end_date: date

    description: str | None = None

    target_load: float | None = Field(
        default=None,
        ge=0.0,
    )

    load_method: str | None = Field(
        default=None,
        max_length=32,
    )

    target_duration_sec: int | None = Field(
        default=None,
        ge=0,
    )

    extra_data: dict[str, Any] = Field(
        default_factory=dict,
    )

    objectives: list[
        TrainingPeriodObjectiveCreate
    ] = Field(
        default_factory=list,
    )


def serialize_objective(
    objective: TrainingPeriodObjective,
) -> dict:
    return {
        "id": str(objective.id),
        "objective_type": objective.objective_type.value,
        "weight": objective.weight,
    }

def build_execution_comparison(
    workout: PlannedWorkout,
    session: WorkoutSession | None,
) -> dict:
    if session is None:
        return {
            "basis": "NONE",
            "delta_percent": None,
        }

    has_duration = workout.duration_sec is not None
    has_distance = workout.distance_m is not None

    if has_duration and has_distance:
        return {
            "basis": "MIXED",
            "delta_percent": None,
        }

    if has_duration:
        if (
            workout.duration_sec == 0
            or session.duration_sec is None
        ):
            return {
                "basis": "DURATION",
                "delta_percent": None,
            }

        return {
            "basis": "DURATION",
            "delta_percent": round(
                (
                    session.duration_sec
                    - workout.duration_sec
                )
                / workout.duration_sec
                * 100,
                1,
            ),
        }

    if has_distance:
        if (
            workout.distance_m == 0
            or session.distance_m is None
        ):
            return {
                "basis": "DISTANCE",
                "delta_percent": None,
            }

        return {
            "basis": "DISTANCE",
            "delta_percent": round(
                (
                    session.distance_m
                    - workout.distance_m
                )
                / workout.distance_m
                * 100,
                1,
            ),
        }

    return {
        "basis": "NONE",
        "delta_percent": None,
    }

def serialize_workout_summary(
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

    comparison = build_execution_comparison(
        workout,
        primary_session,
    )

    return {
        "id": str(workout.id),
        "date": workout.date,
        "planned_start_time": workout.planned_start_time,
        "sport": workout.sport.value,
        "title": workout.title,
        "status": workout.status.value,
        "duration_sec": workout.duration_sec,
        "distance_m": workout.distance_m,
        "intensity_type": workout.intensity_type,
        "execution": {
            "has_actual": primary_session is not None,
            "actual_session_count": len(sessions),
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
            "comparison_basis": comparison["basis"],
            "delta_percent": comparison["delta_percent"],
        },
    }

def build_weekly_summary(
    workouts: list[PlannedWorkout],
    sessions: list[WorkoutSession],
    linked_sessions: list[WorkoutSession],
    period_start: date,
    period_end: date,
    timezone_name: str,
) -> list[dict]:
    weeks: dict[date, dict] = {}

    local_timezone = ZoneInfo(timezone_name)
    today = datetime.now(
        local_timezone
    ).date()

    first_week_start = (
        period_start
        - timedelta(
            days=period_start.weekday()
        )
    )

    last_week_start = (
        period_end
        - timedelta(
            days=period_end.weekday()
        )
    )

    current_week_start = first_week_start

    while current_week_start <= last_week_start:
        week_end = (
            current_week_start
            + timedelta(days=6)
        )

        if week_end < today:
            phase = "PAST"
        elif current_week_start > today:
            phase = "FUTURE"
        else:
            phase = "CURRENT"

        weeks[current_week_start] = {
            "week_start": current_week_start,
            "week_end": week_end,
            "phase": phase,
            "planned": {
                "workout_count": 0,
                "workout_count_by_sport": {},
                "duration_sec": 0,
                "duration_known_count": 0,
                "distance_by_sport": {},
                "distance_known_count": 0,
            },
            "execution": {
                "planned_workout_count": 0,
                "completed_plan_count": 0,
                "uncompleted_plan_count": 0,
                "completion_rate_percent": None,
                "linked_session_count": 0,
                "provider_exact_link_count": 0,
                "manual_confirmed_link_count": 0,
                "auto_matched_link_count": 0,
                "unknown_link_source_count": 0,
            },
            "actual": {
                "session_count": 0,
                "session_count_by_sport": {},
                "plan_associated_count": 0,
                "provider_linked_count": 0,
                "manual_linked_count": 0,
                "auto_linked_count": 0,
                "unknown_link_source_count": 0,
                "unassociated_count": 0,
                "duration_sec": 0,
                "distance_by_sport": {},
                "cardio_load": 0.0,
                "cardio_load_session_count": 0,
            },
            "summary": {
                "planned_duration_complete": False,
                "notes": [],
            },
        }

        current_week_start += timedelta(
            days=7
        )

    workout_week_by_id: dict[
        UUID,
        date,
    ] = {}

    completed_workout_ids_by_week: dict[
        date,
        set[UUID],
    ] = {
        week_start: set()
        for week_start in weeks
    }

    for workout in workouts:
        week_start = (
            workout.date
            - timedelta(
                days=workout.date.weekday()
            )
        )

        if week_start not in weeks:
            continue

        workout_week_by_id[
            workout.id
        ] = week_start

        planned = weeks[
            week_start
        ]["planned"]

        planned["workout_count"] += 1

        sport = workout.sport.value

        planned[
            "workout_count_by_sport"
        ][sport] = (
            planned[
                "workout_count_by_sport"
            ].get(
                sport,
                0,
            )
            + 1
        )

        if workout.duration_sec is not None:
            planned["duration_sec"] += (
                workout.duration_sec
            )
            planned[
                "duration_known_count"
            ] += 1

        if workout.distance_m is not None:
            planned[
                "distance_by_sport"
            ][sport] = (
                planned[
                    "distance_by_sport"
                ].get(
                    sport,
                    0.0,
                )
                + workout.distance_m
            )

            planned[
                "distance_known_count"
            ] += 1

    for session in linked_sessions:
        workout_id = (
            session.planned_workout_id
        )

        if (
            workout_id is None
            or workout_id
            not in workout_week_by_id
        ):
            continue

        week_start = (
            workout_week_by_id[
                workout_id
            ]
        )

        execution = weeks[
            week_start
        ]["execution"]

        execution[
            "linked_session_count"
        ] += 1

        completed_workout_ids_by_week[
            week_start
        ].add(workout_id)

        if (
            session.planned_workout_link_source
            == WorkoutLinkSource.PROVIDER_EXACT
        ):
            execution[
                "provider_exact_link_count"
            ] += 1

        elif (
            session.planned_workout_link_source
            == WorkoutLinkSource.MANUAL_CONFIRMED
        ):
            execution[
                "manual_confirmed_link_count"
            ] += 1

        elif (
            session.planned_workout_link_source
            == WorkoutLinkSource.AUTO_MATCHED
        ):
            execution[
                "auto_matched_link_count"
            ] += 1

        else:
            execution[
                "unknown_link_source_count"
            ] += 1

    for session in sessions:
        local_date = (
            session.started_at
            .astimezone(
                local_timezone
            )
            .date()
        )

        week_start = (
            local_date
            - timedelta(
                days=local_date.weekday()
            )
        )

        if week_start not in weeks:
            continue

        actual = weeks[
            week_start
        ]["actual"]

        actual["session_count"] += 1

        sport = session.sport.value

        actual[
            "session_count_by_sport"
        ][sport] = (
            actual[
                "session_count_by_sport"
            ].get(
                sport,
                0,
            )
            + 1
        )

        if session.planned_workout_id is None:
            actual[
                "unassociated_count"
            ] += 1

        else:
            actual[
                "plan_associated_count"
            ] += 1

            if (
                session.planned_workout_link_source
                == WorkoutLinkSource.PROVIDER_EXACT
            ):
                actual[
                    "provider_linked_count"
                ] += 1

            elif (
                session.planned_workout_link_source
                == WorkoutLinkSource.MANUAL_CONFIRMED
            ):
                actual[
                    "manual_linked_count"
                ] += 1

            elif (
                session.planned_workout_link_source
                == WorkoutLinkSource.AUTO_MATCHED
            ):
                actual[
                    "auto_linked_count"
                ] += 1

            else:
                actual[
                    "unknown_link_source_count"
                ] += 1

        if session.duration_sec is not None:
            actual[
                "duration_sec"
            ] += session.duration_sec

        if session.distance_m is not None:
            actual[
                "distance_by_sport"
            ][sport] = (
                actual[
                    "distance_by_sport"
                ].get(
                    sport,
                    0.0,
                )
                + session.distance_m
            )

        if session.cardio_load is not None:
            actual[
                "cardio_load"
            ] += session.cardio_load

            actual[
                "cardio_load_session_count"
            ] += 1

    for week_start, week in weeks.items():
        planned = week["planned"]
        execution = week["execution"]
        actual = week["actual"]

        planned_workout_count = (
            planned["workout_count"]
        )

        completed_plan_count = len(
            completed_workout_ids_by_week[
                week_start
            ]
        )

        execution[
            "planned_workout_count"
        ] = planned_workout_count

        execution[
            "completed_plan_count"
        ] = completed_plan_count

        execution[
            "uncompleted_plan_count"
        ] = (
            planned_workout_count
            - completed_plan_count
        )

        execution[
            "completion_rate_percent"
        ] = (
            round(
                completed_plan_count
                / planned_workout_count
                * 100,
                1,
            )
            if planned_workout_count
            else None
        )

        actual["cardio_load"] = round(
            actual["cardio_load"],
            2,
        )

        planned_duration_complete = (
            planned_workout_count > 0
            and planned[
                "duration_known_count"
            ]
            == planned_workout_count
        )

        week["summary"][
            "planned_duration_complete"
        ] = planned_duration_complete

        notes: list[str] = []

        phase = week["phase"]

        if phase == "FUTURE":
            notes.append(
                "A hét még nem kezdődött el."
            )

        elif planned_workout_count > 0:
            rate = execution[
                "completion_rate_percent"
            ]

            if phase == "CURRENT":
                notes.append(
                    (
                        f"Eddig "
                        f"{completed_plan_count} / "
                        f"{planned_workout_count} "
                        f"tervezett edzés teljesült"
                        + (
                            f" ({rate}%)."
                            if rate is not None
                            else "."
                        )
                    )
                )

            else:
                notes.append(
                    (
                        f"A tervezett "
                        f"{planned_workout_count} "
                        f"edzésből "
                        f"{completed_plan_count} "
                        f"teljesült"
                        + (
                            f" ({rate}%)."
                            if rate is not None
                            else "."
                        )
                    )
                )

        elif phase == "PAST":
            notes.append(
                "Erre a hétre nem volt "
                "tervezett edzés."
            )

        elif phase == "CURRENT":
            notes.append(
                "Erre a hétre jelenleg nincs "
                "tervezett edzés."
            )

        if (
            phase != "FUTURE"
            and actual["session_count"] > 0
        ):
            notes.append(
                (
                    f"A héten "
                    f"{actual['session_count']} "
                    f"tényleges edzés került "
                    f"rögzítésre."
                )
            )

        if (
            planned_workout_count > 0
            and not planned_duration_complete
        ):
            notes.append(
                (
                    "A tervezett idő "
                    f"{planned['duration_known_count']} / "
                    f"{planned_workout_count} "
                    "edzésnél ismert, ezért a heti "
                    "időalapú terv–tény összevetés "
                    "nem teljes."
                )
            )

        week["summary"]["notes"] = notes

    return [
        weeks[week_start]
        for week_start in sorted(weeks)
    ]

def build_period_summary(
    workouts: list[PlannedWorkout],
    linked_sessions: list[WorkoutSession],
    sessions_in_period: list[WorkoutSession],
) -> dict:
    workout_ids = {
        workout.id
        for workout in workouts
    }

    planned = {
        "workout_count": len(workouts),
        "duration_sec": 0,
        "duration_known_count": 0,
        "distance_by_sport": {},
        "distance_known_count": 0,
    }

    for workout in workouts:
        if workout.duration_sec is not None:
            planned["duration_sec"] += (
                workout.duration_sec
            )
            planned["duration_known_count"] += 1

        if workout.distance_m is not None:
            sport = workout.sport.value

            planned["distance_by_sport"][sport] = (
                    planned["distance_by_sport"].get(
                        sport,
                        0.0,
                    )
                    + workout.distance_m
            )

            planned["distance_known_count"] += 1

    completed_workout_ids = {
        session.planned_workout_id
        for session in linked_sessions
        if session.planned_workout_id in workout_ids
    }

    planned_workout_count = len(workouts)
    completed_plan_count = len(
        completed_workout_ids
    )

    execution = {
        "planned_workout_count": (
            planned_workout_count
        ),
        "completed_plan_count": (
            completed_plan_count
        ),
        "uncompleted_plan_count": (
            planned_workout_count
            - completed_plan_count
        ),
        "completion_rate_percent": (
            round(
                completed_plan_count
                / planned_workout_count
                * 100,
                1,
            )
            if planned_workout_count
            else None
        ),
        "linked_session_count": len(
            linked_sessions
        ),
        "provider_exact_link_count": 0,
        "manual_confirmed_link_count": 0,
        "auto_matched_link_count": 0,
        "unknown_link_source_count": 0,
    }

    for session in linked_sessions:
        if (
            session.planned_workout_link_source
            == WorkoutLinkSource.PROVIDER_EXACT
        ):
            execution[
                "provider_exact_link_count"
            ] += 1

        elif (
            session.planned_workout_link_source
            == WorkoutLinkSource.MANUAL_CONFIRMED
        ):
            execution[
                "manual_confirmed_link_count"
            ] += 1

        elif (
            session.planned_workout_link_source
            == WorkoutLinkSource.AUTO_MATCHED
        ):
            execution[
                "auto_matched_link_count"
            ] += 1

        else:
            execution[
                "unknown_link_source_count"
            ] += 1

    actual_in_period = {
        "session_count": len(
            sessions_in_period
        ),
        "duration_sec": 0,
        "distance_by_sport": {},
        "cardio_load": 0.0,
        "cardio_load_session_count": 0,
    }

    for session in sessions_in_period:
        if session.duration_sec is not None:
            actual_in_period[
                "duration_sec"
            ] += session.duration_sec

        if session.distance_m is not None:
            sport = session.sport.value

            actual_in_period[
                "distance_by_sport"
            ][sport] = (
                actual_in_period[
                    "distance_by_sport"
                ].get(
                    sport,
                    0.0,
                )
                + session.distance_m
            )

        if session.cardio_load is not None:
            actual_in_period[
                "cardio_load"
            ] += session.cardio_load

            actual_in_period[
                "cardio_load_session_count"
            ] += 1

    actual_in_period["cardio_load"] = round(
        actual_in_period["cardio_load"],
        2,
    )

    return {
        "planned": planned,
        "execution": execution,
        "actual_in_period": actual_in_period,
    }

def serialize_period(
    period: TrainingPeriod,
    objectives: list[
        TrainingPeriodObjective
    ] | None = None,
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
            serialize_objective(objective)
            for objective in (
                objectives or []
            )
        ],
    }


@router.get("")
async def list_training_periods(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    result = await db.scalars(
        select(TrainingPeriod)
        .where(
            TrainingPeriod.user_id == user.id
        )
        .order_by(
            TrainingPeriod.start_date.asc()
        )
    )

    periods = list(result)

    if not periods:
        return []

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

    objectives_by_period: dict[
        UUID,
        list[TrainingPeriodObjective],
    ] = {}

    for objective in objective_result:
        objectives_by_period.setdefault(
            objective.period_id,
            [],
        ).append(objective)

    return [
        serialize_period(
            period,
            objectives_by_period.get(
                period.id,
                [],
            ),
        )
        for period in periods
    ]


@router.get("/{period_id}")
async def get_training_period(
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    period = await db.scalar(
        select(TrainingPeriod).where(
            TrainingPeriod.id == period_id,
            TrainingPeriod.user_id == user.id,
        )
    )

    if period is None:
        raise HTTPException(
            status_code=404,
            detail="Training period not found",
        )

    objective_result = await db.scalars(
        select(TrainingPeriodObjective)
        .where(
            TrainingPeriodObjective.period_id
            == period.id
        )
        .order_by(
            TrainingPeriodObjective.objective_type
        )
    )

    objectives = list(objective_result)

    workout_result = await db.scalars(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.user_id == user.id,
            PlannedWorkout.training_period_id
            == period.id,
        )
        .order_by(
            PlannedWorkout.date.asc(),
            PlannedWorkout.planned_start_time.asc(),
        )
    )

    workouts = list(workout_result)

    workout_ids = [
        workout.id
        for workout in workouts
    ]

    linked_sessions: list[
        WorkoutSession
    ] = []

    load_trend = await get_weekly_cardio_load_series(
        db=db,
        user=user,
        start_date=period.start_date,
        end_date=period.end_date,
        timezone_name=user.timezone,
    )

    current_load_state = await get_current_load_state(
        db=db,
        user=user,
        as_of_date=datetime.now(
            ZoneInfo(user.timezone)
        ).date(),
        timezone_name=user.timezone,
    )

    load_trend_by_week = {
        item["week_start"]: item
        for item in load_trend
    }

    training_load_proxies = await get_training_load_proxies(
        db=db,
        user=user,
        as_of_date=datetime.now(
            ZoneInfo(user.timezone)
        ).date(),
        timezone_name=user.timezone,
    )

    training_load_series = await get_training_load_series(
        db=db,
        user=user,
        as_of_date=datetime.now(
            ZoneInfo(user.timezone)
        ).date(),
        timezone_name=user.timezone,
        max_history_days=126,
    )

    if workout_ids:
        linked_session_result = await db.scalars(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id
                == user.id,
                WorkoutSession.planned_workout_id.in_(
                    workout_ids
                ),
            )
            .order_by(
                WorkoutSession.started_at.asc()
            )
        )

        linked_sessions = list(
            linked_session_result
        )

    linked_sessions_by_workout: dict[
        UUID,
        list[WorkoutSession],
    ] = {}

    for session in linked_sessions:
        if session.planned_workout_id is None:
            continue

        linked_sessions_by_workout.setdefault(
            session.planned_workout_id,
            [],
        ).append(session)

    local_timezone = ZoneInfo(user.timezone)

    period_start_datetime = datetime.combine(
        period.start_date,
        time.min,
        tzinfo=local_timezone,
    )

    period_end_datetime = datetime.combine(
        period.end_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    session_result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.started_at
            >= period_start_datetime,
            WorkoutSession.started_at
            < period_end_datetime,
        )
        .order_by(
            WorkoutSession.started_at.asc()
        )
    )

    sessions = list(session_result)

    response = serialize_period(
        period,
        objectives,
    )

    response["workouts"] = [
        serialize_workout_summary(
            workout,
            linked_sessions_by_workout.get(
                workout.id,
                [],
            ),
        )
        for workout in workouts
    ]

    weeks = build_weekly_summary(
        workouts=workouts,
        sessions=sessions,
        linked_sessions=linked_sessions,
        period_start=period.start_date,
        period_end=period.end_date,
        timezone_name=user.timezone,
    )

    for week in weeks:
        week["load_trend"] = (
            load_trend_by_week.get(
                week["week_start"]
            )
        )

    response["weeks"] = weeks

    response["summary"] = build_period_summary(
        workouts=workouts,
        linked_sessions=linked_sessions,
        sessions_in_period=sessions,
    )

    response["current_load_state"] = (
        current_load_state
    )

    response["training_load_proxies"] = (
        training_load_proxies
    )

    response["training_load_series"] = (
        training_load_series
    )

    return response


@router.post("", status_code=201)
async def create_training_period(
    payload: TrainingPeriodCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=400,
            detail=(
                "end_date must be on or after "
                "start_date"
            ),
        )

    objective_types = [
        objective.objective_type
        for objective in payload.objectives
    ]

    if len(objective_types) != len(
        set(objective_types)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Objective types must be unique "
                "within a training period"
            ),
        )

    total_weight = sum(
        objective.weight
        for objective in payload.objectives
    )

    if total_weight > 1.000001:
        raise HTTPException(
            status_code=400,
            detail=(
                "Objective weights cannot total "
                "more than 1.0"
            ),
        )

    if payload.parent_id is not None:
        parent = await db.scalar(
            select(TrainingPeriod).where(
                TrainingPeriod.id
                == payload.parent_id,
                TrainingPeriod.user_id
                == user.id,
            )
        )

        if parent is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Parent training period "
                    "not found"
                ),
            )

        if (
            payload.start_date
            < parent.start_date
            or payload.end_date
            > parent.end_date
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Child training period must "
                    "fit inside its parent period"
                ),
            )

    period = TrainingPeriod(
        user_id=user.id,
        parent_id=payload.parent_id,
        period_type=payload.period_type,
        title=payload.title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        description=payload.description,
        target_load=payload.target_load,
        load_method=payload.load_method,
        target_duration_sec=(
            payload.target_duration_sec
        ),
        extra_data=payload.extra_data,
    )

    db.add(period)

    await db.flush()

    objectives: list[
        TrainingPeriodObjective
    ] = []

    for item in payload.objectives:
        objective = TrainingPeriodObjective(
            period_id=period.id,
            objective_type=item.objective_type,
            weight=item.weight,
        )

        db.add(objective)
        objectives.append(objective)

    await db.commit()

    return serialize_period(
        period,
        objectives,
    )