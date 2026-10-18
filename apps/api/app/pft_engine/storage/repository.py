from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import sqlite3
import json

from app.pft_engine.contracts.output import (
    PftProcessingOutputV2,
)
from app.pft_engine.contracts.input import (
    RawSample,
)

class ImportStatus(StrEnum):
    CREATED = "CREATED"
    ALREADY_IMPORTED = "ALREADY_IMPORTED"


class PftReprocessingConflict(ValueError):
    """A source already exists in an archive under another processing lineage."""


@dataclass(frozen=True)
class ImportResult:
    status: ImportStatus
    session_id: int


@dataclass(frozen=True)
class StoredPftSession:
    id: int

    source_sha256: str
    source_filename: str

    started_at: str

    protocol_name: str
    protocol_version: str

    output_schema_version: str
    processor_version: str

    quality_grade: str

    result_json: str

    created_at: str


@dataclass(frozen=True)
class StoredPftSample:
    session_id: int
    sample_index: int

    elapsed_s: float

    hr_bpm: float | None
    power_w: float | None
    speed_mps: float | None
    cadence_rpm: float | None
    distance_m: float | None


def _from_row(
    row: sqlite3.Row,
) -> StoredPftSession:
    return StoredPftSession(
        id=row["id"],
        source_sha256=(
            row["source_sha256"]
        ),
        source_filename=(
            row["source_filename"]
        ),
        started_at=row["started_at"],
        protocol_name=(
            row["protocol_name"]
        ),
        protocol_version=(
            row["protocol_version"]
        ),
        output_schema_version=(
            row["output_schema_version"]
        ),
        processor_version=(
            row["processor_version"]
        ),
        quality_grade=(
            row["quality_grade"]
        ),
        result_json=row["result_json"],
        created_at=row["created_at"],
    )


class PftRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        self._connection = connection

    def import_session(
        self,
        *,
        source_filename: str,
        source_sha256: str,
        output: PftProcessingOutputV2,
        result_json: str,
    ) -> ImportResult:

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO pft_sessions (
                source_sha256,
                source_filename,
                started_at,
                protocol_name,
                protocol_version,
                output_schema_version,
                processor_version,
                quality_grade,
                result_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_sha256,
                source_filename,
                output.session.started_at,
                output.protocol.name,
                output.protocol.version,
                output.schema_version,
                (
                    output.algorithm_lineage
                    .processor
                ),
                output.session_quality_grade,
                result_json,
                created_at,
            ),
        )

        self._connection.commit()

        if cursor.rowcount == 1:
            return ImportResult(
                status=ImportStatus.CREATED,
                session_id=int(
                    cursor.lastrowid
                ),
            )

        existing = (
            self._connection.execute(
                """
                SELECT id, result_json
                FROM pft_sessions
                WHERE source_sha256 = ?
                """,
                (source_sha256,),
            ).fetchone()
        )

        if existing is None:
            raise RuntimeError(
                "Duplicate import was ignored but "
                "existing session could not be found."
            )

        stored_document = json.loads(existing["result_json"])
        current_document = json.loads(result_json)
        for field in ("schema_version", "protocol", "algorithm_lineage"):
            if stored_document.get(field) != current_document.get(field):
                raise PftReprocessingConflict(
                    "This source was already imported with different processing "
                    "lineage. Use a separate archive for reprocessing; the "
                    "original archived result has been retained."
                )

        return ImportResult(
            status=(
                ImportStatus
                .ALREADY_IMPORTED
            ),
            session_id=int(
                existing["id"]
            ),
        )

    def get_session(
        self,
        session_id: int,
    ) -> StoredPftSession | None:

        row = self._connection.execute(
            """
            SELECT *
            FROM pft_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

        if row is None:
            return None

        return _from_row(row)

    def list_sessions(
        self,
        *,
        limit: int = 100,
    ) -> tuple[StoredPftSession, ...]:

        if limit <= 0:
            raise ValueError(
                "limit must be positive."
            )

        rows = self._connection.execute(
            """
            SELECT *
            FROM pft_sessions
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return tuple(
            _from_row(row)
            for row in rows
        )

    def replace_samples(
        self,
        *,
        session_id: int,
        samples: tuple[RawSample, ...],
    ) -> None:

        rows: list[tuple] = []

        previous: RawSample | None = None

        for index, sample in enumerate(samples):
            speed_mps: float | None = None

            if (
                previous is not None
                and previous.distance_m is not None
                and sample.distance_m is not None
            ):
                dt = (
                    sample.elapsed_s
                    - previous.elapsed_s
                )

                distance_delta = (
                    sample.distance_m
                    - previous.distance_m
                )

                if (
                    dt > 0.0
                    and distance_delta >= 0.0
                ):
                    speed_mps = (
                        distance_delta / dt
                    )

            rows.append(
                (
                    session_id,
                    index,
                    sample.elapsed_s,
                    sample.hr_bpm,
                    sample.power_w,
                    speed_mps,
                    sample.cadence_rpm,
                    sample.distance_m,
                )
            )

            previous = sample

        self._connection.execute(
            """
            DELETE FROM pft_session_samples
            WHERE session_id = ?
            """,
            (session_id,),
        )

        self._connection.executemany(
            """
            INSERT INTO pft_session_samples (
                session_id,
                sample_index,
                elapsed_s,
                hr_bpm,
                power_w,
                speed_mps,
                cadence_rpm,
                distance_m
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        self._connection.commit()

    def get_samples(
        self,
        session_id: int,
    ) -> tuple[StoredPftSample, ...]:

        rows = self._connection.execute(
            """
            SELECT
                session_id,
                sample_index,
                elapsed_s,
                hr_bpm,
                power_w,
                speed_mps,
                cadence_rpm,
                distance_m
            FROM pft_session_samples
            WHERE session_id = ?
            ORDER BY sample_index
            """,
            (session_id,),
        ).fetchall()

        return tuple(
            StoredPftSample(
                session_id=row["session_id"],
                sample_index=row["sample_index"],
                elapsed_s=row["elapsed_s"],
                hr_bpm=row["hr_bpm"],
                power_w=row["power_w"],
                speed_mps=row["speed_mps"],
                cadence_rpm=row["cadence_rpm"],
                distance_m=row["distance_m"],
            )
            for row in rows
        )
