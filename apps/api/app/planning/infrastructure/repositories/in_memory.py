from ...domain.evidence.models import EvidenceItem
from ...domain.persistence.models import (
    SnapshotConflictError,
    SnapshotRecord,
    SnapshotSaveResult,
    SnapshotSaveStatus,
)


class InMemoryPlanningSnapshotRepository:
    """Executable reference for immutable persistence semantics."""

    def __init__(self) -> None:
        self._records: dict[str, SnapshotRecord] = {}

    def save(self, record: SnapshotRecord) -> SnapshotSaveResult:
        existing = self._records.get(record.snapshot_id)
        if existing is None:
            self._records[record.snapshot_id] = record
            return SnapshotSaveResult(
                status=SnapshotSaveStatus.CREATED,
                snapshot_id=record.snapshot_id,
                content_hash=record.content_hash,
            )
        if existing.content_hash != record.content_hash:
            raise SnapshotConflictError(
                "Immutable snapshot ID already exists with different content."
            )
        if existing.contract_json != record.contract_json:
            raise SnapshotConflictError(
                "Snapshot hash matched but canonical stored contract differed."
            )
        return SnapshotSaveResult(
            status=SnapshotSaveStatus.ALREADY_PRESENT,
            snapshot_id=record.snapshot_id,
            content_hash=record.content_hash,
        )

    def get(self, snapshot_id: str) -> SnapshotRecord | None:
        return self._records.get(snapshot_id)

    def list_for_athlete(
        self,
        *,
        athlete_id: str,
        limit: int = 50,
    ) -> tuple[SnapshotRecord, ...]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        records = [
            item for item in self._records.values()
            if item.athlete_id == athlete_id
        ]
        records.sort(
            key=lambda item: (item.created_at, item.snapshot_id),
            reverse=True,
        )
        return tuple(records[:limit])


class InMemoryEvidenceRepository:
    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}

    def save(self, item: EvidenceItem) -> None:
        existing = self._items.get(item.evidence_id)
        if existing is not None and existing.content_hash != item.content_hash:
            raise ValueError(
                "Evidence ID already exists with different content."
            )
        self._items[item.evidence_id] = item

    def list_available(
        self,
        *,
        athlete_id: str,
        information_cutoff_at,
    ) -> tuple[EvidenceItem, ...]:
        return tuple(
            item
            for item in sorted(
                self._items.values(),
                key=lambda candidate: (
                    candidate.available_at,
                    candidate.evidence_id,
                ),
            )
            if item.athlete_id == athlete_id
            and item.available_at <= information_cutoff_at
            and item.observed_at <= information_cutoff_at
        )
