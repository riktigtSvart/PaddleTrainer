from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


SNAPSHOT_SCHEMA_VERSION = "0.1"
TRUST_POLICY_SCHEMA_VERSION = "0.1"
REPRESENTATIVENESS_POLICY_SCHEMA_VERSION = "0.1"


def build_hydrology_trust_decision_snapshot(
    *,
    environment_evidence_set_id: str,
    environment_evidence_hash: str | None,
    route_hydrology_source_resolution_snapshot: Mapping[str, Any] | None,
    route_hydrology_representativeness: Mapping[str, Any] | None,
    trusted_route_hydrology_context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build compact immutable lineage for the downstream hydrology trust decision.

    This snapshot is deliberately separate from raw/normalized environment evidence.
    It captures the derived decision, the policy that produced it, the source-resolution
    commitment, and the temporal support mask used for segment-level gating.
    """
    if not isinstance(trusted_route_hydrology_context, Mapping):
        return None

    evidence_set_id = _string(environment_evidence_set_id)
    if evidence_set_id is None:
        raise ValueError("environment_evidence_set_id is required")

    resolution_hash = None
    if isinstance(route_hydrology_source_resolution_snapshot, Mapping):
        resolution_hash = _string(
            route_hydrology_source_resolution_snapshot.get("resolution_hash")
        )

    representativeness_policy = (
        deepcopy(dict(route_hydrology_representativeness.get("policy") or {}))
        if isinstance(route_hydrology_representativeness, Mapping)
        else {}
    )
    trust_policy = deepcopy(
        dict(trusted_route_hydrology_context.get("policy") or {})
    )

    trust_policy_hash = _policy_hash(
        TRUST_POLICY_SCHEMA_VERSION,
        trust_policy,
    )
    representativeness_policy_hash = _policy_hash(
        REPRESENTATIVENESS_POLICY_SCHEMA_VERSION,
        representativeness_policy,
    )

    temporal_support = _temporal_support_commitment(
        route_hydrology_representativeness
    )

    representativeness_by_route = {
        _route_index(route, position): route
        for position, route in enumerate(
            _sequence_of_mappings(
                route_hydrology_representativeness.get("routes")
                if isinstance(route_hydrology_representativeness, Mapping)
                else None
            )
        )
    }

    route_snapshots: list[dict[str, Any]] = []
    for position, route in enumerate(
        _sequence_of_mappings(trusted_route_hydrology_context.get("routes"))
    ):
        route_index = _route_index(route, position)
        rep_route = representativeness_by_route.get(route_index)
        route_mask_hash = _route_temporal_support_mask_hash(rep_route)
        route_snapshots.append(
            {
                "route_index": route_index,
                "exercise_index": _integer(route.get("exercise_index")),
                "representativeness_status": _string(
                    route.get("representativeness_status")
                ),
                "trust_status": _string(route.get("trust_status")),
                "source_context_available": bool(
                    route.get("source_context_available")
                ),
                "hydrology_context_included": bool(
                    route.get("hydrology_context_included")
                ),
                "usable_for_downstream_environment_context": bool(
                    route.get("usable_for_downstream_environment_context")
                ),
                "usable_with_limitations": bool(
                    route.get("usable_with_limitations")
                ),
                "source_context_segment_count": _integer(
                    route.get("source_context_segment_count")
                )
                or 0,
                "trusted_context_segment_count": _integer(
                    route.get("trusted_context_segment_count")
                )
                or 0,
                "withheld_context_segment_count": _integer(
                    route.get("withheld_context_segment_count")
                )
                or 0,
                "segment_filter_applied": bool(
                    route.get("segment_filter_applied")
                ),
                "representativeness_resolution_basis": sorted(
                    _string_list(
                        route.get("representativeness_resolution_basis")
                    )
                ),
                "representativeness_limitations": sorted(
                    _string_list(route.get("representativeness_limitations"))
                ),
                "trust_basis": sorted(_string_list(route.get("trust_basis"))),
                "temporal_support_mask_hash": route_mask_hash,
            }
        )

    route_snapshots.sort(
        key=lambda item: (
            item.get("route_index", 0),
            item.get("exercise_index")
            if item.get("exercise_index") is not None
            else -1,
        )
    )

    snapshot: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "environment_evidence_set_id": evidence_set_id,
        "environment_evidence_hash": _string(environment_evidence_hash),
        "hydrology_source_resolution_hash": resolution_hash,
        "trusted_context_schema_version": trusted_route_hydrology_context.get(
            "schema_version"
        ),
        "representativeness_schema_version": (
            route_hydrology_representativeness.get("schema_version")
            if isinstance(route_hydrology_representativeness, Mapping)
            else None
        ),
        "decision_status": trusted_route_hydrology_context.get("status"),
        "route_count": trusted_route_hydrology_context.get("route_count"),
        "trusted_route_count": trusted_route_hydrology_context.get(
            "trusted_route_count"
        ),
        "trusted_with_limitations_route_count": trusted_route_hydrology_context.get(
            "trusted_with_limitations_route_count"
        ),
        "withheld_route_count": trusted_route_hydrology_context.get(
            "withheld_route_count"
        ),
        "not_applicable_route_count": trusted_route_hydrology_context.get(
            "not_applicable_route_count"
        ),
        "trust_policy_schema_version": TRUST_POLICY_SCHEMA_VERSION,
        "trust_policy": trust_policy,
        "trust_policy_hash": trust_policy_hash,
        "representativeness_policy_schema_version": (
            REPRESENTATIVENESS_POLICY_SCHEMA_VERSION
        ),
        "representativeness_policy": representativeness_policy,
        "representativeness_policy_hash": representativeness_policy_hash,
        "temporal_support_mask_hash": temporal_support["aggregate_hash"],
        "temporal_support_routes": temporal_support["routes"],
        "routes": route_snapshots,
        "scope": {
            "domain": "HYDROLOGY_TRUST_DECISION_LINEAGE",
            "derived_from_environment_evidence": True,
            "mutates_environment_evidence_hash": False,
            "stores_full_hydrology_context_payload": False,
            "stores_temporal_support_as_hash_commitment": True,
            "allows_multiple_decisions_per_environment_evidence_set": True,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
        },
    }
    snapshot["decision_hash"] = hydrology_trust_decision_snapshot_hash(snapshot)
    return snapshot


def hydrology_trust_decision_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    canonical = {
        key: deepcopy(value)
        for key, value in snapshot.items()
        if key != "decision_hash"
    }
    return _canonical_hash(canonical)


def verify_hydrology_trust_decision_snapshot(
    snapshot: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    expected = _string(snapshot.get("decision_hash"))
    if expected is None:
        return False
    return expected == hydrology_trust_decision_snapshot_hash(snapshot)


def _temporal_support_commitment(
    representativeness: Mapping[str, Any] | None,
) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    for position, route in enumerate(
        _sequence_of_mappings(
            representativeness.get("routes")
            if isinstance(representativeness, Mapping)
            else None
        )
    ):
        temporal = route.get("temporal_evidence")
        temporal = temporal if isinstance(temporal, Mapping) else {}
        routes.append(
            {
                "route_index": _route_index(route, position),
                "exercise_index": _integer(route.get("exercise_index")),
                "route_segment_count": _integer(
                    temporal.get("route_segment_count")
                )
                or 0,
                "timestamped_segment_count": _integer(
                    temporal.get("timestamped_segment_count")
                )
                or 0,
                "temporally_supported_segment_count": _integer(
                    temporal.get("temporally_supported_segment_count")
                )
                or 0,
                "mask_hash": _route_temporal_support_mask_hash(route),
            }
        )
    routes.sort(
        key=lambda item: (
            item.get("route_index", 0),
            item.get("exercise_index")
            if item.get("exercise_index") is not None
            else -1,
        )
    )
    return {
        "routes": routes,
        "aggregate_hash": _canonical_hash(routes),
    }


def _route_temporal_support_mask_hash(
    route: Mapping[str, Any] | None,
) -> str:
    if not isinstance(route, Mapping):
        return _canonical_hash(
            {
                "route_segment_count": 0,
                "timestamped_segment_count": 0,
                "mask": [],
            }
        )

    temporal = route.get("temporal_evidence")
    temporal = temporal if isinstance(temporal, Mapping) else {}
    mask: list[dict[str, Any]] = []
    for position, segment in enumerate(_sequence_of_mappings(route.get("segments"))):
        segment_index = _integer(segment.get("segment_index"))
        if segment_index is None:
            segment_index = position
        mask.append(
            {
                "segment_index": segment_index,
                "temporally_supported": segment.get("temporally_supported") is True,
            }
        )
    mask.sort(key=lambda item: item["segment_index"])
    return _canonical_hash(
        {
            "route_segment_count": _integer(
                temporal.get("route_segment_count")
            )
            or 0,
            "timestamped_segment_count": _integer(
                temporal.get("timestamped_segment_count")
            )
            or 0,
            "mask": mask,
        }
    )


def _policy_hash(schema_version: str, policy: Mapping[str, Any]) -> str:
    return _canonical_hash(
        {
            "schema_version": schema_version,
            "policy": deepcopy(dict(policy)),
        }
    )


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _route_index(route: Mapping[str, Any], fallback: int) -> int:
    parsed = _integer(route.get("route_index"))
    return parsed if parsed is not None else fallback


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if item is not None]


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
