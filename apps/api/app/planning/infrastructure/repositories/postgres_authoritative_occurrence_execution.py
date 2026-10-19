from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...domain.occurrence_execution import (
    AuthoritativeOccurrenceExecutionLink,
    OccurrenceExecutionConflictError,
    OccurrenceExecutionLinkBasis,
    restore_authoritative_occurrence_execution_link,
)
from ..persistence.sqlalchemy_models import (
    PlanningOccurrenceExecutionLinkRow,
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
            "Occurrence execution-link UUID field is invalid."
        ) from exc


def _same_binding(
    left: AuthoritativeOccurrenceExecutionLink,
    right: AuthoritativeOccurrenceExecutionLink,
) -> bool:
    excluded = {
        "link_id",
        "created_at",
        "content_hash",
    }
    return all(
        getattr(left, name) == getattr(right, name)
        for name in left.__dataclass_fields__
        if name not in excluded
    )


class SqlAlchemyAuthoritativeOccurrenceExecutionLinkRepository:
    """Append-only authoritative occurrence/execution linkage.

    Methods flush but never commit. Update/delete operations are not
    exposed.
    """

    repository_version = (
        "authoritative-occurrence-execution-link-repository-v0.1"
    )

    def __init__(self, session) -> None:
        self._session = session

    async def get_by_occurrence(
        self,
        *,
        plan_execution_link_id: str,
        authoritative_occurrence_id: str,
    ) -> AuthoritativeOccurrenceExecutionLink | None:
        result = await self._session.execute(
            select(PlanningOccurrenceExecutionLinkRow).where(
                PlanningOccurrenceExecutionLinkRow.plan_execution_link_id
                == plan_execution_link_id,
                PlanningOccurrenceExecutionLinkRow.authoritative_occurrence_id
                == authoritative_occurrence_id,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else self._from_row(row)

    async def list_by_plan_execution_link(
        self,
        *,
        plan_execution_link_id: str,
    ) -> tuple[AuthoritativeOccurrenceExecutionLink, ...]:
        result = await self._session.execute(
            select(PlanningOccurrenceExecutionLinkRow)
            .where(
                PlanningOccurrenceExecutionLinkRow.plan_execution_link_id
                == plan_execution_link_id
            )
            .order_by(
                PlanningOccurrenceExecutionLinkRow.authoritative_occurrence_id,
                PlanningOccurrenceExecutionLinkRow.link_id,
            )
        )
        return tuple(
            self._from_row(row)
            for row in result.scalars().all()
        )

    async def save(
        self,
        link: AuthoritativeOccurrenceExecutionLink,
    ) -> AuthoritativeOccurrenceExecutionLink:
        if not link.verify_content_hash():
            raise ValueError(
                "Occurrence execution-link content hash is invalid."
            )

        existing = await self.get_by_occurrence(
            plan_execution_link_id=link.plan_execution_link_id,
            authoritative_occurrence_id=(
                link.authoritative_occurrence_id
            ),
        )
        if existing is not None:
            if _same_binding(existing, link):
                return existing
            raise OccurrenceExecutionConflictError(
                "Authoritative occurrence is already linked to "
                "different execution evidence."
            )

        self._session.add(
            PlanningOccurrenceExecutionLinkRow(
                link_id=link.link_id,
                schema_version=link.schema_version,
                athlete_id=_uuid(link.athlete_id),
                plan_execution_link_id=(
                    link.plan_execution_link_id
                ),
                logical_plan_id=link.logical_plan_id,
                observed_revision_id=link.observed_revision_id,
                authoritative_occurrence_id=(
                    link.authoritative_occurrence_id
                ),
                workout_session_id=_uuid(
                    link.workout_session_id
                ),
                link_basis=link.link_basis.value,
                phase_reconciliation_artifact_id=(
                    link.phase_reconciliation_artifact_id
                ),
                phase_reconciliation_rules_version=(
                    link.phase_reconciliation_rules_version
                ),
                session_source_content_hash=(
                    link.session_source_content_hash
                ),
                plan_source_content_hash=(
                    link.plan_source_content_hash
                ),
                stable_source_occurrence_id=(
                    link.stable_source_occurrence_id
                ),
                captured_contract_occurrence_id=(
                    link.captured_contract_occurrence_id
                ),
                hypothesis_id=link.hypothesis_id,
                candidate_start_min_s=(
                    link.candidate_start_window_s[0]
                ),
                candidate_start_max_s=(
                    link.candidate_start_window_s[1]
                ),
                candidate_completion_min_s=(
                    link.candidate_completion_window_s[0]
                ),
                candidate_completion_max_s=(
                    link.candidate_completion_window_s[1]
                ),
                clock_domain=link.clock_domain,
                confirmation_id=link.confirmation_id,
                confirmation_submitted_at=(
                    link.confirmation_submitted_at
                ),
                occurrence_alignment_status=(
                    link.occurrence_alignment_status
                ),
                plan_content_at_execution_status=(
                    link.plan_content_at_execution_status
                ),
                provider_event_verified=(
                    link.provider_event_verified
                ),
                clock_alignment_verified=(
                    link.clock_alignment_verified
                ),
                actual_boundary_verified=(
                    link.actual_boundary_verified
                ),
                temporal_match_used=link.temporal_match_used,
                created_at=link.created_at,
                content_hash_algorithm=(
                    link.content_hash_algorithm
                ),
                content_hash=link.content_hash,
            )
        )

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise OccurrenceExecutionConflictError(
                "Authoritative occurrence execution-link "
                "insert conflict."
            ) from exc

        return link

    def _from_row(
        self,
        row: PlanningOccurrenceExecutionLinkRow,
    ) -> AuthoritativeOccurrenceExecutionLink:
        return restore_authoritative_occurrence_execution_link(
            link_id=row.link_id,
            schema_version=row.schema_version,
            athlete_id=str(row.athlete_id),
            plan_execution_link_id=row.plan_execution_link_id,
            logical_plan_id=row.logical_plan_id,
            observed_revision_id=row.observed_revision_id,
            authoritative_occurrence_id=(
                row.authoritative_occurrence_id
            ),
            workout_session_id=str(row.workout_session_id),
            link_basis=OccurrenceExecutionLinkBasis(
                row.link_basis
            ),
            phase_reconciliation_artifact_id=(
                row.phase_reconciliation_artifact_id
            ),
            phase_reconciliation_rules_version=(
                row.phase_reconciliation_rules_version
            ),
            session_source_content_hash=(
                row.session_source_content_hash
            ),
            plan_source_content_hash=(
                row.plan_source_content_hash
            ),
            stable_source_occurrence_id=(
                row.stable_source_occurrence_id
            ),
            captured_contract_occurrence_id=(
                row.captured_contract_occurrence_id
            ),
            hypothesis_id=row.hypothesis_id,
            candidate_start_window_s=(
                row.candidate_start_min_s,
                row.candidate_start_max_s,
            ),
            candidate_completion_window_s=(
                row.candidate_completion_min_s,
                row.candidate_completion_max_s,
            ),
            clock_domain=row.clock_domain,
            confirmation_id=row.confirmation_id,
            confirmation_submitted_at=_db_utc(
                row.confirmation_submitted_at
            ),
            occurrence_alignment_status=(
                row.occurrence_alignment_status
            ),
            plan_content_at_execution_status=(
                row.plan_content_at_execution_status
            ),
            provider_event_verified=(
                row.provider_event_verified
            ),
            clock_alignment_verified=(
                row.clock_alignment_verified
            ),
            actual_boundary_verified=(
                row.actual_boundary_verified
            ),
            temporal_match_used=row.temporal_match_used,
            created_at=_db_utc(row.created_at),
            content_hash_algorithm=row.content_hash_algorithm,
            content_hash=row.content_hash,
        )


def build_production_authoritative_occurrence_execution_repository(
    session,
):
    return (
        SqlAlchemyAuthoritativeOccurrenceExecutionLinkRepository(
            session
        )
    )
