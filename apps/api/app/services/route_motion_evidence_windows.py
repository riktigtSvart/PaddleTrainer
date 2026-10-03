from __future__ import annotations

import math
import statistics
from typing import Any


DEFAULT_WINDOW_RADIUS_SEGMENTS = 2
DEFAULT_EXTREME_WINDOW_LIMIT = 10


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


def _median(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return float(
        statistics.median(values)
    )


def _minimum(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return min(values)


def _maximum(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return max(values)


def _cancellation_fraction(
    values: list[float],
) -> float | None:
    if not values:
        return None

    absolute_sum = sum(
        abs(value)
        for value in values
    )

    if absolute_sum <= 0.0:
        return None

    result = (
        1.0
        - abs(sum(values))
        / absolute_sum
    )

    return max(
        0.0,
        min(
            1.0,
            result,
        ),
    )


def _opposite_nonzero_sign(
    first: float,
    second: float,
) -> bool:
    return (
        (
            first > 0.0
            and second < 0.0
        )
        or
        (
            first < 0.0
            and second > 0.0
        )
    )


def _build_residual_context(
    observations: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    speed_residuals = [
        value
        for observation
        in observations
        if (
            value := _finite_number(
                observation.get(
                    "speed_residual_mps"
                )
            )
        )
        is not None
    ]

    distance_residuals = [
        value
        for observation
        in observations
        if (
            value := _finite_number(
                observation.get(
                    "speed_residual_distance_m"
                )
            )
        )
        is not None
    ]

    sign_reversal_count = 0

    compensation_distances: list[
        float
    ] = []

    adjacent_cancellation_fractions: list[
        float
    ] = []

    for position in range(
        len(observations) - 1
    ):
        current = _finite_number(
            observations[position].get(
                "speed_residual_distance_m"
            )
        )

        following = _finite_number(
            observations[
                position + 1
            ].get(
                "speed_residual_distance_m"
            )
        )

        if (
            current is None
            or following is None
        ):
            continue

        if not _opposite_nonzero_sign(
            current,
            following,
        ):
            continue

        sign_reversal_count += 1

        compensation_distances.append(
            min(
                abs(current),
                abs(following),
            )
        )

        pair_absolute_sum = (
            abs(current)
            + abs(following)
        )

        if pair_absolute_sum > 0.0:
            pair_cancellation = (
                1.0
                - abs(
                    current
                    + following
                )
                / pair_absolute_sum
            )

            adjacent_cancellation_fractions.append(
                max(
                    0.0,
                    min(
                        1.0,
                        pair_cancellation,
                    ),
                )
            )

    longest_run_count = 0
    longest_run_duration_ms = 0

    current_sign: int | None = None
    current_run_count = 0
    current_run_duration_ms = 0

    for observation in observations:
        residual = _finite_number(
            observation.get(
                "speed_residual_mps"
            )
        )

        interval_ms = _integer(
            observation.get(
                "interval_ms"
            )
        )

        if (
            residual is None
            or residual == 0.0
        ):
            current_sign = None
            current_run_count = 0
            current_run_duration_ms = 0
            continue

        sign = (
            1
            if residual > 0.0
            else -1
        )

        if sign == current_sign:
            current_run_count += 1
        else:
            current_sign = sign
            current_run_count = 1
            current_run_duration_ms = 0

        if (
            interval_ms is not None
            and interval_ms > 0
        ):
            current_run_duration_ms += (
                interval_ms
            )

        if (
            current_run_count
            > longest_run_count
        ):
            longest_run_count = (
                current_run_count
            )

        if (
            current_run_duration_ms
            > longest_run_duration_ms
        ):
            longest_run_duration_ms = (
                current_run_duration_ms
            )

    return {
        "speed_residual_observation_count": (
            len(speed_residuals)
        ),
        "maximum_absolute_speed_residual_mps": (
            max(
                (
                    abs(value)
                    for value
                    in speed_residuals
                ),
                default=None,
            )
        ),
        "residual_distance_observation_count": (
            len(distance_residuals)
        ),
        "signed_residual_distance_sum_m": (
            sum(distance_residuals)
            if distance_residuals
            else None
        ),
        "absolute_residual_distance_sum_m": (
            sum(
                abs(value)
                for value
                in distance_residuals
            )
            if distance_residuals
            else None
        ),
        "window_residual_cancellation_fraction": (
            _cancellation_fraction(
                distance_residuals
            )
        ),
        "residual_sign_reversal_count": (
            sign_reversal_count
        ),
        "maximum_compensating_residual_distance_m": (
            _maximum(
                compensation_distances
            )
        ),
        "maximum_adjacent_residual_cancellation_fraction": (
            _maximum(
                adjacent_cancellation_fractions
            )
        ),
        "longest_same_sign_residual_run_segment_count": (
            longest_run_count
        ),
        "longest_same_sign_residual_run_duration_ms": (
            longest_run_duration_ms
        ),
    }


def _build_geometry_context(
    observations: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    segment_indices = {
        segment_index
        for observation
        in observations
        if (
            segment_index := _integer(
                observation.get(
                    "segment_index"
                )
            )
        )
        is not None
    }

    cross_track_values: list[
        float
    ] = []

    heading_change_rates: list[
        float
    ] = []

    implied_turn_radii: list[
        float
    ] = []

    path_excess_values: list[
        float
    ] = []

    net_displacement_fractions: list[
        float
    ] = []

    along_track_fractions: list[
        float
    ] = []

    geometry_pair_count = 0

    for observation in observations:
        pair = observation.get(
            "forward_pair"
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

        # A pair only belongs to the window if
        # both of its segments are inside it.
        if (
            first_segment_index
            not in segment_indices
            or second_segment_index
            not in segment_indices
        ):
            continue

        geometry_pair_count += 1

        value = _finite_number(
            pair.get(
                "middle_point_"
                "cross_track_deviation_m"
            )
        )

        if value is not None:
            cross_track_values.append(
                value
            )

        value = _finite_number(
            pair.get(
                "heading_change_rate_"
                "deg_per_sec"
            )
        )

        if value is not None:
            heading_change_rates.append(
                value
            )

        value = _finite_number(
            pair.get(
                "implied_turn_radius_m"
            )
        )

        if (
            value is not None
            and value >= 0.0
        ):
            implied_turn_radii.append(
                value
            )

        value = _finite_number(
            pair.get(
                "path_minus_"
                "net_displacement_m"
            )
        )

        if value is not None:
            path_excess_values.append(
                value
            )

        value = _finite_number(
            pair.get(
                "net_displacement_"
                "fraction_of_path"
            )
        )

        if value is not None:
            net_displacement_fractions.append(
                value
            )

        value = _finite_number(
            pair.get(
                "middle_point_"
                "along_track_fraction"
            )
        )

        if value is not None:
            along_track_fractions.append(
                value
            )

    outside_unit_interval_count = sum(
        1
        for value
        in along_track_fractions
        if (
            value < 0.0
            or value > 1.0
        )
    )

    return {
        "geometry_pair_count": (
            geometry_pair_count
        ),
        "maximum_middle_point_cross_track_deviation_m": (
            _maximum(
                cross_track_values
            )
        ),
        "maximum_heading_change_rate_deg_per_sec": (
            _maximum(
                heading_change_rates
            )
        ),
        "minimum_implied_turn_radius_m": (
            _minimum(
                implied_turn_radii
            )
        ),
        "path_minus_net_displacement_sum_m": (
            sum(path_excess_values)
            if path_excess_values
            else None
        ),
        "maximum_path_minus_net_displacement_m": (
            _maximum(
                path_excess_values
            )
        ),
        "minimum_net_displacement_fraction_of_path": (
            _minimum(
                net_displacement_fractions
            )
        ),
        "minimum_middle_point_along_track_fraction": (
            _minimum(
                along_track_fractions
            )
        ),
        "maximum_middle_point_along_track_fraction": (
            _maximum(
                along_track_fractions
            )
        ),
        "middle_point_along_track_outside_unit_interval_count": (
            outside_unit_interval_count
        ),
    }


def _build_cross_source_context(
    observations: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    signed_differences: list[
        float
    ] = []

    absolute_differences: list[
        float
    ] = []

    for observation in observations:
        signed_difference = (
            _finite_number(
                observation.get(
                    "gps_minus_"
                    "polar_speed_mps"
                )
            )
        )

        absolute_difference = (
            _finite_number(
                observation.get(
                    "absolute_gps_"
                    "polar_speed_difference_mps"
                )
            )
        )

        if signed_difference is not None:
            signed_differences.append(
                signed_difference
            )

        if absolute_difference is not None:
            absolute_differences.append(
                absolute_difference
            )
        elif signed_difference is not None:
            absolute_differences.append(
                abs(signed_difference)
            )

    return {
        "gps_polar_comparison_count": (
            len(absolute_differences)
        ),
        "mean_gps_minus_polar_speed_mps": (
            _mean(
                signed_differences
            )
        ),
        "median_gps_minus_polar_speed_mps": (
            _median(
                signed_differences
            )
        ),
        "mean_absolute_gps_polar_speed_difference_mps": (
            _mean(
                absolute_differences
            )
        ),
        "median_absolute_gps_polar_speed_difference_mps": (
            _median(
                absolute_differences
            )
        ),
        "maximum_absolute_gps_polar_speed_difference_mps": (
            _maximum(
                absolute_differences
            )
        ),
    }


def _build_speed_context(
    observations: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    speeds = [
        value
        for observation
        in observations
        if (
            value := _finite_number(
                observation.get(
                    "gps_ground_speed_mps"
                )
            )
        )
        is not None
    ]

    return {
        "gps_ground_speed_observation_count": (
            len(speeds)
        ),
        "minimum_gps_ground_speed_mps": (
            _minimum(speeds)
        ),
        "maximum_gps_ground_speed_mps": (
            _maximum(speeds)
        ),
        "mean_gps_ground_speed_mps": (
            _mean(speeds)
        ),
        "median_gps_ground_speed_mps": (
            _median(speeds)
        ),
    }


def _build_window(
    observations: list[
        dict[str, Any]
    ],
    *,
    center_position: int,
    start_position: int,
    end_position: int,
) -> dict[str, Any]:
    window_observations = (
        observations[
            start_position:end_position
        ]
    )

    center = observations[
        center_position
    ]

    first = (
        window_observations[0]
        if window_observations
        else {}
    )

    last = (
        window_observations[-1]
        if window_observations
        else {}
    )

    start_elapsed_ms = _integer(
        first.get(
            "start_exercise_elapsed_ms"
        )
    )

    end_elapsed_ms = _integer(
        last.get(
            "end_exercise_elapsed_ms"
        )
    )

    elapsed_ms = (
        end_elapsed_ms
        - start_elapsed_ms
        if (
            start_elapsed_ms is not None
            and end_elapsed_ms is not None
            and end_elapsed_ms
            >= start_elapsed_ms
        )
        else None
    )

    motion_observation_count = sum(
        1
        for observation
        in window_observations
        if (
            observation.get(
                "motion_available"
            )
            is True
        )
    )

    return {
        "center_segment_index": (
            center.get(
                "segment_index"
            )
        ),
        "window_start_segment_index": (
            first.get(
                "segment_index"
            )
        ),
        "window_end_segment_index": (
            last.get(
                "segment_index"
            )
        ),
        "segment_count": (
            len(window_observations)
        ),
        "motion_observation_count": (
            motion_observation_count
        ),
        "start_exercise_elapsed_ms": (
            start_elapsed_ms
        ),
        "end_exercise_elapsed_ms": (
            end_elapsed_ms
        ),
        "elapsed_ms": elapsed_ms,
        "window_start_time_since_route_start_ms": (
            first.get(
                "time_since_route_start_ms"
            )
        ),
        "center_time_since_route_start_ms": (
            center.get(
                "time_since_route_start_ms"
            )
        ),
        **_build_speed_context(
            window_observations
        ),
        **_build_geometry_context(
            window_observations
        ),
        **_build_residual_context(
            window_observations
        ),
        **_build_cross_source_context(
            window_observations
        ),
    }


def build_route_motion_evidence_windows(
    motion_anomaly_evidence: dict[
        str,
        Any,
    ],
    *,
    window_radius_segments: int = (
        DEFAULT_WINDOW_RADIUS_SEGMENTS
    ),
) -> dict[str, Any]:
    if window_radius_segments < 0:
        raise ValueError(
            "window_radius_segments "
            "must be >= 0"
        )

    raw_routes = (
        motion_anomaly_evidence.get(
            "routes"
        )
        or []
    )

    route_results: list[
        dict[str, Any]
    ] = []

    total_window_count = 0

    for route_position, raw_route in enumerate(
        raw_routes
    ):
        if not isinstance(
            raw_route,
            dict,
        ):
            continue

        observations = [
            observation
            for observation
            in (
                raw_route.get(
                    "observations"
                )
                or []
            )
            if isinstance(
                observation,
                dict,
            )
        ]

        windows: list[
            dict[str, Any]
        ] = []

        for center_position in range(
            len(observations)
        ):
            start_position = max(
                0,
                center_position
                - window_radius_segments,
            )

            end_position = min(
                len(observations),
                center_position
                + window_radius_segments
                + 1,
            )

            windows.append(
                _build_window(
                    observations,
                    center_position=(
                        center_position
                    ),
                    start_position=(
                        start_position
                    ),
                    end_position=(
                        end_position
                    ),
                )
            )

        total_window_count += len(
            windows
        )

        route_results.append(
            {
                "route_index": (
                    route_position
                ),
                "exercise_index": (
                    raw_route.get(
                        "exercise_index"
                    )
                ),
                "available": bool(
                    windows
                ),
                "observation_count": (
                    len(observations)
                ),
                "window_count": (
                    len(windows)
                ),
                "window_radius_segments": (
                    window_radius_segments
                ),
                "target_window_size_segments": (
                    window_radius_segments
                    * 2
                    + 1
                ),
                "windows": windows,
            }
        )

    return {
        "provider": (
            motion_anomaly_evidence.get(
                "provider"
            )
        ),
        "available": bool(
            total_window_count
        ),
        "window_radius_segments": (
            window_radius_segments
        ),
        "target_window_size_segments": (
            window_radius_segments
            * 2
            + 1
        ),
        "route_count": (
            len(route_results)
        ),
        "window_count": (
            total_window_count
        ),
        "routes": route_results,
    }


def _compact_window(
    window: dict[str, Any],
) -> dict[str, Any]:
    fields = (
        "center_segment_index",
        "window_start_segment_index",
        "window_end_segment_index",
        "segment_count",
        "motion_observation_count",
        "start_exercise_elapsed_ms",
        "end_exercise_elapsed_ms",
        "elapsed_ms",
        "window_start_time_since_route_start_ms",
        "center_time_since_route_start_ms",
        "minimum_gps_ground_speed_mps",
        "maximum_gps_ground_speed_mps",
        "mean_gps_ground_speed_mps",
        "maximum_middle_point_cross_track_deviation_m",
        "maximum_heading_change_rate_deg_per_sec",
        "minimum_implied_turn_radius_m",
        "path_minus_net_displacement_sum_m",
        "maximum_path_minus_net_displacement_m",
        "minimum_net_displacement_fraction_of_path",
        "minimum_middle_point_along_track_fraction",
        "maximum_middle_point_along_track_fraction",
        "middle_point_along_track_outside_unit_interval_count",
        "maximum_absolute_speed_residual_mps",
        "signed_residual_distance_sum_m",
        "absolute_residual_distance_sum_m",
        "window_residual_cancellation_fraction",
        "residual_sign_reversal_count",
        "maximum_compensating_residual_distance_m",
        "maximum_adjacent_residual_cancellation_fraction",
        "longest_same_sign_residual_run_segment_count",
        "longest_same_sign_residual_run_duration_ms",
        "gps_polar_comparison_count",
        "mean_absolute_gps_polar_speed_difference_mps",
        "maximum_absolute_gps_polar_speed_difference_mps",
    )

    return {
        field: window.get(field)
        for field in fields
    }


def _rank_windows(
    windows: list[dict[str, Any]],
    *,
    field: str,
    limit: int,
    reverse: bool = True,
) -> list[dict[str, Any]]:
    candidates: list[
        tuple[float, int, dict[str, Any]]
    ] = []

    for window in windows:
        value = _finite_number(
            window.get(field)
        )

        if value is None:
            continue

        center_segment_index = (
            _integer(
                window.get(
                    "center_segment_index"
                )
            )
        )

        candidates.append(
            (
                value,
                (
                    center_segment_index
                    if center_segment_index
                    is not None
                    else -1
                ),
                window,
            )
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=reverse,
    )

    return [
        _compact_window(item[2])
        for item in candidates[:limit]
    ]


def build_route_motion_evidence_windows_summary(
    evidence_windows: dict[str, Any],
    *,
    extreme_window_limit: int = (
        DEFAULT_EXTREME_WINDOW_LIMIT
    ),
) -> dict[str, Any]:
    if extreme_window_limit < 1:
        raise ValueError(
            "extreme_window_limit "
            "must be >= 1"
        )

    route_results: list[
        dict[str, Any]
    ] = []

    for route in (
        evidence_windows.get("routes")
        or []
    ):
        if not isinstance(route, dict):
            continue

        windows = [
            window
            for window in (
                route.get("windows")
                or []
            )
            if isinstance(
                window,
                dict,
            )
        ]

        extremes = {
            "highest_window_cross_track_deviation": (
                _rank_windows(
                    windows,
                    field=(
                        "maximum_middle_point_"
                        "cross_track_deviation_m"
                    ),
                    limit=extreme_window_limit,
                )
            ),
            "highest_window_heading_change_rate": (
                _rank_windows(
                    windows,
                    field=(
                        "maximum_heading_change_"
                        "rate_deg_per_sec"
                    ),
                    limit=extreme_window_limit,
                )
            ),
            "highest_window_absolute_speed_residual": (
                _rank_windows(
                    windows,
                    field=(
                        "maximum_absolute_"
                        "speed_residual_mps"
                    ),
                    limit=extreme_window_limit,
                )
            ),
            "highest_window_compensating_residual_distance": (
                _rank_windows(
                    windows,
                    field=(
                        "maximum_compensating_"
                        "residual_distance_m"
                    ),
                    limit=extreme_window_limit,
                )
            ),
            "highest_window_residual_cancellation_fraction": (
                _rank_windows(
                    windows,
                    field=(
                        "window_residual_"
                        "cancellation_fraction"
                    ),
                    limit=extreme_window_limit,
                )
            ),
            "highest_window_gps_polar_speed_difference": (
                _rank_windows(
                    windows,
                    field=(
                        "maximum_absolute_gps_"
                        "polar_speed_difference_mps"
                    ),
                    limit=extreme_window_limit,
                )
            ),
            "longest_window_same_sign_residual_run": (
                _rank_windows(
                    windows,
                    field=(
                        "longest_same_sign_"
                        "residual_run_duration_ms"
                    ),
                    limit=extreme_window_limit,
                )
            ),
        }

        route_results.append(
            {
                "route_index": (
                    route.get(
                        "route_index"
                    )
                ),
                "exercise_index": (
                    route.get(
                        "exercise_index"
                    )
                ),
                "available": (
                    route.get(
                        "available"
                    )
                ),
                "observation_count": (
                    route.get(
                        "observation_count"
                    )
                ),
                "window_count": (
                    route.get(
                        "window_count"
                    )
                ),
                "window_radius_segments": (
                    route.get(
                        "window_radius_segments"
                    )
                ),
                "target_window_size_segments": (
                    route.get(
                        "target_window_size_segments"
                    )
                ),
                "extreme_window_limit": (
                    extreme_window_limit
                ),
                "extremes": extremes,
            }
        )

    return {
        "provider": (
            evidence_windows.get(
                "provider"
            )
        ),
        "available": (
            evidence_windows.get(
                "available"
            )
        ),
        "window_radius_segments": (
            evidence_windows.get(
                "window_radius_segments"
            )
        ),
        "target_window_size_segments": (
            evidence_windows.get(
                "target_window_size_segments"
            )
        ),
        "route_count": (
            evidence_windows.get(
                "route_count"
            )
        ),
        "window_count": (
            evidence_windows.get(
                "window_count"
            )
        ),
        "extreme_window_limit": (
            extreme_window_limit
        ),
        "routes": route_results,
    }