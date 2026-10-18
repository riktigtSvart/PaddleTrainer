from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SnapshotKind(StrEnum):
    DOMAIN_SNAPSHOT = "domain_snapshot"
    PLANNING_CONTEXT = "planning_context"


class SnapshotSaveStatus(StrEnum):
    CREATED = "created"
    ALREADY_PRESENT = "already_present"


class SnapshotConflictError(RuntimeError):
    """Same stable snapshot ID was reused for different immutable content."""


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_kind: SnapshotKind
    snapshot_id: str
    athlete_id: str
    schema_version: str
    as_of: datetime
    information_cutoff_at: datetime
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str
    contract_json: str


@dataclass(frozen=True)
class SnapshotSaveResult:
    status: SnapshotSaveStatus
    snapshot_id: str
    content_hash: str
