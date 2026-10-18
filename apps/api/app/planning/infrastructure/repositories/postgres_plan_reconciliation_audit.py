from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...domain.common.serialization import canonical_json
from ...domain.plan_revision.reconciliation_audit import (
    PolarReconciliationAuditRecord,
    load_polar_reconciliation_audit_record,
)
from ..persistence.sqlalchemy_models import PlanningPlanRevisionReconciliationAuditRow


class PlanReconciliationAuditPersistenceError(RuntimeError):
    pass


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _uuid(value: str, *, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UUID string.") from exc


class SqlAlchemyPlanReconciliationAuditRepository:
    def __init__(self, session):
        self._session = session

    async def persist_polar_audit(
        self,
        *,
        record: PolarReconciliationAuditRecord,
    ) -> PolarReconciliationAuditRecord:
        if not record.verify_reconciliation_artifact_hash():
            raise ValueError("Polar reconciliation artifact hash does not verify.")
        if not record.verify_content_hash():
            raise ValueError("Polar reconciliation audit record hash does not verify.")
        self._session.add(
            PlanningPlanRevisionReconciliationAuditRow(
                revision_id=record.revision_id,
                audit_schema_version=record.audit_schema_version,
                logical_plan_id=record.logical_plan_id,
                athlete_id=_uuid(record.athlete_id, field_name="athlete_id"),
                source_workout_id=_uuid(
                    record.source_workout_id,
                    field_name="source_workout_id",
                ),
                capture_id=record.capture_id,
                reconciliation_schema_version=record.reconciliation_schema_version,
                reconciliation_rules_version=record.reconciliation_rules_version,
                reconciliation_content_hash_algorithm=(
                    record.reconciliation_content_hash_algorithm
                ),
                reconciliation_content_hash=record.reconciliation_content_hash,
                reconciliation_artifact_json=json.loads(
                    record.reconciliation_canonical_json
                ),
                reconciliation_captured_at=record.reconciliation_captured_at,
                source_content_sha256=record.source_content_sha256,
                source_read_content_hash=record.source_read_content_hash,
                timezone_context_name=record.timezone_context_name,
                timezone_context_source=record.timezone_context_source,
                reconciliation_status=record.reconciliation_status,
                created_at=record.created_at,
                audit_content_hash_algorithm=record.content_hash_algorithm,
                audit_content_hash=record.content_hash,
            )
        )
        try:
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise PlanReconciliationAuditPersistenceError(
                "Polar reconciliation audit persistence failed."
            ) from exc
        return record

    async def get_polar_audit(
        self,
        *,
        revision_id: str,
    ) -> PolarReconciliationAuditRecord | None:
        try:
            result = await self._session.execute(
                select(PlanningPlanRevisionReconciliationAuditRow).where(
                    PlanningPlanRevisionReconciliationAuditRow.revision_id
                    == revision_id
                )
            )
        except SQLAlchemyError as exc:
            raise PlanReconciliationAuditPersistenceError(
                "Polar reconciliation audit storage is unavailable."
            ) from exc
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return load_polar_reconciliation_audit_record(
            audit_schema_version=row.audit_schema_version,
            revision_id=row.revision_id,
            logical_plan_id=row.logical_plan_id,
            athlete_id=str(row.athlete_id),
            source_workout_id=str(row.source_workout_id),
            capture_id=row.capture_id,
            reconciliation_schema_version=row.reconciliation_schema_version,
            reconciliation_rules_version=row.reconciliation_rules_version,
            reconciliation_content_hash_algorithm=(
                row.reconciliation_content_hash_algorithm
            ),
            reconciliation_content_hash=row.reconciliation_content_hash,
            reconciliation_canonical_json=canonical_json(
                row.reconciliation_artifact_json
            ),
            reconciliation_captured_at=_db_utc(row.reconciliation_captured_at),
            source_content_sha256=row.source_content_sha256,
            source_read_content_hash=row.source_read_content_hash,
            timezone_context_name=row.timezone_context_name,
            timezone_context_source=row.timezone_context_source,
            reconciliation_status=row.reconciliation_status,
            created_at=_db_utc(row.created_at),
            content_hash_algorithm=row.audit_content_hash_algorithm,
            content_hash=row.audit_content_hash,
        )


def build_production_plan_reconciliation_audit_repository(session):
    return SqlAlchemyPlanReconciliationAuditRepository(session)
