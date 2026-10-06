from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trusted_environment_context_snapshot import (
    verify_trusted_environment_context_snapshot,
)


TABLE_NAME = "route_trusted_environment_context_snapshots"


async def persist_trusted_route_environment_context_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist immutable derived trusted-environment projection lineage."""
    if not verify_trusted_environment_context_snapshot(snapshot):
        raise ValueError("Invalid trusted environment context snapshot hash")

    evidence_set_uuid = str(evidence_set_id)
    snapshot_evidence_set_id = str(
        snapshot.get("environment_evidence_set_id") or ""
    )
    if snapshot_evidence_set_id != evidence_set_uuid:
        raise ValueError(
            "Trusted environment context snapshot evidence_set_id does not "
            "match persistence target"
        )

    projection_hash = str(snapshot["projection_hash"])
    existing = await load_trusted_route_environment_context_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
        projection_hash=projection_hash,
    )
    if existing is not None:
        lineage_count = await count_trusted_route_environment_context_snapshots(
            db,
            evidence_set_id=evidence_set_uuid,
        )
        return {
            "status": "ALREADY_CURRENT",
            "snapshot_id": existing.get("snapshot_id"),
            "evidence_set_id": evidence_set_uuid,
            "projection_hash": projection_hash,
            "round_trip_verified": existing.get("snapshot") == dict(snapshot),
            "round_trip": existing.get("snapshot"),
            "lineage_snapshot_count": lineage_count,
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
                trusted_environment_context_schema_version,
                projection_policy_schema_version,
                projection_status,
                water_environment_identity_hash,
                hydrology_trust_decision_hash,
                projection_policy_hash,
                water_identity_mask_hash,
                weather_mask_hash,
                wind_mask_hash,
                hydrology_mask_hash,
                aggregate_environment_mask_hash,
                projection_hash,
                snapshot_json
            ) VALUES (
                CAST(:id AS uuid),
                CAST(:evidence_set_id AS uuid),
                :snapshot_schema_version,
                :trusted_environment_context_schema_version,
                :projection_policy_schema_version,
                :projection_status,
                :water_environment_identity_hash,
                :hydrology_trust_decision_hash,
                :projection_policy_hash,
                :water_identity_mask_hash,
                :weather_mask_hash,
                :wind_mask_hash,
                :hydrology_mask_hash,
                :aggregate_environment_mask_hash,
                :projection_hash,
                CAST(:snapshot_json AS jsonb)
            )
            """
        ),
        {
            "id": snapshot_id,
            "evidence_set_id": evidence_set_uuid,
            "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
            "trusted_environment_context_schema_version": snapshot.get(
                "trusted_environment_context_schema_version"
            ),
            "projection_policy_schema_version": snapshot.get(
                "projection_policy_schema_version"
            ),
            "projection_status": snapshot.get("projection_status"),
            "water_environment_identity_hash": snapshot.get(
                "water_environment_identity_hash"
            ),
            "hydrology_trust_decision_hash": snapshot.get(
                "hydrology_trust_decision_hash"
            ),
            "projection_policy_hash": snapshot.get("projection_policy_hash"),
            "water_identity_mask_hash": (
                snapshot.get("component_mask_hashes") or {}
            ).get("water_identity"),
            "weather_mask_hash": (
                snapshot.get("component_mask_hashes") or {}
            ).get("weather"),
            "wind_mask_hash": (
                snapshot.get("component_mask_hashes") or {}
            ).get("wind"),
            "hydrology_mask_hash": (
                snapshot.get("component_mask_hashes") or {}
            ).get("hydrology"),
            "aggregate_environment_mask_hash": snapshot.get(
                "aggregate_environment_mask_hash"
            ),
            "projection_hash": projection_hash,
            "snapshot_json": snapshot_json,
        },
    )
    await db.commit()

    round_trip = await load_trusted_route_environment_context_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
        projection_hash=projection_hash,
    )
    if round_trip is None:
        raise ValueError(
            "Trusted environment context snapshot could not be read back "
            "after persistence"
        )

    lineage_count = await count_trusted_route_environment_context_snapshots(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    return {
        "status": "CREATED",
        "snapshot_id": round_trip.get("snapshot_id"),
        "evidence_set_id": evidence_set_uuid,
        "projection_hash": projection_hash,
        "round_trip_verified": round_trip.get("snapshot") == dict(snapshot),
        "round_trip": round_trip.get("snapshot"),
        "lineage_snapshot_count": lineage_count,
    }


async def load_trusted_route_environment_context_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    projection_hash: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            f"""
            SELECT
                id AS snapshot_id,
                evidence_set_id,
                snapshot_schema_version,
                trusted_environment_context_schema_version,
                projection_policy_schema_version,
                projection_status,
                water_environment_identity_hash,
                hydrology_trust_decision_hash,
                projection_policy_hash,
                water_identity_mask_hash,
                weather_mask_hash,
                wind_mask_hash,
                hydrology_mask_hash,
                aggregate_environment_mask_hash,
                projection_hash,
                snapshot_json
            FROM {TABLE_NAME}
            WHERE evidence_set_id = CAST(:evidence_set_id AS uuid)
              AND projection_hash = :projection_hash
            LIMIT 1
            """
        ),
        {
            "evidence_set_id": str(evidence_set_id),
            "projection_hash": str(projection_hash),
        },
    )
    row = result.mappings().first()
    if row is None:
        return None

    snapshot_value = row.get("snapshot_json")
    if isinstance(snapshot_value, str):
        snapshot_value = json.loads(snapshot_value)

    return {
        "snapshot_id": str(row.get("snapshot_id")),
        "evidence_set_id": str(row.get("evidence_set_id")),
        "snapshot_schema_version": row.get("snapshot_schema_version"),
        "trusted_environment_context_schema_version": row.get(
            "trusted_environment_context_schema_version"
        ),
        "projection_policy_schema_version": row.get(
            "projection_policy_schema_version"
        ),
        "projection_status": row.get("projection_status"),
        "water_environment_identity_hash": row.get(
            "water_environment_identity_hash"
        ),
        "hydrology_trust_decision_hash": row.get(
            "hydrology_trust_decision_hash"
        ),
        "projection_policy_hash": row.get("projection_policy_hash"),
        "water_identity_mask_hash": row.get("water_identity_mask_hash"),
        "weather_mask_hash": row.get("weather_mask_hash"),
        "wind_mask_hash": row.get("wind_mask_hash"),
        "hydrology_mask_hash": row.get("hydrology_mask_hash"),
        "aggregate_environment_mask_hash": row.get(
            "aggregate_environment_mask_hash"
        ),
        "projection_hash": row.get("projection_hash"),
        "snapshot": snapshot_value,
    }


async def count_trusted_route_environment_context_snapshots(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
) -> int:
    result = await db.execute(
        text(
            f"""
            SELECT COUNT(*) AS snapshot_count
            FROM {TABLE_NAME}
            WHERE evidence_set_id = CAST(:evidence_set_id AS uuid)
            """
        ),
        {"evidence_set_id": str(evidence_set_id)},
    )
    row = result.mappings().first()
    return int(row.get("snapshot_count") or 0) if row is not None else 0
