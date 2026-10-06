from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_TRUSTED = "TRUSTED"
STATUS_TRUSTED_WITH_LIMITATIONS = "TRUSTED_WITH_LIMITATIONS"
STATUS_WITHHELD = "WITHHELD"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_MIXED = "MIXED"

ENVIRONMENT_RIVER_INLAND = "RIVER_INLAND"
ENVIRONMENT_MARINE = "MARINE"
WATER_TRUSTED_STATUSES = {"DIRECT_RESOLVED", "CONTINUITY_SUPPORTED"}

HYDROLOGY_TRUSTED = "TRUSTED"
HYDROLOGY_TRUSTED_WITH_LIMITATIONS = "TRUSTED_WITH_LIMITATIONS"
HYDROLOGY_WITHHELD = "WITHHELD"
HYDROLOGY_NOT_APPLICABLE = "NOT_APPLICABLE"


def build_trusted_route_environment_context(
    route_environment_context_input: Mapping[str, Any] | None,
    route_water_environment_identity: Mapping[str, Any] | None,
    route_weather_sample_matching: Mapping[str, Any] | None,
    route_wind_context: Mapping[str, Any] | None,
    trusted_route_hydrology_context: Mapping[str, Any] | None,
    *,
    weather_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate already-established environmental evidence into a trusted projection.

    This is deliberately not a new truth engine.  Each component retains the
    trust ceiling established by its own upstream layer.  Weather and wind are
    accepted only with limitations until a dedicated representativeness layer
    exists.  Hydrology trust is inherited from V17 and can never be promoted
    here.  No current velocity, physiological response, or causal effect is
    inferred.
    """
    route_inputs = _route_lookup(route_environment_context_input)
    water_routes = _route_lookup(route_water_environment_identity)
    weather_routes = _route_lookup(route_weather_sample_matching)
    wind_routes = _route_lookup(route_wind_context)
    hydrology_routes = _route_lookup(trusted_route_hydrology_context)
    weather_samples = _weather_sample_lookup(weather_source)

    route_keys = _ordered_union_route_keys(
        route_inputs,
        water_routes,
        weather_routes,
        wind_routes,
        hydrology_routes,
    )

    route_results: list[dict[str, Any]] = []
    counts = _empty_status_counts()

    for route_key in route_keys:
        route_result = _build_route_result(
            route_key=route_key,
            route_input=route_inputs.get(route_key),
            water_route=water_routes.get(route_key),
            weather_route=weather_routes.get(route_key),
            wind_route=wind_routes.get(route_key),
            hydrology_route=hydrology_routes.get(route_key),
            weather_samples=weather_samples,
            weather_source=weather_source,
        )
        route_results.append(route_result)
        counts[route_result["status"]] += 1

    return {
        "provider": "PADDLETRAINER",
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _overall_status(route_results),
        "route_count": len(route_results),
        "trusted_route_count": counts[STATUS_TRUSTED],
        "trusted_with_limitations_route_count": counts[
            STATUS_TRUSTED_WITH_LIMITATIONS
        ],
        "withheld_route_count": counts[STATUS_WITHHELD],
        "unavailable_route_count": counts[STATUS_UNAVAILABLE],
        "not_applicable_route_count": counts[STATUS_NOT_APPLICABLE],
        "input_provenance": {
            "route_environment_context_input_schema_version": _schema_version(
                route_environment_context_input
            ),
            "route_water_environment_identity_schema_version": _schema_version(
                route_water_environment_identity
            ),
            "route_weather_sample_matching_schema_version": _schema_version(
                route_weather_sample_matching
            ),
            "route_wind_context_schema_version": _schema_version(
                route_wind_context
            ),
            "trusted_route_hydrology_context_schema_version": _schema_version(
                trusted_route_hydrology_context
            ),
            "weather_source_provider": _string(
                weather_source.get("provider")
                if isinstance(weather_source, Mapping)
                else None
            ),
            "weather_source_product": _string(
                weather_source.get("product")
                if isinstance(weather_source, Mapping)
                else None
            ),
            "weather_source_type": _string(
                weather_source.get("source_type")
                if isinstance(weather_source, Mapping)
                else None
            ),
        },
        "policy": {
            "trusted_water_identity_statuses": sorted(WATER_TRUSTED_STATUSES),
            "weather_match_available": STATUS_TRUSTED_WITH_LIMITATIONS,
            "wind_context_available": STATUS_TRUSTED_WITH_LIMITATIONS,
            "hydrology_trust_status_passthrough": True,
            "component_promotion_allowed": False,
            "segment_environment_usable_when_any_component_usable": True,
        },
        "scope": {
            "domain": "TRUSTED_ROUTE_ENVIRONMENT_CONTEXT",
            "aggregates_existing_trusted_or_limited_components": True,
            "resolves_new_provider_evidence": False,
            "estimates_weather_representativeness": False,
            "estimates_hydrology_representativeness": False,
            "promotes_component_trust": False,
            "preserves_component_limitations": True,
            "controls_downstream_environment_context_use": True,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "infers_physiological_response": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_trusted_route_environment_context_summary(
    trusted_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a compact route summary without per-segment environment payloads."""
    result = deepcopy(dict(trusted_context))
    result["routes"] = []
    for route in _sequence_of_mappings(trusted_context.get("routes")):
        compact = deepcopy(dict(route))
        compact.pop("segments", None)
        compact["segments_included"] = False
        result["routes"].append(compact)
    return result


def _build_route_result(
    *,
    route_key: tuple[int, int | None],
    route_input: Mapping[str, Any] | None,
    water_route: Mapping[str, Any] | None,
    weather_route: Mapping[str, Any] | None,
    wind_route: Mapping[str, Any] | None,
    hydrology_route: Mapping[str, Any] | None,
    weather_samples: Mapping[str, Mapping[str, Any]],
    weather_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    route_index, exercise_index = route_key

    route_segments = _sequence_of_mappings(
        route_input.get("segments") if isinstance(route_input, Mapping) else None
    )
    water_segments = _items_by_order_index(water_route, "segments")
    weather_matches = _items_by_order_index(weather_route, "matches")
    wind_segments = _items_by_order_index(wind_route, "segments")
    hydrology_context = (
        hydrology_route.get("trusted_context")
        if isinstance(hydrology_route, Mapping)
        and isinstance(hydrology_route.get("trusted_context"), Mapping)
        else None
    )
    hydrology_segments = _items_by_order_index(
        hydrology_context,
        "segments",
        fallback_key="segment_index",
    )

    order_indices = _route_order_indices(
        route_segments,
        water_segments,
        weather_matches,
        wind_segments,
        hydrology_segments,
    )

    segment_results: list[dict[str, Any]] = []
    counts = _empty_status_counts()
    component_usable_counts = {
        "water_identity": 0,
        "weather": 0,
        "wind": 0,
        "hydrology": 0,
    }

    for position, order_index in enumerate(order_indices):
        route_segment = _segment_by_order_index(route_segments, order_index, position)
        water = water_segments.get(order_index)
        weather = weather_matches.get(order_index)
        wind = wind_segments.get(order_index)
        hydrology = hydrology_segments.get(order_index)

        water_component = _water_component(water)
        weather_component = _weather_component(
            weather,
            weather_samples,
            weather_source,
        )
        wind_component = _wind_component(wind)
        hydrology_component = _hydrology_component(
            hydrology_route,
            hydrology,
        )

        components = {
            "water_identity": water_component,
            "weather": weather_component,
            "wind": wind_component,
            "hydrology": hydrology_component,
        }
        for name, component in components.items():
            if component.get("usable_for_downstream_environment_context") is True:
                component_usable_counts[name] += 1

        status = _aggregate_component_status(components.values())
        counts[status] += 1
        limitations = _unique_strings(
            item
            for component in components.values()
            for item in _string_list(component.get("limitations"))
        )
        trust_basis = _unique_strings(
            item
            for component in components.values()
            for item in _string_list(component.get("trust_basis"))
        )

        segment_results.append(
            {
                "order_index": order_index,
                "segment_index": _integer(
                    route_segment.get("segment_index")
                    if isinstance(route_segment, Mapping)
                    else None
                ),
                "status": status,
                "usable_for_downstream_environment_context": status
                in {STATUS_TRUSTED, STATUS_TRUSTED_WITH_LIMITATIONS},
                "usable_with_limitations": status == STATUS_TRUSTED_WITH_LIMITATIONS,
                "component_statuses": {
                    name: component.get("status")
                    for name, component in components.items()
                },
                "water_identity": water_component,
                "weather": weather_component,
                "wind": wind_component,
                "hydrology": hydrology_component,
                "trust_basis": trust_basis,
                "limitations": limitations,
            }
        )

    route_status = _route_status_from_segment_counts(counts, len(segment_results))
    hydrology_status = _string(
        hydrology_route.get("trust_status")
        if isinstance(hydrology_route, Mapping)
        else None
    )

    return {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "available": bool(segment_results),
        "status": route_status,
        "segment_count": len(segment_results),
        "trusted_segment_count": counts[STATUS_TRUSTED],
        "trusted_with_limitations_segment_count": counts[
            STATUS_TRUSTED_WITH_LIMITATIONS
        ],
        "withheld_segment_count": counts[STATUS_WITHHELD],
        "unavailable_segment_count": counts[STATUS_UNAVAILABLE],
        "not_applicable_segment_count": counts[STATUS_NOT_APPLICABLE],
        "downstream_usable_segment_count": (
            counts[STATUS_TRUSTED] + counts[STATUS_TRUSTED_WITH_LIMITATIONS]
        ),
        "water_identity_usable_segment_count": component_usable_counts[
            "water_identity"
        ],
        "weather_usable_segment_count": component_usable_counts["weather"],
        "wind_usable_segment_count": component_usable_counts["wind"],
        "hydrology_usable_segment_count": component_usable_counts["hydrology"],
        "hydrology_route_trust_status": hydrology_status,
        "environment_types": _string_list(
            water_route.get("environment_types")
            if isinstance(water_route, Mapping)
            else None
        ),
        "mixed_environment_route": bool(
            water_route.get("mixed_environment_route")
            if isinstance(water_route, Mapping)
            else False
        ),
        "route_limitations": _unique_strings(
            item
            for segment in segment_results
            for item in _string_list(segment.get("limitations"))
        ),
        "segments": segment_results,
    }


def _water_component(segment: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(segment, Mapping):
        return _component_unavailable("WATER_ENVIRONMENT_IDENTITY_UNAVAILABLE")

    environment_type = _string(segment.get("environment_type"))
    resolution_status = _string(segment.get("resolution_status"))
    cross_domain_conflict = segment.get("cross_domain_conflict") is True
    trusted = (
        resolution_status in WATER_TRUSTED_STATUSES
        and environment_type in {ENVIRONMENT_RIVER_INLAND, ENVIRONMENT_MARINE}
        and not cross_domain_conflict
    )

    if trusted:
        return {
            "status": STATUS_TRUSTED,
            "available": True,
            "applicable": True,
            "included": True,
            "usable_for_downstream_environment_context": True,
            "environment_type": environment_type,
            "resolution_status": resolution_status,
            "resolved_river_inland_identity": deepcopy(
                segment.get("resolved_river_inland_identity")
            ),
            "resolved_marine_region_identity": deepcopy(
                segment.get("resolved_marine_region_identity")
            ),
            "trust_basis": ["TRUSTED_WATER_ENVIRONMENT_IDENTITY_AVAILABLE"],
            "limitations": [],
        }

    return {
        "status": STATUS_WITHHELD,
        "available": True,
        "applicable": True,
        "included": False,
        "usable_for_downstream_environment_context": False,
        "environment_type": environment_type,
        "resolution_status": resolution_status,
        "resolved_river_inland_identity": None,
        "resolved_marine_region_identity": None,
        "trust_basis": ["WATER_ENVIRONMENT_IDENTITY_NOT_TRUSTED_RESOLVED"],
        "limitations": ["WATER_ENVIRONMENT_IDENTITY_WITHHELD"],
    }


def _weather_component(
    match: Mapping[str, Any] | None,
    weather_samples: Mapping[str, Mapping[str, Any]],
    weather_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(match, Mapping) or match.get("available") is not True:
        return _component_unavailable("WEATHER_SAMPLE_MATCH_UNAVAILABLE")

    sample_id = _string(match.get("matched_sample_id"))
    sample = weather_samples.get(sample_id) if sample_id is not None else None
    limitations = ["WEATHER_REPRESENTATIVENESS_NOT_SEPARATELY_ESTABLISHED"]
    source_type = _string(
        weather_source.get("source_type")
        if isinstance(weather_source, Mapping)
        else None
    )
    if source_type and "MODEL" in source_type.upper():
        limitations.append("MODELLED_GRIDDED_WEATHER")

    return {
        "status": STATUS_TRUSTED_WITH_LIMITATIONS,
        "available": True,
        "applicable": True,
        "included": True,
        "usable_for_downstream_environment_context": True,
        "match_status": _string(match.get("status")),
        "sample_id": sample_id,
        "absolute_time_delta_seconds": match.get("absolute_time_delta_seconds"),
        "surface_distance_to_sample_m": match.get("surface_distance_to_sample_m"),
        "sample": deepcopy(dict(sample)) if isinstance(sample, Mapping) else None,
        "trust_basis": [
            "WEATHER_SAMPLE_MATCH_AVAILABLE",
            "WEATHER_ACCEPTED_WITH_LIMITATIONS",
        ],
        "limitations": limitations,
    }


def _wind_component(segment: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(segment, Mapping) or segment.get("available") is not True:
        result = _component_unavailable("WIND_CONTEXT_UNAVAILABLE")
        if isinstance(segment, Mapping):
            result["source_status"] = _string(segment.get("status"))
        return result

    return {
        "status": STATUS_TRUSTED_WITH_LIMITATIONS,
        "available": True,
        "applicable": True,
        "included": True,
        "usable_for_downstream_environment_context": True,
        "source_status": _string(segment.get("status")),
        "headwind_component_mps": segment.get("headwind_component_mps"),
        "tailwind_component_mps": segment.get("tailwind_component_mps"),
        "crosswind_magnitude_mps": segment.get("crosswind_magnitude_mps"),
        "relative_air_velocity_along_course_mps": segment.get(
            "relative_air_velocity_along_course_mps"
        ),
        "relative_air_velocity_cross_course_mps": segment.get(
            "relative_air_velocity_cross_course_mps"
        ),
        "relative_air_speed_mps": segment.get("relative_air_speed_mps"),
        "trust_basis": [
            "ROUTE_WIND_CONTEXT_AVAILABLE",
            "DERIVED_WIND_CONTEXT_ACCEPTED_WITH_LIMITATIONS",
        ],
        "limitations": [
            "WIND_DERIVED_FROM_WEATHER_AND_GROUND_COURSE",
            "BOAT_THROUGH_WATER_SPEED_NOT_ESTABLISHED",
        ],
    }


def _hydrology_component(
    hydrology_route: Mapping[str, Any] | None,
    segment: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(hydrology_route, Mapping):
        return _component_unavailable("TRUSTED_HYDROLOGY_CONTEXT_UNAVAILABLE")

    trust_status = _string(hydrology_route.get("trust_status"))
    limitations = _string_list(hydrology_route.get("representativeness_limitations"))
    basis = _string_list(hydrology_route.get("trust_basis"))

    if trust_status == HYDROLOGY_NOT_APPLICABLE:
        return {
            "status": STATUS_NOT_APPLICABLE,
            "available": True,
            "applicable": False,
            "included": False,
            "usable_for_downstream_environment_context": False,
            "trust_basis": basis or ["HYDROLOGY_NOT_APPLICABLE"],
            "limitations": limitations,
            "context": None,
        }

    if trust_status == HYDROLOGY_WITHHELD:
        return {
            "status": STATUS_WITHHELD,
            "available": True,
            "applicable": True,
            "included": False,
            "usable_for_downstream_environment_context": False,
            "trust_basis": basis or ["HYDROLOGY_WITHHELD_UPSTREAM"],
            "limitations": limitations,
            "context": None,
        }

    if trust_status in {
        HYDROLOGY_TRUSTED,
        HYDROLOGY_TRUSTED_WITH_LIMITATIONS,
    }:
        if not isinstance(segment, Mapping):
            return {
                "status": STATUS_WITHHELD,
                "available": True,
                "applicable": True,
                "included": False,
                "usable_for_downstream_environment_context": False,
                "trust_basis": [
                    *basis,
                    "TRUSTED_HYDROLOGY_ROUTE_SEGMENT_CONTEXT_MISSING",
                ],
                "limitations": _unique_strings(
                    [*limitations, "HYDROLOGY_SEGMENT_CONTEXT_MISSING"]
                ),
                "context": None,
            }

        return {
            "status": trust_status,
            "available": True,
            "applicable": True,
            "included": True,
            "usable_for_downstream_environment_context": True,
            "trust_basis": basis,
            "limitations": limitations,
            "context": deepcopy(dict(segment)),
        }

    return _component_unavailable("HYDROLOGY_TRUST_STATUS_UNAVAILABLE")


def _component_unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": STATUS_UNAVAILABLE,
        "available": False,
        "applicable": True,
        "included": False,
        "usable_for_downstream_environment_context": False,
        "trust_basis": [reason],
        "limitations": [],
    }


def _aggregate_component_status(
    components: Sequence[Mapping[str, Any]] | Any,
) -> str:
    items = list(components)
    usable = [
        item for item in items
        if item.get("usable_for_downstream_environment_context") is True
    ]
    if usable:
        if (
            all(item.get("status") == STATUS_TRUSTED for item in usable)
            and all(
                item.get("status") in {STATUS_TRUSTED, STATUS_NOT_APPLICABLE}
                for item in items
            )
        ):
            return STATUS_TRUSTED
        return STATUS_TRUSTED_WITH_LIMITATIONS

    statuses = {_string(item.get("status")) for item in items}
    if STATUS_WITHHELD in statuses:
        return STATUS_WITHHELD
    if statuses and statuses <= {STATUS_NOT_APPLICABLE, STATUS_UNAVAILABLE}:
        if STATUS_UNAVAILABLE in statuses:
            return STATUS_UNAVAILABLE
        return STATUS_NOT_APPLICABLE
    return STATUS_UNAVAILABLE


def _route_status_from_segment_counts(
    counts: Mapping[str, int],
    segment_count: int,
) -> str:
    if segment_count <= 0:
        return STATUS_UNAVAILABLE
    if counts[STATUS_TRUSTED_WITH_LIMITATIONS] > 0:
        return STATUS_TRUSTED_WITH_LIMITATIONS
    if counts[STATUS_TRUSTED] > 0:
        if counts[STATUS_TRUSTED] == segment_count:
            return STATUS_TRUSTED
        return STATUS_TRUSTED_WITH_LIMITATIONS
    if counts[STATUS_WITHHELD] > 0:
        return STATUS_WITHHELD
    if counts[STATUS_UNAVAILABLE] > 0:
        return STATUS_UNAVAILABLE
    if counts[STATUS_NOT_APPLICABLE] == segment_count:
        return STATUS_NOT_APPLICABLE
    return STATUS_UNAVAILABLE


def _overall_status(routes: Sequence[Mapping[str, Any]]) -> str | None:
    statuses = {
        _string(route.get("status"))
        for route in routes
        if _string(route.get("status")) is not None
    }
    if not statuses:
        return None
    if len(statuses) == 1:
        return next(iter(statuses))
    return STATUS_MIXED


def _route_lookup(
    context: Mapping[str, Any] | None,
) -> dict[tuple[int, int | None], Mapping[str, Any]]:
    if not isinstance(context, Mapping):
        return {}
    result: dict[tuple[int, int | None], Mapping[str, Any]] = {}
    for position, route in enumerate(_sequence_of_mappings(context.get("routes"))):
        route_index = _integer(route.get("route_index"))
        if route_index is None:
            route_index = position
        result[(route_index, _integer(route.get("exercise_index")))] = route
    return result


def _ordered_union_route_keys(*lookups: Mapping[tuple[int, int | None], Any]) -> list[tuple[int, int | None]]:
    keys: list[tuple[int, int | None]] = []
    for lookup in lookups:
        for key in lookup:
            if key not in keys:
                keys.append(key)
    return keys


def _items_by_order_index(
    route: Mapping[str, Any] | None,
    field: str,
    *,
    fallback_key: str | None = None,
) -> dict[int, Mapping[str, Any]]:
    if not isinstance(route, Mapping):
        return {}
    result: dict[int, Mapping[str, Any]] = {}
    for position, item in enumerate(_sequence_of_mappings(route.get(field))):
        order_index = _integer(item.get("order_index"))
        if order_index is None and fallback_key is not None:
            order_index = _integer(item.get(fallback_key))
        if order_index is None:
            order_index = position
        result[order_index] = item
    return result


def _route_order_indices(
    route_segments: Sequence[Mapping[str, Any]],
    *lookups: Mapping[int, Mapping[str, Any]],
) -> list[int]:
    indices: list[int] = []
    for position, segment in enumerate(route_segments):
        order_index = _integer(segment.get("order_index"))
        if order_index is None:
            order_index = position
        if order_index not in indices:
            indices.append(order_index)
    for lookup in lookups:
        for order_index in lookup:
            if order_index not in indices:
                indices.append(order_index)
    return sorted(indices)


def _segment_by_order_index(
    route_segments: Sequence[Mapping[str, Any]],
    order_index: int,
    fallback_position: int,
) -> Mapping[str, Any]:
    for position, segment in enumerate(route_segments):
        parsed = _integer(segment.get("order_index"))
        parsed = parsed if parsed is not None else position
        if parsed == order_index:
            return segment
    if 0 <= fallback_position < len(route_segments):
        return route_segments[fallback_position]
    return {}


def _weather_sample_lookup(
    weather_source: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(weather_source, Mapping):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for sample in _sequence_of_mappings(weather_source.get("samples")):
        sample_id = _string(sample.get("sample_id"))
        if sample_id is not None:
            result[sample_id] = sample
    return result


def _schema_version(context: Mapping[str, Any] | None) -> Any:
    return context.get("schema_version") if isinstance(context, Mapping) else None


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if item is not None]


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _string(value)
        if text is not None and text not in result:
            result.append(text)
    return result


def _empty_status_counts() -> dict[str, int]:
    return {
        STATUS_TRUSTED: 0,
        STATUS_TRUSTED_WITH_LIMITATIONS: 0,
        STATUS_WITHHELD: 0,
        STATUS_NOT_APPLICABLE: 0,
        STATUS_UNAVAILABLE: 0,
    }


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
