"""Explain existing route input gates without fetching or promoting evidence."""

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
from typing import Any

COMPONENTS = ("water_identity", "weather", "wind", "hydrology")


def build_route_input_diagnostics(
    input_route: Mapping[str, Any],
    model_route: Mapping[str, Any],
    windows: list[Mapping[str, Any]],
    *,
    trusted_environment: Mapping[str, Any] | None = None,
    provider_selection: Mapping[str, Any] | None = None,
    weather_source: Mapping[str, Any] | None = None,
    audit_source_hash: str | None = None,
    detail_limit: int = 25,
) -> dict[str, Any]:
    """Counts cover all rows; packets are bounded, with explicit truncation.

    Component absence is reported even where the existing aggregate accepts a
    partial context with limitations. No new all-components-required rule is
    invented. Forecast issue/availability proof is not implemented in V24.7.
    Consequently these supplied contexts never authorize pre-exercise features.
    """
    if type(detail_limit) is not int or not 1 <= detail_limit <= 100:
        raise ValueError("detail_limit must be an integer from 1 to 100")
    key = (input_route.get("route_index"), input_route.get("exercise_index"))
    environment_routes = [
        r
        for r in _items(_mapping(trusted_environment).get("routes"))
        if (r.get("route_index"), r.get("exercise_index")) == key
    ]
    environment_route = environment_routes[0] if len(environment_routes) == 1 else {}
    env_by_order = _lookup(_items(environment_route.get("segments")))
    model_by_order = _lookup(_items(model_route.get("segments")))
    input_by_order = _lookup(_items(input_route.get("segments")))
    counts: Counter[str] = Counter()
    component_counts = {name: Counter() for name in COMPONENTS}
    examples: dict[str, list[Any]] = defaultdict(list)
    binding_reasons = set()
    excluded, details = [], []
    for window in windows:
        order = window.get("order_index")
        source = _unique(input_by_order, order)
        model = _unique(model_by_order, order)
        environment = _unique(env_by_order, order)
        if trusted_environment is None:
            environment = _mapping(source.get("environment_context"))
        reasons = list(model.get("input_blocking_reasons", []))
        if not model:
            reasons.append("MODEL_SEGMENT_IDENTITY_MISSING_OR_AMBIGUOUS")
        if not source:
            reasons.append("INPUT_SEGMENT_IDENTITY_MISSING_OR_AMBIGUOUS")
        if trusted_environment is not None:
            if len(environment_routes) != 1:
                reasons.append("ENVIRONMENT_ROUTE_IDENTITY_MISSING_OR_AMBIGUOUS")
            elif not environment:
                reasons.append("ENVIRONMENT_SEGMENT_IDENTITY_MISSING_OR_AMBIGUOUS")
            elif (
                source.get("environment_usable") is True
                and source.get("environment_context") != environment
            ):
                reasons.append("ENVIRONMENT_SEGMENT_SOURCE_MISMATCH")
        binding_reasons.update(reason for reason in reasons if reason.startswith("ENVIRONMENT_"))
        coverage = window.get("grid_coverage_status")
        if coverage != "COMPLETE":
            reasons.append(
                "HR_WINDOW_INVALID" if coverage == "INVALID_WINDOW" else "HR_LABEL_GRID_INCOMPLETE"
            )
            excluded.append(
                {
                    k: deepcopy(window.get(k))
                    for k in (
                        "order_index",
                        "start_exercise_elapsed_ms",
                        "end_exercise_elapsed_ms",
                        "grid_coverage_status",
                        "expected_grid_slot_count",
                        "positive_finite_grid_sample_count",
                        "missing_or_invalid_grid_slot_count",
                        "hr_signal_diagnostics",
                    )
                }
            )
        temporal = _mapping(window.get("temporal_context"))
        if temporal.get("status") == "WITHHELD":
            reasons.append("TEMPORAL_WINDOW_SUPPORT_UNAVAILABLE")
        components = {}
        for name in COMPONENTS:
            component = _mapping(environment.get(name))
            status = component.get("status", "COMPONENT_DETAIL_NOT_PROVIDED")
            if not isinstance(status, str):
                status = "COMPONENT_STATUS_INVALID"
            component_counts[name][status] += 1
            components[name] = _component_detail(component)
        reasons = list(dict.fromkeys(reasons))
        for reason in reasons:
            counts[reason] += 1
            if len(examples[reason]) < 3:
                examples[reason].append(order)
        details.append(
            {
                "order_index": order,
                "workload_available": source.get("workload_available") is True,
                "environment_status": environment.get("status", source.get("environment_status")),
                "upstream_segment_input_eligible": model.get("input_eligible") is True,
                "existing_preparation_candidate": window.get("candidate_for_data_preparation")
                is True,
                "blocking_reasons": reasons,
                "components": components,
            }
        )
    source_hash = _hash(
        {
            "input_route": input_route,
            "model_route": model_route,
            "windows": windows,
            "trusted_environment": trusted_environment,
            "provider_selection": provider_selection,
            "weather_source": weather_source,
            "owner_bound_audit_source_hash": audit_source_hash,
        }
    )
    result = {
        "schema_version": "0.1",
        "diagnostics_version": "0.1.0",
        "status": "DESCRIPTIVE_INPUT_DIAGNOSTICS" if source_hash else "WITHHELD",
        "source_hash": source_hash,
        "owner_bound_audit_source_hash": audit_source_hash,
        "route_index": key[0],
        "exercise_index": key[1],
        "route_blocking_reasons": deepcopy(model_route.get("input_blocking_reasons", [])),
        "upstream_input_state": {
            k: deepcopy(input_route.get(k))
            for k in (
                "status",
                "model_ready",
                "athlete_state_status",
                "environment_route_status",
                "segment_count",
                "workload_segment_count",
                "environment_usable_segment_count",
                "aligned_usable_segment_count",
            )
        },
        "segment_count": len(windows),
        "environment_detail_binding_verified": trusted_environment is not None
        and len(environment_routes) == 1
        and not binding_reasons
        and source_hash is not None,
        "binding_blocking_reasons": sorted(binding_reasons),
        "segment_blocking_reason_counts": dict(sorted(counts.items())),
        "blocking_reason_examples": dict(sorted(examples.items())),
        "component_status_counts": {
            name: dict(sorted(c.items())) for name, c in component_counts.items()
        },
        "provider_selection": deepcopy(dict(provider_selection or {})),
        "component_source_selection": _selection_status(provider_selection),
        "environment_aggregation_policy": "EXISTING_UPSTREAM_PARTIAL_CONTEXT_WITH_LIMITATIONS",
        "weather_feature_availability": _weather_availability(weather_source),
        "pre_exercise_feature_authorized": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "excluded_hr_windows": _packet(excluded, detail_limit),
        "segment_details": _packet(details, detail_limit),
    }
    result["decision_hash"] = _hash(result)
    return result


