from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.planning.api.dev import create_planning_dev_app
from app.planning.domain.common.snapshot import create_domain_snapshot
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
)
from app.planning.domain.persistence.snapshot_codec import encode_domain_snapshot
from app.planning.infrastructure.repositories.sqlite import (
    PlanningSqliteDatabase,
    SqlitePlanningAuditRepository,
    SqlitePlanningSnapshotRepository,
)


def _dt() -> datetime:
    return datetime(2026, 10, 17, 8, tzinfo=timezone.utc)


def _seed(path):
    database = PlanningSqliteDatabase(path)
    snapshots = SqlitePlanningSnapshotRepository(database)
    audit = SqlitePlanningAuditRepository(database)
    snapshot = create_domain_snapshot(
        snapshot_id="snapshot-1",
        athlete_id="athlete-1",
        domain_type="STATE",
        schema_version="state_v0.1",
        as_of=_dt(),
        information_cutoff_at=_dt(),
        created_at=_dt(),
        payload={"state": "known"},
    )
    snapshots.save(encode_domain_snapshot(snapshot))
    audit.save(
        AuditArtifactRecord(
            artifact_kind=AuditArtifactKind.PLANNER_RUN_RECORD,
            artifact_id="run-1",
            athlete_id="athlete-1",
            schema_version="planner_run_record_v0.1",
            created_at=_dt(),
            content_hash_algorithm="sha256-canonical-json-v0.1",
            content_hash="r" * 64,
            contract_json='{"run_id":"run-1"}',
        )
    )


def test_dev_api_reads_snapshot_and_run(tmp_path) -> None:
    path = tmp_path / "planning.sqlite3"
    _seed(path)
    client = TestClient(create_planning_dev_app(path))

    health = client.get("/dev/planning/health")
    snapshot = client.get("/dev/planning/snapshots/snapshot-1")
    run = client.get("/dev/planning/runs/run-1")

    assert health.status_code == 200
    assert health.json()["mode"] == "read_only"
    assert snapshot.status_code == 200
    assert snapshot.json()["contract"]["payload"]["state"] == "known"
    assert run.status_code == 200
    assert run.json()["contract"]["run_id"] == "run-1"


def test_dev_api_lists_athlete_records(tmp_path) -> None:
    path = tmp_path / "planning.sqlite3"
    _seed(path)
    client = TestClient(create_planning_dev_app(path))

    snapshots = client.get(
        "/dev/planning/athletes/athlete-1/snapshots"
    )
    artifacts = client.get(
        "/dev/planning/athletes/athlete-1/artifacts",
        params={"artifact_kind": "planner_run_record"},
    )

    assert snapshots.status_code == 200
    assert len(snapshots.json()["items"]) == 1
    assert artifacts.status_code == 200
    assert len(artifacts.json()["items"]) == 1


def test_dev_api_is_read_only(tmp_path) -> None:
    path = tmp_path / "planning.sqlite3"
    _seed(path)
    client = TestClient(create_planning_dev_app(path))

    response = client.post(
        "/dev/planning/snapshots/snapshot-1",
        json={"attempt": "write"},
    )

    assert response.status_code == 405


def test_dev_api_returns_404_for_missing_record(tmp_path) -> None:
    path = tmp_path / "planning.sqlite3"
    client = TestClient(create_planning_dev_app(path))

    response = client.get("/dev/planning/runs/missing")

    assert response.status_code == 404
