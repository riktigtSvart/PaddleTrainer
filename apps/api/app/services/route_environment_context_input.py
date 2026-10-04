from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any


SCHEMA_VERSION = "0.1"

SCOPE_ENVIRONMENTAL_ENRICHMENT_INPUT = (
    "ENVIRONMENTAL_ENRICHMENT_INPUT"
)

STATUS_ENDPOINT_POSITIONS_AVAILABLE = (
    "ENDPOINT_POSITIONS_AVAILABLE"
)
STATUS_POSITION_ENDPOINT_UNAVAILABLE = (
    "POSITION_ENDPOINT_UNAVAILABLE"
)

REASON_EXTERNAL_WORKLOAD_UNAVAILABLE = (
    "ROUTE_EXTERNAL_WORKLOAD_EVIDENCE_UNAVAILABLE"
)


def _integer(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
    ):
        return int(value)

    return None


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(
        value,
        (int, float),
    ):
        return None

    result = float(value)

    if not math.isfinite(
        result
    ):
        return None

    return result


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None


def _resolve_start_datetime(
    exercise_start_time: Any,
    timezone_offset_minutes: Any,
) -> datetime | None:
    parsed = _parse_datetime(
        exercise_start_time
    )

    if parsed is None:
        return None

    if parsed.tzinfo is not None:
        return parsed

    offset_minutes = _integer(
        timezone_offset_minutes
    )

    if offset_minutes is None:
        return None

    return parsed.replace(
        tzinfo=timezone(
            timedelta(
                minutes=offset_minutes
            )
        )
    )


def _timestamp_at_elapsed(
    exercise_start: datetime | None,
    elapsed_ms: Any,
) -> str | None:
    elapsed = _finite_number(
        elapsed_ms
    )

    if (
        exercise_start is None
        or elapsed is None
        or elapsed < 0.0
    ):
        return None

    return (
        exercise_start
        + timedelta(
            milliseconds=elapsed
        )
    ).isoformat()


def _position(
    point: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(
        point,
        dict,
    ):
        return None

    latitude = _finite_number(
        point.get(
            "latitude_deg"
        )
    )
    longitude = _finite_number(
        point.get(
            "longitude_deg"
        )
    )

    if (
        latitude is None
        or longitude is None
    ):
        return None

    return {
        "waypoint_index": (
            _integer(
                point.get(
                    "waypoint_index"
                )
            )
        ),
        "exercise_elapsed_ms": (
            _integer(
                point.get(
                    "exercise_elapsed_ms"
                )
            )
        ),
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "altitude_m": _finite_number(
            point.get(
                "altitude_m"
            )
        ),
    }


def _route_lookup(
    evidence: dict[str, Any],
) -> dict[
    tuple[int, int | None],
    dict[str, Any],
]:
    result = {}

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
            (
                route_index,
                exercise_index,
            )
        ] = route

    return result


