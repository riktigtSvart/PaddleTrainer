from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "0.1"

WATERBODY_IDENTITY_STATUS = "UNRESOLVED"
ROUTE_CHOICE_CONTEXT_STATUS = "UNOBSERVED"


def _integer(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if (
        isinstance(value, float)
        and value.is_integer()
    ):
        return int(value)

    return None


def _route_key(
    route_index: int,
    exercise_index: int | None,
) -> tuple[int, int | None]:
    return (
        route_index,
        exercise_index,
    )


def _routes_by_key(
    evidence: dict[str, Any] | None,
) -> dict[
    tuple[int, int | None],
    dict[str, Any],
]:
    result = {}

    if not isinstance(
        evidence,
        dict,
    ):
        return result

    for route_position, route in enumerate(
        evidence.get(
            "routes"
        )
        or []
    ):
        if not isinstance(
            route,
            dict,
        ):
            continue

        route_index = _integer(
            route.get(
                "route_index"
            )
        )

        if route_index is None:
            route_index = route_position

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

        result[
            _route_key(
                route_index,
                exercise_index,
            )
        ] = route

    return result


def _items_by_order_index(
    route: dict[str, Any] | None,
    field_name: str,
) -> dict[int, dict[str, Any]]:
    result = {}

    if not isinstance(
        route,
        dict,
    ):
        return result

    for item in (
        route.get(
            field_name
        )
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        order_index = _integer(
            item.get(
                "order_index"
            )
        )

        if order_index is None:
            continue

        result[
            order_index
        ] = item

    return result


def _catalog_weather_samples(
    weather_source: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(
        weather_source,
        dict,
    ):
        return []

    by_id = {}

    for sample in (
        weather_source.get(
            "samples"
        )
        or []
    ):
        if not isinstance(
            sample,
            dict,
        ):
            continue

        sample_id = sample.get(
            "sample_id"
        )

        if not isinstance(
            sample_id,
            str,
        ) or not sample_id:
            continue

        by_id[
            sample_id
        ] = deepcopy(
            sample
        )

    return [
        by_id[key]
        for key in sorted(
            by_id
        )
    ]


def _catalog_hydrology_measurements(
    hydrology_source: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(
        hydrology_source,
        dict,
    ):
        return []

    by_id = {}

    for measurement in (
        hydrology_source.get(
            "measurements"
        )
        or []
    ):
        if not isinstance(
            measurement,
            dict,
        ):
            continue

        measurement_id = (
            measurement.get(
                "measurement_id"
            )
        )

        if not isinstance(
            measurement_id,
            str,
        ) or not measurement_id:
            continue

        by_id[
            measurement_id
        ] = deepcopy(
            measurement
        )

    return [
        by_id[key]
        for key in sorted(
            by_id
        )
    ]


def _hydrology_metric_record(
    metric: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(
        metric,
        dict,
    ):
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "measurement_id": None,
            "observed_at": None,
            "absolute_time_delta_seconds": None,
            "value": None,
            "unit": None,
            "data_type_code": None,
            "data_quality_code": None,
            "field_quality_code": None,
        }

    return {
        "available": (
            metric.get(
                "available"
            )
            is True
        ),
        "status": (
            metric.get(
                "status"
            )
        ),
        "measurement_id": (
            metric.get(
                "measurement_id"
            )
        ),
        "observed_at": (
            metric.get(
                "observed_at"
            )
        ),
        "absolute_time_delta_seconds": (
            metric.get(
                "absolute_time_delta_seconds"
            )
        ),
        "value": (
            metric.get(
                "value"
            )
        ),
        "unit": (
            metric.get(
                "unit"
            )
        ),
        "data_type_code": (
            metric.get(
                "data_type_code"
            )
        ),
        "data_quality_code": (
            metric.get(
                "data_quality_code"
            )
        ),
        "field_quality_code": (
            metric.get(
                "field_quality_code"
            )
        ),
    }


def _record_id(
    *,
    session_external_id: str | None,
    route_index: int,
    exercise_index: int | None,
    start_waypoint_index: int | None,
    end_waypoint_index: int | None,
    start_elapsed_ms: int | None,
    end_elapsed_ms: int | None,
) -> str:
    parts = [
        session_external_id
        or "SESSION_UNKNOWN",
        f"r{route_index}",
        (
            f"e{exercise_index}"
            if exercise_index
            is not None
            else "eUNKNOWN"
        ),
        (
            f"wp{start_waypoint_index}"
            if start_waypoint_index
            is not None
            else "wpUNKNOWN"
        ),
        (
            f"wp{end_waypoint_index}"
            if end_waypoint_index
            is not None
            else "wpUNKNOWN"
        ),
        (
            f"t{start_elapsed_ms}"
            if start_elapsed_ms
            is not None
            else "tUNKNOWN"
        ),
        (
            f"t{end_elapsed_ms}"
            if end_elapsed_ms
            is not None
            else "tUNKNOWN"
        ),
    ]

    return ":".join(
        parts
    )


def build_route_environment_evidence_record(
    *,
    session_external_id: str | None,
    route_environment_context_input: dict[str, Any],
    route_external_workload_evidence: dict[str, Any],
    route_weather_sample_matching: dict[str, Any] | None = None,
    route_wind_context: dict[str, Any] | None = None,
    weather_source: dict[str, Any] | None = None,
    route_hydrology_context: dict[str, Any] | None = None,
    hydrology_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a persistence-ready evidence record without causal inference.

    The record preserves actual traversed geometry and environmental
    evidence. It does not assume that upstream and downstream traversals
    use the same flow line, or that their speed difference identifies
    local current velocity.
    """
    environment_routes = _routes_by_key(
        route_environment_context_input
    )
    external_routes = _routes_by_key(
        route_external_workload_evidence
    )
    weather_match_routes = _routes_by_key(
        route_weather_sample_matching
    )
    wind_routes = _routes_by_key(
        route_wind_context
    )
    hydrology_routes = _routes_by_key(
        route_hydrology_context
    )

    route_records = []

    for key, environment_route in (
        environment_routes.items()
    ):
        (
            route_index,
            exercise_index,
        ) = key

        external_by_order = (
            _items_by_order_index(
                external_routes.get(
                    key
                ),
                "observations",
            )
        )
        weather_by_order = (
            _items_by_order_index(
                weather_match_routes.get(
                    key
                ),
                "matches",
            )
        )
        wind_by_order = (
            _items_by_order_index(
                wind_routes.get(
                    key
                ),
                "segments",
            )
        )
        hydrology_by_order = (
            _items_by_order_index(
                hydrology_routes.get(
                    key
                ),
                "segments",
            )
        )

        segment_records = []

        for segment in (
            environment_route.get(
                "segments"
            )
            or []
        ):
            if not isinstance(
                segment,
                dict,
            ):
                continue

            order_index = _integer(
                segment.get(
                    "order_index"
                )
            )

            if order_index is None:
                continue

            external = (
                external_by_order.get(
                    order_index
                )
                or {}
            )
            weather_match = (
                weather_by_order.get(
                    order_index
                )
                or {}
            )
            wind = (
                wind_by_order.get(
                    order_index
                )
                or {}
            )
            hydrology = (
                hydrology_by_order.get(
                    order_index
                )
                or {}
            )

            start_waypoint_index = (
                _integer(
                    segment.get(
                        "start_waypoint_index"
                    )
                )
            )
            end_waypoint_index = (
                _integer(
                    segment.get(
                        "end_waypoint_index"
                    )
                )
            )
            start_elapsed_ms = (
                _integer(
                    segment.get(
                        "start_exercise_elapsed_ms"
                    )
                )
            )
            end_elapsed_ms = (
                _integer(
                    segment.get(
                        "end_exercise_elapsed_ms"
                    )
                )
            )

            segment_records.append(
                {
                    "record_id": (
                        _record_id(
                            session_external_id=(
                                session_external_id
                            ),
                            route_index=(
                                route_index
                            ),
                            exercise_index=(
                                exercise_index
                            ),
                            start_waypoint_index=(
                                start_waypoint_index
                            ),
                            end_waypoint_index=(
                                end_waypoint_index
                            ),
                            start_elapsed_ms=(
                                start_elapsed_ms
                            ),
                            end_elapsed_ms=(
                                end_elapsed_ms
                            ),
                        )
                    ),
                    "order_index": (
                        order_index
                    ),
                    "source_locator": {
                        "source_segment_index": (
                            _integer(
                                segment.get(
                                    "segment_index"
                                )
                            )
                        ),
                        "start_waypoint_index": (
                            start_waypoint_index
                        ),
                        "end_waypoint_index": (
                            end_waypoint_index
                        ),
                        "start_exercise_elapsed_ms": (
                            start_elapsed_ms
                        ),
                        "end_exercise_elapsed_ms": (
                            end_elapsed_ms
                        ),
                        "start_timestamp": (
                            segment.get(
                                "start_timestamp"
                            )
                        ),
                        "midpoint_timestamp": (
                            segment.get(
                                "midpoint_timestamp"
                            )
                        ),
                        "end_timestamp": (
                            segment.get(
                                "end_timestamp"
                            )
                        ),
                    },
                    "actual_path_evidence": {
                        "start_position": deepcopy(
                            segment.get(
                                "start_position"
                            )
                        ),
                        "end_position": deepcopy(
                            segment.get(
                                "end_position"
                            )
                        ),
                        "surface_distance_m": (
                            external.get(
                                "surface_distance_m"
                            )
                        ),
                        "movement_bearing_deg": (
                            segment.get(
                                "movement_bearing_deg"
                            )
                        ),
                        "position_status": (
                            segment.get(
                                "position_status"
                            )
                        ),
                    },
                    "external_motion": {
                        "gps_ground_speed_mps": (
                            segment.get(
                                "gps_ground_speed_mps"
                            )
                        ),
                        "ground_speed_change_rate_mps2": (
                            segment.get(
                                "ground_speed_change_rate_mps2"
                            )
                        ),
                        "cumulative_trusted_surface_distance_m": (
                            external.get(
                                "cumulative_trusted_surface_distance_m"
                            )
                        ),
                    },
                    "weather": {
                        "match_available": (
                            weather_match.get(
                                "available"
                            )
                            is True
                        ),
                        "match_status": (
                            weather_match.get(
                                "status"
                            )
                        ),
                        "sample_id": (
                            weather_match.get(
                                "matched_sample_id"
                            )
                        ),
                        "absolute_time_delta_seconds": (
                            weather_match.get(
                                "absolute_time_delta_seconds"
                            )
                        ),
                        "surface_distance_to_sample_m": (
                            weather_match.get(
                                "surface_distance_to_sample_m"
                            )
                        ),
                    },
                    "wind_physics": {
                        "available": (
                            wind.get(
                                "available"
                            )
                            is True
                        ),
                        "status": (
                            wind.get(
                                "status"
                            )
                        ),
                        "headwind_component_mps": (
                            wind.get(
                                "headwind_component_mps"
                            )
                        ),
                        "tailwind_component_mps": (
                            wind.get(
                                "tailwind_component_mps"
                            )
                        ),
                        "crosswind_magnitude_mps": (
                            wind.get(
                                "crosswind_magnitude_mps"
                            )
                        ),
                        "relative_air_velocity_along_course_mps": (
                            wind.get(
                                "relative_air_velocity_along_course_mps"
                            )
                        ),
                        "relative_air_velocity_cross_course_mps": (
                            wind.get(
                                "relative_air_velocity_cross_course_mps"
                            )
                        ),
                        "relative_air_speed_mps": (
                            wind.get(
                                "relative_air_speed_mps"
                            )
                        ),
                    },
                    "hydrology": {
                        "station_surface_distance_m": (
                            hydrology.get(
                                "station_surface_distance_m"
                            )
                        ),
                        "water_level": (
                            _hydrology_metric_record(
                                hydrology.get(
                                    "water_level"
                                )
                            )
                        ),
                        "discharge": (
                            _hydrology_metric_record(
                                hydrology.get(
                                    "discharge"
                                )
                            )
                        ),
                        "water_temperature": (
                            _hydrology_metric_record(
                                hydrology.get(
                                    "water_temperature"
                                )
                            )
                        ),
                        "current_speed_estimate_mps": (
                            hydrology.get(
                                "current_speed_estimate_mps"
                            )
                        ),
                        "current_direction_deg": (
                            hydrology.get(
                                "current_direction_deg"
                            )
                        ),
                    },
                    "waterbody_identity": {
                        "status": (
                            WATERBODY_IDENTITY_STATUS
                        ),
                        "waterbody_id": None,
                        "river_reach_id": None,
                        "flow_relation": None,
                        "route_corridor_id": None,
                    },
                    "route_choice_context": {
                        "status": (
                            ROUTE_CHOICE_CONTEXT_STATUS
                        ),
                        "route_choice_intent": None,
                        "group_tactical_context": None,
                        "preferred_flow_line": None,
                    },
                }
            )

        route_records.append(
            {
                "route_index": (
                    route_index
                ),
                "exercise_index": (
                    exercise_index
                ),
                "available": bool(
                    segment_records
                ),
                "quality_provenance": deepcopy(
                    environment_route.get(
                        "quality_provenance"
                    )
                ),
                "time_context": deepcopy(
                    environment_route.get(
                        "time_context"
                    )
                ),
                "segment_record_count": (
                    len(
                        segment_records
                    )
                ),
                "route_semantics": {
                    "actual_traversed_path_is_primary_evidence": (
                        True
                    ),
                    "same_flow_line_across_traversals_assumed": (
                        False
                    ),
                    "same_hydraulic_exposure_for_same_reach_assumed": (
                        False
                    ),
                    "upstream_downstream_half_speed_difference_used_as_current_estimate": (
                        False
                    ),
                    "route_choice_intent_inferred": (
                        False
                    ),
                    "group_tactical_context_inferred": (
                        False
                    ),
                },
                "segments": (
                    segment_records
                ),
            }
        )

    weather_catalog = (
        _catalog_weather_samples(
            weather_source
        )
    )
    hydrology_catalog = (
        _catalog_hydrology_measurements(
            hydrology_source
        )
    )

    return {
        "schema_version": (
            SCHEMA_VERSION
        ),
        "session_external_id": (
            session_external_id
        ),
        "provider": (
            route_environment_context_input.get(
                "provider"
            )
        ),
        "available": any(
            route.get(
                "available"
            )
            is True
            for route in (
                route_records
            )
        ),
        "route_count": (
            len(
                route_records
            )
        ),
        "scope": {
            "purpose": (
                "PERSISTENCE_READY_ROUTE_ENVIRONMENT_EVIDENCE"
            ),
            "raw_provider_data_mutated": (
                False
            ),
            "trusted_route_view_used": (
                True
            ),
            "estimates_local_current_velocity": (
                False
            ),
            "infers_route_choice_intent": (
                False
            ),
            "infers_group_tactics": (
                False
            ),
            "performs_physiological_interpretation": (
                False
            ),
        },
        "source_catalog": {
            "weather_source": (
                {
                    key: deepcopy(
                        value
                    )
                    for key, value
                    in (
                        weather_source
                        or {}
                    ).items()
                    if key
                    != "samples"
                }
                if isinstance(
                    weather_source,
                    dict,
                )
                else None
            ),
            "weather_samples": (
                weather_catalog
            ),
            "hydrology_source": (
                {
                    key: deepcopy(
                        value
                    )
                    for key, value
                    in (
                        hydrology_source
                        or {}
                    ).items()
                    if key
                    != "measurements"
                }
                if isinstance(
                    hydrology_source,
                    dict,
                )
                else None
            ),
            "hydrology_measurements": (
                hydrology_catalog
            ),
        },
        "routes": (
            route_records
        ),
    }


def build_route_environment_evidence_record_summary(
    evidence_record: dict[str, Any],
) -> dict[str, Any]:
    source_catalog = (
        evidence_record.get(
            "source_catalog"
        )
        or {}
    )

    return {
        **{
            key: value
            for key, value
            in evidence_record.items()
            if key not in (
                "routes",
                "source_catalog",
            )
        },
        "source_catalog": {
            "weather_source": (
                source_catalog.get(
                    "weather_source"
                )
            ),
            "weather_sample_count": (
                len(
                    source_catalog.get(
                        "weather_samples"
                    )
                    or []
                )
            ),
            "hydrology_source": (
                source_catalog.get(
                    "hydrology_source"
                )
            ),
            "hydrology_measurement_count": (
                len(
                    source_catalog.get(
                        "hydrology_measurements"
                    )
                    or []
                )
            ),
            "payloads_included": False,
        },
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key != "segments"
                },
                "segments_included": (
                    False
                ),
                "segment_payload_count": (
                    len(
                        route.get(
                            "segments"
                        )
                        or []
                    )
                ),
            }
            for route in (
                evidence_record.get(
                    "routes"
                )
                or []
            )
            if isinstance(
                route,
                dict,
            )
        ],
    }
