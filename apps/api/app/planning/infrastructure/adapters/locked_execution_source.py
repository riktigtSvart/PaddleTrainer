from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.entities import (
    PlannedWorkout,
    WorkoutSession,
)
from app.services.executed_workout_read import (
    stored_session_snapshot,
)

from ...domain.execution_link import snapshot_content_hash
from ...ports.execution_source import (
    ExecutionSourceNotFound,
    LockedExecutionSourceCapture,
)
from .locked_plan_source import (
    CurrentAppLockedPlanSourceHashProvider,
)


def _uuid(value: str, *, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc


def _value(value):
    return getattr(value, "value", value)


class CurrentAppLockedExecutionSource:
    """Lock current mutable execution and plan-source evidence.

    The full planned-workout content hash is delegated to the same
    locked source provider used by authoritative plan adoption.
    """

    def __init__(self) -> None:
        self._plan_source_hash_provider = (
            CurrentAppLockedPlanSourceHashProvider()
        )

    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id: str,
        source_workout_id: str,
        workout_session_id: str,
    ) -> LockedExecutionSourceCapture:
        athlete_uuid = _uuid(
            athlete_id,
            field_name="athlete_id",
        )
        source_uuid = _uuid(
            source_workout_id,
            field_name="source_workout_id",
        )
        session_uuid = _uuid(
            workout_session_id,
            field_name="workout_session_id",
        )

        source_hash = (
            await self._plan_source_hash_provider.lock_and_hash(
                session,
                source_workout_id=source_workout_id,
                athlete_id=athlete_id,
            )
        )

        source_result = await session.execute(
            select(PlannedWorkout)
            .where(
                PlannedWorkout.id == source_uuid,
                PlannedWorkout.user_id == athlete_uuid,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        source_row = source_result.scalar_one_or_none()
        if source_row is None:
            raise ExecutionSourceNotFound(
                "Owned source workout not found."
            )

        session_result = await session.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.id == session_uuid,
                WorkoutSession.user_id == athlete_uuid,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        session_row = session_result.scalar_one_or_none()
        if session_row is None:
            raise ExecutionSourceNotFound(
                "Owned workout session not found."
            )

        session_snapshot = stored_session_snapshot(
            session_row,
            athlete_uuid,
        )

        # Only identity/link-relevant planned-workout fields are
        # projected here. Full mutable source content is separately
        # bound by source_hash above.
        source_snapshot = {
            "id": str(source_row.id),
            "user_id": str(source_row.user_id),
            "sport": _value(source_row.sport),
            "source": _value(source_row.source),
            "polar_target_id": (
                None
                if source_row.polar_target_id is None
                else str(source_row.polar_target_id)
            ),
        }

        return LockedExecutionSourceCapture(
            session_snapshot=session_snapshot,
            source_workout_snapshot=source_snapshot,
            source_workout_content_hash=source_hash,
            session_source_content_hash=snapshot_content_hash(
                session_snapshot
            ),
        )