def _match_route(
    lookup: dict[
        tuple[int, int | None],
        dict[str, Any],
    ],
    *,
    route_index: int,
    exercise_index: int | None,
) -> dict[str, Any] | None:
    exact = lookup.get(
        (
            route_index,
            exercise_index,
        )
    )

    if exact is not None:
        return exact

    matches = [
        route
        for (
            (
                _candidate_route_index,
                candidate_exercise_index,
            ),
            route,
        )
        in lookup.items()
        if candidate_exercise_index
        == exercise_index
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def build_route_environment_context_input(
    trusted_normalized_routes: dict[str, Any],
    route_external_workload_evidence: dict[str, Any],
    *,
    session_time_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Join trusted motion observations to route endpoint positions/time.

    No weather, hydrology, current, wind, or physiological interpretation
    is performed here. This object is only an input contract for later
    environmental enrichment.
    """
    normalized_lookup = _route_lookup(
        trusted_normalized_routes
    )

    time_context = (
        session_time_context
        if isinstance(
            session_time_context,
            dict,
        )
        else {}
    )

    exercise_start_time = (
        time_context.get(
            "exercise_start_time"
        )
    )
    timezone_offset_minutes = (
        time_context.get(
            "timezone_offset_minutes"
        )
    )

    resolved_exercise_start = (
        _resolve_start_datetime(
            exercise_start_time,
            timezone_offset_minutes,
        )
    )

    route_results = []

    for route_position, route in enumerate(
        route_external_workload_evidence.get(
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

        normalized_route = _match_route(
            normalized_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )

        points_by_waypoint_index = {}

        if isinstance(
            normalized_route,
            dict,
        ):
            for point in (
                normalized_route.get(
                    "points"
                )
                or []
            ):
                if not isinstance(
                    point,
                    dict,
                ):
                    continue

                waypoint_index = _integer(
                    point.get(
                        "waypoint_index"
                    )
                )

                if waypoint_index is None:
                    continue

                points_by_waypoint_index[
                    waypoint_index
                ] = point

        external_available = (
            route.get(
                "available"
            )
            is True
        )

        segments = []

        if external_available:
            for observation in (
                route.get(
                    "observations"
                )
                or []
            ):
                if not isinstance(
                    observation,
                    dict,
                ):
                    continue

                start_waypoint_index = _integer(
                    observation.get(
                        "start_waypoint_index"
                    )
                )
                end_waypoint_index = _integer(
                    observation.get(
                        "end_waypoint_index"
                    )
                )

                start_position = _position(
                    points_by_waypoint_index.get(
                        start_waypoint_index
                    )
                )
                end_position = _position(
                    points_by_waypoint_index.get(
                        end_waypoint_index
                    )
                )

                positions_available = (
                    start_position is not None
                    and end_position is not None
                )

                start_elapsed_ms = _integer(
                    observation.get(
                        "start_exercise_elapsed_ms"
                    )
                )
                midpoint_elapsed_ms = (
                    observation.get(
                        "segment_midpoint_exercise_elapsed_ms"
                    )
                )
                end_elapsed_ms = _integer(
                    observation.get(
                        "end_exercise_elapsed_ms"
                    )
                )

                segments.append(
                    {
                        "order_index": (
                            _integer(
                                observation.get(
                                    "order_index"
                                )
                            )
                        ),
                        "segment_index": (
                            _integer(
                                observation.get(
                                    "segment_index"
                                )
                            )
                        ),
                        "segment_index_scope": (
                            observation.get(
                                "segment_index_scope"
                            )
                        ),
                        "source_segment_index": (
                            _integer(
                                observation.get(
                                    "source_segment_index"
                                )
                            )
                        ),
                        "source_segment_index_scope": (
                            observation.get(
                                "source_segment_index_scope"
                            )
                        ),
                        "source_segment_index_status": (
                            observation.get(
                                "source_segment_index_status"
                            )
                        ),
                        "source_waypoint_contiguous": (
                            observation.get(
                                "source_waypoint_contiguous"
                            )
                            is True
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
                        "segment_midpoint_exercise_elapsed_ms": (
                            midpoint_elapsed_ms
                        ),
                        "end_exercise_elapsed_ms": (
                            end_elapsed_ms
                        ),
                        "start_timestamp": (
                            _timestamp_at_elapsed(
                                resolved_exercise_start,
                                start_elapsed_ms,
                            )
                        ),
                        "midpoint_timestamp": (
                            _timestamp_at_elapsed(
                                resolved_exercise_start,
                                midpoint_elapsed_ms,
                            )
                        ),
                        "end_timestamp": (
                            _timestamp_at_elapsed(
                                resolved_exercise_start,
                                end_elapsed_ms,
                            )
                        ),
                        "start_position": (
                            start_position
                        ),
                        "end_position": (
                            end_position
                        ),
                        "position_status": (
                            STATUS_ENDPOINT_POSITIONS_AVAILABLE
                            if positions_available
                            else STATUS_POSITION_ENDPOINT_UNAVAILABLE
                        ),
                        "gps_ground_speed_mps": (
                            _finite_number(
                                observation.get(
                                    "gps_ground_speed_mps"
                                )
                            )
                        ),
                        "ground_speed_change_rate_mps2": (
                            _finite_number(
                                observation.get(
                                    "ground_speed_change_rate_mps2"
                                )
                            )
                        ),
                        "movement_bearing_deg": (
                            _finite_number(
                                observation.get(
                                    "initial_bearing_deg"
                                )
                            )
                        ),
                        "absolute_bearing_change_from_previous_deg": (
                            _finite_number(
                                observation.get(
                                    "absolute_bearing_change_from_previous_deg"
                                )
                            )
                        ),
                    }
                )

        available = bool(
            segments
        )

        if not external_available:
            reason = (
                REASON_EXTERNAL_WORKLOAD_UNAVAILABLE
            )
        else:
            reason = None

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": available,
                "reason": reason,
                "usable_interval": route.get(
                    "usable_interval"
                ),
                "quality_provenance": route.get(
                    "quality_provenance"
                ),
                "input_provenance": {
                    "external_workload_evidence_version": (
                        route_external_workload_evidence.get(
                            "evidence_version"
                        )
                    ),
                    "trusted_normalized_provider": (
                        trusted_normalized_routes.get(
                            "provider"
                        )
                    ),
                },
                "time_context": {
                    "exercise_start_time": (
                        exercise_start_time
                    ),
                    "timezone_offset_minutes": (
                        _integer(
                            timezone_offset_minutes
                        )
                    ),
                    "absolute_timestamps_resolved": (
                        resolved_exercise_start
                        is not None
                    ),
                    "resolved_exercise_start_timestamp": (
                        resolved_exercise_start.isoformat()
                        if resolved_exercise_start
                        is not None
                        else None
                    ),
                },
                "segment_count": len(
                    segments
                ),
                "position_complete_segment_count": (
                    sum(
                        1
                        for segment in segments
                        if segment.get(
                            "position_status"
                        )
                        == STATUS_ENDPOINT_POSITIONS_AVAILABLE
                    )
                ),
                "timestamp_complete_segment_count": (
                    sum(
                        1
                        for segment in segments
                        if (
                            segment.get(
                                "start_timestamp"
                            )
                            is not None
                            and segment.get(
                                "midpoint_timestamp"
                            )
                            is not None
                            and segment.get(
                                "end_timestamp"
                            )
                            is not None
                        )
                    )
                ),
                "segments": segments,
            }
        )

    return {
        "provider": (
            route_external_workload_evidence.get(
                "provider"
            )
            or trusted_normalized_routes.get(
                "provider"
            )
        ),
        "schema_version": (
            SCHEMA_VERSION
        ),
        "available": any(
            route.get(
                "available"
            )
            is True
            for route in route_results
        ),
        "route_count": len(
            route_results
        ),
        "scope": {
            "domain": (
                SCOPE_ENVIRONMENTAL_ENRICHMENT_INPUT
            ),
            "contains_weather": False,
            "contains_hydrology": False,
            "contains_current_estimate": False,
            "contains_wind_adjustment": False,
            "contains_physiological_interpretation": False,
            "interpolates_position": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_route_environment_context_input_summary(
    context_input: dict[str, Any],
) -> dict[str, Any]:
    return {
        **context_input,
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key != "segments"
                },
                "segments_included": False,
                "segment_payload_count": len(
                    route.get(
                        "segments"
                    )
                    or []
                ),
            }
            for route in (
                context_input.get(
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
