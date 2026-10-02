from __future__ import annotations

import math
from typing import Any


EARTH_MEAN_RADIUS_M = 6_371_008.8
DEFAULT_EXTREME_OBSERVATION_LIMIT = 10
DEFAULT_LOCAL_TREND_RADIUS_SEGMENTS = 2
DEFAULT_FORWARD_RESIDUAL_SEGMENTS = 3


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


def _coordinate(
    point: dict[str, Any] | None,
) -> tuple[float, float] | None:
    if not isinstance(point, dict):
        return None

    latitude = _finite_number(
        point.get("latitude_deg")
    )
    longitude = _finite_number(
        point.get("longitude_deg")
    )

    if (
        latitude is None
        or longitude is None
        or latitude < -90.0
        or latitude > 90.0
        or longitude < -180.0
        or longitude > 180.0
    ):
        return None

    return latitude, longitude


def _surface_distance_m(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    lat1 = math.radians(start[0])
    lon1 = math.radians(start[1])
    lat2 = math.radians(end[0])
    lon2 = math.radians(end[1])

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2.0) ** 2
    )

    central_angle = 2.0 * math.asin(
        min(1.0, math.sqrt(haversine))
    )

    return (
        EARTH_MEAN_RADIUS_M
        * central_angle
    )


def _local_xy_m(
    origin: tuple[float, float],
    point: tuple[float, float],
) -> tuple[float, float]:
    origin_lat = math.radians(origin[0])
    origin_lon = math.radians(origin[1])

    point_lat = math.radians(point[0])
    point_lon = math.radians(point[1])

    mean_lat = (
        origin_lat + point_lat
    ) / 2.0

    x = (
        EARTH_MEAN_RADIUS_M
        * (point_lon - origin_lon)
        * math.cos(mean_lat)
    )

    y = (
        EARTH_MEAN_RADIUS_M
        * (point_lat - origin_lat)
    )

    return x, y


def _middle_point_geometry(
    start: tuple[float, float],
    middle: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, float | None]:
    middle_x, middle_y = (
        _local_xy_m(
            start,
            middle,
        )
    )

    end_x, end_y = _local_xy_m(
        start,
        end,
    )

    anchor_length_squared = (
        end_x * end_x
        + end_y * end_y
    )

    if anchor_length_squared <= 0.0:
        return {
            "middle_point_cross_track_deviation_m": (
                None
            ),
            "middle_point_along_track_fraction": (
                None
            ),
        }

    anchor_length = math.sqrt(
        anchor_length_squared
    )

    along_track_fraction = (
        middle_x * end_x
        + middle_y * end_y
    ) / anchor_length_squared

    cross_track_deviation_m = abs(
        middle_x * end_y
        - middle_y * end_x
    ) / anchor_length

    return {
        "middle_point_cross_track_deviation_m": (
            cross_track_deviation_m
        ),
        "middle_point_along_track_fraction": (
            along_track_fraction
        ),
    }


def _segment_midpoint_ms(
    segment: dict[str, Any] | None,
) -> float | None:
    if not isinstance(segment, dict):
        return None

    start_ms = _integer(
        segment.get(
            "start_exercise_elapsed_ms"
        )
    )
    end_ms = _integer(
        segment.get(
            "end_exercise_elapsed_ms"
        )
    )

    if (
        start_ms is None
        or end_ms is None
        or end_ms <= start_ms
    ):
        return None

    return (
        start_ms + end_ms
    ) / 2.0


def _bearing_separation_deg(
    first: Any,
    second: Any,
) -> float | None:
    first_value = _finite_number(first)
    second_value = _finite_number(second)

    if (
        first_value is None
        or second_value is None
    ):
        return None

    difference = abs(
        (
            second_value
            - first_value
            + 180.0
        )
        % 360.0
        - 180.0
    )

    return difference


def _find_route(
    normalized_routes: dict[str, Any],
    *,
    exercise_index: int,
) -> dict[str, Any] | None:
    for route in (
        normalized_routes.get("routes")
        or []
    ):
        if not isinstance(route, dict):
            continue

        if (
            route.get("exercise_index")
            == exercise_index
        ):
            return route

    return None


