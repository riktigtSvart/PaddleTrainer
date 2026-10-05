from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping


SNAPSHOT_SCHEMA_VERSION = "0.1"
EVIDENCE_HASH_BINDING_SCHEMA_VERSION = "0.1"


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(candidate.get("source_provider") or ""),
        str(candidate.get("station_registry_number") or ""),
        str(candidate.get("station_name") or ""),
    )


def _identity_sort_key(identity: Mapping[str, Any]) -> tuple[str, str, str]:
    names = identity.get("identity_names") or []
    first_name = str(names[0]) if names else ""
    return (
        str(identity.get("source_provider") or ""),
        str(identity.get("waterbody_id") or ""),
        first_name,
    )


def _normalized_route(route: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(route))

    identities = [
        deepcopy(dict(item))
        for item in route.get("trusted_river_inland_identities") or []
        if isinstance(item, Mapping)
    ]
    normalized["trusted_river_inland_identities"] = sorted(
        identities,
        key=_identity_sort_key,
    )

    evaluated = []
    for item in route.get("evaluated_candidates") or []:
        if not isinstance(item, Mapping):
            continue
        candidate = item.get("candidate_source")
        normalized_item = deepcopy(dict(item))
        if isinstance(candidate, Mapping):
            normalized_item["candidate_source"] = deepcopy(dict(candidate))
        evaluated.append(normalized_item)

    normalized["evaluated_candidates"] = sorted(
        evaluated,
        key=lambda item: _candidate_sort_key(
            item.get("candidate_source")
            if isinstance(item.get("candidate_source"), Mapping)
            else {}
        ),
    )

    resolved = route.get("resolved_hydrology_source")
    normalized["resolved_hydrology_source"] = (
        deepcopy(dict(resolved)) if isinstance(resolved, Mapping) else None
    )
    return normalized


def build_route_hydrology_source_resolution_snapshot(
    route_hydrology_source_resolution: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build an immutable, compact snapshot of V14 hydrology-source resolution.

    V14 contains no segment-level payload, so the persisted form preserves the
    complete resolution/provenance semantics while normalizing list ordering for
    stable hashing. UNRESOLVED and NOT_APPLICABLE are intentionally first-class
    persisted outcomes.
    """
    if not isinstance(route_hydrology_source_resolution, Mapping):
        return None

    candidates = [
        deepcopy(dict(item))
        for item in route_hydrology_source_resolution.get("candidate_sources") or []
        if isinstance(item, Mapping)
    ]
    candidates = sorted(candidates, key=_candidate_sort_key)

    routes = [
        _normalized_route(route)
        for route in route_hydrology_source_resolution.get("routes") or []
        if isinstance(route, Mapping)
    ]
    routes = sorted(
        routes,
        key=lambda route: (
            route.get("route_index") if isinstance(route.get("route_index"), int) else 0,
            route.get("exercise_index")
            if isinstance(route.get("exercise_index"), int)
            else -1,
        ),
    )

    snapshot: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "resolution_schema_version": route_hydrology_source_resolution.get(
            "schema_version"
        ),
        "provider": route_hydrology_source_resolution.get("provider"),
        "available": route_hydrology_source_resolution.get("available"),
        "status": route_hydrology_source_resolution.get("status"),
        "route_count": route_hydrology_source_resolution.get("route_count"),
        "candidate_source_count": route_hydrology_source_resolution.get(
            "candidate_source_count"
        ),
        "identity_supported_route_count": route_hydrology_source_resolution.get(
            "identity_supported_route_count"
        ),
        "direct_resolved_route_count": route_hydrology_source_resolution.get(
            "direct_resolved_route_count"
        ),
        "ambiguous_route_count": route_hydrology_source_resolution.get(
            "ambiguous_route_count"
        ),
        "unresolved_route_count": route_hydrology_source_resolution.get(
            "unresolved_route_count"
        ),
        "not_applicable_route_count": route_hydrology_source_resolution.get(
            "not_applicable_route_count"
        ),
        "input_provenance": deepcopy(
            route_hydrology_source_resolution.get("input_provenance")
        ),
        "scope": deepcopy(route_hydrology_source_resolution.get("scope")),
        "candidate_sources": candidates,
        "routes": routes,
    }
    snapshot["resolution_hash"] = route_hydrology_source_resolution_snapshot_hash(
        snapshot
    )
    return snapshot


def route_hydrology_source_resolution_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    canonical = {
        key: deepcopy(value)
        for key, value in snapshot.items()
        if key != "resolution_hash"
    }
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def verify_route_hydrology_source_resolution_snapshot(
    snapshot: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    expected_hash = snapshot.get("resolution_hash")
    if not isinstance(expected_hash, str) or not expected_hash:
        return False
    return expected_hash == route_hydrology_source_resolution_snapshot_hash(snapshot)


def bind_route_hydrology_source_resolution_snapshot_to_evidence_record(
    evidence_record: dict[str, Any],
    snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Attach the snapshot; environment evidence persistence remains hash owner."""
    if not isinstance(evidence_record, dict):
        raise ValueError("Environment evidence record must be a dict")
    if snapshot is None:
        return evidence_record
    if not verify_route_hydrology_source_resolution_snapshot(snapshot):
        raise ValueError("Invalid route hydrology source resolution snapshot hash")

    resolution_hash = str(snapshot["resolution_hash"])
    evidence_record["route_hydrology_source_resolution_snapshot"] = deepcopy(
        dict(snapshot)
    )
    evidence_record["hydrology_source_resolution_hash_binding"] = {
        "binding_schema_version": EVIDENCE_HASH_BINDING_SCHEMA_VERSION,
        "hash_owner": "ENVIRONMENT_EVIDENCE_PERSISTENCE",
        "route_hydrology_source_resolution_hash": resolution_hash,
    }
    return evidence_record
