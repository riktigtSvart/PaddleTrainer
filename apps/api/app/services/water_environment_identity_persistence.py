from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.route_water_environment_identity_snapshot import (
    verify_route_water_environment_identity_snapshot,
)


TABLE_NAME = "route_water_environment_identity_snapshots"


async def persist_route_water_environment_identity_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one immutable water-environment identity snapshot per evidence set.

    Existing rows are never overwritten. Repeating the same snapshot is
    idempotent; attempting to attach different identity content to the same
    immutable environment evidence set raises ValueError.
    """
    if not verify_route_water_environment_identity_snapshot(snapshot):
        raise ValueError("Invalid route water environment identity snapshot hash")

    evidence_set_uuid = str(evidence_set_id)
    identity_hash = str(snapshot["identity_hash"])

    existing = await load_route_water_environment_identity_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    if existing is not None:
        existing_hash = existing.get("identity_hash")
        if existing_hash != identity_hash:
            raise ValueError(
                "Immutable environment evidence set already has a different "
                "water environment identity snapshot"
            )
        return {
            "status": "ALREADY_CURRENT",
            "snapshot_id": existing.get("snapshot_id"),
            "evidence_set_id": evidence_set_uuid,
            "identity_hash": identity_hash,
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
                identity_schema_version,
                identity_hash,
                snapshot_json
            ) VALUES (
                CAST(:id AS uuid),
                CAST(:evidence_set_id AS uuid),
                :snapshot_schema_version,
                :identity_schema_version,
                :identity_hash,
                CAST(:snapshot_json AS jsonb)
            )
            """
        ),
        {
            "id": snapshot_id,
            "evidence_set_id": evidence_set_uuid,
            "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
            "identity_schema_version": snapshot.get("identity_schema_version"),
            "identity_hash": identity_hash,
            "snapshot_json": snapshot_json,
        },
    )
    await db.commit()

    round_trip = await load_route_water_environment_identity_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    if round_trip is None:
        raise ValueError(
            "Water environment identity snapshot could not be read back after persistence"
        )

    round_trip_snapshot = round_trip.get("snapshot")
    round_trip_verified = (
        round_trip.get("identity_hash") == identity_hash
        and round_trip_snapshot == dict(snapshot)
        and verify_route_water_environment_identity_snapshot(round_trip_snapshot)
    )
    if not round_trip_verified:
        raise ValueError("Water environment identity snapshot round-trip verification failed")

    return {
        "status": "CREATED",
        "snapshot_id": round_trip.get("snapshot_id"),
        "evidence_set_id": evidence_set_uuid,
        "identity_hash": identity_hash,
        "round_trip_verified": True,
        "round_trip": round_trip_snapshot,
    }


async def load_route_water_environment_identity_snapshot(
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
                identity_schema_version,
                identity_hash,
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
        "identity_schema_version": row.get("identity_schema_version"),
        "identity_hash": row.get("identity_hash"),
        "snapshot": snapshot,
    }
