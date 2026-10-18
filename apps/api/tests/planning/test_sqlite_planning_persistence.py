from datetime import datetime, timezone
from dataclasses import replace

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
from app.planning.infrastructure.repositories.sqlite import (
    PLANNING_SQLITE_SCHEMA_VERSION,
    PlanningSqliteDatabase,
    SqlitePlanningSnapshotRepository,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _record(snapshot_id: str = "snapshot-1"):
    snapshot = create_domain_snapshot(
        snapshot_id=snapshot_id,
        athlete_id="athlete-1",
        domain_type="TEST_STATE",
        schema_version="test_v0.1",
        as_of=_dt(8),
        information_cutoff_at=_dt(7),
        created_at=_dt(8),
        payload={"status": "known"},
    )
    return encode_domain_snapshot(snapshot)


def test_sqlite_schema_initializes_without_using_global_user_version(tmp_path) -> None:
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")

    assert database.schema_version() == PLANNING_SQLITE_SCHEMA_VERSION
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0


def test_snapshot_persists_across_repository_instances(tmp_path) -> None:
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    first = SqlitePlanningSnapshotRepository(database)
    saved = first.save(_record())

    second = SqlitePlanningSnapshotRepository(database)
    restored_record = second.get("snapshot-1")

    assert saved.status == SnapshotSaveStatus.CREATED
    assert restored_record is not None
    restored = decode_domain_snapshot(restored_record)
    assert restored.payload["status"] == "known"
    assert restored.verify_content_hash()


def test_snapshot_save_is_idempotent(tmp_path) -> None:
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    repo = SqlitePlanningSnapshotRepository(database)
    record = _record()

    first = repo.save(record)
    second = repo.save(record)

    assert first.status == SnapshotSaveStatus.CREATED
    assert second.status == SnapshotSaveStatus.ALREADY_PRESENT


def test_snapshot_id_collision_is_rejected(tmp_path) -> None:
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    repo = SqlitePlanningSnapshotRepository(database)
    repo.save(_record())
    changed = replace(_record(), contract_json='{"different":true}')

    with pytest.raises(SnapshotConflictError):
        repo.save(changed)


def test_snapshot_listing_is_athlete_scoped(tmp_path) -> None:
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    repo = SqlitePlanningSnapshotRepository(database)
    repo.save(_record("a"))
    other = replace(_record("b"), athlete_id="athlete-2")
    repo.save(other)

    found = repo.list_for_athlete(athlete_id="athlete-1")

    assert [item.snapshot_id for item in found] == ["a"]
