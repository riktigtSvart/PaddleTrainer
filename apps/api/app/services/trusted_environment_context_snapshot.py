from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


SNAPSHOT_SCHEMA_VERSION = "0.2"
PROJECTION_POLICY_SCHEMA_VERSION = "0.1"
COMPONENT_NAMES = (
    "water_identity",
    "weather",
    "wind",
    "hydrology",
)


def build_trusted_route_environment_context_snapshot(
    *,
    environment_evidence_set_id: str,
    environment_evidence_hash: str | None,
    route_water_environment_identity_snapshot: Mapping[str, Any] | None,
    hydrology_trust_decision_snapshot: Mapping[str, Any] | None,
    hydrology_relation_decision_snapshot: Mapping[str, Any] | None = None,
    trusted_route_environment_context: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build compact immutable lineage for the trusted environment projection.

    Raw/normalized environment evidence remains owned by the environment evidence
    persistence layer. This snapshot commits only to the derived downstream trust
    projection, its upstream trust commitments, and per-component segment masks.
    """
    if not isinstance(trusted_route_environment_context, Mapping):
        return None

    evidence_set_id = _string(environment_evidence_set_id)
    if evidence_set_id is None:
        raise ValueError("environment_evidence_set_id is required")

    projection_policy = deepcopy(
        dict(trusted_route_environment_context.get("policy") or {})
    )
    projection_policy_hash = _policy_hash(
        PROJECTION_POLICY_SCHEMA_VERSION,
        projection_policy,
    )

    route_snapshots: list[dict[str, Any]] = []
    aggregate_component_routes: dict[str, list[dict[str, Any]]] = {
        component: [] for component in COMPONENT_NAMES
    }
    aggregate_environment_routes: list[dict[str, Any]] = []

    for position, route in enumerate(
        _sequence_of_mappings(trusted_route_environment_context.get("routes"))
    ):
        route_index = _route_index(route, position)
        exercise_index = _integer(route.get("exercise_index"))
        component_hashes = {
            component: _route_component_mask_hash(route, component)
            for component in COMPONENT_NAMES
        }
        environment_mask_hash = _route_environment_mask_hash(route)

        for component in COMPONENT_NAMES:
            aggregate_component_routes[component].append(
                {
                    "route_index": route_index,
                    "exercise_index": exercise_index,
                    "mask_hash": component_hashes[component],
                }
            )
        aggregate_environment_routes.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "mask_hash": environment_mask_hash,
            }
        )

        route_snapshots.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "status": _string(route.get("status")),
                "segment_count": _integer(route.get("segment_count")) or 0,
                "trusted_segment_count": _integer(
                    route.get("trusted_segment_count")
                )
                or 0,
                "trusted_with_limitations_segment_count": _integer(
                    route.get("trusted_with_limitations_segment_count")
                )
                or 0,
                "withheld_segment_count": _integer(
                    route.get("withheld_segment_count")
                )
                or 0,
                "unavailable_segment_count": _integer(
                    route.get("unavailable_segment_count")
                )
                or 0,
                "not_applicable_segment_count": _integer(
                    route.get("not_applicable_segment_count")
                )
                or 0,
                "downstream_usable_segment_count": _integer(
                    route.get("downstream_usable_segment_count")
                )
                or 0,
                "water_identity_usable_segment_count": _integer(
                    route.get("water_identity_usable_segment_count")
                )
                or 0,
                "weather_usable_segment_count": _integer(
                    route.get("weather_usable_segment_count")
                )
                or 0,
                "wind_usable_segment_count": _integer(
                    route.get("wind_usable_segment_count")
                )
                or 0,
                "hydrology_usable_segment_count": _integer(
                    route.get("hydrology_usable_segment_count")
                )
                or 0,
                "hydrology_route_trust_status": _string(
                    route.get("hydrology_route_trust_status")
                ),
                "environment_types": sorted(
                    set(_string_list(route.get("environment_types")))
                ),
                "mixed_environment_route": bool(
                    route.get("mixed_environment_route")
                ),
                "route_limitations": sorted(
                    set(_string_list(route.get("route_limitations")))
                ),
                "component_mask_hashes": component_hashes,
                "environment_mask_hash": environment_mask_hash,
            }
        )

    route_snapshots.sort(key=_route_sort_key)
    for routes in aggregate_component_routes.values():
        routes.sort(key=_route_sort_key)
    aggregate_environment_routes.sort(key=_route_sort_key)

    component_mask_hashes = {
        component: _canonical_hash(routes)
        for component, routes in aggregate_component_routes.items()
    }
    aggregate_environment_mask_hash = _canonical_hash(
        aggregate_environment_routes
    )

    input_provenance = deepcopy(
        dict(trusted_route_environment_context.get("input_provenance") or {})
    )

    snapshot: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "environment_evidence_set_id": evidence_set_id,
        "environment_evidence_hash": _string(environment_evidence_hash),
        "water_environment_identity_hash": _upstream_hash(
            route_water_environment_identity_snapshot,
            "identity_hash",
        ),
        "hydrology_trust_decision_hash": _upstream_hash(
            hydrology_trust_decision_snapshot,
            "decision_hash",
        ),
        "hydrology_relation_decision_hash": _upstream_hash(
            hydrology_relation_decision_snapshot,
            "relation_decision_hash",
        ),
        "trusted_environment_context_schema_version": _string(
            trusted_route_environment_context.get("schema_version")
        ),
        "projection_status": _string(
            trusted_route_environment_context.get("status")
        ),
        "route_count": _integer(
            trusted_route_environment_context.get("route_count")
        )
        or len(route_snapshots),
        "trusted_route_count": _integer(
            trusted_route_environment_context.get("trusted_route_count")
        )
        or 0,
        "trusted_with_limitations_route_count": _integer(
            trusted_route_environment_context.get(
                "trusted_with_limitations_route_count"
            )
        )
        or 0,
        "withheld_route_count": _integer(
            trusted_route_environment_context.get("withheld_route_count")
        )
        or 0,
        "unavailable_route_count": _integer(
            trusted_route_environment_context.get("unavailable_route_count")
        )
        or 0,
        "not_applicable_route_count": _integer(
            trusted_route_environment_context.get("not_applicable_route_count")
        )
        or 0,
        "input_provenance": input_provenance,
        "projection_policy_schema_version": PROJECTION_POLICY_SCHEMA_VERSION,
        "projection_policy": projection_policy,
        "projection_policy_hash": projection_policy_hash,
        "component_mask_hashes": component_mask_hashes,
        "aggregate_environment_mask_hash": aggregate_environment_mask_hash,
        "routes": route_snapshots,
        "scope": {
            "domain": "TRUSTED_ROUTE_ENVIRONMENT_CONTEXT_LINEAGE",
            "derived_from_environment_evidence": True,
            "mutates_environment_evidence_hash": False,
            "stores_full_environment_context_payload": False,
            "stores_component_segment_masks_as_hash_commitments": True,
            "allows_multiple_projections_per_environment_evidence_set": True,
            "links_relation_derived_hydrology_lineage_when_present": True,
            "promotes_component_trust": False,
            "resolves_new_provider_evidence": False,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "infers_physiological_response": False,
        },
    }
    snapshot["projection_hash"] = trusted_environment_context_snapshot_hash(
        snapshot
    )
    return snapshot


def trusted_environment_context_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    canonical = {
        key: deepcopy(value)
        for key, value in snapshot.items()
        if key != "projection_hash"
    }
    return _canonical_hash(canonical)


def verify_trusted_environment_context_snapshot(
    snapshot: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    expected = _string(snapshot.get("projection_hash"))
    if expected is None:
        return False
    return expected == trusted_environment_context_snapshot_hash(snapshot)


def _route_component_mask_hash(
    route: Mapping[str, Any],
    component_name: str,
) -> str:
    mask: list[dict[str, Any]] = []
    for position, segment in enumerate(_sequence_of_mappings(route.get("segments"))):
        component = segment.get(component_name)
        component = component if isinstance(component, Mapping) else {}
        order_index = _integer(segment.get("order_index"))
        if order_index is None:
            order_index = position
        mask.append(
            {
                "order_index": order_index,
                "status": _string(component.get("status")),
                "usable": component.get(
                    "usable_for_downstream_environment_context"
                )
                is True,
                "included": component.get("included") is True,
                "applicable": component.get("applicable") is not False,
            }
        )
    mask.sort(key=lambda item: item["order_index"])
    return _canonical_hash(mask)


def _route_environment_mask_hash(route: Mapping[str, Any]) -> str:
    mask: list[dict[str, Any]] = []
    for position, segment in enumerate(_sequence_of_mappings(route.get("segments"))):
        order_index = _integer(segment.get("order_index"))
        if order_index is None:
            order_index = position
        component_statuses = segment.get("component_statuses")
        component_statuses = (
            dict(component_statuses)
            if isinstance(component_statuses, Mapping)
            else {}
        )
        mask.append(
            {
                "order_index": order_index,
                "status": _string(segment.get("status")),
                "usable": segment.get(
                    "usable_for_downstream_environment_context"
                )
                is True,
                "usable_with_limitations": segment.get(
                    "usable_with_limitations"
                )
                is True,
                "component_statuses": {
                    key: _string(value)
                    for key, value in sorted(component_statuses.items())
                },
            }
        )
    mask.sort(key=lambda item: item["order_index"])
    return _canonical_hash(mask)


def _policy_hash(schema_version: str, policy: Mapping[str, Any]) -> str:
    return _canonical_hash(
        {
            "schema_version": schema_version,
            "policy": deepcopy(dict(policy)),
        }
    )


def _upstream_hash(
    snapshot: Mapping[str, Any] | None,
    key: str,
) -> str | None:
    if not isinstance(snapshot, Mapping):
        return None
    return _string(snapshot.get(key))


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


def _route_sort_key(item: Mapping[str, Any]) -> tuple[int, int]:
    route_index = _integer(item.get("route_index")) or 0
    exercise_index = _integer(item.get("exercise_index"))
    return route_index, exercise_index if exercise_index is not None else -1


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    result: list[str] = []
    for item in value:
        text = _string(item)
        if text is not None:
            result.append(text)
    return result


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
