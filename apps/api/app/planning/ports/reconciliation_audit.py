from typing import Protocol

from ..domain.plan_revision.reconciliation_audit import PolarReconciliationAuditRecord


class PlanReconciliationAuditRepository(Protocol):
    async def persist_polar_audit(
        self,
        *,
        record: PolarReconciliationAuditRecord,
    ) -> PolarReconciliationAuditRecord:
        ...

    async def get_polar_audit(
        self,
        *,
        revision_id: str,
    ) -> PolarReconciliationAuditRecord | None:
        ...
