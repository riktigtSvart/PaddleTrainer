from __future__ import annotations

import math
from typing import Any

from app.services.route_motion_speed_trajectory import (
    build_speed_trajectory_summary,
)


DEFAULT_STARTUP_SEGMENT_COUNT = 5


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

    if not math.isfinite(result):
        return None

    return result


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


def _mean(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def _route_lookup(
    routes: list[dict[str, Any]],
) -> dict[
    tuple[int, int | None],
    dict[str, Any],
]:
    result = {}

    for route_position, route in enumerate(
        routes
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

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

        result[
            (
                route_index
                if route_index is not None
                else route_position,
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

    exercise_matches = [
        route
        for (
            (_route_index, candidate_exercise_index),
            route,
        )
        in lookup.items()
        if (
            candidate_exercise_index
            == exercise_index
        )
    ]

    if len(exercise_matches) == 1:
        return exercise_matches[0]

    return None


def _build_startup_trajectory(
    expected_segment_indices: list[int],
    observations_by_segment_index: dict[
        int,
        dict[str, Any],
    ],
    *,
    first_route_waypoint_exercise_elapsed_ms: (
        int | None
    ),
) -> tuple[
    list[dict[str, Any]],
    list[int],
]:
    missing_segment_indices = [
        segment_index
        for segment_index
        in expected_segment_indices
        if segment_index
        not in observations_by_segment_index
    ]

    trajectory = []
    previous_speed = None

    for order_index, segment_index in enumerate(
        expected_segment_indices
    ):
        observation = (
            observations_by_segment_index.get(
                segment_index
            )
        )

        if observation is None:
            continue

        speed = _finite_number(
            observation.get(
                "gps_ground_speed_mps"
            )
        )

        speed_change = None

        if (
            speed is not None
            and previous_speed is not None
        ):
            speed_change = (
                speed
                - previous_speed
            )

        start_exercise_elapsed_ms = _integer(
            observation.get(
                "start_exercise_elapsed_ms"
            )
        )

        time_since_first_route_waypoint_ms = None

        if (
            start_exercise_elapsed_ms is not None
            and first_route_waypoint_exercise_elapsed_ms
            is not None
        ):
            time_since_first_route_waypoint_ms = (
                start_exercise_elapsed_ms
                - first_route_waypoint_exercise_elapsed_ms
            )

        trajectory.append(
            {
                "order_index": order_index,
                "segment_index": segment_index,
                "motion_available": (
                    observation.get(
                        "motion_available"
                    )
                ),
                "reason": (
                    observation.get(
                        "reason"
                    )
                ),
                "start_exercise_elapsed_ms": (
                    start_exercise_elapsed_ms
                ),
                "end_exercise_elapsed_ms": (
                    observation.get(
                        "end_exercise_elapsed_ms"
                    )
                ),
                "time_since_first_route_waypoint_ms": (
                    time_since_first_route_waypoint_ms
                ),
                "interval_ms": (
                    observation.get(
                        "interval_ms"
                    )
                ),
                "gps_ground_speed_mps": speed,
                "gps_speed_change_from_previous_mps": (
                    speed_change
                ),
                "initial_bearing_deg": (
                    observation.get(
                        "initial_bearing_deg"
                    )
                ),
                "polar_speed_sample_mean_mps": (
                    observation.get(
                        "polar_speed_sample_mean_mps"
                    )
                ),
                "gps_minus_polar_speed_mps": (
                    observation.get(
                        "gps_minus_polar_speed_mps"
                    )
                ),
                "absolute_gps_polar_speed_difference_mps": (
                    observation.get(
                        "absolute_gps_polar_speed_difference_mps"
                    )
                ),
                "speed_residual_mps": (
                    observation.get(
                        "speed_residual_mps"
                    )
                ),
                "absolute_speed_residual_mps": (
                    observation.get(
                        "absolute_speed_residual_mps"
                    )
                ),
            }
        )

        if speed is not None:
            previous_speed = speed

    return (
        trajectory,
        missing_segment_indices,
    )


def _geometry_summary(
    observations: list[dict[str, Any]],
    *,
    selected_segment_indices: set[int],
) -> dict[str, Any]:
    unique_pairs = {}

    for observation in observations:
        for pair_key in (
            "previous_pair",
            "forward_pair",
        ):
            pair = observation.get(
                pair_key
            )

            if not isinstance(
                pair,
                dict,
            ):
                continue

            first_segment_index = _integer(
                pair.get(
                    "first_segment_index"
                )
            )

            second_segment_index = _integer(
                pair.get(
                    "second_segment_index"
                )
            )

            if (
                first_segment_index is None
                or second_segment_index is None
                or first_segment_index
                not in selected_segment_indices
                or second_segment_index
                not in selected_segment_indices
            ):
                continue

            unique_pairs.setdefault(
                (
                    first_segment_index,
                    second_segment_index,
                ),
                pair,
            )

    pairs = list(
        unique_pairs.values()
    )

    cross_track_values = [
        value
        for pair in pairs
        if (
            value := _finite_number(
                pair.get(
                    "middle_point_cross_track_deviation_m"
                )
            )
        )
        is not None
    ]

    heading_change_rates = [
        value
        for pair in pairs
        if (
            value := _finite_number(
                pair.get(
                    "heading_change_rate_deg_per_sec"
                )
            )
        )
        is not None
    ]

    turn_radii = [
        value
        for pair in pairs
        if (
            value := _finite_number(
                pair.get(
                    "implied_turn_radius_m"
                )
            )
        )
        is not None
    ]

    path_minus_net_values = [
        value
        for pair in pairs
        if (
            value := _finite_number(
                pair.get(
                    "path_minus_net_displacement_m"
                )
            )
        )
        is not None
    ]

    net_path_fractions = [
        value
        for pair in pairs
        if (
            value := _finite_number(
                pair.get(
                    "net_displacement_fraction_of_path"
                )
            )
        )
        is not None
    ]

    along_track_fractions = [
        value
        for pair in pairs
        if (
            value := _finite_number(
                pair.get(
                    "middle_point_along_track_fraction"
                )
            )
        )
        is not None
    ]

    return {
        "pair_count": len(pairs),
        "maximum_middle_point_cross_track_deviation_m": (
            max(cross_track_values)
            if cross_track_values
            else None
        ),
        "maximum_heading_change_rate_deg_per_sec": (
            max(heading_change_rates)
            if heading_change_rates
            else None
        ),
        "minimum_implied_turn_radius_m": (
            min(turn_radii)
            if turn_radii
            else None
        ),
        "path_minus_net_displacement_sum_m": (
            sum(path_minus_net_values)
            if path_minus_net_values
            else None
        ),
        "maximum_path_minus_net_displacement_m": (
            max(path_minus_net_values)
            if path_minus_net_values
            else None
        ),
        "minimum_net_displacement_fraction_of_path": (
            min(net_path_fractions)
            if net_path_fractions
            else None
        ),
        "minimum_middle_point_along_track_fraction": (
            min(along_track_fractions)
            if along_track_fractions
            else None
        ),
        "maximum_middle_point_along_track_fraction": (
            max(along_track_fractions)
            if along_track_fractions
            else None
        ),
        "middle_point_along_track_outside_unit_interval_count": (
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


def _temporal_residual_summary(
    observations: list[dict[str, Any]],
    *,
    selected_segment_indices: set[int],
) -> dict[str, Any]:
    absolute_residuals = [
        value
        for observation in observations
        if (
            value := _finite_number(
                observation.get(
                    "absolute_speed_residual_mps"
                )
            )
        )
        is not None
    ]

    residual_distances = [
        value
        for observation in observations
        if (
            value := _finite_number(
                observation.get(
                    "speed_residual_distance_m"
                )
            )
        )
        is not None
    ]

    signed_residual_distance_sum = (
        sum(residual_distances)
        if residual_distances
        else None
    )

    absolute_residual_distance_sum = (
        sum(
            abs(value)
            for value in residual_distances
        )
        if residual_distances
        else None
    )

    window_residual_cancellation_fraction = None

    if (
        signed_residual_distance_sum
        is not None
        and absolute_residual_distance_sum
        is not None
        and absolute_residual_distance_sum
        > 0.0
    ):
        window_residual_cancellation_fraction = (
            1.0
            - abs(
                signed_residual_distance_sum
            )
            / absolute_residual_distance_sum
        )

    residual_sign_reversal_count = 0
    compensating_residual_distances = []
    adjacent_cancellation_fractions = []

    for observation in observations:
        segment_index = _integer(
            observation.get(
                "segment_index"
            )
        )

        if (
            segment_index is None
            or segment_index + 1
            not in selected_segment_indices
        ):
            continue

        if (
            observation.get(
                "residual_sign_reversal"
            )
            is True
        ):
            residual_sign_reversal_count += 1

        compensating_distance = _finite_number(
            observation.get(
                "compensating_residual_distance_m"
            )
        )

        if compensating_distance is not None:
            compensating_residual_distances.append(
                compensating_distance
            )

        cancellation_fraction = _finite_number(
            observation.get(
                "residual_cancellation_fraction"
            )
        )

        if cancellation_fraction is not None:
            adjacent_cancellation_fractions.append(
                cancellation_fraction
            )

    return {
        "residual_observation_count": (
            len(absolute_residuals)
        ),
        "maximum_absolute_speed_residual_mps": (
            max(absolute_residuals)
            if absolute_residuals
            else None
        ),
        "signed_residual_distance_sum_m": (
            signed_residual_distance_sum
        ),
        "absolute_residual_distance_sum_m": (
            absolute_residual_distance_sum
        ),
        "window_residual_cancellation_fraction": (
            window_residual_cancellation_fraction
        ),
        "residual_sign_reversal_count": (
            residual_sign_reversal_count
        ),
        "maximum_compensating_residual_distance_m": (
            max(
                compensating_residual_distances
            )
            if compensating_residual_distances
            else None
        ),
        "maximum_adjacent_residual_cancellation_fraction": (
            max(
                adjacent_cancellation_fractions
            )
            if adjacent_cancellation_fractions
            else None
        ),
    }


def _cross_source_speed_summary(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    signed_differences = []
    absolute_differences = []

    for observation in observations:
        signed_difference = _finite_number(
            observation.get(
                "gps_minus_polar_speed_mps"
            )
        )

        absolute_difference = _finite_number(
            observation.get(
                "absolute_gps_polar_speed_difference_mps"
            )
        )

        if (
            absolute_difference is None
            and signed_difference is not None
        ):
            absolute_difference = abs(
                signed_difference
            )

        if signed_difference is not None:
            signed_differences.append(
                signed_difference
            )

        if absolute_difference is not None:
            absolute_differences.append(
                absolute_difference
            )

    return {
        "comparison_count": (
            len(
                absolute_differences
            )
        ),
        "mean_gps_minus_polar_speed_mps": (
            _mean(
                signed_differences
            )
        ),
        "mean_absolute_gps_polar_speed_difference_mps": (
            _mean(
                absolute_differences
            )
        ),
        "maximum_absolute_gps_polar_speed_difference_mps": (
            max(
                absolute_differences
            )
            if absolute_differences
            else None
        ),
    }


def build_route_motion_startup_evidence(
    normalized_routes: dict[str, Any],
    motion_anomaly_evidence: dict[str, Any],
    *,
    startup_segment_count: int = (
        DEFAULT_STARTUP_SEGMENT_COUNT
    ),
) -> dict[str, Any]:
    if startup_segment_count < 1:
        raise ValueError(
            "startup_segment_count must be >= 1"
        )

    normalized_route_items = [
        route
        for route in (
            normalized_routes.get(
                "routes"
            )
            or []
        )
        if isinstance(
            route,
            dict,
        )
    ]

    anomaly_route_lookup = _route_lookup(
        [
            route
            for route in (
                motion_anomaly_evidence.get(
                    "routes"
                )
                or []
            )
            if isinstance(
                route,
                dict,
            )
        ]
    )

    route_results = []

    for route_index, normalized_route in enumerate(
        normalized_route_items
    ):
        exercise_index = _integer(
            normalized_route.get(
                "exercise_index"
            )
        )

        points = [
            point
            for point in (
                normalized_route.get(
                    "points"
                )
                or []
            )
            if isinstance(
                point,
                dict,
            )
        ]

        route_start_offset_ms = _integer(
            normalized_route.get(
                "route_start_offset_ms"
            )
        )

        first_route_waypoint_source_elapsed_ms = None
        first_route_waypoint_exercise_elapsed_ms = None

        if points:
            first_route_waypoint_source_elapsed_ms = (
                _integer(
                    points[0].get(
                        "source_elapsed_ms"
                    )
                )
            )

            first_route_waypoint_exercise_elapsed_ms = (
                _integer(
                    points[0].get(
                        "exercise_elapsed_ms"
                    )
                )
            )

        route_candidate_segment_count = max(
            len(points) - 1,
            0,
        )

        expected_segment_count = min(
            startup_segment_count,
            route_candidate_segment_count,
        )

        expected_segment_indices = list(
            range(
                expected_segment_count
            )
        )

        anomaly_route = _match_route(
            anomaly_route_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )

        observations = []

        if anomaly_route is not None:
            observations = [
                observation
                for observation in (
                    anomaly_route.get(
                        "observations"
                    )
                    or []
                )
                if isinstance(
                    observation,
                    dict,
                )
            ]

        observations_by_segment_index = {}

        for observation in observations:
            segment_index = _integer(
                observation.get(
                    "segment_index"
                )
            )

            if segment_index is None:
                continue

            observations_by_segment_index[
                segment_index
            ] = observation

        (
            trajectory,
            missing_segment_indices,
        ) = _build_startup_trajectory(
            expected_segment_indices,
            observations_by_segment_index,
            first_route_waypoint_exercise_elapsed_ms=(
                first_route_waypoint_exercise_elapsed_ms
            ),
        )

        selected_observations = [
            observations_by_segment_index[
                segment_index
            ]
            for segment_index
            in expected_segment_indices
            if segment_index
            in observations_by_segment_index
        ]

        selected_segment_indices = set(
            expected_segment_indices
        )

        startup_window_start_exercise_elapsed_ms = None
        startup_window_end_exercise_elapsed_ms = None

        start_values = [
            value
            for observation in selected_observations
            if (
                value := _integer(
                    observation.get(
                        "start_exercise_elapsed_ms"
                    )
                )
            )
            is not None
        ]

        end_values = [
            value
            for observation in selected_observations
            if (
                value := _integer(
                    observation.get(
                        "end_exercise_elapsed_ms"
                    )
                )
            )
            is not None
        ]

        if start_values:
            startup_window_start_exercise_elapsed_ms = (
                min(
                    start_values
                )
            )

        if end_values:
            startup_window_end_exercise_elapsed_ms = (
                max(
                    end_values
                )
            )

        startup_window_elapsed_ms = None

        if (
            startup_window_start_exercise_elapsed_ms
            is not None
            and startup_window_end_exercise_elapsed_ms
            is not None
        ):
            startup_window_elapsed_ms = (
                startup_window_end_exercise_elapsed_ms
                - startup_window_start_exercise_elapsed_ms
            )

        available = bool(
            selected_observations
        )

        reason = None

        if not points:
            reason = (
                "ROUTE_POINTS_UNAVAILABLE"
            )
        elif anomaly_route is None:
            reason = (
                "MOTION_ANOMALY_ROUTE_UNAVAILABLE"
            )
        elif not selected_observations:
            reason = (
                "STARTUP_OBSERVATIONS_UNAVAILABLE"
            )

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": (
                    exercise_index
                ),
                "available": available,
                "reason": reason,
                "startup_segment_count_target": (
                    startup_segment_count
                ),
                "route_candidate_segment_count": (
                    route_candidate_segment_count
                ),
                "expected_startup_segment_count": (
                    expected_segment_count
                ),
                "observed_startup_segment_count": (
                    len(
                        selected_observations
                    )
                ),
                "target_segment_count_reached": (
                    len(
                        selected_observations
                    )
                    == startup_segment_count
                ),
                "expected_segment_indices": (
                    expected_segment_indices
                ),
                "missing_expected_segment_indices": (
                    missing_segment_indices
                ),
                "route_start_offset_ms": (
                    route_start_offset_ms
                ),
                "first_route_waypoint_source_elapsed_ms": (
                    first_route_waypoint_source_elapsed_ms
                ),
                "first_route_waypoint_exercise_elapsed_ms": (
                    first_route_waypoint_exercise_elapsed_ms
                ),
                "startup_window_start_exercise_elapsed_ms": (
                    startup_window_start_exercise_elapsed_ms
                ),
                "startup_window_end_exercise_elapsed_ms": (
                    startup_window_end_exercise_elapsed_ms
                ),
                "startup_window_elapsed_ms": (
                    startup_window_elapsed_ms
                ),
                "trajectory": trajectory,
                "trajectory_summary": (
                    build_speed_trajectory_summary(
                        trajectory
                    )
                ),
                "geometry": (
                    _geometry_summary(
                        selected_observations,
                        selected_segment_indices=(
                            selected_segment_indices
                        ),
                    )
                ),
                "temporal_residual": (
                    _temporal_residual_summary(
                        selected_observations,
                        selected_segment_indices=(
                            selected_segment_indices
                        ),
                    )
                ),
                "cross_source_speed": (
                    _cross_source_speed_summary(
                        selected_observations
                    )
                ),
            }
        )

    return {
        "provider": (
            normalized_routes.get(
                "provider"
            )
            or motion_anomaly_evidence.get(
                "provider"
            )
        ),
        "available": any(
            route.get(
                "available"
            )
            for route in route_results
        ),
        "startup_segment_count_target": (
            startup_segment_count
        ),
        "route_count": (
            len(
                route_results
            )
        ),
        "routes": route_results,
    }
