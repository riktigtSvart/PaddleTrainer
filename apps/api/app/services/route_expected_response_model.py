from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any

SCHEMA_VERSION = "0.1"
MODEL_ID = "PADDLETRAINER_EXPECTED_RESPONSE_FOUNDATION"
MODEL_VERSION = "0.1.0"
SUPPORTED_INPUT_SCHEMA_VERSION = "0.1"
MODEL_NOT_CONFIGURED = "PHYSIOLOGICAL_RESPONSE_MODEL_NOT_CONFIGURED"
USABLE_STATUSES = {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"}


def build_route_expected_response_model(
    expected_response_input: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate the V24 model boundary without inventing a response estimator.

    V21 readiness is input readiness only. Even eligible inputs cannot produce
    physiological numbers until a separately versioned, validated model exists.
    The full input (not its compact summary) is committed by a canonical hash.
    Neither upstream trust nor component-specific state validity is promoted.
    """
    source = expected_response_input if isinstance(expected_response_input, Mapping) else {}
    input_hash = _hash(source) if source else None
    global_reasons = []
    if source.get("schema_version") != SUPPORTED_INPUT_SCHEMA_VERSION:
        global_reasons.append("EXPECTED_RESPONSE_INPUT_SCHEMA_UNSUPPORTED")
    if source and input_hash is None:
        global_reasons.append("EXPECTED_RESPONSE_INPUT_NOT_CANONICAL_JSON")
    global_reasons.extend(_athlete_state_reasons(source.get("athlete_state")))

    routes = []
    source_routes = source.get("routes")
    source_routes = source_routes if isinstance(source_routes, list) else []
    route_keys = [
        (route.get("route_index"), route.get("exercise_index"))
        for route in source_routes
        if isinstance(route, Mapping)
    ]
    # Identity ambiguity must block every instance, including the first one.
    for route in source_routes:
        if not isinstance(route, Mapping):
            global_reasons.append("EXPECTED_RESPONSE_INPUT_ROUTE_INVALID")
    global_reasons = list(dict.fromkeys(global_reasons))
    for route in source_routes:
        if not isinstance(route, Mapping):
            continue
        reasons = list(global_reasons)
        key = (route.get("route_index"), route.get("exercise_index"))
        if not _index(key[0]) or (key[1] is not None and not _index(key[1])):
            reasons.append("ROUTE_IDENTITY_INVALID")
        elif route_keys.count(key) > 1:
            reasons.append("ROUTE_IDENTITY_AMBIGUOUS")
        if route.get("status") not in {"READY", "READY_WITH_LIMITATIONS"}:
            reasons.append("EXPECTED_RESPONSE_INPUT_NOT_READY")
        if route.get("model_ready") is not True:
            reasons.append("UPSTREAM_MODEL_INPUT_NOT_READY")
        if route.get("athlete_state_status") != "BOUND":
            reasons.append("ROUTE_ATHLETE_STATE_NOT_BOUND")
        if route.get("environment_route_status") not in USABLE_STATUSES:
            reasons.append("ROUTE_ENVIRONMENT_NOT_USABLE")

        segments = route.get("segments")
        segments = segments if isinstance(segments, list) else []
        segment_results = [_segment_result(segment) for segment in segments]
        orders = [item["order_index"] for item in segment_results]
        if any(not _index(order) for order in orders):
            reasons.append("SEGMENT_IDENTITY_INVALID")
        elif len(orders) != len(set(orders)):
            reasons.append("SEGMENT_IDENTITY_AMBIGUOUS")
        if not segments:
            reasons.append("FULL_EXPECTED_RESPONSE_INPUT_SEGMENTS_REQUIRED")
        if any(not item["input_eligible"] for item in segment_results):
            reasons.append("SEGMENT_INPUT_NOT_USABLE")
        workload_count = sum(item["workload_available"] for item in segment_results)
        aligned_count = sum(item["input_eligible"] for item in segment_results)
        for count_key, actual in (
            ("segment_count", len(segments)),
            ("workload_segment_count", workload_count),
            ("aligned_usable_segment_count", aligned_count),
        ):
            declared = route.get(count_key)
            if not _index(declared) or declared != actual:
                reasons.append("EXPECTED_RESPONSE_INPUT_SEGMENT_COUNTS_INCONSISTENT")
                break

        reasons = list(dict.fromkeys(reasons))
        eligible = not reasons
        routes.append(
            {
                "route_index": deepcopy(route.get("route_index")),
                "exercise_index": deepcopy(route.get("exercise_index")),
                "input_status": route.get("status"),
                "input_eligible": eligible,
                "input_blocking_reasons": reasons,
                "status": "NOT_ESTIMATED" if eligible else "WITHHELD",
                "segment_count": len(segments),
                "aligned_usable_segment_count": aligned_count,
                "limitations": _strings(route.get("limitations")),
                "expected_response": {
                    "status": "WITHHELD",
                    "available": False,
                    "value": None,
                    "unit": None,
                    "withheld_reasons": [*reasons, MODEL_NOT_CONFIGURED],
                    "uncertainty": {
                        "status": "NOT_ESTABLISHED",
                        "interval": None,
                        "confidence_level": None,
                    },
                },
                "segments": segment_results,
            }
        )

    eligible_count = sum(route["input_eligible"] for route in routes)
    athlete_state = source.get("athlete_state")
    athlete_state = athlete_state if isinstance(athlete_state, Mapping) else {}
    result = {
        "provider": "PADDLETRAINER",
        "schema_version": SCHEMA_VERSION,
        "available": bool(routes),
        "response_available": False,
        "status": ("NOT_ESTIMATED" if eligible_count else "WITHHELD") if routes else "UNAVAILABLE",
        "model": {
            "model_id": MODEL_ID,
            "model_version": MODEL_VERSION,
            "stage": "FOUNDATION_ONLY",
            "response_domain": "PHYSIOLOGICAL_RESPONSE",
            "estimator_configured": False,
            "calibration_available": False,
            "numeric_output_authorized": False,
        },
        "route_count": len(routes),
        "input_eligible_route_count": eligible_count,
        "input_blocked_route_count": len(routes) - eligible_count,
        "estimated_route_count": 0,
        "response_withheld_route_count": len(routes),
        "input_provenance": {
            "expected_response_input_schema_version": source.get("schema_version"),
            "expected_response_input_hash": input_hash,
            "upstream_input_provenance": deepcopy(source.get("input_provenance")),
            "athlete_state_binding": _binding_provenance(athlete_state.get("binding")),
        },
        "limitations": [MODEL_NOT_CONFIGURED, *global_reasons],
        "policy": {
            "full_input_required": True,
            "input_readiness_is_not_response_model_validity": True,
            "verifiable_non_future_temporal_binding_required": True,
            "missing_model_blocks_numeric_output": True,
            "partial_route_prediction_allowed": False,
        },
        "scope": {
            "domain": "EXPECTED_RESPONSE_MODEL_FOUNDATION",
            "estimates_expected_response": False,
            "estimates_expected_heart_rate": False,
            "infers_causal_environment_effect": False,
            "recommends_training_dose": False,
            "converts_ground_speed_to_boat_through_water_speed": False,
            "estimates_local_current_velocity": False,
            "promotes_component_trust": False,
            "establishes_component_specific_state_validity": False,
            "uses_actual_response_for_prediction": False,
            "persists_model_decisions": False,
            "mutates_input_evidence": False,
        },
        "routes": routes,
    }
    result["decision_hash"] = _hash(result)
    return result


def build_route_expected_response_model_summary(
    expected_response_model: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep the full decision commitment while omitting segment diagnostics."""
    result = deepcopy(dict(expected_response_model))
    for route in result.get("routes", []):
        route.pop("segments", None)
        route["segments_included"] = False
    return result


def _segment_result(segment: Any) -> dict[str, Any]:
    segment = segment if isinstance(segment, Mapping) else {}
    workload_available = segment.get("workload_available") is True and isinstance(
        segment.get("external_workload"), Mapping
    )
    environment = segment.get("environment_context")
    environment_usable = (
        segment.get("environment_usable") is True
        and segment.get("environment_context_withheld") is not True
        and segment.get("environment_status") in USABLE_STATUSES
        and isinstance(environment, Mapping)
        and environment.get("status") in USABLE_STATUSES
        and environment.get("usable_for_downstream_environment_context") is True
    )
    reasons = []
    if not workload_available:
        reasons.append("SEGMENT_EXTERNAL_WORKLOAD_UNAVAILABLE")
    if not environment_usable:
        reasons.append("SEGMENT_ENVIRONMENT_NOT_USABLE")
    if segment.get("aligned_for_expected_response_input") is not True:
        reasons.append("SEGMENT_INPUT_NOT_ALIGNED")
    return {
        "order_index": deepcopy(segment.get("order_index")),
        "workload_available": workload_available,
        "input_eligible": not reasons,
        "input_blocking_reasons": reasons,
        "limitations": _strings(segment.get("limitations")),
    }


def _binding_provenance(binding: Any) -> dict[str, Any] | None:
    if not isinstance(binding, Mapping):
        return None
    return {
        key: deepcopy(binding.get(key))
        for key in (
            "schema_version",
            "status",
            "target_timestamp",
            "selected_snapshot",
            "policy",
            "binding_basis",
            "limitations",
            "source_adapter",
            "live_source",
        )
    }


def _athlete_state_reasons(state: Any) -> list[str]:
    if not isinstance(state, Mapping) or (
        state.get("status") != "BOUND"
        or state.get("explicitly_bound") is not True
        or state.get("available") is not True
        or not isinstance(state.get("context"), Mapping)
    ):
        return ["ATHLETE_STATE_NOT_EXPLICITLY_BOUND"]
    binding = state.get("binding")
    if not isinstance(binding, Mapping) or (
        binding.get("status") != "BOUND" or binding.get("bound") is not True
    ):
        return ["ATHLETE_STATE_TEMPORAL_BINDING_NOT_VERIFIABLE"]
    snapshot = binding.get("selected_snapshot")
    policy = binding.get("policy")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    policy = policy if isinstance(policy, Mapping) else {}
    target = _timestamp(binding.get("target_timestamp"))
    timestamp = _timestamp(snapshot.get("state_timestamp"))
    max_age = policy.get("max_carry_forward_seconds")
    if target is None or timestamp is None or not _finite_nonnegative(max_age):
        return ["ATHLETE_STATE_TEMPORAL_BINDING_NOT_VERIFIABLE"]
    age = (target - timestamp).total_seconds()
    if age < 0:
        return ["ATHLETE_STATE_IS_FUTURE"]
    if age > max_age:
        return ["ATHLETE_STATE_OUTSIDE_CARRY_FORWARD_POLICY"]
    declared_age = snapshot.get("age_seconds")
    if not _finite_nonnegative(declared_age) or not math.isclose(declared_age, age, abs_tol=1e-6):
        return ["ATHLETE_STATE_BINDING_AGE_INCONSISTENT"]
    context_hash = _hash(state["context"])
    if context_hash is None or context_hash != _hash(binding.get("athlete_state_context")):
        return ["ATHLETE_STATE_BOUND_CONTEXT_MISMATCH"]
    return []


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _index(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _strings(value: Any) -> list[str]:
    return (
        list(dict.fromkeys(item for item in value if isinstance(item, str)))
        if isinstance(value, list)
        else []
    )


def _json_default(value: Any) -> str:
    # Match API date serialization, but never silently stringify unknown objects.
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Unsupported evidence type: {type(value).__name__}")


def _hash(value: Any) -> str | None:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
