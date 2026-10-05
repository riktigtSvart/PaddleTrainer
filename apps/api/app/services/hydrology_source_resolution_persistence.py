from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.route_hydrology_source_resolution_snapshot import (
    verify_route_hydrology_source_resolution_snapshot,
)


TABLE_NAME = "route_hydrology_source_resolution_snapshots"


async def persist_route_hydrology_source_resolution_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one immutable hydrology-source resolution per evidence set."""
    if not verify_route_hydrology_source_resolution_snapshot(snapshot):
        raise ValueError("Invalid route hydrology source resolution snapshot hash")

    evidence_set_uuid = str(evidence_set_id)
    resolution_hash = str(snapshot["resolution_hash"])

    existing = await load_route_hydrology_source_resolution_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    if existing is not None:
        if existing.get("resolution_hash") != resolution_hash:
            raise ValueError(
                "Immutable environment evidence set already has a different "
                "hydrology source resolution snapshot"
            )
        return {
            "status": "ALREADY_CURRENT",
            "snapshot_id": existing.get("snapshot_id"),
            "evidence_set_id": evidence_set_uuid,
            "resolution_hash": resolution_hash,
            "round_trip_verified": existing.get("snapshot") == dict(snapshot),
            "round_trip": existing.get("snapshot"),
        }

    snapshot_id = str(uuid4())
    snapshot_json = json.dumps(
        dict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_NAME} (
                id,
                evidence_set_id,
                snapshot_schema_version,
                resolution_schema_version,
                resolution_hash,
                snapshot_json
            ) VALUES (
                CAST(:id AS uuid),
                CAST(:evidence_set_id AS uuid),
                :snapshot_schema_version,
                :resolution_schema_version,
                :resolution_hash,
                CAST(:snapshot_json AS jsonb)
            )
            """
        ),
        {
            "id": snapshot_id,
            "evidence_set_id": evidence_set_uuid,
            "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
            "resolution_schema_version": snapshot.get("resolution_schema_version"),
            "resolution_hash": resolution_hash,
            "snapshot_json": snapshot_json,
        },
    )
    await db.commit()

    round_trip = await load_route_hydrology_source_resolution_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    if round_trip is None:
        raise ValueError(
            "Hydrology source resolution snapshot could not be read back after persistence"
        )

    round_trip_snapshot = round_trip.get("snapshot")
    round_trip_verified = (
        round_trip.get("resolution_hash") == resolution_hash
        and round_trip_snapshot == dict(snapshot)
        and verify_route_hydrology_source_resolution_snapshot(round_trip_snapshot)
    )
    if not round_trip_verified:
        raise ValueError(
            "Hydrology source resolution snapshot round-trip verification failed"
        )

    return {
        "status": "CREATED",
        "snapshot_id": round_trip.get("snapshot_id"),
        "evidence_set_id": evidence_set_uuid,
        "resolution_hash": resolution_hash,
        "round_trip_verified": True,
        "round_trip": round_trip_snapshot,
    }


async def load_route_hydrology_source_resolution_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            f"""
            SELECT
                id::text AS snapshot_id,
                evidence_set_id::text AS evidence_set_id,
                snapshot_schema_version,
                resolution_schema_version,
                resolution_hash,
                snapshot_json
            FROM {TABLE_NAME}
            WHERE evidence_set_id = CAST(:evidence_set_id AS uuid)
            """
        ),
        {"evidence_set_id": str(evidence_set_id)},
    )
    row = result.mappings().first()
    if row is None:
        return None

    snapshot = row.get("snapshot_json")
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)

    return {
        "snapshot_id": row.get("snapshot_id"),
        "evidence_set_id": row.get("evidence_set_id"),
        "snapshot_schema_version": row.get("snapshot_schema_version"),
        "resolution_schema_version": row.get("resolution_schema_version"),
        "resolution_hash": row.get("resolution_hash"),
        "snapshot": snapshot,
    }
