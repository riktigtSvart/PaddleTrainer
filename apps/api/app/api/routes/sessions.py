from uuid import UUID
from app.services.users import get_or_create_demo_user
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import (
    PlannedWorkout,
    WorkoutLinkSource,
    WorkoutSession,
)
from app.services.exercise_hr_response import (
    build_exercise_hr_response_evidence,
)
from app.services.polar_training_samples import (
    normalize_polar_training_samples,
)
from app.services.sample_coverage import (
    build_sample_coverage_evidence,
)
from app.services.exercise_hr_trajectory import (
    build_exercise_hr_trajectory_evidence,
)
from app.services.exercise_hr_speed_alignment import (
    build_exercise_hr_speed_alignment,
)
from app.services.exercise_hr_speed_segments import (
    build_exercise_hr_speed_segments,
)
from app.services.exercise_speed_distance_consistency import (
    build_exercise_speed_distance_consistency,
)


class SessionPlannedWorkoutUpdate(BaseModel):
    planned_workout_id: UUID | None

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
)


def serialize_session(
    session: WorkoutSession,
    include_raw: bool = False,
) -> dict:
    item = {
        "id": str(session.id),
        "planned_workout_id": (
            str(session.planned_workout_id)
            if session.planned_workout_id
            else None
        ),
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
    }

    if include_raw:
        item["raw_data"] = session.raw_data

    return item


def serialize_planned_workout(
    workout: PlannedWorkout,
) -> dict:
    return {
        "id": str(workout.id),
        "date": workout.date,
        "sport": workout.sport.value,
        "title": workout.title,
        "status": workout.status.value,
        "duration_sec": workout.duration_sec,
        "distance_m": workout.distance_m,
        "intensity_type": workout.intensity_type,
    }


@router.get("")
async def list_sessions(
    include_raw: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    result = await db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id
        )
        .order_by(
            WorkoutSession.started_at.desc()
        )
    )

    sessions = list(result)

    return [
        serialize_session(
            session,
            include_raw=include_raw,
        )
        for session in sessions
    ]


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    include_raw: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    session = await db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.id == session_id,
            WorkoutSession.user_id == user.id,
        )
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    response = serialize_session(
        session,
        include_raw=include_raw,
    )

    planned_workout = None

    if session.planned_workout_id is not None:
        planned_workout = await db.scalar(
            select(PlannedWorkout).where(
                PlannedWorkout.id
                == session.planned_workout_id,
                PlannedWorkout.user_id
                == user.id,
            )
        )

    response["planned_workout"] = (
        serialize_planned_workout(
            planned_workout
        )
        if planned_workout is not None
        else None
    )

    return response


@router.get(
    "/{session_id}/exercise-hr-response"
)
async def get_exercise_hr_response(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    session = await db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.id == session_id,
            WorkoutSession.user_id == user.id,
        )
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session.external_provider != "POLAR":
        return {
            "session_id": str(session.id),
            "external_provider": (
                session.external_provider
            ),
            "external_id": session.external_id,
            "sport": session.sport.value,
            "started_at": session.started_at,
            "duration_sec": session.duration_sec,
            "evidence": {
                "metric_key": (
                    "heart_rate_bpm"
                ),
                "provider": (
                    session.external_provider
                ),
                "available": False,
                "exercise_count": 0,
                "exercises": [],
                "unavailability_reason": (
                    "PROVIDER_NORMALIZER_"
                    "UNAVAILABLE"
                ),
            },
        }

    normalized = (
        normalize_polar_training_samples(
            session.raw_data
        )
    )

    evidence = (
        build_exercise_hr_response_evidence(
            normalized
        )
    )

    sample_coverage = (
        build_sample_coverage_evidence(
            normalized,
            session_duration_sec=(
                session.duration_sec
            ),
        )
    )

    hr_trajectory = (
        build_exercise_hr_trajectory_evidence(
            normalized
        )
    )

    hr_speed_alignment = (
        build_exercise_hr_speed_alignment(
            normalized
        )
    )

    hr_speed_segments = (
        build_exercise_hr_speed_segments(
            normalized
        )
    )

    speed_distance_consistency = (
        build_exercise_speed_distance_consistency(
            normalized
        )
    )

    return {
        "session_id": str(session.id),
        "external_provider": (
            session.external_provider
        ),
        "external_id": session.external_id,
        "sport": session.sport.value,
        "started_at": session.started_at,
        "duration_sec": session.duration_sec,
        "sample_coverage": (
            sample_coverage
        ),
        "evidence": evidence,
        "hr_trajectory": hr_trajectory,
        "hr_speed_alignment": (
            hr_speed_alignment
        ),
        "hr_speed_segments": (
            hr_speed_segments
        ),
        "speed_distance_consistency": (
            speed_distance_consistency
        ),
    }


@router.patch("/{session_id}/planned-workout")
async def set_session_planned_workout(
    session_id: UUID,
    payload: SessionPlannedWorkoutUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    session = await db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.id == session_id,
            WorkoutSession.user_id == user.id,
        )
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if payload.planned_workout_id is None:
        session.planned_workout_id = None
        session.planned_workout_link_source = None

        await db.commit()

        return serialize_session(session)

    workout = await db.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.id
            == payload.planned_workout_id,
            PlannedWorkout.user_id == user.id,
        )
    )

    if workout is None:
        raise HTTPException(
            status_code=404,
            detail="Planned workout not found",
        )

    if workout.sport != session.sport:
        raise HTTPException(
            status_code=400,
            detail=(
                "Session and planned workout "
                "must have the same sport"
            ),
        )

    if (
        session.planned_workout_id is not None
        and session.planned_workout_id != workout.id
        and session.planned_workout_link_source
        == WorkoutLinkSource.PROVIDER_EXACT
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "A provider-exact workout link "
                "cannot be overwritten manually"
            ),
        )

    session.planned_workout_id = workout.id

    if (
        session.planned_workout_link_source
        != WorkoutLinkSource.PROVIDER_EXACT
    ):
        session.planned_workout_link_source = (
            WorkoutLinkSource.MANUAL_CONFIRMED
        )

    await db.commit()

    return serialize_session(session)