from __future__ import annotations

import math
import statistics
from typing import Any


DEFAULT_RANKING_LIMIT = 10


FAMILY_DIMENSIONS = {
    "geometry": (
        "cross_track_deviation",
        "heading_change_rate",
    ),
    "temporal": (
        "absolute_speed_residual",
        "compensating_residual_distance",
        "residual_cancellation",
        "same_sign_residual_run_duration",
    ),
    "cross_source": (
        "gps_polar_speed_difference",
    ),
}


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


def _range(
    item: dict[str, Any],
    *,
    start_key: str,
    end_key: str,
) -> tuple[int, int] | None:
    start = _integer(
        item.get(start_key)
    )

    end = _integer(
        item.get(end_key)
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


def _center_inside(
    center: int,
    region: dict[str, Any],
) -> bool:
    region_range = _range(
        region,
        start_key=(
            "region_start_segment_index"
        ),
        end_key=(
            "region_end_segment_index"
        ),
    )

    if region_range is None:
        return False

    return (
        region_range[0]
        <= center
        <= region_range[1]
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


def _build_region_profile(
    anchor: dict[str, Any],
    dimensions: dict[str, Any],
    dimension_keys: tuple[str, ...],
) -> dict[str, Any] | None:
    center = _integer(
        anchor.get(
            "representative_center_segment_index"
        )
    )

    anchor_range = _range(
        anchor,
        start_key=(
            "region_start_segment_index"
        ),
        end_key=(
            "region_end_segment_index"
        ),
    )

    if (
        center is None
        or anchor_range is None
    ):
        return None

    support = []

    for dimension_key in dimension_keys:
        regions = (
            dimensions.get(
                dimension_key
            )
            or []
        )

        matching = [
            region
            for region in regions
            if (
                isinstance(region, dict)
                and _center_inside(
                    center,
                    region,
                )
            )
        ]

        if not matching:
            continue

        matching.sort(
            key=lambda region: (
                _integer(
                    region.get("rank")
                )
                or 10**9
            )
        )

        region = matching[0]

        support.append(
            {
                "dimension_key": (
                    dimension_key
                ),
                "rank": (
                    region.get("rank")
                ),
                "metric_field": (
                    region.get(
                        "metric_field"
                    )
                ),
                "metric_value": (
                    region.get(
                        "metric_value"
                    )
                ),
                "region_start_segment_index": (
                    region.get(
                        "region_start_segment_index"
                    )
                ),
                "region_end_segment_index": (
                    region.get(
                        "region_end_segment_index"
                    )
                ),
            }
        )

    support_ranks = [
        rank
        for item in support
        if (
            rank := _integer(
                item.get("rank")
            )
        )
        is not None
    ]

    return {
        "anchor_dimension_key": (
            anchor.get(
                "dimension_key"
            )
        ),
        "anchor_dimension_rank": (
            anchor.get(
                "rank"
            )
        ),
        "region_start_segment_index": (
            anchor_range[0]
        ),
        "region_end_segment_index": (
            anchor_range[1]
        ),
        "representative_center_segment_index": (
            center
        ),
        "support_dimension_count": (
            len(support)
        ),
        "best_support_rank": (
            min(support_ranks)
            if support_ranks
            else None
        ),
        "median_support_rank": (
            float(
                statistics.median(
                    support_ranks
                )
            )
            if support_ranks
            else None
        ),
        "supporting_dimensions": (
            support
        ),
        "representative_window": (
            anchor.get(
                "representative_window"
            )
        ),
    }


def _build_family_ranking(
    dimensions: dict[str, Any],
    *,
    dimension_keys: tuple[str, ...],
    ranking_limit: int,
) -> list[dict[str, Any]]:
    candidates = []

    for dimension_key in dimension_keys:
        for region in (
            dimensions.get(
                dimension_key
            )
            or []
        ):
            if not isinstance(
                region,
                dict,
            ):
                continue

            profile = (
                _build_region_profile(
                    region,
                    dimensions,
                    dimension_keys,
                )
            )

            if profile is not None:
                candidates.append(
                    profile
                )

    candidates.sort(
        key=lambda item: (
            -(
                _integer(
                    item.get(
                        "support_dimension_count"
                    )
                )
                or 0
            ),
            (
                _integer(
                    item.get(
                        "best_support_rank"
                    )
                )
                or 10**9
            ),
            (
                _finite_number(
                    item.get(
                        "median_support_rank"
                    )
                )
                or float("inf")
            ),
            (
                _integer(
                    item.get(
                        "anchor_dimension_rank"
                    )
                )
                or 10**9
            ),
            (
                _integer(
                    item.get(
                        "representative_center_segment_index"
                    )
                )
                or 10**9
            ),
        )
    )

    selected = []

    for candidate in candidates:
        candidate_range = _range(
            candidate,
            start_key=(
                "region_start_segment_index"
            ),
            end_key=(
                "region_end_segment_index"
            ),
        )

        if candidate_range is None:
            continue

        if any(
            _ranges_overlap(
                candidate_range,
                selected_range,
            )
            for selected_range
            in (
                _range(
                    selected_item,
                    start_key=(
                        "region_start_segment_index"
                    ),
                    end_key=(
                        "region_end_segment_index"
                    ),
                )
                for selected_item
                in selected
            )
            if selected_range is not None
        ):
            continue

        selected.append(
            candidate
        )

        if (
            len(selected)
            >= ranking_limit
        ):
            break

    for position, item in enumerate(
        selected,
        start=1,
    ):
        item["inspection_rank"] = (
            position
        )

    return selected


def _build_speed_transition_ranking(
    windows: list[dict[str, Any]],
    *,
    ranking_limit: int,
) -> list[dict[str, Any]]:
    candidates = []

    for window in windows:
        minimum_speed = _finite_number(
            window.get(
                "minimum_gps_ground_speed_mps"
            )
        )

        maximum_speed = _finite_number(
            window.get(
                "maximum_gps_ground_speed_mps"
            )
        )

        window_range = _range(
            window,
            start_key=(
                "window_start_segment_index"
            ),
            end_key=(
                "window_end_segment_index"
            ),
        )

        if (
            minimum_speed is None
            or maximum_speed is None
            or window_range is None
        ):
            continue

        speed_range = (
            maximum_speed
            - minimum_speed
        )

        if speed_range < 0.0:
            continue

        candidates.append(
            {
                "gps_ground_speed_range_mps": (
                    speed_range
                ),
                "minimum_gps_ground_speed_mps": (
                    minimum_speed
                ),
                "maximum_gps_ground_speed_mps": (
                    maximum_speed
                ),
                "window_start_segment_index": (
                    window_range[0]
                ),
                "window_end_segment_index": (
                    window_range[1]
                ),
                "center_segment_index": (
                    window.get(
                        "center_segment_index"
                    )
                ),
                "center_time_since_route_start_ms": (
                    window.get(
                        "center_time_since_route_start_ms"
                    )
                ),
                "representative_window": (
                    _compact_window(
                        window
                    )
                ),
            }
        )

    candidates.sort(
        key=lambda item: (
            -item[
                "gps_ground_speed_range_mps"
            ],
            (
                _integer(
                    item.get(
                        "center_segment_index"
                    )
                )
                or 10**9
            ),
        )
    )

    selected = []

    for candidate in candidates:
        candidate_range = (
            candidate[
                "window_start_segment_index"
            ],
            candidate[
                "window_end_segment_index"
            ],
        )

        if any(
            _ranges_overlap(
                candidate_range,
                (
                    existing[
                        "window_start_segment_index"
                    ],
                    existing[
                        "window_end_segment_index"
                    ],
                ),
            )
            for existing
            in selected
        ):
            continue

        selected.append(
            candidate
        )

        if (
            len(selected)
            >= ranking_limit
        ):
            break

    for position, item in enumerate(
        selected,
        start=1,
    ):
        item["inspection_rank"] = (
            position
        )

    return selected


def build_route_motion_evidence_ranking(
    evidence_windows: dict[
        str,
        Any,
    ],
    evidence_regions: dict[
        str,
        Any,
    ],
    *,
    ranking_limit: int = (
        DEFAULT_RANKING_LIMIT
    ),
) -> dict[str, Any]:
    if ranking_limit < 1:
        raise ValueError(
            "ranking_limit must be >= 1"
        )

    window_routes = {
        route.get(
            "exercise_index"
        ): route
        for route in (
            evidence_windows.get(
                "routes"
            )
            or []
        )
        if isinstance(
            route,
            dict,
        )
    }

    route_results = []

    for region_route in (
        evidence_regions.get(
            "routes"
        )
        or []
    ):
        if not isinstance(
            region_route,
            dict,
        ):
            continue

        exercise_index = (
            region_route.get(
                "exercise_index"
            )
        )

        window_route = (
            window_routes.get(
                exercise_index
            )
            or {}
        )

        dimensions = (
            region_route.get(
                "dimensions"
            )
            or {}
        )

        windows = [
            window
            for window in (
                window_route.get(
                    "windows"
                )
                or []
            )
            if isinstance(
                window,
                dict,
            )
        ]

        families = {}

        for (
            family_key,
            dimension_keys,
        ) in FAMILY_DIMENSIONS.items():
            families[
                family_key
            ] = (
                _build_family_ranking(
                    dimensions,
                    dimension_keys=(
                        dimension_keys
                    ),
                    ranking_limit=(
                        ranking_limit
                    ),
                )
            )

        route_results.append(
            {
                "exercise_index": (
                    exercise_index
                ),
                "available": bool(
                    windows
                    or dimensions
                ),
                "ranking_limit": (
                    ranking_limit
                ),
                "families": (
                    families
                ),
                "speed_transition": (
                    _build_speed_transition_ranking(
                        windows,
                        ranking_limit=(
                            ranking_limit
                        ),
                    )
                ),
            }
        )

    return {
        "provider": (
            evidence_regions.get(
                "provider"
            )
            or evidence_windows.get(
                "provider"
            )
        ),
        "available": any(
            route.get("available")
            for route in route_results
        ),
        "ranking_limit": (
            ranking_limit
        ),
        "route_count": (
            len(route_results)
        ),
        "routes": route_results,
    }