from typing import Protocol

from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
)


class PlanningAuditRepository(Protocol):
    def save(
        self,
        record: AuditArtifactRecord,
    ) -> AuditArtifactSaveResult:
        ...

    def get(
        self,
        *,
        artifact_kind: AuditArtifactKind,
        artifact_id: str,
    ) -> AuditArtifactRecord | None:
        ...

    def list_for_athlete(
        self,
        *,
        athlete_id: str,
        artifact_kind: AuditArtifactKind | None = None,
        limit: int = 50,
    ) -> tuple[AuditArtifactRecord, ...]:
        ...


class AsyncPlanningAuditRepository(Protocol):
    async def save(
        self,
        record: AuditArtifactRecord,
    ) -> AuditArtifactSaveResult:
        ...

    async def get(
        self,
        *,
        artifact_kind: AuditArtifactKind,
        artifact_id: str,
    ) -> AuditArtifactRecord | None:
        ...

    async def list_for_athlete(
        self,
        *,
        athlete_id: str,
        artifact_kind: AuditArtifactKind | None = None,
        limit: int = 50,
    ) -> tuple[AuditArtifactRecord, ...]:
        ...