def _find_motion_route(
    motion_evidence: dict[str, Any],
    *,
    exercise_index: int,
) -> dict[str, Any] | None:
    for route in (
        motion_evidence.get("routes")
        or []
    ):
        if not isinstance(route, dict):
            continue

        if (
            route.get("exercise_index")
            == exercise_index
        ):
            return route

    return None


def _find_consistency_exercise(
    speed_gps_consistency: (
        dict[str, Any] | None
    ),
    *,
    exercise_index: int,
) -> dict[str, Any] | None:
    if not isinstance(
        speed_gps_consistency,
        dict,
    ):
        return None

    for exercise in (
        speed_gps_consistency.get(
            "exercises"
        )
        or []
    ):
        if not isinstance(
            exercise,
            dict,
        ):
            continue

        if (
            exercise.get("exercise_index")
            == exercise_index
        ):
            return exercise

    return None


def _point_map(
    route: dict[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    if not isinstance(route, dict):
        return {}

    result: dict[
        int,
        dict[str, Any],
    ] = {}

    for point in (
        route.get("points")
        or []
    ):
        if not isinstance(point, dict):
            continue

        waypoint_index = _integer(
            point.get("waypoint_index")
        )

        if waypoint_index is None:
            continue

        result[waypoint_index] = point

    return result


def _comparison_map(
    consistency_exercise: (
        dict[str, Any] | None
    ),
) -> dict[int, dict[str, Any]]:
    if not isinstance(
        consistency_exercise,
        dict,
    ):
        return {}

    result: dict[
        int,
        dict[str, Any],
    ] = {}

    for comparison in (
        consistency_exercise.get(
            "comparisons"
        )
        or []
    ):
        if not isinstance(
            comparison,
            dict,
        ):
            continue

        segment_index = _integer(
            comparison.get("segment_index")
        )

        if segment_index is None:
            continue

        result[segment_index] = comparison

    return result


def _two_segment_context(
    first: dict[str, Any] | None,
    second: dict[str, Any] | None,
    points: dict[
        int,
        dict[str, Any],
    ],
) -> dict[str, Any] | None:
    if (
        not isinstance(first, dict)
        or not isinstance(second, dict)
    ):
        return None

    first_start = _integer(
        first.get(
            "start_waypoint_index"
        )
    )
    first_end = _integer(
        first.get(
            "end_waypoint_index"
        )
    )
    second_start = _integer(
        second.get(
            "start_waypoint_index"
        )
    )
    second_end = _integer(
        second.get(
            "end_waypoint_index"
        )
    )

    if (
        first_start is None
        or first_end is None
        or second_start is None
        or second_end is None
        or first_end != second_start
    ):
        return None

    first_distance = _finite_number(
        first.get("surface_distance_m")
    )
    second_distance = _finite_number(
        second.get("surface_distance_m")
    )

    if (
        first_distance is None
        or second_distance is None
        or first_distance < 0.0
        or second_distance < 0.0
    ):
        return None

    start_coordinate = _coordinate(
        points.get(first_start)
    )
    middle_coordinate = _coordinate(
        points.get(first_end)
    )
    end_coordinate = _coordinate(
        points.get(second_end)
    )

    net_displacement_m = None
    middle_geometry = {
        "middle_point_cross_track_deviation_m": (
            None
        ),
        "middle_point_along_track_fraction": (
            None
        ),
    }

    if (
        start_coordinate is not None
        and end_coordinate is not None
    ):
        net_displacement_m = (
            _surface_distance_m(
                start_coordinate,
                end_coordinate,
            )
        )

    if (
        start_coordinate is not None
        and middle_coordinate is not None
        and end_coordinate is not None
    ):
        middle_geometry = (
            _middle_point_geometry(
                start_coordinate,
                middle_coordinate,
                end_coordinate,
            )
        )

    path_distance_m = (
        first_distance
        + second_distance
    )

    if (
        net_displacement_m is not None
        and path_distance_m > 0.0
    ):
        net_fraction = (
            net_displacement_m
            / path_distance_m
        )
        path_minus_net_m = (
            path_distance_m
            - net_displacement_m
        )
    else:
        net_fraction = None
        path_minus_net_m = None

    first_start_ms = _integer(
        first.get(
            "start_exercise_elapsed_ms"
        )
    )
    second_end_ms = _integer(
        second.get(
            "end_exercise_elapsed_ms"
        )
    )

    bearing_separation_deg = (
        _bearing_separation_deg(
            first.get(
                "initial_bearing_deg"
            ),
            second.get(
                "initial_bearing_deg"
            ),
        )
    )

    first_midpoint_ms = (
        _segment_midpoint_ms(first)
    )
    second_midpoint_ms = (
        _segment_midpoint_ms(second)
    )

    midpoint_separation_ms = (
        second_midpoint_ms
        - first_midpoint_ms
        if (
            first_midpoint_ms is not None
            and second_midpoint_ms is not None
            and (
                second_midpoint_ms
                > first_midpoint_ms
            )
        )
        else None
    )

    if (
        bearing_separation_deg is not None
        and midpoint_separation_ms
        is not None
    ):
        heading_change_rate_deg_per_sec = (
            bearing_separation_deg
            / (
                midpoint_separation_ms
                / 1000.0
            )
        )
    else:
        heading_change_rate_deg_per_sec = (
            None
        )

    speeds = [
        value
        for value in (
            _finite_number(
                first.get(
                    "gps_ground_speed_mps"
                )
            ),
            _finite_number(
                second.get(
                    "gps_ground_speed_mps"
                )
            ),
        )
        if (
            value is not None
            and value >= 0.0
        )
    ]

    representative_speed_mps = (
        sum(speeds) / len(speeds)
        if speeds
        else None
    )

    if (
        representative_speed_mps
        is not None
        and heading_change_rate_deg_per_sec
        is not None
        and heading_change_rate_deg_per_sec
        > 0.0
    ):
        angular_rate_rad_per_sec = (
            math.radians(
                heading_change_rate_deg_per_sec
            )
        )

        implied_turn_radius_m = (
            representative_speed_mps
            / angular_rate_rad_per_sec
        )
    else:
        implied_turn_radius_m = None

    return {
        "first_segment_index": (
            first.get("segment_index")
        ),
        "second_segment_index": (
            second.get("segment_index")
        ),
        "start_waypoint_index": first_start,
        "middle_waypoint_index": first_end,
        "end_waypoint_index": second_end,
        "start_exercise_elapsed_ms": (
            first_start_ms
        ),
        "end_exercise_elapsed_ms": (
            second_end_ms
        ),
        "elapsed_ms": (
            second_end_ms - first_start_ms
            if (
                first_start_ms is not None
                and second_end_ms is not None
            )
            else None
        ),
        "path_distance_m": path_distance_m,
        "net_displacement_m": (
            net_displacement_m
        ),
        "net_displacement_fraction_of_path": (
            net_fraction
        ),
        "path_minus_net_displacement_m": (
            path_minus_net_m
        ),
        "bearing_separation_deg": (
            bearing_separation_deg
        ),
        "segment_midpoint_separation_ms": (
            midpoint_separation_ms
        ),
        "heading_change_rate_deg_per_sec": (
            heading_change_rate_deg_per_sec
        ),
        "representative_speed_mps": (
            representative_speed_mps
        ),
        "implied_turn_radius_m": (
            implied_turn_radius_m
        ),
        **middle_geometry,
    }


def _rank_observations(
    observations: list[dict[str, Any]],
    *,
    value_getter,
    reverse: bool,
    limit: int,
) -> list[dict[str, Any]]:
    ranked: list[
        tuple[
            float,
            dict[str, Any],
        ]
    ] = []

    for observation in observations:
        value = _finite_number(
            value_getter(observation)
        )

        if value is None:
            continue

        ranked.append(
            (
                value,
                observation,
            )
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=reverse,
    )

    return [
        observation
        for _, observation
        in ranked[:limit]
    ]


def build_route_motion_anomaly_evidence(
    normalized_routes: dict[str, Any],
    motion_evidence: dict[str, Any],
    speed_gps_consistency: (
        dict[str, Any] | None
    ) = None,
    *,
    extreme_observation_limit: int = (
        DEFAULT_EXTREME_OBSERVATION_LIMIT
    ),
) -> dict[str, Any]:
    if extreme_observation_limit < 1:
        raise ValueError(
            "extreme_observation_limit "
            "must be at least 1"
        )

    exercise_indices = sorted(
        {
            route["exercise_index"]
            for route in (
                motion_evidence.get("routes")
                or []
            )
            if (
                isinstance(route, dict)
                and isinstance(
                    route.get(
                        "exercise_index"
                    ),
                    int,
                )
            )
        }
    )

    route_results: list[
        dict[str, Any]
    ] = []

    for exercise_index in exercise_indices:
        normalized_route = _find_route(
            normalized_routes,
            exercise_index=exercise_index,
        )

        motion_route = _find_motion_route(
            motion_evidence,
            exercise_index=exercise_index,
        )

        if motion_route is None:
            continue

        points = _point_map(
            normalized_route
        )

        route_point_elapsed_values = [
            _integer(
                point.get(
                    "exercise_elapsed_ms"
                )
            )
            for point in points.values()
        ]

        route_point_elapsed_values = [
            value
            for value
            in route_point_elapsed_values
            if value is not None
        ]

        route_start_exercise_elapsed_ms = (
            min(route_point_elapsed_values)
            if route_point_elapsed_values
            else None
        )

        consistency_exercise = (
            _find_consistency_exercise(
                speed_gps_consistency,
                exercise_index=exercise_index,
            )
        )

        comparisons = _comparison_map(
            consistency_exercise
        )

        segments = [
            segment
            for segment in (
                motion_route.get("segments")
                or []
            )
            if isinstance(segment, dict)
        ]

        observations: list[
            dict[str, Any]
        ] = []

        for position, segment in enumerate(
            segments
        ):
            previous_segment = (
                segments[position - 1]
                if position > 0
                else None
            )

            next_segment = (
                segments[position + 1]
                if (
                    position + 1
                    < len(segments)
                )
                else None
            )

            segment_index = _integer(
                segment.get("segment_index")
            )

            gps_speed = _finite_number(
                segment.get(
                    "gps_ground_speed_mps"
                )
            )

            previous_speed = (
                _finite_number(
                    previous_segment.get(
                        "gps_ground_speed_mps"
                    )
                )
                if previous_segment
                else None
            )

            next_speed = (
                _finite_number(
                    next_segment.get(
                        "gps_ground_speed_mps"
                    )
                )
                if next_segment
                else None
            )

            comparison = (
                comparisons.get(
                    segment_index
                )
                if segment_index
                is not None
                else None
            )

            current_interval_ms = _integer(
                segment.get("interval_ms")
            )

            previous_interval_ms = (
                _integer(
                    previous_segment.get(
                        "interval_ms"
                    )
                )
                if previous_segment
                else None
            )

            next_interval_ms = (
                _integer(
                    next_segment.get(
                        "interval_ms"
                    )
                )
                if next_segment
                else None
            )

            local_intervals = [
                value
                for value in (
                    previous_interval_ms,
                    current_interval_ms,
                    next_interval_ms,
                )
                if value is not None
            ]

            local_speed_trend = (
                _build_local_speed_trend(
                    segments,
                    position=position,
                )
            )

            observation = {
                "segment_index": (
                    segment_index
                ),
                "motion_available": (
                    segment.get(
                        "motion_available"
                    )
                ),
                "reason": (
                    segment.get("reason")
                ),
                "start_waypoint_index": (
                    segment.get(
                        "start_waypoint_index"
                    )
                ),
                "end_waypoint_index": (
                    segment.get(
                        "end_waypoint_index"
                    )
                ),
                "start_exercise_elapsed_ms": (
                    segment.get(
                        "start_exercise_elapsed_ms"
                    )
                ),
                "end_exercise_elapsed_ms": (
                    segment.get(
                        "end_exercise_elapsed_ms"
                    )
                ),
                "time_since_exercise_start_ms": (
                    segment.get(
                        "start_exercise_elapsed_ms"
                    )
                ),
                "interval_ms": (
                    current_interval_ms
                ),
                "surface_distance_m": (
                    _finite_number(
                        segment.get(
                            "surface_distance_m"
                        )
                    )
                ),
                "gps_ground_speed_mps": (
                    gps_speed
                ),
                "initial_bearing_deg": (
                    _finite_number(
                        segment.get(
                            "initial_bearing_deg"
                        )
                    )
                ),
                "previous_gps_ground_speed_mps": (
                    previous_speed
                ),
                "next_gps_ground_speed_mps": (
                    next_speed
                ),
                "speed_change_from_previous_mps": (
                    gps_speed
                    - previous_speed
                    if (
                        gps_speed is not None
                        and previous_speed
                        is not None
                    )
                    else None
                ),
                "speed_change_to_next_mps": (
                    next_speed
                    - gps_speed
                    if (
                        gps_speed is not None
                        and next_speed
                        is not None
                    )
                    else None
                ),
                "bearing_separation_from_previous_deg": (
                    _bearing_separation_deg(
                        (
                            previous_segment.get(
                                "initial_bearing_deg"
                            )
                            if previous_segment
                            else None
                        ),
                        segment.get(
                            "initial_bearing_deg"
                        ),
                    )
                ),
                "bearing_separation_to_next_deg": (
                    _bearing_separation_deg(
                        segment.get(
                            "initial_bearing_deg"
                        ),
                        (
                            next_segment.get(
                                "initial_bearing_deg"
                            )
                            if next_segment
                            else None
                        ),
                    )
                ),
                "previous_interval_ms": (
                    previous_interval_ms
                ),
                "next_interval_ms": (
                    next_interval_ms
                ),
                "local_maximum_interval_ms": (
                    max(local_intervals)
                    if local_intervals
                    else None
                ),
                "previous_pair": (
                    _two_segment_context(
                        previous_segment,
                        segment,
                        points,
                    )
                ),
                "forward_pair": (
                    _two_segment_context(
                        segment,
                        next_segment,
                        points,
                    )
                ),
                "polar_speed_sample_mean_mps": (
                    _finite_number(
                        comparison.get(
                            "polar_speed_sample_mean_mps"
                        )
                    )
                    if comparison
                    else None
                ),
                "gps_minus_polar_speed_mps": (
                    _finite_number(
                        comparison.get(
                            "difference_mps"
                        )
                    )
                    if comparison
                    else None
                ),
                "absolute_gps_polar_speed_difference_mps": (
                    _finite_number(
                        comparison.get(
                            "absolute_difference_mps"
                        )
                    )
                    if comparison
                    else None
                ),
                "time_since_route_start_ms": (
                    (
                            segment.get(
                                "start_exercise_elapsed_ms"
                            )
                            - route_start_exercise_elapsed_ms
                    )
                    if (
                            isinstance(
                                segment.get(
                                    "start_exercise_elapsed_ms"
                                ),
                                int,
                            )
                            and route_start_exercise_elapsed_ms
                            is not None
                    )
                    else None
                ),
                **local_speed_trend,
            }

            observations.append(
                observation
            )

        highest_speed = _rank_observations(
            observations,
            value_getter=lambda item: (
                item.get(
                    "gps_ground_speed_mps"
                )
            ),
            reverse=True,
            limit=extreme_observation_limit,
        )

        highest_polar_difference = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    item.get(
                        "absolute_gps_polar_"
                        "speed_difference_mps"
                    )
                ),
                reverse=True,
                limit=(
                    extreme_observation_limit
                ),
            )
        )

        highest_path_minus_net = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    (
                        item.get(
                            "forward_pair"
                        )
                        or {}
                    ).get(
                        "path_minus_net_"
                        "displacement_m"
                    )
                ),
                reverse=True,
                limit=(
                    extreme_observation_limit
                ),
            )
        )

        lowest_net_fraction = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    (
                        item.get(
                            "forward_pair"
                        )
                        or {}
                    ).get(
                        "net_displacement_"
                        "fraction_of_path"
                    )
                ),
                reverse=False,
                limit=(
                    extreme_observation_limit
                ),
            )
        )
        
        _attach_temporal_residual_context(
            observations
        )


        highest_cross_track = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    (
                            item.get("forward_pair")
                            or {}
                    ).get(
                        "middle_point_"
                        "cross_track_deviation_m"
                    )
                ),
                reverse=True,
                limit=extreme_observation_limit,
            )
        )

        highest_heading_change_rate = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    (
                            item.get("forward_pair")
                            or {}
                    ).get(
                        "heading_change_rate_"
                        "deg_per_sec"
                    )
                ),
                reverse=True,
                limit=extreme_observation_limit,
            )
        )

        highest_speed_residual = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    item.get(
                        "absolute_speed_residual_mps"
                    )
                ),
                reverse=True,
                limit=extreme_observation_limit,
            )
        )

        highest_residual_compensation = (
            _rank_observations(
                observations,
                value_getter=lambda item: (
                    item.get(
                        "compensating_"
                        "residual_distance_m"
                    )
                ),
                reverse=True,
                limit=extreme_observation_limit,
            )
        )

        route_results.append(
            {
                "exercise_index": (
                    exercise_index
                ),
                "available": bool(
                    observations
                ),
                "observation_count": (
                    len(observations)
                ),
                "polar_speed_comparison_available": (
                    bool(comparisons)
                ),
                "extreme_observation_limit": (
                    extreme_observation_limit
                ),
                "extremes": {
                    "highest_gps_ground_speed": (
                        highest_speed
                    ),
                    "highest_absolute_gps_polar_speed_difference": (
                        highest_polar_difference
                    ),
                    "highest_forward_path_minus_net_displacement": (
                        highest_path_minus_net
                    ),
                    "lowest_forward_net_displacement_fraction_of_path": (
                        lowest_net_fraction
                    ),
                    "highest_forward_cross_track_deviation": (
                        highest_cross_track
                    ),
                    "highest_forward_heading_change_rate": (
                        highest_heading_change_rate
                    ),
                    "highest_absolute_local_speed_residual": (
                        highest_speed_residual
                    ),
                    "highest_residual_compensation_distance": (
                        highest_residual_compensation
                    ),
                },
                "observations": observations,
                "route_start_exercise_elapsed_ms": (
                    route_start_exercise_elapsed_ms
                ),
            }
        )

    return {
        "provider": (
            motion_evidence.get("provider")
            or normalized_routes.get(
                "provider"
            )
        ),
        "available": any(
            route.get("available")
            is True
            for route in route_results
        ),
        "route_count": len(
            route_results
        ),
        "routes": route_results,
    }


