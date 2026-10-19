from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...domain.execution_link import (
    AuthoritativeExecutionLinkConflictError,
    AuthoritativePlanExecutionLink,
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
)
from ..persistence.sqlalchemy_models import (
    PlanningPlanExecutionLinkRow,
)


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(
            "Execution-link UUID field is invalid."
        ) from exc


def _same_binding(
    left: AuthoritativePlanExecutionLink,
    right: AuthoritativePlanExecutionLink,
) -> bool:
    return (
        left.athlete_id == right.athlete_id
        and left.logical_plan_id == right.logical_plan_id
        and left.observed_revision_id
        == right.observed_revision_id
        and left.workout_session_id
        == right.workout_session_id
        and left.source_workout_id
        == right.source_workout_id
        and left.link_basis == right.link_basis
        and left.provider_target_id
        == right.provider_target_id
        and left.source_workout_content_hash
        == right.source_workout_content_hash
        and left.session_source_content_hash
        == right.session_source_content_hash
        and left.observed_revision_content_hash
        == right.observed_revision_content_hash
        and left.plan_content_at_execution_status
        == right.plan_content_at_execution_status
        and left.temporal_match_used
        == right.temporal_match_used
    )


class SqlAlchemyAuthoritativePlanExecutionLinkRepository:
    """Append-only authoritative plan-to-execution linkage.

    Methods flush but never commit. No update or delete operation is
    exposed by this repository.
    """

    repository_version = (
        "authoritative-plan-execution-link-repository-v0.1"
    )

    def __init__(self, session) -> None:
        self._session = session

    async def get_by_session(
        self,
        *,
        workout_session_id: str,
    ) -> AuthoritativePlanExecutionLink | None:
        result = await self._session.execute(
            select(PlanningPlanExecutionLinkRow).where(
                PlanningPlanExecutionLinkRow.workout_session_id
                == _uuid(workout_session_id)
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else self._from_row(row)

    async def save(
        self,
        link: AuthoritativePlanExecutionLink,
    ) -> AuthoritativePlanExecutionLink:
        if not link.verify_content_hash():
            raise ValueError(
                "Execution-link content hash is invalid."
            )

        existing = await self.get_by_session(
            workout_session_id=link.workout_session_id
        )
        if existing is not None:
            if _same_binding(existing, link):
                return existing
            raise AuthoritativeExecutionLinkConflictError(
                "Workout session is already linked to another "
                "authoritative plan binding."
            )

        self._session.add(
            PlanningPlanExecutionLinkRow(
                link_id=link.link_id,
                schema_version=link.schema_version,
                athlete_id=_uuid(link.athlete_id),
                logical_plan_id=link.logical_plan_id,
                observed_revision_id=link.observed_revision_id,
                workout_session_id=_uuid(
                    link.workout_session_id
                ),
                source_workout_id=_uuid(
                    link.source_workout_id
                ),
                link_basis=link.link_basis.value,
                provider_target_id=link.provider_target_id,
                source_workout_content_hash=
                    link.source_workout_content_hash,
                session_source_content_hash=
                    link.session_source_content_hash,
                observed_revision_content_hash=
                    link.observed_revision_content_hash,
                plan_content_at_execution_status=
                    link.plan_content_at_execution_status,
                temporal_match_used=link.temporal_match_used,
                created_at=link.created_at,
                content_hash_algorithm=
                    link.content_hash_algorithm,
                content_hash=link.content_hash,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise AuthoritativeExecutionLinkConflictError(
                "Authoritative execution-link insert conflict."
            ) from exc

        return link

    def _from_row(
        self,
        row: PlanningPlanExecutionLinkRow,
    ) -> AuthoritativePlanExecutionLink:
        link = finalize_authoritative_plan_execution_link(
            link_id=row.link_id,
            athlete_id=str(row.athlete_id),
            logical_plan_id=row.logical_plan_id,
            observed_revision_id=row.observed_revision_id,
            workout_session_id=str(row.workout_session_id),
            source_workout_id=str(row.source_workout_id),
            link_basis=ExecutionLinkBasis(row.link_basis),
            provider_target_id=row.provider_target_id,
            source_workout_content_hash=
                row.source_workout_content_hash,
            session_source_content_hash=
                row.session_source_content_hash,
            observed_revision_content_hash=
                row.observed_revision_content_hash,
            created_at=_db_utc(row.created_at),
        )
        if link.content_hash != row.content_hash:
            raise ValueError(
                "Stored authoritative execution-link hash mismatch."
            )
        return link


def build_production_authoritative_plan_execution_repository(
    session,
):
    return SqlAlchemyAuthoritativePlanExecutionLinkRepository(
        session
    )
