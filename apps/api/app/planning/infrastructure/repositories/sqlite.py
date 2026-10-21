from datetime import datetime
from pathlib import Path
import sqlite3

from ...domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveResult,
    AuditArtifactSaveStatus,
)
from ...domain.persistence.models import (
    SnapshotConflictError,
    SnapshotKind,
    SnapshotRecord,
    SnapshotSaveResult,
    SnapshotSaveStatus,
)
from ...domain.common.time import to_utc


PLANNING_SQLITE_SCHEMA_VERSION = 1


def _dt_to_storage(value: datetime) -> str:
    return to_utc(value, field_name="datetime").isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _dt_from_storage(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PlanningSqliteSchemaError(RuntimeError):
    pass


class PlanningSqliteDatabase:
    """Small planning-owned SQLite sidecar for P0.12.

    It deliberately does not alter the application's existing database or
    migration history. A later adapter may map the same repository contracts
    to the main persistence technology after that schema is inspected.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS planning_schema_meta (
                    schema_name TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT schema_version FROM planning_schema_meta "
                "WHERE schema_name = ?",
                ("planning_core",),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO planning_schema_meta "
                    "(schema_name, schema_version) VALUES (?, ?)",
                    ("planning_core", PLANNING_SQLITE_SCHEMA_VERSION),
                )
            elif row["schema_version"] != PLANNING_SQLITE_SCHEMA_VERSION:
                raise PlanningSqliteSchemaError(
                    "Unsupported planning SQLite schema version: "
                    f"{row['schema_version']}"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS planning_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    snapshot_kind TEXT NOT NULL,
                    athlete_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    information_cutoff_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    content_hash_algorithm TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    contract_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_planning_snapshots_athlete_created "
                "ON planning_snapshots(athlete_id, created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS planning_audit_artifacts (
                    artifact_kind TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    athlete_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    persisted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    content_hash_algorithm TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    contract_json TEXT NOT NULL,
                    PRIMARY KEY (artifact_kind, artifact_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_planning_audit_athlete_kind_created "
                "ON planning_audit_artifacts"
                "(athlete_id, artifact_kind, created_at DESC)"
            )

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT schema_version FROM planning_schema_meta "
                "WHERE schema_name = ?",
                ("planning_core",),
            ).fetchone()
        if row is None:
            raise PlanningSqliteSchemaError(
                "Planning schema metadata is missing."
            )
        return int(row["schema_version"])


class SqlitePlanningSnapshotRepository:
    def __init__(self, database: PlanningSqliteDatabase) -> None:
        self.database = database

    @staticmethod
    def _from_row(row: sqlite3.Row) -> SnapshotRecord:
        return SnapshotRecord(
            snapshot_kind=SnapshotKind(row["snapshot_kind"]),
            snapshot_id=row["snapshot_id"],
            athlete_id=row["athlete_id"],
            schema_version=row["schema_version"],
            as_of=_dt_from_storage(row["as_of"]),
            information_cutoff_at=_dt_from_storage(
                row["information_cutoff_at"]
            ),
            created_at=_dt_from_storage(row["created_at"]),
            content_hash_algorithm=row["content_hash_algorithm"],
            content_hash=row["content_hash"],
            contract_json=row["contract_json"],
        )

    def save(self, record: SnapshotRecord) -> SnapshotSaveResult:
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM planning_snapshots WHERE snapshot_id = ?",
                (record.snapshot_id,),
            ).fetchone()
            if existing is not None:
                current = self._from_row(existing)
                if (
                    current.content_hash != record.content_hash
                    or current.contract_json != record.contract_json
                    or current.snapshot_kind != record.snapshot_kind
                ):
                    raise SnapshotConflictError(
                        "Immutable snapshot ID already exists with different "
                        "content."
                    )
                return SnapshotSaveResult(
                    status=SnapshotSaveStatus.ALREADY_PRESENT,
                    snapshot_id=record.snapshot_id,
                    content_hash=record.content_hash,
                )

            connection.execute(
                """
                INSERT INTO planning_snapshots (
                    snapshot_id, snapshot_kind, athlete_id, schema_version,
                    as_of, information_cutoff_at, created_at,
                    content_hash_algorithm, content_hash, contract_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.snapshot_id,
                    record.snapshot_kind.value,
                    record.athlete_id,
                    record.schema_version,
                    _dt_to_storage(record.as_of),
                    _dt_to_storage(record.information_cutoff_at),
                    _dt_to_storage(record.created_at),
                    record.content_hash_algorithm,
                    record.content_hash,
                    record.contract_json,
                ),
            )
        return SnapshotSaveResult(
            status=SnapshotSaveStatus.CREATED,
            snapshot_id=record.snapshot_id,
            content_hash=record.content_hash,
        )

    def get(self, snapshot_id: str) -> SnapshotRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM planning_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_athlete(
        self,
        *,
        athlete_id: str,
        limit: int = 50,
    ) -> tuple[SnapshotRecord, ...]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM planning_snapshots "
                "WHERE athlete_id = ? "
                "ORDER BY created_at DESC, snapshot_id ASC LIMIT ?",
                (athlete_id, limit),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)


