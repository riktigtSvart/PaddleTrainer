from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hydrology_relation_decision_snapshot import (
    verify_hydrology_relation_decision_snapshot,
)


TABLE_NAME = "route_hydrology_relation_decision_snapshots"


async def persist_hydrology_relation_decision_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if not verify_hydrology_relation_decision_snapshot(snapshot):
        raise ValueError("Invalid hydrology relation decision snapshot hash")

    evidence_set_uuid = str(evidence_set_id)
    snapshot_evidence_set_id = str(
        snapshot.get("environment_evidence_set_id") or ""
    )
    if snapshot_evidence_set_id != evidence_set_uuid:
        raise ValueError(
            "Hydrology relation decision snapshot evidence_set_id does not "
            "match persistence target"
        )

    decision_hash = str(snapshot["relation_decision_hash"])
    existing = await load_hydrology_relation_decision_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
        relation_decision_hash=decision_hash,
    )
    if existing is not None:
        lineage_count = await count_hydrology_relation_decision_snapshots(
            db,
            evidence_set_id=evidence_set_uuid,
        )
        return {
            "status": "ALREADY_CURRENT",
            "snapshot_id": existing.get("snapshot_id"),
            "evidence_set_id": evidence_set_uuid,
            "relation_decision_hash": decision_hash,
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
                relation_catalog_schema_version,
                relation_catalog_provider,
                relation_catalog_product,
                relation_evidence_schema_version,
                relation_aware_context_schema_version,
                relation_evidence_status,
                relation_aware_context_status,
                hydrology_source_resolution_hash,
                relation_catalog_hash,
                relation_policy_hash,
                relation_decision_hash,
                snapshot_json
            ) VALUES (
                CAST(:id AS uuid),
                CAST(:evidence_set_id AS uuid),
                :snapshot_schema_version,
                :relation_catalog_schema_version,
                :relation_catalog_provider,
                :relation_catalog_product,
                :relation_evidence_schema_version,
                :relation_aware_context_schema_version,
                :relation_evidence_status,
                :relation_aware_context_status,
                :hydrology_source_resolution_hash,
                :relation_catalog_hash,
                :relation_policy_hash,
                :relation_decision_hash,
                CAST(:snapshot_json AS jsonb)
            )
            """
        ),
        {
            "id": snapshot_id,
            "evidence_set_id": evidence_set_uuid,
            "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
            "relation_catalog_schema_version": snapshot.get(
                "relation_catalog_schema_version"
            ),
            "relation_catalog_provider": snapshot.get("relation_catalog_provider"),
            "relation_catalog_product": snapshot.get("relation_catalog_product"),
            "relation_evidence_schema_version": snapshot.get(
                "relation_evidence_schema_version"
            ),
            "relation_aware_context_schema_version": snapshot.get(
                "relation_aware_context_schema_version"
            ),
            "relation_evidence_status": snapshot.get("relation_evidence_status"),
            "relation_aware_context_status": snapshot.get(
                "relation_aware_context_status"
            ),
            "hydrology_source_resolution_hash": snapshot.get(
                "hydrology_source_resolution_hash"
            ),
            "relation_catalog_hash": snapshot.get("relation_catalog_hash"),
            "relation_policy_hash": snapshot.get("relation_policy_hash"),
            "relation_decision_hash": decision_hash,
            "snapshot_json": snapshot_json,
        },
    )
    await db.commit()

    round_trip = await load_hydrology_relation_decision_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
        relation_decision_hash=decision_hash,
    )
    if round_trip is None:
        raise ValueError(
            "Hydrology relation decision snapshot could not be read back after persistence"
        )

    lineage_count = await count_hydrology_relation_decision_snapshots(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    return {
        "status": "CREATED",
        "snapshot_id": round_trip.get("snapshot_id"),
        "evidence_set_id": evidence_set_uuid,
        "relation_decision_hash": decision_hash,
        "round_trip_verified": round_trip.get("snapshot") == dict(snapshot),
        "round_trip": round_trip.get("snapshot"),
        "lineage_snapshot_count": lineage_count,
    }


async def load_hydrology_relation_decision_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    relation_decision_hash: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            f"""
            SELECT
                id AS snapshot_id,
                evidence_set_id,
                snapshot_schema_version,
                relation_catalog_schema_version,
                relation_catalog_provider,
                relation_catalog_product,
                relation_evidence_schema_version,
                relation_aware_context_schema_version,
                relation_evidence_status,
                relation_aware_context_status,
                hydrology_source_resolution_hash,
                relation_catalog_hash,
                relation_policy_hash,
                relation_decision_hash,
                snapshot_json
            FROM {TABLE_NAME}
            WHERE evidence_set_id = CAST(:evidence_set_id AS uuid)
              AND relation_decision_hash = :relation_decision_hash
            LIMIT 1
            """
        ),
        {
            "evidence_set_id": str(evidence_set_id),
            "relation_decision_hash": str(relation_decision_hash),
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
        "relation_catalog_schema_version": row.get(
            "relation_catalog_schema_version"
        ),
        "relation_catalog_provider": row.get("relation_catalog_provider"),
        "relation_catalog_product": row.get("relation_catalog_product"),
        "relation_evidence_schema_version": row.get(
            "relation_evidence_schema_version"
        ),
        "relation_aware_context_schema_version": row.get(
            "relation_aware_context_schema_version"
        ),
        "relation_evidence_status": row.get("relation_evidence_status"),
        "relation_aware_context_status": row.get("relation_aware_context_status"),
        "hydrology_source_resolution_hash": row.get(
            "hydrology_source_resolution_hash"
        ),
        "relation_catalog_hash": row.get("relation_catalog_hash"),
        "relation_policy_hash": row.get("relation_policy_hash"),
        "relation_decision_hash": row.get("relation_decision_hash"),
        "snapshot": snapshot_value,
    }


async def count_hydrology_relation_decision_snapshots(
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
