from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_READY = "READY"
STATUS_READY_WITH_LIMITATIONS = "READY_WITH_LIMITATIONS"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_WITHHELD = "WITHHELD"
STATUS_UNAVAILABLE = "UNAVAILABLE"

ATHLETE_STATE_BOUND = "BOUND"
ATHLETE_STATE_NOT_BOUND = "NOT_BOUND"

ENVIRONMENT_USABLE_STATUSES = {
    "TRUSTED",
    "TRUSTED_WITH_LIMITATIONS",
}


def build_route_expected_response_input(
    route_external_workload_evidence: Mapping[str, Any] | None,
    trusted_route_environment_context: Mapping[str, Any] | None,
    *,
    athlete_state_context: Mapping[str, Any] | None = None,
    athlete_state_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the explicit input boundary for a future expected-response model.

    This function does not estimate an expected physiological response. It only
    aligns already-trusted external workload with already-gated environmental
    context and records whether an explicit athlete-state snapshot has been
    bound by the caller. A readiness projection is deliberately not accepted as
    an implicit substitute for AthleteState.
    """
    workload_routes = _route_lookup(route_external_workload_evidence)
    environment_routes = _route_lookup(trusted_route_environment_context)
    route_keys = _ordered_union_route_keys(workload_routes, environment_routes)

    athlete_state = _athlete_state_component(
        athlete_state_context,
        athlete_state_binding,
    )

    route_results: list[dict[str, Any]] = []
    status_counts = {
        STATUS_READY: 0,
        STATUS_READY_WITH_LIMITATIONS: 0,
        STATUS_INCOMPLETE: 0,
        STATUS_WITHHELD: 0,
        STATUS_UNAVAILABLE: 0,
    }

    for route_key in route_keys:
        route_result = _build_route_result(
            route_key=route_key,
            workload_route=workload_routes.get(route_key),
            environment_route=environment_routes.get(route_key),
            athlete_state=athlete_state,
        )
        route_results.append(route_result)
        status_counts[route_result["status"]] += 1

    return {
        "provider": "PADDLETRAINER",
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _overall_status(route_results),
        "route_count": len(route_results),
        "ready_route_count": status_counts[STATUS_READY],
        "ready_with_limitations_route_count": status_counts[
            STATUS_READY_WITH_LIMITATIONS
        ],
        "incomplete_route_count": status_counts[STATUS_INCOMPLETE],
        "withheld_route_count": status_counts[STATUS_WITHHELD],
        "unavailable_route_count": status_counts[STATUS_UNAVAILABLE],
        "model_ready_route_count": sum(
            1 for route in route_results if route.get("model_ready") is True
        ),
        "input_provenance": {
            "route_external_workload_evidence_schema_version": _schema_version(
                route_external_workload_evidence
            ),
            "trusted_route_environment_context_schema_version": _schema_version(
                trusted_route_environment_context
            ),
            "athlete_state_schema_version": _schema_version(
                athlete_state_context
            ),
            "athlete_state_binding_schema_version": _schema_version(
                athlete_state_binding
            ),
        },
        "athlete_state": athlete_state,
        "policy": {
            "requires_external_workload": True,
            "requires_downstream_usable_environment_context": True,
            "requires_explicit_athlete_state_binding_for_model_readiness": True,
            "readiness_projection_is_not_athlete_state": True,
            "accepts_environment_trusted_with_limitations": True,
            "component_promotion_allowed": False,
            "missing_or_withheld_input_blocks_model_readiness": True,
        },
        "scope": {
            "domain": "EXPECTED_RESPONSE_INPUT",
            "assembles_model_inputs": True,
            "estimates_expected_response": False,
            "estimates_expected_heart_rate": False,
            "infers_physiological_response": False,
            "infers_causal_environment_effect": False,
            "recommends_training_dose": False,
            "converts_ground_speed_to_boat_through_water_speed": False,
            "estimates_local_current_velocity": False,
            "promotes_component_trust": False,
            "mutates_input_evidence": False,
        },
        "routes": route_results,
    }


def build_route_expected_response_input_summary(
    expected_response_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the contract without per-segment payloads."""
    result = deepcopy(dict(expected_response_input))
    result["routes"] = []
    for route in _sequence_of_mappings(expected_response_input.get("routes")):
        compact = deepcopy(dict(route))
        compact.pop("segments", None)
        compact["segments_included"] = False
        result["routes"].append(compact)
    return result


def _build_route_result(
    *,
    route_key: tuple[int, int | None],
    workload_route: Mapping[str, Any] | None,
    environment_route: Mapping[str, Any] | None,
    athlete_state: Mapping[str, Any],
) -> dict[str, Any]:
    route_index, exercise_index = route_key

    workload_segments = _workload_items_by_order_index(workload_route)
    environment_segments = _items_by_order_index(environment_route, "segments")
    order_indices = _ordered_union_indices(workload_segments, environment_segments)

    segment_results: list[dict[str, Any]] = []
    workload_segment_count = 0
    environment_usable_segment_count = 0
    aligned_usable_segment_count = 0

    for order_index in order_indices:
        workload_segment = workload_segments.get(order_index)
        environment_segment = environment_segments.get(order_index)

        workload_available = isinstance(workload_segment, Mapping)
        if workload_available:
            workload_segment_count += 1

        environment_status = _string(
            environment_segment.get("status")
            if isinstance(environment_segment, Mapping)
            else None
        )
        environment_usable = bool(
            isinstance(environment_segment, Mapping)
            and environment_segment.get(
                "usable_for_downstream_environment_context"
            )
            is True
            and environment_status in ENVIRONMENT_USABLE_STATUSES
        )
        if environment_usable:
            environment_usable_segment_count += 1
        if workload_available and environment_usable:
            aligned_usable_segment_count += 1

        limitations = _unique_strings(
            _string_list(
                environment_segment.get("limitations")
                if isinstance(environment_segment, Mapping)
                else None
            )
        )

        segment_results.append(
            {
                "order_index": order_index,
                "workload_available": workload_available,
                "environment_status": environment_status or STATUS_UNAVAILABLE,
                "environment_usable": environment_usable,
                "aligned_for_expected_response_input": (
                    workload_available and environment_usable
                ),
                "external_workload": (
                    deepcopy(dict(workload_segment))
                    if workload_available
                    else None
                ),
                "environment_context": (
                    deepcopy(dict(environment_segment))
                    if environment_usable
                    else None
                ),
                "environment_context_withheld": bool(
                    isinstance(environment_segment, Mapping)
                    and not environment_usable
                ),
                "limitations": limitations,
            }
        )

    workload_available = bool(workload_segments)
    environment_available = bool(environment_segments)
    environment_route_status = _string(
        environment_route.get("status")
        if isinstance(environment_route, Mapping)
        else None
    )
    environment_route_usable = (
        environment_available
        and environment_route_status in ENVIRONMENT_USABLE_STATUSES
        and aligned_usable_segment_count == workload_segment_count
        and workload_segment_count > 0
    )
    athlete_bound = athlete_state.get("status") == ATHLETE_STATE_BOUND

    limitations = _unique_strings(
        [
            *_string_list(
                workload_route.get("limitations")
                if isinstance(workload_route, Mapping)
                else None
            ),
            *_string_list(
                environment_route.get("route_limitations")
                if isinstance(environment_route, Mapping)
                else None
            ),
            *_string_list(athlete_state.get("limitations")),
        ]
    )

    status, model_ready = _route_status(
        workload_available=workload_available,
        environment_available=environment_available,
        environment_route_usable=environment_route_usable,
        environment_route_status=environment_route_status,
        athlete_bound=athlete_bound,
        limitations=limitations,
    )

    if not workload_available:
        limitations = _append_unique(
            limitations,
            "TRUSTED_EXTERNAL_WORKLOAD_UNAVAILABLE",
        )
    if not environment_available:
        limitations = _append_unique(
            limitations,
            "TRUSTED_ENVIRONMENT_CONTEXT_UNAVAILABLE",
        )
    elif not environment_route_usable:
        limitations = _append_unique(
            limitations,
            "TRUSTED_ENVIRONMENT_CONTEXT_INCOMPLETE_FOR_WORKLOAD_SEGMENTS",
        )
    if not athlete_bound:
        limitations = _append_unique(
            limitations,
            "ATHLETE_STATE_NOT_EXPLICITLY_BOUND",
        )

    return {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "available": workload_available or environment_available,
        "status": status,
        "model_ready": model_ready,
        "segment_count": len(order_indices),
        "workload_segment_count": workload_segment_count,
        "environment_segment_count": len(environment_segments),
        "environment_usable_segment_count": environment_usable_segment_count,
        "aligned_usable_segment_count": aligned_usable_segment_count,
        "environment_route_status": environment_route_status,
        "athlete_state_status": athlete_state.get("status"),
        "limitations": limitations,
        "segments": segment_results,
    }


def _route_status(
    *,
    workload_available: bool,
    environment_available: bool,
    environment_route_usable: bool,
    environment_route_status: str | None,
    athlete_bound: bool,
    limitations: list[str],
) -> tuple[str, bool]:
    if not workload_available:
        return STATUS_UNAVAILABLE, False

    if environment_route_status == "WITHHELD":
        return STATUS_WITHHELD, False

    if not environment_available or not environment_route_usable or not athlete_bound:
        return STATUS_INCOMPLETE, False

    if limitations or environment_route_status == "TRUSTED_WITH_LIMITATIONS":
        return STATUS_READY_WITH_LIMITATIONS, True

    return STATUS_READY, True


def _athlete_state_component(
    athlete_state_context: Mapping[str, Any] | None,
    athlete_state_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    binding_status = _string(
        athlete_state_binding.get("status")
        if isinstance(athlete_state_binding, Mapping)
        else None
    )
    explicitly_bound = (
        isinstance(athlete_state_context, Mapping)
        and binding_status == ATHLETE_STATE_BOUND
    )

    if not explicitly_bound:
        return {
            "status": ATHLETE_STATE_NOT_BOUND,
            "available": isinstance(athlete_state_context, Mapping),
            "explicitly_bound": False,
            "binding": (
                deepcopy(dict(athlete_state_binding))
                if isinstance(athlete_state_binding, Mapping)
                else None
            ),
            "context": None,
            "limitations": ["ATHLETE_STATE_NOT_EXPLICITLY_BOUND"],
        }

    limitations = _unique_strings(
        [
            *_string_list(athlete_state_binding.get("limitations")),
            *_string_list(athlete_state_context.get("traceability_gaps")),
        ]
    )

    return {
        "status": ATHLETE_STATE_BOUND,
        "available": True,
        "explicitly_bound": True,
        "binding": deepcopy(dict(athlete_state_binding)),
        "context": deepcopy(dict(athlete_state_context)),
        "limitations": limitations,
    }


def _overall_status(routes: Sequence[Mapping[str, Any]]) -> str:
    if not routes:
        return STATUS_UNAVAILABLE

    statuses = {_string(route.get("status")) for route in routes}
    statuses.discard(None)

    if statuses == {STATUS_READY}:
        return STATUS_READY
    if statuses.issubset({STATUS_READY, STATUS_READY_WITH_LIMITATIONS}) and statuses:
        return STATUS_READY_WITH_LIMITATIONS
    if STATUS_INCOMPLETE in statuses:
        return STATUS_INCOMPLETE
    if STATUS_WITHHELD in statuses:
        return STATUS_WITHHELD
    return STATUS_UNAVAILABLE


def _route_lookup(
    source: Mapping[str, Any] | None,
) -> dict[tuple[int, int | None], Mapping[str, Any]]:
    result: dict[tuple[int, int | None], Mapping[str, Any]] = {}
    if not isinstance(source, Mapping):
        return result

    for position, route in enumerate(_sequence_of_mappings(source.get("routes"))):
        route_index = _integer(route.get("route_index"))
        if route_index is None:
            route_index = position
        exercise_index = _integer(route.get("exercise_index"))
        result[(route_index, exercise_index)] = route
    return result


def _ordered_union_route_keys(
    *lookups: Mapping[tuple[int, int | None], Mapping[str, Any]],
) -> list[tuple[int, int | None]]:
    keys: set[tuple[int, int | None]] = set()
    for lookup in lookups:
        keys.update(lookup.keys())
    return sorted(
        keys,
        key=lambda item: (
            item[0],
            item[1] if item[1] is not None else -1,
        ),
    )


def _items_by_order_index(
    route: Mapping[str, Any] | None,
    field: str,
) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    if not isinstance(route, Mapping):
        return result

    for position, item in enumerate(_sequence_of_mappings(route.get(field))):
        order_index = _integer(item.get("order_index"))
        if order_index is None:
            order_index = _integer(item.get("segment_index"))
        if order_index is None:
            order_index = position
        result[order_index] = item
    return result



def _workload_items_by_order_index(
    route: Mapping[str, Any] | None,
) -> dict[int, Mapping[str, Any]]:
    """Read the canonical external-workload route shape.

    route_external_workload_evidence exposes trusted per-segment payloads under
    ``observations``. ``segments`` remains accepted as a compatibility fallback
    for older/synthetic callers, but production workload evidence must not be
    treated as unavailable merely because it does not use that alias.
    """
    if not isinstance(route, Mapping):
        return {}

    observations = _items_by_order_index(route, "observations")
    if observations:
        return observations

    return _items_by_order_index(route, "segments")

def _ordered_union_indices(
    *lookups: Mapping[int, Mapping[str, Any]],
) -> list[int]:
    indices: set[int] = set()
    for lookup in lookups:
        indices.update(lookup.keys())
    return sorted(indices)


def _schema_version(source: Mapping[str, Any] | None) -> str | None:
    if not isinstance(source, Mapping):
        return None
    return _string(source.get("schema_version")) or _string(source.get("evidence_version"))


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in value:
        text = _string(item)
        if text is not None:
            result.append(text)
    return result


def _unique_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _string(value)
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _append_unique(values: list[str], value: str) -> list[str]:
    if value in values:
        return values
    return [*values, value]