def _component_detail(component: Mapping[str, Any]) -> dict[str, Any]:
    # No invented distance, timestamp or identity when the upstream layer lacks it.
    return {
        key: deepcopy(component.get(key))
        for key in (
            "status",
            "available",
            "applicable",
            "usable_for_downstream_environment_context",
            "trust_basis",
            "limitations",
            "source_status",
            "environment_type",
            "resolution_status",
            "resolved_river_inland_identity",
            "resolved_marine_region_identity",
            "sample_id",
            "absolute_time_delta_seconds",
            "surface_distance_to_sample_m",
            "sample",
            "context",
        )
        if key in component
    }


def _weather_availability(source: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _mapping(source)
    provider, product, kind = (source.get(k) for k in ("provider", "product", "source_type"))
    descriptor = " ".join(str(v).upper() for v in (provider, product, kind) if v)
    status = (
        "NOT_PROVIDED"
        if not source
        else "SYNTHETIC_TEST_CONTEXT"
        if "SYNTHETIC" in descriptor or provider == "INSPECT_QUERY"
        else "RETROSPECTIVE_HISTORICAL_CONTEXT"
        if "HISTORICAL" in descriptor or "REANALYSIS" in descriptor
        else "PRE_EXERCISE_AVAILABILITY_NOT_ESTABLISHED"
    )
    return {
        "status": status,
        "provider": provider,
        "product": product,
        "source_type": kind,
        "forecast_issue_time_verified": False,
        "available_before_exercise_verified": False,
        "pre_exercise_feature_authorized": False,
        "limitations": ["FORECAST_AVAILABILITY_PROOF_NOT_IMPLEMENTED"],
    }


def _selection_status(selection: Mapping[str, Any] | None) -> dict[str, str]:
    if selection is None:
        return {name: "SELECTION_NOT_PROVIDED" for name in COMPONENTS}
    weather = bool(selection.get("weather_provider"))
    synthetic = selection.get("synthetic_wind_selected") is True
    return {
        "water_identity": "SELECTED"
        if any(
            selection.get(k)
            for k in (
                "waterbody_provider",
                "water_surface_provider",
                "marine_surface_provider",
            )
        )
        else "NOT_SELECTED",
        "weather": "SYNTHETIC_TEST" if synthetic else "SELECTED" if weather else "NOT_SELECTED",
        "wind": "SYNTHETIC_TEST"
        if synthetic
        else "DERIVED_FROM_SELECTED_WEATHER"
        if weather
        else "NOT_SELECTED",
        "hydrology": "SELECTED" if selection.get("hydrology_provider") else "NOT_SELECTED",
    }


def _packet(items: list[Any], limit: int) -> dict[str, Any]:
    return {
        "total_count": len(items),
        "returned_count": min(len(items), limit),
        "truncated": len(items) > limit,
        "items": items[:limit],
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Mapping[str, Any]]:
    return [v for v in value if isinstance(v, Mapping)] if isinstance(value, list) else []


def _lookup(items: list[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    result: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        order = item.get("order_index")
        if type(order) is int and order >= 0:
            result[order].append(item)
    return result


def _unique(lookup: Mapping[int, list[Mapping[str, Any]]], key: Any) -> Mapping[str, Any]:
    values = lookup.get(key, []) if type(key) is int and key >= 0 else []
    return values[0] if len(values) == 1 else {}


def _hash(value: Any) -> str | None:
    def default(item: Any) -> str:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError("Noncanonical source")

    try:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
                default=default,
            ).encode()
        ).hexdigest()
    except (ValueError, TypeError, OverflowError):
        return None
