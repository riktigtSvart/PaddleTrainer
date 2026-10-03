from __future__ import annotations

import math
from typing import Any


EARTH_MEAN_RADIUS_M = 6_371_008.8
DEFAULT_WINDOW_SEGMENT_COUNT = 5


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return result


def _integer(value: Any) -> int | None:
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
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    latitude_1, longitude_1 = first
    latitude_2, longitude_2 = second

    phi_1 = math.radians(latitude_1)
    phi_2 = math.radians(latitude_2)
    delta_phi = math.radians(
        latitude_2 - latitude_1
    )
    delta_lambda = math.radians(
        longitude_2 - longitude_1
    )

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1)
        * math.cos(phi_2)
        * math.sin(delta_lambda / 2.0) ** 2
    )

    return (
        2.0
        * EARTH_MEAN_RADIUS_M
        * math.asin(
            min(
                1.0,
                math.sqrt(a),
            )
        )
    )


def _local_xy_m(
    coordinate: tuple[float, float],
    *,
    origin: tuple[float, float],
) -> tuple[float, float]:
    latitude, longitude = coordinate
    origin_latitude, origin_longitude = origin

    x = (
        EARTH_MEAN_RADIUS_M
        * math.radians(
            longitude - origin_longitude
        )
        * math.cos(
            math.radians(origin_latitude)
        )
    )
    y = (
        EARTH_MEAN_RADIUS_M
        * math.radians(
            latitude - origin_latitude
        )
    )

    return x, y


def _chord_geometry(
    coordinates: list[tuple[float, float]],
) -> dict[str, Any]:
    first = coordinates[0]
    last = coordinates[-1]

    end_x, end_y = _local_xy_m(
        last,
        origin=first,
    )

    chord_squared = (
        end_x * end_x
        + end_y * end_y
    )

    if chord_squared <= 0.0:
        return {
            "maximum_intermediate_point_cross_track_deviation_m": None,
            "minimum_intermediate_point_along_track_fraction": None,
            "maximum_intermediate_point_along_track_fraction": None,
            "intermediate_point_along_track_outside_unit_interval_count": 0,
        }

    chord_length = math.sqrt(
        chord_squared
    )

    cross_track_values = []
    along_track_fractions = []

    for coordinate in coordinates[1:-1]:
        x, y = _local_xy_m(
            coordinate,
            origin=first,
        )

        cross_track_values.append(
            abs(
                end_x * y
                - end_y * x
            )
            / chord_length
        )

        along_track_fractions.append(
            (
                x * end_x
                + y * end_y
            )
            / chord_squared
        )

    return {
        "maximum_intermediate_point_cross_track_deviation_m": (
            max(cross_track_values)
            if cross_track_values
            else 0.0
        ),
        "minimum_intermediate_point_along_track_fraction": (
            min(along_track_fractions)
            if along_track_fractions
            else None
        ),
        "maximum_intermediate_point_along_track_fraction": (
            max(along_track_fractions)
            if along_track_fractions
            else None
        ),
        "intermediate_point_along_track_outside_unit_interval_count": (
            sum(
                1
                for value
                in along_track_fractions
                if (
                    value < 0.0
                    or value > 1.0
                )
            )
        ),
    }


def _window(
    points: list[dict[str, Any]],
    *,
    start_segment_index: int,
    segment_count: int,
) -> dict[str, Any]:
    selected_points = points[
        start_segment_index:
        start_segment_index
        + segment_count
        + 1
    ]

    start_point = selected_points[0]
    end_point = selected_points[-1]

    coordinates = [
        _coordinate(point)
        for point
        in selected_points
    ]

    start_elapsed_ms = _integer(
        start_point.get(
            "exercise_elapsed_ms"
        )
    )
    end_elapsed_ms = _integer(
        end_point.get(
            "exercise_elapsed_ms"
        )
    )

    intervals = []

    for first_point, second_point in zip(
        selected_points,
        selected_points[1:],
    ):
        first_elapsed_ms = _integer(
            first_point.get(
                "exercise_elapsed_ms"
            )
        )
        second_elapsed_ms = _integer(
            second_point.get(
                "exercise_elapsed_ms"
            )
        )

        if (
            first_elapsed_ms is None
            or second_elapsed_ms is None
        ):
            continue

        intervals.append(
            second_elapsed_ms
            - first_elapsed_ms
        )

    base = {
        "start_segment_index": start_segment_index,
        "end_segment_index": (
            start_segment_index
            + segment_count
            - 1
        ),
        "segment_count": segment_count,
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
            start_elapsed_ms
        ),
        "end_exercise_elapsed_ms": (
            end_elapsed_ms
        ),
        "window_elapsed_ms": (
            end_elapsed_ms
            - start_elapsed_ms
            if (
                start_elapsed_ms is not None
                and end_elapsed_ms is not None
            )
            else None
        ),
        "timestamped_adjacent_interval_count": (
            len(intervals)
        ),
        "positive_adjacent_interval_count": (
            sum(
                1
                for value in intervals
                if value > 0
            )
        ),
        "all_adjacent_intervals_positive": (
            len(intervals) == segment_count
            and all(
                value > 0
                for value in intervals
            )
        ),
        "minimum_adjacent_interval_ms": (
            min(intervals)
            if intervals
            else None
        ),
        "maximum_adjacent_interval_ms": (
            max(intervals)
            if intervals
            else None
        ),
    }

    if any(
        coordinate is None
        for coordinate in coordinates
    ):
        return {
            **base,
            "available": False,
            "reason": "COORDINATES_UNAVAILABLE",
            "path_distance_m": None,
            "net_displacement_m": None,
            "path_minus_net_displacement_m": None,
            "net_displacement_fraction_of_path": None,
            "maximum_intermediate_point_cross_track_deviation_m": None,
            "minimum_intermediate_point_along_track_fraction": None,
            "maximum_intermediate_point_along_track_fraction": None,
            "intermediate_point_along_track_outside_unit_interval_count": None,
        }

    concrete_coordinates = [
        coordinate
        for coordinate
        in coordinates
        if coordinate is not None
    ]

    segment_distances = [
        _surface_distance_m(
            first,
            second,
        )
        for first, second in zip(
            concrete_coordinates,
            concrete_coordinates[1:],
        )
    ]

    path_distance_m = sum(
        segment_distances
    )

    net_displacement_m = (
        _surface_distance_m(
            concrete_coordinates[0],
            concrete_coordinates[-1],
        )
    )

    path_minus_net_displacement_m = (
        path_distance_m
        - net_displacement_m
    )

    net_displacement_fraction_of_path = (
        net_displacement_m
        / path_distance_m
        if path_distance_m > 0.0
        else None
    )

    return {
        **base,
        "available": True,
        "reason": None,
        "path_distance_m": path_distance_m,
        "net_displacement_m": (
            net_displacement_m
        ),
        "path_minus_net_displacement_m": (
            path_minus_net_displacement_m
        ),
        "net_displacement_fraction_of_path": (
            net_displacement_fraction_of_path
        ),
        **_chord_geometry(
            concrete_coordinates
        ),
    }


