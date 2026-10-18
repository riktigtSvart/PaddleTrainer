from __future__ import annotations

from types import SimpleNamespace
from typing import Protocol
from uuid import UUID

from sqlalchemy import select


class LockedPlanSourceHashProvider(Protocol):
    async def lock_and_hash(
        self,
        session,
        *,
        source_workout_id: str,
        athlete_id: str,
    ) -> str:
        """Return the current source-content hash while holding source locks."""
        ...


class CurrentAppLockedPlanSourceHashProvider:
    """Compute the exact plan-read source hash under database row locks.

    The parent PlannedWorkout row is locked before its WorkoutBlock rows. The
    source snapshot is then passed through the existing plan-contract snapshot
    serializer and digest function, so adoption compares against the same
    source_content_sha256 semantics as the current read API.
    """

    async def lock_and_hash(
        self,
        session,
        *,
        source_workout_id: str,
        athlete_id: str,
    ) -> str:
        from app.models.entities import PlannedWorkout, WorkoutBlock
        from app.services.plan_contract_read import (
            PlanReadError,
            digest,
            stored_workout_snapshot,
        )

        try:
            workout_uuid = UUID(source_workout_id)
            athlete_uuid = UUID(athlete_id)
        except ValueError as exc:
            raise ValueError("source_workout_id and athlete_id must be UUID strings.") from exc

        result = await session.execute(
            select(PlannedWorkout)
            .where(
                PlannedWorkout.id == workout_uuid,
                PlannedWorkout.user_id == athlete_uuid,
            )
            .with_for_update()
        )
        workout = result.scalar_one_or_none()
        if workout is None:
            raise PlanReadError("PLAN_CONTRACT_WORKOUT_NOT_FOUND", 404)

        blocks_result = await session.execute(
            select(WorkoutBlock)
            .where(WorkoutBlock.workout_id == workout_uuid)
            .order_by(WorkoutBlock.position, WorkoutBlock.id)
            .with_for_update()
        )
        blocks = list(blocks_result.scalars())

        # Avoid relationship lazy loading and ensure the hash is based exactly
        # on the locked rows returned above.
        proxy_values = {
            column.name: getattr(workout, column.name)
            for column in PlannedWorkout.__table__.columns
        }
        proxy = SimpleNamespace(**proxy_values, blocks=blocks)
        snapshot = stored_workout_snapshot(proxy, athlete_uuid)
        return digest(snapshot)