def _build_local_speed_trend(
    segments: list[dict[str, Any]],
    *,
    position: int,
    radius: int = (
        DEFAULT_LOCAL_TREND_RADIUS_SEGMENTS
    ),
) -> dict[str, Any]:
    target = segments[position]

    target_midpoint_ms = (
        _segment_midpoint_ms(target)
    )

    target_speed = _finite_number(
        target.get(
            "gps_ground_speed_mps"
        )
    )

    if (
        target_midpoint_ms is None
        or target_speed is None
    ):
        return {
            "local_speed_trend_context_segment_indices": [],
            "local_speed_trend_context_count": 0,
            "local_speed_trend_slope_mps2": None,
            "expected_gps_ground_speed_mps": None,
            "speed_residual_mps": None,
            "absolute_speed_residual_mps": None,
            "speed_residual_distance_m": None,
        }

    observations: list[
        tuple[float, float, int | None]
    ] = []

    start = max(
        0,
        position - radius,
    )
    end = min(
        len(segments),
        position + radius + 1,
    )

    for context_position in range(
        start,
        end,
    ):
        if context_position == position:
            continue

        context_segment = (
            segments[context_position]
        )

        midpoint_ms = _segment_midpoint_ms(
            context_segment
        )
        speed = _finite_number(
            context_segment.get(
                "gps_ground_speed_mps"
            )
        )

        if (
            midpoint_ms is None
            or speed is None
        ):
            continue

        relative_time_sec = (
            midpoint_ms
            - target_midpoint_ms
        ) / 1000.0

        observations.append(
            (
                relative_time_sec,
                speed,
                _integer(
                    context_segment.get(
                        "segment_index"
                    )
                ),
            )
        )

    has_past_context = any(
        relative_time_sec < 0.0
        for (
            relative_time_sec,
            _,
            _,
        ) in observations
    )

    has_future_context = any(
        relative_time_sec > 0.0
        for (
            relative_time_sec,
            _,
            _,
        ) in observations
    )

    if (
            len(observations) < 2
            or not has_past_context
            or not has_future_context
    ):
        return {
            "local_speed_trend_context_segment_indices": [
                item[2]
                for item in observations
            ],
            "local_speed_trend_context_count": (
                len(observations)
            ),
            "local_speed_trend_slope_mps2": None,
            "expected_gps_ground_speed_mps": None,
            "speed_residual_mps": None,
            "absolute_speed_residual_mps": None,
            "speed_residual_distance_m": None,
        }

    x_values = [
        item[0]
        for item in observations
    ]
    y_values = [
        item[1]
        for item in observations
    ]

    x_mean = (
        sum(x_values)
        / len(x_values)
    )
    y_mean = (
        sum(y_values)
        / len(y_values)
    )

    denominator = sum(
        (x - x_mean) ** 2
        for x in x_values
    )

    if denominator <= 0.0:
        slope = None
        expected_speed = None
    else:
        slope = (
            sum(
                (x - x_mean)
                * (y - y_mean)
                for x, y in zip(
                    x_values,
                    y_values,
                )
            )
            / denominator
        )

        # target time is x == 0
        expected_speed = (
            y_mean
            - slope * x_mean
        )

    if expected_speed is None:
        residual = None
    else:
        residual = (
            target_speed
            - expected_speed
        )

    interval_ms = _integer(
        target.get("interval_ms")
    )

    residual_distance_m = (
        residual
        * interval_ms
        / 1000.0
        if (
            residual is not None
            and interval_ms is not None
            and interval_ms > 0
        )
        else None
    )

    return {
        "local_speed_trend_context_segment_indices": [
            item[2]
            for item in observations
        ],
        "local_speed_trend_context_count": (
            len(observations)
        ),
        "local_speed_trend_slope_mps2": (
            slope
        ),
        "expected_gps_ground_speed_mps": (
            expected_speed
        ),
        "speed_residual_mps": residual,
        "absolute_speed_residual_mps": (
            abs(residual)
            if residual is not None
            else None
        ),
        "speed_residual_distance_m": (
            residual_distance_m
        ),
    }


