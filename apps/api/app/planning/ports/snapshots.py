from typing import Protocol

from ..domain.persistence.models import SnapshotRecord, SnapshotSaveResult


class PlanningSnapshotRepository(Protocol):
    def save(self, record: SnapshotRecord) -> SnapshotSaveResult:
        ...

    def get(self, snapshot_id: str) -> SnapshotRecord | None:
        ...

    def list_for_athlete(
        self,
        *,
        athlete_id: str,
        limit: int = 50,
    ) -> tuple[SnapshotRecord, ...]:
        ...
