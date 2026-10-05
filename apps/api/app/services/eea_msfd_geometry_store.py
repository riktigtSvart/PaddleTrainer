from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


SOURCE_PROVIDER = "EEA_MSFD"
SOURCE_DATASET = "MSFD_REGIONS_AND_SUBREGIONS_V1_SEP_2022"
SOURCE_LAYER = "MSFD_REGIONS_AND_SUBREGIONS"
DEFAULT_CELL_SIZE_DEG = 0.25
ENV_STORE_PATH = "PADDLETRAINER_EEA_MSFD_GEOMETRY_STORE"


@dataclass(frozen=True)
class EEAMSFDGeometryCoverageCell:
    cell_x: int
    cell_y: int
    xmin_lon: float
    ymin_lat: float
    xmax_lon: float
    ymax_lat: float

    @property
    def key(self) -> tuple[int, int]:
        return (self.cell_x, self.cell_y)


@dataclass(frozen=True)
class EEAMSFDCachedFeature:
    object_id: str
    raw_feature: dict[str, Any]
    snapshot_sha256: str
    fetched_at: str
    last_seen_at: str


class EEAMSFDGeometryStore:
    """Local structural cache for raw EEA MSFD region geometry.

    The store is deliberately independent from session evidence persistence.
    It records immutable-ish raw ArcGIS feature snapshots plus fixed-cell
    discovery coverage, including zero-result cells. A changed provider
    geometry creates a new SHA-256 snapshot instead of overwriting history.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        cell_size_deg: float = DEFAULT_CELL_SIZE_DEG,
    ) -> None:
        if cell_size_deg <= 0.0:
            raise ValueError("cell_size_deg must be > 0")
        self.path = Path(path) if path is not None else default_store_path()
        self.cell_size_deg = float(cell_size_deg)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS eea_msfd_feature_snapshots (
                    source_provider TEXT NOT NULL,
                    source_dataset TEXT NOT NULL,
                    source_layer TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    first_fetched_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    payload_gzip BLOB NOT NULL,
                    PRIMARY KEY (
                        source_provider,
                        source_dataset,
                        source_layer,
                        object_id,
                        snapshot_sha256
                    )
                );

                CREATE INDEX IF NOT EXISTS ix_eea_msfd_snapshot_latest
                ON eea_msfd_feature_snapshots (
                    source_provider, source_dataset, source_layer,
                    object_id, last_seen_at
                );

                CREATE TABLE IF NOT EXISTS eea_msfd_coverage_cells (
                    source_provider TEXT NOT NULL,
                    source_dataset TEXT NOT NULL,
                    source_layer TEXT NOT NULL,
                    cell_size_deg REAL NOT NULL,
                    cell_x INTEGER NOT NULL,
                    cell_y INTEGER NOT NULL,
                    xmin_lon REAL NOT NULL,
                    ymin_lat REAL NOT NULL,
                    xmax_lon REAL NOT NULL,
                    ymax_lat REAL NOT NULL,
                    discovered_at TEXT NOT NULL,
                    object_ids_json TEXT NOT NULL,
                    PRIMARY KEY (
                        source_provider,
                        source_dataset,
                        source_layer,
                        cell_size_deg,
                        cell_x,
                        cell_y
                    )
                );
                """
            )

    def coverage_cells_for_bounds(
        self,
        *,
        xmin_lon: float,
        ymin_lat: float,
        xmax_lon: float,
        ymax_lat: float,
    ) -> tuple[EEAMSFDGeometryCoverageCell, ...]:
        if xmin_lon > xmax_lon or ymin_lat > ymax_lat:
            raise ValueError("invalid bounds")

        size = self.cell_size_deg
        eps = 1e-12
        min_x = math.floor((xmin_lon + 180.0) / size)
        max_x = math.floor((xmax_lon + 180.0 - eps) / size)
        min_y = math.floor((ymin_lat + 90.0) / size)
        max_y = math.floor((ymax_lat + 90.0 - eps) / size)

        cells: list[EEAMSFDGeometryCoverageCell] = []
        for cell_y in range(min_y, max_y + 1):
            for cell_x in range(min_x, max_x + 1):
                cell_xmin = cell_x * size - 180.0
                cell_ymin = cell_y * size - 90.0
                cells.append(
                    EEAMSFDGeometryCoverageCell(
                        cell_x=cell_x,
                        cell_y=cell_y,
                        xmin_lon=cell_xmin,
                        ymin_lat=cell_ymin,
                        xmax_lon=cell_xmin + size,
                        ymax_lat=cell_ymin + size,
                    )
                )
        return tuple(cells)

    def get_cell_object_ids(
        self,
        *,
        cell: EEAMSFDGeometryCoverageCell,
    ) -> tuple[str, ...] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT object_ids_json
                FROM eea_msfd_coverage_cells
                WHERE source_provider = ?
                  AND source_dataset = ?
                  AND source_layer = ?
                  AND cell_size_deg = ?
                  AND cell_x = ?
                  AND cell_y = ?
                """,
                (
                    SOURCE_PROVIDER,
                    SOURCE_DATASET,
                    SOURCE_LAYER,
                    self.cell_size_deg,
                    cell.cell_x,
                    cell.cell_y,
                ),
            ).fetchone()
        if row is None:
            return None
        raw = json.loads(row["object_ids_json"])
        if not isinstance(raw, list):
            return ()
        return tuple(str(value) for value in raw)

    def put_cell_object_ids(
        self,
        *,
        cell: EEAMSFDGeometryCoverageCell,
        object_ids: Sequence[str | int],
        discovered_at: str | None = None,
    ) -> None:
        timestamp = discovered_at or _utc_now_iso()
        normalized_ids = sorted(
            {str(value) for value in object_ids}, key=_object_id_sort_key
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO eea_msfd_coverage_cells (
                    source_provider,
                    source_dataset,
                    source_layer,
                    cell_size_deg,
                    cell_x,
                    cell_y,
                    xmin_lon,
                    ymin_lat,
                    xmax_lon,
                    ymax_lat,
                    discovered_at,
                    object_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    source_provider,
                    source_dataset,
                    source_layer,
                    cell_size_deg,
                    cell_x,
                    cell_y
                ) DO UPDATE SET
                    xmin_lon = excluded.xmin_lon,
                    ymin_lat = excluded.ymin_lat,
                    xmax_lon = excluded.xmax_lon,
                    ymax_lat = excluded.ymax_lat,
                    discovered_at = excluded.discovered_at,
                    object_ids_json = excluded.object_ids_json
                """,
                (
                    SOURCE_PROVIDER,
                    SOURCE_DATASET,
                    SOURCE_LAYER,
                    self.cell_size_deg,
                    cell.cell_x,
                    cell.cell_y,
                    cell.xmin_lon,
                    cell.ymin_lat,
                    cell.xmax_lon,
                    cell.ymax_lat,
                    timestamp,
                    json.dumps(normalized_ids, separators=(",", ":")),
                ),
            )

    def get_features(
        self,
        *,
        object_ids: Sequence[str | int],
    ) -> dict[str, EEAMSFDCachedFeature]:
        normalized_ids = tuple(dict.fromkeys(str(value) for value in object_ids))
        if not normalized_ids:
            return {}

        found: dict[str, EEAMSFDCachedFeature] = {}
        with self._connect() as connection:
            for offset in range(0, len(normalized_ids), 500):
                batch = normalized_ids[offset : offset + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""
                    SELECT s.object_id, s.first_fetched_at, s.last_seen_at,
                           s.snapshot_sha256, s.payload_gzip
                    FROM eea_msfd_feature_snapshots AS s
                    WHERE s.source_provider = ?
                      AND s.source_dataset = ?
                      AND s.source_layer = ?
                      AND s.object_id IN ({placeholders})
                      AND s.last_seen_at = (
                          SELECT MAX(s2.last_seen_at)
                          FROM eea_msfd_feature_snapshots AS s2
                          WHERE s2.source_provider = s.source_provider
                            AND s2.source_dataset = s.source_dataset
                            AND s2.source_layer = s.source_layer
                            AND s2.object_id = s.object_id
                      )
                    """,
                    (
                        SOURCE_PROVIDER,
                        SOURCE_DATASET,
                        SOURCE_LAYER,
                        *batch,
                    ),
                ).fetchall()
                for row in rows:
                    payload_bytes = gzip.decompress(row["payload_gzip"])
                    raw_feature = json.loads(payload_bytes.decode("utf-8"))
                    if not isinstance(raw_feature, dict):
                        continue
                    object_id = str(row["object_id"])
                    found[object_id] = EEAMSFDCachedFeature(
                        object_id=object_id,
                        raw_feature=raw_feature,
                        snapshot_sha256=str(row["snapshot_sha256"]),
                        fetched_at=str(row["first_fetched_at"]),
                        last_seen_at=str(row["last_seen_at"]),
                    )
        return found

    def put_features(
        self,
        *,
        features: Sequence[Mapping[str, Any]],
        fetched_at: str | None = None,
    ) -> tuple[str, ...]:
        timestamp = fetched_at or _utc_now_iso()
        stored: list[str] = []
        with self._connect() as connection:
            for feature in features:
                object_id = _feature_object_id(feature)
                if object_id is None:
                    continue
                canonical = json.dumps(
                    dict(feature),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                digest = sha256(canonical).hexdigest()
                compressed = gzip.compress(canonical, compresslevel=6)
                connection.execute(
                    """
                    INSERT INTO eea_msfd_feature_snapshots (
                        source_provider,
                        source_dataset,
                        source_layer,
                        object_id,
                        snapshot_sha256,
                        first_fetched_at,
                        last_seen_at,
                        payload_gzip
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (
                        source_provider,
                        source_dataset,
                        source_layer,
                        object_id,
                        snapshot_sha256
                    ) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        SOURCE_PROVIDER,
                        SOURCE_DATASET,
                        SOURCE_LAYER,
                        object_id,
                        digest,
                        timestamp,
                        timestamp,
                        compressed,
                    ),
                )
                stored.append(object_id)
        return tuple(stored)


def default_store_path() -> Path:
    configured = os.getenv(ENV_STORE_PATH)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".paddletrainer" / "eea_msfd_geometry.sqlite3"


def _feature_object_id(feature: Mapping[str, Any]) -> str | None:
    attributes = feature.get("attributes")
    if not isinstance(attributes, Mapping):
        return None
    value = attributes.get("OBJECTID")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _object_id_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
