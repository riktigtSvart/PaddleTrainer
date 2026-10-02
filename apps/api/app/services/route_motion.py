from __future__ import annotations

import math
from typing import Any


EARTH_MEAN_RADIUS_M = 6_371_008.8


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
    value = point.get("exercise_elapsed_ms")

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


def _coordinate(
    point: dict[str, Any],
) -> tuple[float, float] | None:
    latitude = _finite_number(
        point.get("latitude_deg")
    )
    longitude = _finite_number(
        point.get("longitude_deg")
    )

    if (
        latitude is None
        or longitude is None
        or not -90.0 <= latitude <= 90.0
        or not -180.0 <= longitude <= 180.0
    ):
        return None

    return latitude, longitude


def _surface_distance_m(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    lat1_deg, lon1_deg = start
    lat2_deg, lon2_deg = end

    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)

    delta_lat = math.radians(
        lat2_deg - lat1_deg
    )
    delta_lon = math.radians(
        lon2_deg - lon1_deg
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    central_angle = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return (
        EARTH_MEAN_RADIUS_M
        * central_angle
    )


def _initial_bearing_deg(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float | None:
    if start == end:
        return None

    lat1_deg, lon1_deg = start
    lat2_deg, lon2_deg = end

    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)

    delta_lon = math.radians(
        lon2_deg - lon1_deg
    )

    y = (
        math.sin(delta_lon)
        * math.cos(lat2)
    )

    x = (
        math.cos(lat1)
        * math.sin(lat2)
        - math.sin(lat1)
        * math.cos(lat2)
        * math.cos(delta_lon)
    )

    bearing = math.degrees(
        math.atan2(y, x)
    )

    return (bearing + 360.0) % 360.0


def build_route_motion_evidence(
    normalized_routes: dict[str, Any],
) -> dict[str, Any]:
    raw_routes = (
        normalized_routes.get("routes")
        or []
    )

    if not isinstance(raw_routes, list):
        raw_routes = []

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

        segments: list[dict[str, Any]] = []

        for index in range(
            len(valid_points) - 1
        ):
            start_point = valid_points[index]
            end_point = valid_points[index + 1]

            start_ms = _elapsed_ms(
                start_point
            )
            end_ms = _elapsed_ms(
                end_point
            )

            interval_ms = None

            if (
                start_ms is not None
                and end_ms is not None
            ):
                interval_ms = (
                    end_ms - start_ms
                )

            start_coordinate = _coordinate(
                start_point
            )
            end_coordinate = _coordinate(
                end_point
            )

            distance_m = None
            bearing_deg = None

            if (
                start_coordinate is not None
                and end_coordinate is not None
            ):
                distance_m = (
                    _surface_distance_m(
                        start_coordinate,
                        end_coordinate,
                    )
                )

                bearing_deg = (
                    _initial_bearing_deg(
                        start_coordinate,
                        end_coordinate,
                    )
                )

            ground_speed_mps = None

            if (
                distance_m is not None
                and interval_ms is not None
                and interval_ms > 0
            ):
                ground_speed_mps = (
                    distance_m
                    / (interval_ms / 1000.0)
                )

            motion_available = (
                distance_m is not None
                and interval_ms is not None
                and interval_ms > 0
            )

            if (
                start_coordinate is None
                or end_coordinate is None
            ):
                reason = (
                    "COORDINATES_UNAVAILABLE"
                )
            elif (
                start_ms is None
                or end_ms is None
            ):
                reason = (
                    "TIMESTAMP_UNAVAILABLE"
                )
            elif interval_ms <= 0:
                reason = (
                    "NON_POSITIVE_INTERVAL"
                )
            else:
                reason = None

            segments.append(
                {
                    "segment_index": index,
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
                    "surface_distance_m": (
                        distance_m
                    ),
                    "initial_bearing_deg": (
                        bearing_deg
                    ),
                    "gps_ground_speed_mps": (
                        ground_speed_mps
                    ),
                    "motion_available": (
                        motion_available
                    ),
                    "reason": reason,
                }
            )

        routes.append(
            {
                "exercise_index": (
                    route.get("exercise_index")
                ),
                "waypoint_count": len(
                    valid_points
                ),
                "segment_count": len(
                    segments
                ),
                "motion_segment_count": sum(
                    1
                    for segment in segments
                    if segment[
                        "motion_available"
                    ]
                ),
                "segments": segments,
            }
        )

    return {
        "provider": (
            normalized_routes.get(
                "provider"
            )
        ),
        "available": any(
            route["motion_segment_count"] > 0
            for route in routes
        ),
        "route_count": len(routes),
        "routes": routes,
    }