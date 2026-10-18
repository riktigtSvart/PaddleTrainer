import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query

from ..domain.persistence.audit import AuditArtifactKind
from ..infrastructure.repositories.sqlite import (
    PLANNING_SQLITE_SCHEMA_VERSION,
    PlanningSqliteDatabase,
    SqlitePlanningAuditRepository,
    SqlitePlanningSnapshotRepository,
)


def _snapshot_summary(record) -> dict:
    return {
        "snapshot_id": record.snapshot_id,
        "snapshot_kind": record.snapshot_kind.value,
        "athlete_id": record.athlete_id,
        "schema_version": record.schema_version,
        "as_of": record.as_of.isoformat(),
        "information_cutoff_at": record.information_cutoff_at.isoformat(),
        "created_at": record.created_at.isoformat(),
        "content_hash_algorithm": record.content_hash_algorithm,
        "content_hash": record.content_hash,
    }


def _artifact_summary(record) -> dict:
    return {
        "artifact_kind": record.artifact_kind.value,
        "artifact_id": record.artifact_id,
        "athlete_id": record.athlete_id,
        "schema_version": record.schema_version,
        "created_at": record.created_at.isoformat(),
        "content_hash_algorithm": record.content_hash_algorithm,
        "content_hash": record.content_hash,
    }


def create_planning_dev_router(
    *,
    database: PlanningSqliteDatabase,
) -> APIRouter:
    snapshots = SqlitePlanningSnapshotRepository(database)
    audit = SqlitePlanningAuditRepository(database)
    router = APIRouter(prefix="/dev/planning", tags=["planning-dev"])

    @router.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "mode": "read_only",
            "schema_version": database.schema_version(),
        }

    @router.get("/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str) -> dict:
        record = snapshots.get(snapshot_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return {
            "record": _snapshot_summary(record),
            "contract": json.loads(record.contract_json),
        }

    @router.get("/athletes/{athlete_id}/snapshots")
    def list_snapshots(
        athlete_id: str,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict:
        records = snapshots.list_for_athlete(
            athlete_id=athlete_id,
            limit=limit,
        )
        return {
            "athlete_id": athlete_id,
            "items": [_snapshot_summary(record) for record in records],
        }

    @router.get("/artifacts/{artifact_kind}/{artifact_id}")
    def get_artifact(
        artifact_kind: AuditArtifactKind,
        artifact_id: str,
    ) -> dict:
        record = audit.get(
            artifact_kind=artifact_kind,
            artifact_id=artifact_id,
        )
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="Audit artifact not found",
            )
        return {
            "record": _artifact_summary(record),
            "contract": json.loads(record.contract_json),
        }

    @router.get("/athletes/{athlete_id}/artifacts")
    def list_artifacts(
        athlete_id: str,
        artifact_kind: AuditArtifactKind | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict:
        records = audit.list_for_athlete(
            athlete_id=athlete_id,
            artifact_kind=artifact_kind,
            limit=limit,
        )
        return {
            "athlete_id": athlete_id,
            "items": [_artifact_summary(record) for record in records],
        }

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        record = audit.get(
            artifact_kind=AuditArtifactKind.PLANNER_RUN_RECORD,
            artifact_id=run_id,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "record": _artifact_summary(record),
            "contract": json.loads(record.contract_json),
        }

    return router


def create_planning_dev_app(
    database_path: str | Path,
) -> FastAPI:
    database = PlanningSqliteDatabase(database_path)
    app = FastAPI(title="PaddleTrainer Planning Dev API")
    app.include_router(create_planning_dev_router(database=database))
    # Deliberately no write endpoints in P0.12. Persistence is performed by
    # the planning application service after a validated planner run.
    return app
