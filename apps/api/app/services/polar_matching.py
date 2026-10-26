from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    PlannedWorkout,
    User,
    WorkoutLinkSource,
    WorkoutSession,
    WorkoutStatus,
)


async def link_exact_polar_sessions_after_import(db: AsyncSession, user: User) -> dict:
    """Backfill owned Polar references, without changing plans or existing links.

    Covers previously stored sessions as well as this import's date window.
    A null link is updated conditionally, so a concurrently assigned link wins.
    Plan revisions/occurrences and completion states are not inferred here.
    """
    report = dict(linked=0, already_linked=0, unmatched=0,
                  missing_reference=0, conflicts=0, ambiguous=0)
    # Backfilling history needs only reference columns, not stored sample series.
    plans = (await db.execute(select(PlannedWorkout.id, PlannedWorkout.polar_target_id).where(
        PlannedWorkout.user_id == user.id, PlannedWorkout.polar_target_id.is_not(None),
    ))).all()
    by_target = {}
    for plan in plans:
        by_target.setdefault(plan.polar_target_id, []).append(plan)
    sessions = (await db.execute(select(
        WorkoutSession.id, WorkoutSession.planned_workout_id,
        WorkoutSession.raw_data["trainingTarget"].label("polar_reference"),
    ).where(
        WorkoutSession.user_id == user.id, WorkoutSession.external_provider == "POLAR",
    ))).all()
    for session in sessions:
        reference = session.polar_reference
        target_id = reference.get("id") if isinstance(reference, dict) else None
        valid = (type(target_id) is int and target_id > 0 or
                 type(target_id) is str and 0 < len(target_id) <= 128
                 and target_id == target_id.strip())
        if not valid:
            report["missing_reference"] += 1
            continue
        candidates = by_target.get(str(target_id), [])
        if not candidates:
            report["unmatched"] += 1
            continue
        if len(candidates) != 1:
            report["ambiguous"] += 1
            continue
        plan = candidates[0]
        if session.planned_workout_id == plan.id:
            report["already_linked"] += 1
            continue
        if session.planned_workout_id is not None:
            report["conflicts"] += 1
            continue
        changed = await db.execute(update(WorkoutSession).where(
            WorkoutSession.id == session.id, WorkoutSession.user_id == user.id,
            WorkoutSession.external_provider == "POLAR", WorkoutSession.planned_workout_id.is_(None),
        ).values(planned_workout_id=plan.id, planned_workout_link_source=WorkoutLinkSource.PROVIDER_EXACT))
        report["linked" if changed.rowcount == 1 else "conflicts"] += 1
    await db.commit()
    return report


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
            session.planned_workout_link_source = (
                WorkoutLinkSource.PROVIDER_EXACT
            )
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