def _extreme_window(
    windows: list[dict[str, Any]],
    *,
    field: str,
    mode: str,
) -> dict[str, Any] | None:
    candidates = [
        window
        for window in windows
        if _finite_number(
            window.get(field)
        )
        is not None
    ]

    if not candidates:
        return None

    key = lambda window: _finite_number(
        window.get(field)
    )

    selected = (
        min(
            candidates,
            key=key,
        )
        if mode == "min"
        else max(
            candidates,
            key=key,
        )
    )

    return {
        "start_segment_index": (
            selected.get(
                "start_segment_index"
            )
        ),
        "end_segment_index": (
            selected.get(
                "end_segment_index"
            )
        ),
        field: selected.get(field),
    }


def build_route_motion_path_geometry_evidence(
    normalized_routes: dict[str, Any],
    *,
    window_segment_count: int = (
        DEFAULT_WINDOW_SEGMENT_COUNT
    ),
) -> dict[str, Any]:
    """Build rolling path-vs-net geometry evidence.

    This is descriptive only. It does not classify, smooth, exclude,
    or reconstruct route data.
    """
    if window_segment_count < 1:
        raise ValueError(
            "window_segment_count must be >= 1"
        )

    route_results = []

    for route_index, route in enumerate(
        normalized_routes.get("routes") or []
    ):
        if not isinstance(
            route,
            dict,
        ):
            continue

        points = [
            point
            for point
            in (
                route.get("points")
                or []
            )
            if isinstance(
                point,
                dict,
            )
        ]

        candidate_segment_count = max(
            len(points) - 1,
            0,
        )

        full_window_count = max(
            candidate_segment_count
            - window_segment_count
            + 1,
            0,
        )

        windows = [
            _window(
                points,
                start_segment_index=(
                    start_segment_index
                ),
                segment_count=(
                    window_segment_count
                ),
            )
            for start_segment_index
            in range(
                full_window_count
            )
        ]

        available_window_count = sum(
            1
            for window in windows
            if window.get("available")
            is True
        )

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": (
                    route.get(
                        "exercise_index"
                    )
                ),
                "available": bool(
                    windows
                ),
                "reason": (
                    None
                    if windows
                    else "INSUFFICIENT_ROUTE_POINTS"
                ),
                "point_count": len(points),
                "candidate_segment_count": (
                    candidate_segment_count
                ),
                "window_segment_count": (
                    window_segment_count
                ),
                "full_window_count": (
                    full_window_count
                ),
                "available_window_count": (
                    available_window_count
                ),
                "first_window": (
                    windows[0]
                    if windows
                    else None
                ),
                "minimum_net_displacement_fraction_window": (
                    _extreme_window(
                        windows,
                        field=(
                            "net_displacement_fraction_of_path"
                        ),
                        mode="min",
                    )
                ),
                "maximum_path_minus_net_displacement_window": (
                    _extreme_window(
                        windows,
                        field=(
                            "path_minus_net_displacement_m"
                        ),
                        mode="max",
                    )
                ),
                "maximum_cross_track_window": (
                    _extreme_window(
                        windows,
                        field=(
                            "maximum_intermediate_point_cross_track_deviation_m"
                        ),
                        mode="max",
                    )
                ),
                "windows": windows,
            }
        )

    return {
        "provider": normalized_routes.get(
            "provider"
        ),
        "available": bool(
            route_results
        ),
        "window_segment_count": (
            window_segment_count
        ),
        "route_count": len(
            route_results
        ),
        "routes": route_results,
    }


def build_route_motion_path_geometry_summary(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        **evidence,
        "routes": [
            {
                key: value
                for key, value in route.items()
                if key != "windows"
            }
            for route in (
                evidence.get("routes")
                or []
            )
            if isinstance(
                route,
                dict,
            )
        ],
    }