class SqlitePlanningAuditRepository:
    def __init__(self, database: PlanningSqliteDatabase) -> None:
        self.database = database

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AuditArtifactRecord:
        return AuditArtifactRecord(
            artifact_kind=AuditArtifactKind(row["artifact_kind"]),
            artifact_id=row["artifact_id"],
            athlete_id=row["athlete_id"],
            schema_version=row["schema_version"],
            created_at=_dt_from_storage(row["created_at"]),
            content_hash_algorithm=row["content_hash_algorithm"],
            content_hash=row["content_hash"],
            contract_json=row["contract_json"],
            persisted_at=(
                None
                if row["persisted_at"] is None
                else _dt_from_storage(row["persisted_at"])
            ),
        )

    def save(
        self,
        record: AuditArtifactRecord,
    ) -> AuditArtifactSaveResult:
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM planning_audit_artifacts "
                "WHERE artifact_kind = ? AND artifact_id = ?",
                (record.artifact_kind.value, record.artifact_id),
            ).fetchone()
            if existing is not None:
                current = self._from_row(existing)
                if (
                    current.content_hash != record.content_hash
                    or current.contract_json != record.contract_json
                    or current.athlete_id != record.athlete_id
                ):
                    raise AuditArtifactConflictError(
                        "Immutable audit artifact identity already exists "
                        "with different content."
                    )
                return AuditArtifactSaveResult(
                    status=AuditArtifactSaveStatus.ALREADY_PRESENT,
                    artifact_kind=record.artifact_kind,
                    artifact_id=record.artifact_id,
                    content_hash=record.content_hash,
                )

            connection.execute(
                """
                INSERT INTO planning_audit_artifacts (
                    artifact_kind, artifact_id, athlete_id, schema_version,
                    created_at, content_hash_algorithm, content_hash,
                    contract_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.artifact_kind.value,
                    record.artifact_id,
                    record.athlete_id,
                    record.schema_version,
                    _dt_to_storage(record.created_at),
                    record.content_hash_algorithm,
                    record.content_hash,
                    record.contract_json,
                ),
            )
        return AuditArtifactSaveResult(
            status=AuditArtifactSaveStatus.CREATED,
            artifact_kind=record.artifact_kind,
            artifact_id=record.artifact_id,
            content_hash=record.content_hash,
        )

    def get(
        self,
        *,
        artifact_kind: AuditArtifactKind,
        artifact_id: str,
    ) -> AuditArtifactRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM planning_audit_artifacts "
                "WHERE artifact_kind = ? AND artifact_id = ?",
                (artifact_kind.value, artifact_id),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_athlete(
        self,
        *,
        athlete_id: str,
        artifact_kind: AuditArtifactKind | None = None,
        limit: int = 50,
    ) -> tuple[AuditArtifactRecord, ...]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        with self.database.connect() as connection:
            if artifact_kind is None:
                rows = connection.execute(
                    "SELECT * FROM planning_audit_artifacts "
                    "WHERE athlete_id = ? "
                    "ORDER BY created_at DESC, artifact_kind ASC, "
                    "artifact_id ASC LIMIT ?",
                    (athlete_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM planning_audit_artifacts "
                    "WHERE athlete_id = ? AND artifact_kind = ? "
                    "ORDER BY created_at DESC, artifact_id ASC LIMIT ?",
                    (athlete_id, artifact_kind.value, limit),
                ).fetchall()
        return tuple(self._from_row(row) for row in rows)
