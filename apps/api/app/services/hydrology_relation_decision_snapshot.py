from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


SNAPSHOT_SCHEMA_VERSION = "0.1"
RELATION_POLICY_SCHEMA_VERSION = "0.1"


def build_hydrology_relation_decision_snapshot(
    *,
    environment_evidence_set_id: str,
    environment_evidence_hash: str | None,
    route_hydrology_source_resolution_snapshot: Mapping[str, Any] | None,
    hydrology_relation_catalog: Mapping[str, Any] | None,
    route_hydrology_relation_evidence: Mapping[str, Any] | None,
    relation_aware_trusted_route_hydrology_context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build immutable compact lineage for V23/V23.1 relation decisions.

    The snapshot commits to authoritative catalog semantics, evaluated metric
    transfer decisions, and the effective relation-aware trust projection. It
    deliberately does not duplicate source hydrology measurements or trusted
    segment payloads.
    """
    if not isinstance(hydrology_relation_catalog, Mapping):
        return None
    if not isinstance(route_hydrology_relation_evidence, Mapping):
        return None
    if not isinstance(relation_aware_trusted_route_hydrology_context, Mapping):
        return None

    evidence_set_id = _string(environment_evidence_set_id)
    if evidence_set_id is None:
        raise ValueError("environment_evidence_set_id is required")

    source_resolution_hash = None
    if isinstance(route_hydrology_source_resolution_snapshot, Mapping):
        source_resolution_hash = _string(
            route_hydrology_source_resolution_snapshot.get("resolution_hash")
        )

    catalog_commitment = _catalog_commitment(hydrology_relation_catalog)
    catalog_hash = _canonical_hash(catalog_commitment)

    relation_policy = deepcopy(
        dict(relation_aware_trusted_route_hydrology_context.get("policy") or {})
    )
    relation_policy_hash = _canonical_hash(
        {
            "schema_version": RELATION_POLICY_SCHEMA_VERSION,
            "policy": relation_policy,
        }
    )

    evidence_by_key = {
        _route_key(route, position): route
        for position, route in enumerate(
            _sequence_of_mappings(route_hydrology_relation_evidence.get("routes"))
        )
    }

    route_snapshots: list[dict[str, Any]] = []
    for position, route in enumerate(
        _sequence_of_mappings(
            relation_aware_trusted_route_hydrology_context.get("routes")
        )
    ):
        route_key = _route_key(route, position)
        evidence_route = evidence_by_key.get(route_key)
        route_snapshots.append(
            {
                "route_index": route_key[0],
                "exercise_index": route_key[1],
                "source_resolution_status": _string(
                    evidence_route.get("source_resolution_status")
                    if isinstance(evidence_route, Mapping)
                    else None
                ),
                "relation_evidence_status": _string(
                    evidence_route.get("status")
                    if isinstance(evidence_route, Mapping)
                    else route.get("relation_evidence_status")
                ),
                "direct_trust_status": _string(route.get("direct_trust_status")),
                "trust_status": _string(route.get("trust_status")),
                "trust_mode": _string(route.get("trust_mode")),
                "hydrology_context_included": bool(
                    route.get("hydrology_context_included")
                ),
                "usable_for_downstream_environment_context": bool(
                    route.get("usable_for_downstream_environment_context")
                ),
                "authorized_metric_keys": sorted(
                    set(_string_list(route.get("authorized_metric_keys")))
                ),
                "withheld_metric_keys": sorted(
                    set(_string_list(route.get("withheld_metric_keys")))
                ),
                "unsupported_metric_payload_keys": sorted(
                    set(_string_list(route.get("unsupported_metric_payload_keys")))
                ),
                "metric_decisions": _metric_decision_commitment(
                    route.get("relation_metric_trust")
                ),
                "selected_source_by_metric": _selected_source_commitment(
                    evidence_route.get("selected_source_by_metric")
                    if isinstance(evidence_route, Mapping)
                    else None
                ),
                "relation_ids": _relation_ids(
                    evidence_route.get("metric_relations")
                    if isinstance(evidence_route, Mapping)
                    else None
                ),
                "resolution_basis": sorted(
                    set(
                        _string_list(
                            evidence_route.get("resolution_basis")
                            if isinstance(evidence_route, Mapping)
                            else None
                        )
                    )
                ),
                "limitations": sorted(
                    set(
                        _string_list(
                            evidence_route.get("limitations")
                            if isinstance(evidence_route, Mapping)
                            else None
                        )
                        + _string_list(route.get("representativeness_limitations"))
                    )
                ),
            }
        )

    route_snapshots.sort(key=_route_sort_key)

    snapshot: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "environment_evidence_set_id": evidence_set_id,
        "environment_evidence_hash": _string(environment_evidence_hash),
        "hydrology_source_resolution_hash": source_resolution_hash,
        "relation_catalog_schema_version": _string(
            hydrology_relation_catalog.get("schema_version")
        ),
        "relation_catalog_provider": _string(
            hydrology_relation_catalog.get("provider")
        ),
        "relation_catalog_product": _string(
            hydrology_relation_catalog.get("product")
        ),
        "relation_catalog_hash": catalog_hash,
        "relation_evidence_schema_version": _string(
            route_hydrology_relation_evidence.get("schema_version")
        ),
        "relation_evidence_status": _string(
            route_hydrology_relation_evidence.get("status")
        ),
        "relation_aware_context_schema_version": _string(
            relation_aware_trusted_route_hydrology_context.get("schema_version")
        ),
        "relation_aware_context_status": _string(
            relation_aware_trusted_route_hydrology_context.get("status")
        ),
        "relation_policy_schema_version": RELATION_POLICY_SCHEMA_VERSION,
        "relation_policy": relation_policy,
        "relation_policy_hash": relation_policy_hash,
        "route_count": len(route_snapshots),
        "relation_derived_route_count": sum(
            1
            for route in route_snapshots
            if route.get("trust_mode") == "RELATION_DERIVED_METRIC_PROJECTION"
            and route.get("hydrology_context_included") is True
        ),
        "routes": route_snapshots,
        "scope": {
            "domain": "HYDROLOGY_RELATION_DECISION_LINEAGE",
            "derived_from_environment_evidence": True,
            "mutates_environment_evidence_hash": False,
            "stores_full_relation_catalog": False,
            "stores_full_relation_evidence": False,
            "stores_full_hydrology_measurements": False,
            "commits_catalog_semantics_by_hash": True,
            "commits_metric_authorization_decisions": True,
            "allows_multiple_relation_decisions_per_environment_evidence_set": True,
            "direct_hydrology_trust_lineage_remains_separate": True,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
        },
    }
    snapshot["relation_decision_hash"] = hydrology_relation_decision_snapshot_hash(
        snapshot
    )
    return snapshot


def hydrology_relation_decision_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    canonical = {
        key: deepcopy(value)
        for key, value in snapshot.items()
        if key != "relation_decision_hash"
    }
    return _canonical_hash(canonical)


def verify_hydrology_relation_decision_snapshot(
    snapshot: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    expected = _string(snapshot.get("relation_decision_hash"))
    if expected is None:
        return False
    return expected == hydrology_relation_decision_snapshot_hash(snapshot)


def _catalog_commitment(catalog: Mapping[str, Any]) -> dict[str, Any]:
    documents = []
    for document in _sequence_of_mappings(catalog.get("source_documents")):
        documents.append(_semantic_normalize(document))
    documents.sort(key=lambda item: _string(item.get("document_id")) or "")

    relations = []
    for relation in _sequence_of_mappings(catalog.get("relations")):
        relation_copy = _semantic_normalize(relation)
        metrics = relation_copy.get("metrics")
        if isinstance(metrics, list):
            metrics.sort(key=lambda item: _string(item.get("metric_key")) or "")
        relations.append(relation_copy)
    relations.sort(key=lambda item: _string(item.get("relation_id")) or "")

    return {
        "provider": _string(catalog.get("provider")),
        "product": _string(catalog.get("product")),
        "schema_version": _string(catalog.get("schema_version")),
        "catalog_type": _string(catalog.get("catalog_type")),
        "source_mode": _string(catalog.get("source_mode")),
        "jurisdiction": _string(catalog.get("jurisdiction")),
        "source_documents": documents,
        "metadata": _semantic_normalize(catalog.get("metadata") or {}),
        "relations": relations,
    }


def _semantic_normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _semantic_normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized = [_semantic_normalize(item) for item in value]
        if all(not isinstance(item, (Mapping, list)) for item in normalized):
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
        return normalized
    return deepcopy(value)


def _metric_decision_commitment(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _sequence_of_mappings(value):
        source = row.get("source")
        source = source if isinstance(source, Mapping) else {}
        authority = row.get("authority")
        authority = authority if isinstance(authority, Mapping) else {}
        rows.append(
            {
                "metric_key": _string(row.get("metric_key")),
                "decision": _string(row.get("decision")),
                "payload_field": _string(row.get("payload_field")),
                "payload_projection_supported": bool(
                    row.get("payload_projection_supported")
                ),
                "relation_id": _string(row.get("relation_id")),
                "relation_type": _string(row.get("relation_type")),
                "representativeness_ceiling": _string(
                    row.get("representativeness_ceiling")
                ),
                "station_registry_number": _string(
                    source.get("station_registry_number")
                ),
                "watercourse": _string(source.get("watercourse")),
                "authority_provider": _string(authority.get("provider")),
                "authority_reference": _string(authority.get("reference")),
                "control_structure_state_required": bool(
                    row.get("control_structure_state_required")
                ),
                "control_structure_state_available": _optional_bool(
                    row.get("control_structure_state_available")
                ),
                "calibration_evidence_required": bool(
                    row.get("calibration_evidence_required")
                ),
                "calibration_evidence_available": _optional_bool(
                    row.get("calibration_evidence_available")
                ),
                "limitations": sorted(
                    set(_string_list(row.get("limitations")))
                ),
            }
        )
    rows.sort(
        key=lambda item: (
            item.get("metric_key") or "",
            item.get("relation_id") or "",
            item.get("station_registry_number") or "",
        )
    )
    return rows


def _selected_source_commitment(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for metric_key, source in sorted(value.items(), key=lambda pair: str(pair[0])):
        if not isinstance(source, Mapping):
            continue
        result[str(metric_key)] = {
            "station_registry_number": _string(source.get("station_registry_number")),
            "station_name": _string(source.get("station_name")),
            "watercourse": _string(source.get("watercourse")),
        }
    return result


def _relation_ids(value: Any) -> list[str]:
    ids = {
        relation_id
        for row in _sequence_of_mappings(value)
        for relation_id in [_string(row.get("relation_id"))]
        if relation_id is not None
    }
    return sorted(ids)



def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None

def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _route_key(route: Mapping[str, Any], fallback: int) -> tuple[int, int | None]:
    route_index = _integer(route.get("route_index"))
    exercise_index = _integer(route.get("exercise_index"))
    return (route_index if route_index is not None else fallback, exercise_index)


def _route_sort_key(item: Mapping[str, Any]) -> tuple[int, int]:
    route_index = _integer(item.get("route_index")) or 0
    exercise_index = _integer(item.get("exercise_index"))
    return route_index, exercise_index if exercise_index is not None else -1


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [text for item in value for text in [_string(item)] if text is not None]


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
