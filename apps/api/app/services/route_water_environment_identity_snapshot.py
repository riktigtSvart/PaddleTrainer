from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping


SNAPSHOT_SCHEMA_VERSION = "0.1"


def build_route_water_environment_identity_snapshot(
    route_water_environment_identity: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build the compact immutable payload persisted with environment evidence.

    This snapshot intentionally preserves trusted identity semantics and
    provenance while excluding per-segment payloads. It is suitable for
    semantic hashing and round-trip persistence.
    """
    if not isinstance(route_water_environment_identity, Mapping):
        return None

    routes: list[dict[str, Any]] = []
    for route in route_water_environment_identity.get("routes") or []:
        if not isinstance(route, Mapping):
            continue
        routes.append(
            {
                key: deepcopy(value)
                for key, value in route.items()
                if key != "segments"
            }
        )

    snapshot: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "identity_schema_version": route_water_environment_identity.get(
            "schema_version"
        ),
        "provider": route_water_environment_identity.get("provider"),
        "available": route_water_environment_identity.get("available"),
        "status": route_water_environment_identity.get("status"),
        "route_count": route_water_environment_identity.get("route_count"),
        "river_inland_segment_count": route_water_environment_identity.get(
            "river_inland_segment_count"
        ),
        "marine_segment_count": route_water_environment_identity.get(
            "marine_segment_count"
        ),
        "ambiguous_environment_segment_count": (
            route_water_environment_identity.get(
                "ambiguous_environment_segment_count"
            )
        ),
        "unresolved_environment_segment_count": (
            route_water_environment_identity.get(
                "unresolved_environment_segment_count"
            )
        ),
        "direct_resolved_segment_count": route_water_environment_identity.get(
            "direct_resolved_segment_count"
        ),
        "continuity_supported_segment_count": (
            route_water_environment_identity.get(
                "continuity_supported_segment_count"
            )
        ),
        "ambiguous_segment_count": route_water_environment_identity.get(
            "ambiguous_segment_count"
        ),
        "transition_candidate_segment_count": (
            route_water_environment_identity.get(
                "transition_candidate_segment_count"
            )
        ),
        "unresolved_segment_count": route_water_environment_identity.get(
            "unresolved_segment_count"
        ),
        "cross_domain_conflict_segment_count": (
            route_water_environment_identity.get(
                "cross_domain_conflict_segment_count"
            )
        ),
        "input_provenance": deepcopy(
            route_water_environment_identity.get("input_provenance")
        ),
        "scope": deepcopy(route_water_environment_identity.get("scope")),
        "routes": routes,
    }

    snapshot["identity_hash"] = route_water_environment_identity_snapshot_hash(
        snapshot
    )
    return snapshot


def route_water_environment_identity_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    """Stable semantic hash of a compact water-environment identity snapshot."""
    canonical = {
        key: deepcopy(value)
        for key, value in snapshot.items()
        if key != "identity_hash"
    }
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def verify_route_water_environment_identity_snapshot(
    snapshot: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    expected_hash = snapshot.get("identity_hash")
    if not isinstance(expected_hash, str) or not expected_hash:
        return False
    return expected_hash == route_water_environment_identity_snapshot_hash(
        snapshot
    )


EVIDENCE_HASH_BINDING_SCHEMA_VERSION = "0.2"


def bind_route_water_environment_identity_snapshot_to_evidence_record(
    evidence_record: dict[str, Any],
    snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Attach trusted water identity before environment persistence hashing.

    Environment evidence hashing is owned by
    ``environment_evidence_persistence.build_environment_persistence_plan``.
    The persistence layer canonicalizes the environment evidence and includes
    the stable water-identity hash as an explicit semantic input.  This helper
    therefore must not calculate or overwrite an environment ``evidence_hash``.

    Keeping the hash owner in one place prevents route-level and persistence-
    level hashes from diverging.
    """
    if not isinstance(evidence_record, dict):
        raise ValueError("Environment evidence record must be a dict")

    if snapshot is None:
        return evidence_record

    if not verify_route_water_environment_identity_snapshot(snapshot):
        raise ValueError("Invalid route water environment identity snapshot hash")

    identity_hash = str(snapshot["identity_hash"])

    evidence_record["route_water_environment_identity_snapshot"] = deepcopy(
        dict(snapshot)
    )
    evidence_record["water_environment_identity_hash_binding"] = {
        "binding_schema_version": EVIDENCE_HASH_BINDING_SCHEMA_VERSION,
        "hash_owner": "ENVIRONMENT_EVIDENCE_PERSISTENCE",
        "route_water_environment_identity_hash": identity_hash,
    }
    return evidence_record