def _opposite_nonzero_sign(
    first: float,
    second: float,
) -> bool:
    return (
        (first > 0.0 and second < 0.0)
        or
        (first < 0.0 and second > 0.0)
    )


def _same_nonzero_sign(
    first: float,
    second: float,
) -> bool:
    return (
        (first > 0.0 and second > 0.0)
        or
        (first < 0.0 and second < 0.0)
    )


def _attach_temporal_residual_context(
    observations: list[dict[str, Any]],
    *,
    forward_segment_count: int = (
        DEFAULT_FORWARD_RESIDUAL_SEGMENTS
    ),
) -> None:
    for position, observation in enumerate(
        observations
    ):
        current_residual = _finite_number(
            observation.get(
                "speed_residual_mps"
            )
        )

        next_observation = (
            observations[position + 1]
            if position + 1
            < len(observations)
            else None
        )

        next_residual = (
            _finite_number(
                next_observation.get(
                    "speed_residual_mps"
                )
            )
            if next_observation
            else None
        )

        if (
            current_residual is not None
            and next_residual is not None
        ):
            sign_reversal = (
                _opposite_nonzero_sign(
                    current_residual,
                    next_residual,
                )
            )
        else:
            sign_reversal = None

        observation[
            "next_speed_residual_mps"
        ] = next_residual

        observation[
            "residual_sign_reversal"
        ] = sign_reversal

        observation[
            "compensating_residual_magnitude_mps"
        ] = (
            min(
                abs(current_residual),
                abs(next_residual),
            )
            if sign_reversal is True
            else (
                0.0
                if sign_reversal is False
                else None
            )
        )

        current_distance_residual = (
            _finite_number(
                observation.get(
                    "speed_residual_distance_m"
                )
            )
        )

        next_distance_residual = (
            _finite_number(
                next_observation.get(
                    "speed_residual_distance_m"
                )
            )
            if next_observation
            else None
        )

        if (
            sign_reversal is True
            and current_distance_residual
            is not None
            and next_distance_residual
            is not None
        ):
            absolute_total = (
                abs(current_distance_residual)
                + abs(next_distance_residual)
            )

            compensation_distance = min(
                abs(current_distance_residual),
                abs(next_distance_residual),
            )

            cancellation_fraction = (
                1.0
                - abs(
                    current_distance_residual
                    + next_distance_residual
                )
                / absolute_total
                if absolute_total > 0.0
                else None
            )
        else:
            compensation_distance = (
                0.0
                if sign_reversal is False
                else None
            )
            cancellation_fraction = (
                0.0
                if sign_reversal is False
                else None
            )

        observation[
            "compensating_residual_distance_m"
        ] = compensation_distance

        observation[
            "residual_cancellation_fraction"
        ] = cancellation_fraction

        forward_residual_distances: list[
            float
        ] = []

        for forward_position in range(
            position,
            min(
                len(observations),
                position
                + forward_segment_count,
            ),
        ):
            value = _finite_number(
                observations[
                    forward_position
                ].get(
                    "speed_residual_distance_m"
                )
            )

            if value is None:
                break

            forward_residual_distances.append(
                value
            )

        absolute_sum = sum(
            abs(value)
            for value
            in forward_residual_distances
        )

        signed_sum = sum(
            forward_residual_distances
        )

        observation[
            "forward_residual_segment_count"
        ] = len(
            forward_residual_distances
        )

        observation[
            "forward_residual_distance_sum_m"
        ] = (
            signed_sum
            if forward_residual_distances
            else None
        )

        observation[
            "forward_absolute_residual_distance_sum_m"
        ] = (
            absolute_sum
            if forward_residual_distances
            else None
        )

        observation[
            "forward_residual_cancellation_fraction"
        ] = (
            1.0
            - abs(signed_sum)
            / absolute_sum
            if absolute_sum > 0.0
            else None
        )

        same_sign_count = 0
        same_sign_duration_ms = 0

        if (
            current_residual is not None
            and current_residual != 0.0
        ):
            for following in (
                observations[
                    position + 1:
                ]
            ):
                following_residual = (
                    _finite_number(
                        following.get(
                            "speed_residual_mps"
                        )
                    )
                )

                if (
                    following_residual
                    is None
                    or not _same_nonzero_sign(
                        current_residual,
                        following_residual,
                    )
                ):
                    break

                same_sign_count += 1

                interval_ms = _integer(
                    following.get(
                        "interval_ms"
                    )
                )

                if (
                    interval_ms is not None
                    and interval_ms > 0
                ):
                    same_sign_duration_ms += (
                        interval_ms
                    )

        observation[
            "post_change_same_sign_segment_count"
        ] = same_sign_count

        observation[
            "post_change_same_sign_duration_ms"
        ] = same_sign_duration_ms