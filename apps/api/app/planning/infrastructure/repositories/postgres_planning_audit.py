from __future__ import annotations

from datetime import timezone
from uuid import UUID

from sqlalchemy import func, select

from ...domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
    AuditArtifactSaveStatus,
)
from ..persistence.sqlalchemy_models import (
    PlanningAuditArtifactRow,
)


class SqlAlchemyPlanningAuditRepository:
    """Main-database persistence for immutable planning audit artifacts.

    The repository flushes but never commits. Transaction ownership remains
    with the application service.
    """

    def __init__(self, session) -> None:
        self.session = session

    @staticmethod
    def _athlete_uuid(athlete_id: str) -> UUID:
        try:
            return UUID(athlete_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                "Planning audit athlete_id must be a UUID."
            ) from exc

    @staticmethod
    def _from_row(
        row: PlanningAuditArtifactRow,
    ) -> AuditArtifactRecord:
        created_at = row.created_at
        persisted_at = row.persisted_at

        # PostgreSQL preserves timezone-aware DateTime values. SQLite, used
        # only by repository contract tests here, returns stored UTC values
        # as naive datetimes. Restore UTC at the adapter boundary.
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        if (
            persisted_at is not None
            and persisted_at.tzinfo is None
        ):
            persisted_at = persisted_at.replace(
                tzinfo=timezone.utc
            )

        return AuditArtifactRecord(
            artifact_kind=AuditArtifactKind(row.artifact_kind),
            artifact_id=row.artifact_id,
            athlete_id=str(row.athlete_id),
            schema_version=row.schema_version,
            created_at=created_at,
            content_hash_algorithm=row.content_hash_algorithm,
            content_hash=row.content_hash,
            contract_json=row.contract_json,
            persisted_at=persisted_at,
        )

    async def save(
        self,
        record: AuditArtifactRecord,
    ) -> AuditArtifactSaveResult:
        if record.persisted_at is not None:
            raise ValueError(
                "persisted_at is database-assigned and "
                "must not be supplied by callers."
            )

        result = await self.session.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind
                == record.artifact_kind.value,
                PlanningAuditArtifactRow.artifact_id
                == record.artifact_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            current = self._from_row(existing)
            if (
                current.content_hash != record.content_hash
                or current.contract_json != record.contract_json
                or current.athlete_id != record.athlete_id
            ):
                raise AuditArtifactConflictError(
                    "Immutable audit artifact identity already exists "
                    "with different content."
                )

            return AuditArtifactSaveResult(
                status=AuditArtifactSaveStatus.ALREADY_PRESENT,
                artifact_kind=record.artifact_kind,
                artifact_id=record.artifact_id,
                content_hash=record.content_hash,
            )

        self.session.add(
            PlanningAuditArtifactRow(
                artifact_kind=record.artifact_kind.value,
                artifact_id=record.artifact_id,
                athlete_id=self._athlete_uuid(record.athlete_id),
                schema_version=record.schema_version,
                created_at=record.created_at,
                # Prospective issuance proof uses database time,
                # never a caller-provided Python timestamp.
                # PostgreSQL statement_timestamp() reflects the
                # start of this persistence statement rather than
                # the start of a potentially long transaction.
                persisted_at=(
                    func.statement_timestamp()
                    if self.session.get_bind().dialect.name
                    == "postgresql"
                    else func.current_timestamp()
                ),
                content_hash_algorithm=record.content_hash_algorithm,
                content_hash=record.content_hash,
                contract_json=record.contract_json,
            )
        )
        await self.session.flush()

        return AuditArtifactSaveResult(
            status=AuditArtifactSaveStatus.CREATED,
            artifact_kind=record.artifact_kind,
            artifact_id=record.artifact_id,
            content_hash=record.content_hash,
        )

    async def get(
        self,
        *,
        artifact_kind: AuditArtifactKind,
        artifact_id: str,
    ) -> AuditArtifactRecord | None:
        result = await self.session.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind
                == artifact_kind.value,
                PlanningAuditArtifactRow.artifact_id
                == artifact_id,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else self._from_row(row)

    async def list_for_athlete(
        self,
        *,
        athlete_id: str,
        artifact_kind: AuditArtifactKind | None = None,
        limit: int = 50,
    ) -> tuple[AuditArtifactRecord, ...]:
        if limit < 1 or limit > 500:
            raise ValueError(
                "limit must be between 1 and 500."
            )

        statement = select(
            PlanningAuditArtifactRow
        ).where(
            PlanningAuditArtifactRow.athlete_id
            == self._athlete_uuid(athlete_id)
        )

        if artifact_kind is not None:
            statement = statement.where(
                PlanningAuditArtifactRow.artifact_kind
                == artifact_kind.value
            )

        statement = statement.order_by(
            PlanningAuditArtifactRow.created_at.desc(),
            PlanningAuditArtifactRow.artifact_kind.asc(),
            PlanningAuditArtifactRow.artifact_id.asc(),
        ).limit(limit)

        result = await self.session.execute(statement)

        return tuple(
            self._from_row(row)
            for row in result.scalars().all()
        )


def build_production_planning_audit_repository(
    session,
) -> SqlAlchemyPlanningAuditRepository:
    return SqlAlchemyPlanningAuditRepository(session)
