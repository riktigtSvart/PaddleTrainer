from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.snapshot import create_domain_snapshot
from app.planning.domain.persistence.models import (
    SnapshotConflictError,
    SnapshotSaveStatus,
)
from app.planning.domain.persistence.snapshot_codec import (
    decode_domain_snapshot,
    encode_domain_snapshot,
)
from app.planning.infrastructure.repositories.in_memory import (
    InMemoryPlanningSnapshotRepository,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=timezone.utc)


def _snapshot(snapshot_id: str = "state-1"):
    return create_domain_snapshot(
        snapshot_id=snapshot_id,
        athlete_id="athlete-1",
        domain_type="CURRENT_TRAINING_STATE",
        schema_version="cts_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        payload={"gate": "open_with_constraints"},
    )


def test_domain_snapshot_record_round_trip() -> None:
    original = _snapshot()
    record = encode_domain_snapshot(original)
    restored = decode_domain_snapshot(record)
    assert restored.content_hash == original.content_hash
    assert restored.payload["gate"] == "open_with_constraints"
    assert restored.verify_content_hash()


def test_repository_save_is_idempotent() -> None:
    repo = InMemoryPlanningSnapshotRepository()
    record = encode_domain_snapshot(_snapshot())
    first = repo.save(record)
    second = repo.save(record)
    assert first.status == SnapshotSaveStatus.CREATED
    assert second.status == SnapshotSaveStatus.ALREADY_PRESENT


def test_repository_rejects_same_id_with_different_content() -> None:
    repo = InMemoryPlanningSnapshotRepository()
    repo.save(encode_domain_snapshot(_snapshot()))
    changed = create_domain_snapshot(
        snapshot_id="state-1",
        athlete_id="athlete-1",
        domain_type="CURRENT_TRAINING_STATE",
        schema_version="cts_v0.1",
        as_of=_dt(18),
        information_cutoff_at=_dt(18),
        created_at=_dt(19),
        payload={"gate": "hold"},
    )
    with pytest.raises(SnapshotConflictError):
        repo.save(encode_domain_snapshot(changed))


def test_codec_rejects_tampered_record_hash() -> None:
    record = encode_domain_snapshot(_snapshot())
    tampered = replace(record, content_hash="0" * 64)
    with pytest.raises(ValueError, match="does not verify"):
        decode_domain_snapshot(tampered)
