from __future__ import annotations

import math
import statistics
from typing import Any


DEFAULT_GAP_MULTIPLIER = 1.5


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(value, (int, float)):
        return None

    numeric = float(value)

    if not math.isfinite(numeric):
        return None

    return numeric


def _elapsed_ms(
    point: dict[str, Any],
) -> int | None:
    value = point.get(
        "exercise_elapsed_ms"
    )

    if isinstance(value, bool):
        return None

    if not isinstance(value, int):
        return None

    return value


def _has_valid_coordinate(
    point: dict[str, Any],
) -> bool:
    latitude = _finite_number(
        point.get("latitude_deg")
    )

    longitude = _finite_number(
        point.get("longitude_deg")
    )

    return (
        latitude is not None
        and longitude is not None
        and -90.0 <= latitude <= 90.0
        and -180.0 <= longitude <= 180.0
    )


def build_route_coverage_evidence(
    normalized_routes: dict[str, Any],
    *,
    session_duration_ms: int | None = None,
    gap_multiplier: float = (
        DEFAULT_GAP_MULTIPLIER
    ),
) -> dict[str, Any]:
    raw_routes = (
        normalized_routes.get("routes")
        or []
    )

    if not isinstance(raw_routes, list):
        raw_routes = []

    session_duration = (
        session_duration_ms
        if (
            isinstance(
                session_duration_ms,
                int,
            )
            and not isinstance(
                session_duration_ms,
                bool,
            )
            and session_duration_ms >= 0
        )
        else None
    )

    routes: list[dict[str, Any]] = []

    for route in raw_routes:
        if not isinstance(route, dict):
            continue

        points = (
            route.get("points")
            or []
        )

        if not isinstance(points, list):
            points = []

        valid_points = [
            point
            for point in points
            if isinstance(point, dict)
        ]

        timestamped_points = [
            point
            for point in valid_points
            if _elapsed_ms(point) is not None
        ]

        coordinate_count = sum(
            1
            for point in valid_points
            if _has_valid_coordinate(point)
        )

        waypoint_count = len(valid_points)

        first_elapsed_ms = (
            _elapsed_ms(
                timestamped_points[0]
            )
            if timestamped_points
            else None
        )

        last_elapsed_ms = (
            _elapsed_ms(
                timestamped_points[-1]
            )
            if timestamped_points
            else None
        )

        intervals: list[
            dict[str, Any]
        ] = []

        positive_intervals: list[int] = []
        zero_interval_count = 0
        negative_interval_count = 0

        for point_index in range(
            len(valid_points) - 1
        ):
            start_point = (
                valid_points[point_index]
            )
            end_point = (
                valid_points[point_index + 1]
            )

            start_ms = _elapsed_ms(
                start_point
            )
            end_ms = _elapsed_ms(
                end_point
            )

            if (
                start_ms is None
                or end_ms is None
            ):
                continue

            interval_ms = (
                end_ms - start_ms
            )

            intervals.append(
                {
                    "start_waypoint_index": (
                        start_point.get(
                            "waypoint_index"
                        )
                    ),
                    "end_waypoint_index": (
                        end_point.get(
                            "waypoint_index"
                        )
                    ),
                    "start_exercise_elapsed_ms": (
                        start_ms
                    ),
                    "end_exercise_elapsed_ms": (
                        end_ms
                    ),
                    "interval_ms": interval_ms,
                }
            )

            if interval_ms > 0:
                positive_intervals.append(
                    interval_ms
                )
            elif interval_ms == 0:
                zero_interval_count += 1
            else:
                negative_interval_count += 1

        nominal_interval_ms = None
        minimum_interval_ms = None
        maximum_interval_ms = None
        gap_threshold_ms = None
        gaps: list[dict[str, Any]] = []

        if positive_intervals:
            nominal_interval_ms = (
                statistics.median(
                    positive_intervals
                )
            )

            minimum_interval_ms = min(
                positive_intervals
            )

            maximum_interval_ms = max(
                positive_intervals
            )

            if (
                isinstance(
                    gap_multiplier,
                    (int, float),
                )
                and not isinstance(
                    gap_multiplier,
                    bool,
                )
                and math.isfinite(
                    float(gap_multiplier)
                )
                and gap_multiplier > 1
            ):
                gap_threshold_ms = (
                    nominal_interval_ms
                    * float(
                        gap_multiplier
                    )
                )

                gaps = [
                    interval
                    for interval in intervals
                    if (
                        interval[
                            "interval_ms"
                        ]
                        > gap_threshold_ms
                    )
                ]

        route_span_ms = None

        if (
            first_elapsed_ms is not None
            and last_elapsed_ms is not None
        ):
            route_span_ms = (
                last_elapsed_ms
                - first_elapsed_ms
            )

        route_span_fraction = None
        session_end_minus_last_ms = None

        if (
            session_duration is not None
            and session_duration > 0
        ):
            if route_span_ms is not None:
                route_span_fraction = (
                    route_span_ms
                    / session_duration
                )

            if last_elapsed_ms is not None:
                session_end_minus_last_ms = (
                    session_duration
                    - last_elapsed_ms
                )

        routes.append(
            {
                "exercise_index": (
                    route.get(
                        "exercise_index"
                    )
                ),
                "waypoint_count": (
                    waypoint_count
                ),
                "timestamped_waypoint_count": (
                    len(timestamped_points)
                ),
                "valid_coordinate_count": (
                    coordinate_count
                ),
                "coordinate_fraction": (
                    coordinate_count
                    / waypoint_count
                    if waypoint_count
                    else None
                ),
                "first_exercise_elapsed_ms": (
                    first_elapsed_ms
                ),
                "last_exercise_elapsed_ms": (
                    last_elapsed_ms
                ),
                "route_span_ms": (
                    route_span_ms
                ),
                "route_span_fraction_of_session": (
                    route_span_fraction
                ),
                "session_start_to_first_waypoint_ms": (
                    first_elapsed_ms
                ),
                "session_end_minus_last_waypoint_ms": (
                    session_end_minus_last_ms
                ),
                "adjacent_timestamp_interval_count": (
                    len(intervals)
                ),
                "positive_interval_count": (
                    len(
                        positive_intervals
                    )
                ),
                "zero_interval_count": (
                    zero_interval_count
                ),
                "negative_interval_count": (
                    negative_interval_count
                ),
                "nominal_interval_ms": (
                    nominal_interval_ms
                ),
                "minimum_positive_interval_ms": (
                    minimum_interval_ms
                ),
                "maximum_positive_interval_ms": (
                    maximum_interval_ms
                ),
                "gap_threshold_multiplier": (
                    float(
                        gap_multiplier
                    )
                    if isinstance(
                        gap_multiplier,
                        (int, float),
                    )
                    and not isinstance(
                        gap_multiplier,
                        bool,
                    )
                    else None
                ),
                "gap_threshold_ms": (
                    gap_threshold_ms
                ),
                "gap_count": len(gaps),
                "maximum_gap_ms": (
                    max(
                        (
                            gap[
                                "interval_ms"
                            ]
                            for gap in gaps
                        ),
                        default=None,
                    )
                ),
                "gaps": gaps,
            }
        )

    return {
        "provider": (
            normalized_routes.get(
                "provider"
            )
        ),
        "available": any(
            route[
                "timestamped_waypoint_count"
            ] > 0
            for route in routes
        ),
        "session_duration_ms": (
            session_duration
        ),
        "route_count": len(routes),
        "routes": routes,
    }