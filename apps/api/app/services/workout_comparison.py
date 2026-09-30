from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import (
    BlockType,
    PlannedWorkout,
    User,
    WorkoutSession,
)


def _percent_delta(
    actual: float | int | None,
    planned: float | int | None,
) -> float | None:
    if actual is None or planned is None or planned == 0:
        return None

    return round(
        ((actual - planned) / planned) * 100,
        1,
    )


def _block_to_dict(block) -> dict[str, Any]:
    return {
        "id": str(block.id),
        "position": block.position,
        "block_type": block.block_type.value,
        "name": block.name,
        "duration_sec": block.duration_sec,
        "distance_m": block.distance_m,
        "intensity_type": block.intensity_type,
        "intensity_min": block.intensity_min,
        "intensity_max": block.intensity_max,
        "repeat_count": block.repeat_count,
        "parent_block_id": (
            str(block.parent_block_id)
            if block.parent_block_id
            else None
        ),
    }


def _session_to_dict(
    session: WorkoutSession,
) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "planned_workout_link_source": (
            session.planned_workout_link_source.value
            if session.planned_workout_link_source
            else None
        ),
        "external_provider": session.external_provider,
        "external_id": session.external_id,
        "sport": session.sport.value,
        "name": session.name,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "duration_sec": session.duration_sec,
        "distance_m": session.distance_m,
        "calories": session.calories,
        "avg_hr": session.avg_hr,
        "max_hr": session.max_hr,
        "avg_speed": session.avg_speed,
        "max_speed": session.max_speed,
        "avg_cadence": session.avg_cadence,
        "max_cadence": session.max_cadence,
        "avg_power": session.avg_power,
        "max_power": session.max_power,
        "cardio_load": session.cardio_load,
        "perceived_load": session.perceived_load,
        "rpe": session.rpe,
    }

def _comparison_basis(
    workout: PlannedWorkout,
) -> str:
    leaf_blocks = [
        block
        for block in workout.blocks
        if block.block_type != BlockType.REPEAT
    ]

    has_duration = any(
        block.duration_sec is not None
        for block in leaf_blocks
    )

    has_distance = any(
        block.distance_m is not None
        for block in leaf_blocks
    )

    # Manual / blokk nélküli workout fallback
    if not leaf_blocks:
        has_duration = (
            workout.duration_sec is not None
        )
        has_distance = (
            workout.distance_m is not None
        )

    if has_duration and has_distance:
        return "MIXED"

    if has_duration:
        return "DURATION"

    if has_distance:
        return "DISTANCE"

    return "NONE"

def _completion_summary(
    workout: PlannedWorkout,
    actual: WorkoutSession | None,
    comparison: dict[str, Any],
) -> dict[str, Any]:
    basis = comparison["basis"]

    planned_value = None
    actual_value = None
    delta = None
    delta_percent = None
    unit = None

    if basis == "DURATION":
        unit = "sec"
        planned_value = workout.duration_sec

        if actual is not None:
            actual_value = actual.duration_sec

        delta = comparison[
            "duration_delta_sec"
        ]

        delta_percent = comparison[
            "duration_delta_percent"
        ]

    elif basis == "DISTANCE":
        unit = "m"
        planned_value = workout.distance_m

        if actual is not None:
            actual_value = actual.distance_m

        delta = comparison[
            "distance_delta_m"
        ]

        delta_percent = comparison[
            "distance_delta_percent"
        ]

    return {
        "status": (
            "COMPLETED"
            if actual is not None
            else workout.status.value
        ),
        "basis": basis,
        "unit": unit,
        "planned": planned_value,
        "actual": actual_value,
        "delta": delta,
        "delta_percent": delta_percent,
        "has_actual": actual is not None,
    }


async def get_workout_comparisons(
    db: AsyncSession,
    user: User,
) -> list[dict[str, Any]]:
    workout_result = await db.scalars(
        select(PlannedWorkout)
        .options(
            selectinload(PlannedWorkout.blocks)
        )
        .where(
            PlannedWorkout.user_id == user.id
        )
        .order_by(
            PlannedWorkout.date.desc(),
            PlannedWorkout.planned_start_time.desc(),
        )
    )

    workouts = list(workout_result)

    session_result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.planned_workout_id.is_not(None),
        )
        .order_by(
            WorkoutSession.started_at.desc()
        )
    )

    sessions = list(session_result)

    sessions_by_workout: dict[str, list[WorkoutSession]] = {}

    for session in sessions:
        key = str(session.planned_workout_id)

        sessions_by_workout.setdefault(
            key,
            [],
        ).append(session)

    response = []

    for workout in workouts:
        linked_sessions = sessions_by_workout.get(
            str(workout.id),
            [],
        )

        # Normál Polar esetben 1 session tartozik 1 tervhez.
        # Ha valamiért több van, nem veszítjük el ezt az információt.
        actual = (
            linked_sessions[0]
            if linked_sessions
            else None
        )

        basis = _comparison_basis(workout)

        comparison = {
            "basis": basis,
            "duration_delta_sec": None,
            "duration_delta_percent": None,
            "distance_delta_m": None,
            "distance_delta_percent": None,
        }

        if actual:
            if (
                    basis == "DURATION"
                    and actual.duration_sec is not None
                    and workout.duration_sec is not None
            ):
                comparison["duration_delta_sec"] = (
                        actual.duration_sec
                        - workout.duration_sec
                )

                comparison["duration_delta_percent"] = (
                    _percent_delta(
                        actual.duration_sec,
                        workout.duration_sec,
                    )
                )

            elif (
                    basis == "DISTANCE"
                    and actual.distance_m is not None
                    and workout.distance_m is not None
            ):
                comparison["distance_delta_m"] = round(
                    actual.distance_m
                    - workout.distance_m,
                    1,
                )

                comparison["distance_delta_percent"] = (
                    _percent_delta(
                        actual.distance_m,
                        workout.distance_m,
                    )
                )
        response.append(
            {
                "planned": {
                    "id": str(workout.id),
                    "date": workout.date,
                    "planned_start_time": (
                        workout.planned_start_time
                    ),
                    "sport": workout.sport.value,
                    "title": workout.title,
                    "description": workout.description,
                    "duration_sec": workout.duration_sec,
                    "distance_m": workout.distance_m,
                    "intensity_type": workout.intensity_type,
                    "status": workout.status.value,
                    "source": workout.source,
                    "polar_target_id": workout.polar_target_id,
                    "blocks": [
                        _block_to_dict(block)
                        for block in workout.blocks
                    ],
                },

                "actual": (
                    _session_to_dict(actual)
                    if actual
                    else None
                ),

                "comparison": comparison,

                "completion": _completion_summary(
                    workout,
                    actual,
                    comparison,
                ),

                "actual_session_count": len(
                    linked_sessions
                ),
            }
        )

    return response