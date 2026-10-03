from __future__ import annotations

import math
from typing import Any


DEFAULT_REGION_LIMIT = 10


DIMENSIONS = (
    (
        "cross_track_deviation",
        "maximum_middle_point_cross_track_deviation_m",
    ),
    (
        "heading_change_rate",
        "maximum_heading_change_rate_deg_per_sec",
    ),
    (
        "absolute_speed_residual",
        "maximum_absolute_speed_residual_mps",
    ),
    (
        "compensating_residual_distance",
        "maximum_compensating_residual_distance_m",
    ),
    (
        "residual_cancellation",
        "window_residual_cancellation_fraction",
    ),
    (
        "gps_polar_speed_difference",
        "maximum_absolute_gps_polar_speed_difference_mps",
    ),
    (
        "same_sign_residual_run_duration",
        "longest_same_sign_residual_run_duration_ms",
    ),
)


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


def _segment_range(
    window: dict[str, Any],
) -> tuple[int, int] | None:
    start = _integer(
        window.get(
            "window_start_segment_index"
        )
    )

    end = _integer(
        window.get(
            "window_end_segment_index"
        )
    )

    if (
        start is None
        or end is None
        or end < start
    ):
        return None

    return (
        start,
        end,
    )


def _ranges_overlap(
    first: tuple[int, int],
    second: tuple[int, int],
) -> bool:
    return (
        first[0] <= second[1]
        and second[0] <= first[1]
    )


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


def _build_dimension_regions(
    windows: list[dict[str, Any]],
    *,
    dimension_key: str,
    metric_field: str,
    region_limit: int,
) -> list[dict[str, Any]]:
    candidates: list[
        tuple[
            float,
            int,
            tuple[int, int],
            dict[str, Any],
        ]
    ] = []

    for window in windows:
        value = _finite_number(
            window.get(metric_field)
        )

        segment_range = _segment_range(
            window
        )

        if (
            value is None
            or segment_range is None
        ):
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
                segment_range,
                window,
            )
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            -item[1],
        ),
        reverse=True,
    )

    regions: list[
        dict[str, Any]
    ] = []

    remaining = candidates

    while (
        remaining
        and len(regions)
        < region_limit
    ):
        (
            metric_value,
            center_segment_index,
            representative_range,
            representative_window,
        ) = remaining[0]

        suppressed = []

        next_remaining = []

        for candidate in remaining[1:]:
            if _ranges_overlap(
                representative_range,
                candidate[2],
            ):
                suppressed.append(
                    candidate
                )
            else:
                next_remaining.append(
                    candidate
                )

        regions.append(
            {
                "rank": (
                    len(regions) + 1
                ),
                "dimension_key": (
                    dimension_key
                ),
                "metric_field": (
                    metric_field
                ),
                "metric_value": (
                    metric_value
                ),
                "region_start_segment_index": (
                    representative_range[0]
                ),
                "region_end_segment_index": (
                    representative_range[1]
                ),
                "representative_center_segment_index": (
                    center_segment_index
                ),
                "suppressed_overlapping_window_count": (
                    len(suppressed)
                ),
                "suppressed_overlapping_center_segment_indices": [
                    candidate[1]
                    for candidate in suppressed
                ],
                "representative_window": (
                    _compact_window(
                        representative_window
                    )
                ),
            }
        )

        remaining = (
            next_remaining
        )

    return regions


def build_route_motion_evidence_regions(
    evidence_windows: dict[
        str,
        Any,
    ],
    *,
    region_limit: int = (
        DEFAULT_REGION_LIMIT
    ),
) -> dict[str, Any]:
    if region_limit < 1:
        raise ValueError(
            "region_limit must be >= 1"
        )

    route_results = []

    for route_position, route in enumerate(
        evidence_windows.get(
            "routes"
        )
        or []
    ):
        if not isinstance(
            route,
            dict,
        ):
            continue

        windows = [
            window
            for window in (
                route.get(
                    "windows"
                )
                or []
            )
            if isinstance(
                window,
                dict,
            )
        ]

        dimensions = {}

        for (
            dimension_key,
            metric_field,
        ) in DIMENSIONS:
            dimensions[
                dimension_key
            ] = (
                _build_dimension_regions(
                    windows,
                    dimension_key=(
                        dimension_key
                    ),
                    metric_field=(
                        metric_field
                    ),
                    region_limit=(
                        region_limit
                    ),
                )
            )

        route_results.append(
            {
                "route_index": (
                    route.get(
                        "route_index",
                        route_position,
                    )
                ),
                "exercise_index": (
                    route.get(
                        "exercise_index"
                    )
                ),
                "available": bool(
                    windows
                ),
                "observation_count": (
                    route.get(
                        "observation_count"
                    )
                ),
                "window_count": (
                    len(windows)
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
                "region_limit": (
                    region_limit
                ),
                "dimensions": (
                    dimensions
                ),
            }
        )

    return {
        "provider": (
            evidence_windows.get(
                "provider"
            )
        ),
        "available": any(
            route.get(
                "available"
            )
            for route in route_results
        ),
        "route_count": (
            len(route_results)
        ),
        "region_limit": (
            region_limit
        ),
        "routes": route_results,
    }