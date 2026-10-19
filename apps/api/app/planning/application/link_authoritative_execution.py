from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from ..domain.execution_link import (
    AuthoritativeExecutionLinkConflictError,
    AuthoritativePlanExecutionLink,
    finalize_authoritative_plan_execution_link,
    resolve_execution_link_basis,
)
from ..ports.authoritative_plan_execution import (
    AuthoritativePlanExecutionLinkRepository,
)
from ..ports.authoritative_plan_revision import (
    AuthoritativePlanRevisionRepository,
)
from ..ports.execution_source import (
    LockedExecutionSourceProvider,
)


class AuthoritativeExecutionPlanNotFound(LookupError):
    pass


class AuthoritativeExecutionPlanStateError(ValueError):
    pass


async def link_authoritative_execution_with_repository(
    *,
    athlete_id: str,
    logical_plan_id: str,
    workout_session_id: str,
    revision_repository: AuthoritativePlanRevisionRepository,
    execution_link_repository:
        AuthoritativePlanExecutionLinkRepository,
    execution_source: LockedExecutionSourceProvider,
    session,
    created_at: datetime | None = None,
    id_factory: Callable[[], object] = uuid4,
) -> AuthoritativePlanExecutionLink:
    """Persist one immutable authoritative plan/execution binding.

    This proves execution-to-logical-plan identity only. It does not
    establish historical plan content, occurrence alignment, phase
    alignment, or temporal proximity.
    """

    try:
        existing = await execution_link_repository.get_by_session(
            workout_session_id=workout_session_id
        )
        if existing is not None:
            # Do not disclose another athlete's session binding.
            if existing.athlete_id != athlete_id:
                raise AuthoritativeExecutionPlanNotFound(
                    "Authoritative execution link not found."
                )

            # A session may have only one authoritative logical-plan
            # identity. Immutable evidence is never rebound.
            if existing.logical_plan_id != logical_plan_id:
                raise AuthoritativeExecutionLinkConflictError(
                    "Workout session is already linked to another "
                    "authoritative logical plan."
                )

            # Idempotent retry: a later plan revision must not rewrite
            # the revision observed when this historical link was made.
            await session.commit()
            return existing

        identity = await revision_repository.get_plan_for_update(
            logical_plan_id=logical_plan_id
        )

        # Deliberately do not disclose cross-athlete plan existence.
        if (
            identity is None
            or identity.athlete_id != athlete_id
        ):
            raise AuthoritativeExecutionPlanNotFound(
                "Authoritative plan not found."
            )

        if (
            identity.source_workout_id is None
            or identity.current_revision_id is None
        ):
            raise AuthoritativeExecutionPlanStateError(
                "Authoritative plan has no usable source/current "
                "revision binding."
            )

        if not identity.verify_content_hash():
            raise AuthoritativeExecutionPlanStateError(
                "Authoritative plan identity hash does not verify."
            )

        revision = await revision_repository.get_revision(
            revision_id=identity.current_revision_id
        )
        if revision is None:
            raise AuthoritativeExecutionPlanStateError(
                "Current authoritative revision is missing."
            )

        if (
            revision.logical_plan_id != identity.logical_plan_id
            or revision.athlete_id != identity.athlete_id
            or revision.revision_id
            != identity.current_revision_id
        ):
            raise AuthoritativeExecutionPlanStateError(
                "Current authoritative revision binding is "
                "inconsistent."
            )

        if (
            not revision.verify_content_hash()
            or not revision.verify_contract_hash()
        ):
            raise AuthoritativeExecutionPlanStateError(
                "Current authoritative revision hash does not verify."
            )

        locked = await execution_source.lock_and_capture(
            session,
            athlete_id=athlete_id,
            source_workout_id=identity.source_workout_id,
            workout_session_id=workout_session_id,
        )

        basis, provider_target_id = (
            resolve_execution_link_basis(
                session_snapshot=locked.session_snapshot,
                source_workout_snapshot=(
                    locked.source_workout_snapshot
                ),
            )
        )

        link = finalize_authoritative_plan_execution_link(
            link_id=f"pt-exec-link:{id_factory()}",
            athlete_id=athlete_id,
            logical_plan_id=logical_plan_id,
            observed_revision_id=revision.revision_id,
            workout_session_id=workout_session_id,
            source_workout_id=identity.source_workout_id,
            link_basis=basis,
            provider_target_id=provider_target_id,
            source_workout_content_hash=(
                locked.source_workout_content_hash
            ),
            session_source_content_hash=(
                locked.session_source_content_hash
            ),
            observed_revision_content_hash=(
                revision.content_hash
            ),
            created_at=(
                created_at
                or datetime.now(timezone.utc)
            ),
        )

        persisted = await execution_link_repository.save(
            link
        )
        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return persisted
