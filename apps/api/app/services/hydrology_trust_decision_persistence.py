from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hydrology_trust_decision_snapshot import (
    verify_hydrology_trust_decision_snapshot,
)


TABLE_NAME = "route_hydrology_trust_decision_snapshots"


async def persist_hydrology_trust_decision_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist immutable derived hydrology trust-decision lineage.

    Unlike source-resolution persistence, multiple different decisions are allowed
    for one immutable environment evidence set so policy/model evolution remains
    auditable. Repeating the exact same decision hash is idempotent.
    """
    if not verify_hydrology_trust_decision_snapshot(snapshot):
        raise ValueError("Invalid hydrology trust decision snapshot hash")

    evidence_set_uuid = str(evidence_set_id)
    snapshot_evidence_set_id = str(snapshot.get("environment_evidence_set_id") or "")
    if snapshot_evidence_set_id != evidence_set_uuid:
        raise ValueError(
            "Hydrology trust decision snapshot evidence_set_id does not match "
            "persistence target"
        )

    decision_hash = str(snapshot["decision_hash"])

    existing = await load_hydrology_trust_decision_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
        decision_hash=decision_hash,
    )
    if existing is not None:
        lineage_count = await count_hydrology_trust_decision_snapshots(
            db,
            evidence_set_id=evidence_set_uuid,
        )
        return {
            "status": "ALREADY_CURRENT",
            "snapshot_id": existing.get("snapshot_id"),
            "evidence_set_id": evidence_set_uuid,
            "decision_hash": decision_hash,
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
                trusted_context_schema_version,
                representativeness_schema_version,
                trust_policy_schema_version,
                decision_status,
                hydrology_source_resolution_hash,
                trust_policy_hash,
                representativeness_policy_hash,
                temporal_support_mask_hash,
                decision_hash,
                snapshot_json
            ) VALUES (
                CAST(:id AS uuid),
                CAST(:evidence_set_id AS uuid),
                :snapshot_schema_version,
                :trusted_context_schema_version,
                :representativeness_schema_version,
                :trust_policy_schema_version,
                :decision_status,
                :hydrology_source_resolution_hash,
                :trust_policy_hash,
                :representativeness_policy_hash,
                :temporal_support_mask_hash,
                :decision_hash,
                CAST(:snapshot_json AS jsonb)
            )
            """
        ),
        {
            "id": snapshot_id,
            "evidence_set_id": evidence_set_uuid,
            "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
            "trusted_context_schema_version": snapshot.get(
                "trusted_context_schema_version"
            ),
            "representativeness_schema_version": snapshot.get(
                "representativeness_schema_version"
            ),
            "trust_policy_schema_version": snapshot.get(
                "trust_policy_schema_version"
            ),
            "decision_status": snapshot.get("decision_status"),
            "hydrology_source_resolution_hash": snapshot.get(
                "hydrology_source_resolution_hash"
            ),
            "trust_policy_hash": snapshot.get("trust_policy_hash"),
            "representativeness_policy_hash": snapshot.get(
                "representativeness_policy_hash"
            ),
            "temporal_support_mask_hash": snapshot.get(
                "temporal_support_mask_hash"
            ),
            "decision_hash": decision_hash,
            "snapshot_json": snapshot_json,
        },
    )
    await db.commit()

    round_trip = await load_hydrology_trust_decision_snapshot(
        db,
        evidence_set_id=evidence_set_uuid,
        decision_hash=decision_hash,
    )
    if round_trip is None:
        raise ValueError(
            "Hydrology trust decision snapshot could not be read back after persistence"
        )

    lineage_count = await count_hydrology_trust_decision_snapshots(
        db,
        evidence_set_id=evidence_set_uuid,
    )
    return {
        "status": "CREATED",
        "snapshot_id": round_trip.get("snapshot_id"),
        "evidence_set_id": evidence_set_uuid,
        "decision_hash": decision_hash,
        "round_trip_verified": round_trip.get("snapshot") == dict(snapshot),
        "round_trip": round_trip.get("snapshot"),
        "lineage_snapshot_count": lineage_count,
    }


async def load_hydrology_trust_decision_snapshot(
    db: AsyncSession,
    *,
    evidence_set_id: str | UUID,
    decision_hash: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            f"""
            SELECT
                id AS snapshot_id,
                evidence_set_id,
                snapshot_schema_version,
                trusted_context_schema_version,
                representativeness_schema_version,
                trust_policy_schema_version,
                decision_status,
                hydrology_source_resolution_hash,
                trust_policy_hash,
                representativeness_policy_hash,
                temporal_support_mask_hash,
                decision_hash,
                snapshot_json
            FROM {TABLE_NAME}
            WHERE evidence_set_id = CAST(:evidence_set_id AS uuid)
              AND decision_hash = :decision_hash
            LIMIT 1
            """
        ),
        {
            "evidence_set_id": str(evidence_set_id),
            "decision_hash": str(decision_hash),
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
        "trusted_context_schema_version": row.get(
            "trusted_context_schema_version"
        ),
        "representativeness_schema_version": row.get(
            "representativeness_schema_version"
        ),
        "trust_policy_schema_version": row.get("trust_policy_schema_version"),
        "decision_status": row.get("decision_status"),
        "hydrology_source_resolution_hash": row.get(
            "hydrology_source_resolution_hash"
        ),
        "trust_policy_hash": row.get("trust_policy_hash"),
        "representativeness_policy_hash": row.get(
            "representativeness_policy_hash"
        ),
        "temporal_support_mask_hash": row.get("temporal_support_mask_hash"),
        "decision_hash": row.get("decision_hash"),
        "snapshot": snapshot_value,
    }


async def count_hydrology_trust_decision_snapshots(
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
