from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    PlannedWorkout,
    User,
    WorkoutSession,
    WorkoutStatus,
)


async def link_sessions_to_planned_workouts(
    db: AsyncSession,
    user: User,
) -> dict:
    sessions_result = await db.scalars(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.external_provider == "POLAR",
        )
    )

    sessions = list(sessions_result)

    linked = 0
    already_linked = 0
    unmatched = 0
    conflicts = []

    for session in sessions:
        raw = session.raw_data or {}

        training_target = (
            raw.get("trainingTarget") or {}
        )

        target_id = training_target.get("id")

        if not target_id:
            continue

        target_id = str(target_id)

        planned = await db.scalar(
            select(PlannedWorkout).where(
                PlannedWorkout.user_id == user.id,
                PlannedWorkout.polar_target_id == target_id,
            )
        )

        if not planned:
            unmatched += 1
            continue

        if session.planned_workout_id is None:
            session.planned_workout_id = planned.id
            linked += 1
            continue

        if session.planned_workout_id == planned.id:
            already_linked += 1
            continue

        conflicts.append(
            {
                "session_id": str(session.id),
                "training_target_id": target_id,
                "existing_planned_workout_id": str(
                    session.planned_workout_id
                ),
                "matched_planned_workout_id": str(
                    planned.id
                ),
            }
        )

    await db.commit()

    return {
        "linked": linked,
        "already_linked": already_linked,
        "unmatched": unmatched,
        "conflicts": conflicts,
    }


async def reconcile_completed_planned_workouts(
    db: AsyncSession,
    user: User,
) -> dict:
    sessions_result = await db.scalars(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.external_provider == "POLAR",
            WorkoutSession.planned_workout_id.is_not(None),
        )
    )

    sessions = list(sessions_result)

    completed = 0
    already_completed = 0
    missing_workout = 0

    for session in sessions:
        if session.planned_workout_id is None:
            continue

        planned = await db.get(
            PlannedWorkout,
            session.planned_workout_id,
        )

        if planned is None:
            missing_workout += 1
            continue

        if planned.status == WorkoutStatus.COMPLETED:
            already_completed += 1
            continue

        planned.status = WorkoutStatus.COMPLETED
        planned.updated_at = datetime.now(timezone.utc)

        completed += 1

    await db.commit()

    return {
        "completed": completed,
        "already_completed": already_completed,
        "missing_workout": missing_workout,
    }