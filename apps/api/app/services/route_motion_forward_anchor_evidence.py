from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


CRITERIA_VERSION = "0.1"

DEFAULT_THRESHOLDS = {
    "minimum_path_distance_m": 1.0,
    "minimum_net_displacement_fraction_of_path": 0.98,
    "maximum_path_minus_net_displacement_m": 0.25,
    "maximum_intermediate_cross_track_m": 0.25,
    "maximum_adjacent_interval_ms": 1500,
    "maximum_along_track_outside_unit_interval_count": 0,
    "minimum_consecutive_coherent_windows": 3,
    "inspection_window_limit": 20,
}


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


def _route_lookup(
    evidence: dict[str, Any],
) -> dict[
    tuple[int, int | None],
    dict[str, Any],
]:
    result = {}

    for route_position, route in enumerate(
        evidence.get("routes") or []
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


def _match_startup_route(
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
            (_candidate_route_index, candidate_exercise_index),
            route,
        )
        in lookup.items()
        if candidate_exercise_index
        == exercise_index
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def _window_evaluation(
    window: dict[str, Any],
    *,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    path_distance_m = _finite_number(
        window.get(
            "path_distance_m"
        )
    )
    net_fraction = _finite_number(
        window.get(
            "net_displacement_fraction_of_path"
        )
    )
    path_minus_net_m = _finite_number(
        window.get(
            "path_minus_net_displacement_m"
        )
    )
    cross_track_m = _finite_number(
        window.get(
            "maximum_intermediate_point_cross_track_deviation_m"
        )
    )
    maximum_interval_ms = _integer(
        window.get(
            "maximum_adjacent_interval_ms"
        )
    )
    outside_count = _integer(
        window.get(
            "intermediate_point_along_track_outside_unit_interval_count"
        )
    )

    path_distance_passed = (
        path_distance_m is not None
        and path_distance_m
        >= thresholds[
            "minimum_path_distance_m"
        ]
    )
    net_fraction_passed = (
        net_fraction is not None
        and net_fraction
        >= thresholds[
            "minimum_net_displacement_fraction_of_path"
        ]
    )
    path_minus_net_passed = (
        path_minus_net_m is not None
        and path_minus_net_m
        <= thresholds[
            "maximum_path_minus_net_displacement_m"
        ]
    )
    cross_track_passed = (
        cross_track_m is not None
        and cross_track_m
        <= thresholds[
            "maximum_intermediate_cross_track_m"
        ]
    )
    interval_passed = (
        window.get(
            "all_adjacent_intervals_positive"
        )
        is True
        and maximum_interval_ms
        is not None
        and maximum_interval_ms
        <= thresholds[
            "maximum_adjacent_interval_ms"
        ]
    )
    along_track_passed = (
        outside_count is not None
        and outside_count
        <= thresholds[
            "maximum_along_track_outside_unit_interval_count"
        ]
    )

    coherent = (
        window.get("available") is True
        and path_distance_passed
        and net_fraction_passed
        and path_minus_net_passed
        and cross_track_passed
        and interval_passed
        and along_track_passed
    )

    return {
        "start_segment_index": (
            window.get(
                "start_segment_index"
            )
        ),
        "end_segment_index": (
            window.get(
                "end_segment_index"
            )
        ),
        "start_waypoint_index": (
            window.get(
                "start_waypoint_index"
            )
        ),
        "end_waypoint_index": (
            window.get(
                "end_waypoint_index"
            )
        ),
        "start_exercise_elapsed_ms": (
            window.get(
                "start_exercise_elapsed_ms"
            )
        ),
        "end_exercise_elapsed_ms": (
            window.get(
                "end_exercise_elapsed_ms"
            )
        ),
        "coherent": coherent,
        "metrics": {
            "path_distance_m": (
                path_distance_m
            ),
            "net_displacement_fraction_of_path": (
                net_fraction
            ),
            "path_minus_net_displacement_m": (
                path_minus_net_m
            ),
            "maximum_intermediate_point_cross_track_deviation_m": (
                cross_track_m
            ),
            "maximum_adjacent_interval_ms": (
                maximum_interval_ms
            ),
            "intermediate_point_along_track_outside_unit_interval_count": (
                outside_count
            ),
        },
        "gates": {
            "path_distance_passed": (
                path_distance_passed
            ),
            "net_displacement_fraction_passed": (
                net_fraction_passed
            ),
            "path_minus_net_passed": (
                path_minus_net_passed
            ),
            "cross_track_passed": (
                cross_track_passed
            ),
            "timestamp_continuity_passed": (
                interval_passed
            ),
            "along_track_passed": (
                along_track_passed
            ),
        },
    }


def _first_consecutive_run(
    evaluations: list[dict[str, Any]],
    *,
    minimum_length: int,
) -> list[dict[str, Any]] | None:
    run = []

    for evaluation in evaluations:
        start_segment_index = _integer(
            evaluation.get(
                "start_segment_index"
            )
        )

        if (
            evaluation.get(
                "coherent"
            )
            is not True
            or start_segment_index is None
        ):
            run = []
            continue

        if not run:
            run = [
                evaluation
            ]
        else:
            previous_start = _integer(
                run[-1].get(
                    "start_segment_index"
                )
            )

            if (
                previous_start is not None
                and start_segment_index
                == previous_start + 1
            ):
                run.append(
                    evaluation
                )
            else:
                run = [
                    evaluation
                ]

        if len(run) >= minimum_length:
            return run[
                :minimum_length
            ]

    return None


def build_route_motion_forward_anchor_evidence(
    path_geometry_evidence: dict[str, Any],
    startup_evidence: dict[str, Any],
    *,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find geometry-supported forward-anchor candidates.

    The thresholds are provisional quality-policy parameters, not
    physical truths. This service does not reconstruct any points.
    """
    effective_thresholds = deepcopy(
        DEFAULT_THRESHOLDS
    )

    if thresholds:
        effective_thresholds.update(
            thresholds
        )

    minimum_run = _integer(
        effective_thresholds.get(
            "minimum_consecutive_coherent_windows"
        )
    )
    inspection_limit = _integer(
        effective_thresholds.get(
            "inspection_window_limit"
        )
    )

    if (
        minimum_run is None
        or minimum_run < 1
    ):
        raise ValueError(
            "minimum_consecutive_coherent_windows must be >= 1"
        )

    if (
        inspection_limit is None
        or inspection_limit < 1
    ):
        raise ValueError(
            "inspection_window_limit must be >= 1"
        )

    startup_lookup = _route_lookup(
        startup_evidence
    )

    route_results = []

    for route_position, route in enumerate(
        path_geometry_evidence.get(
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

        startup_route = (
            _match_startup_route(
                startup_lookup,
                route_index=route_index,
                exercise_index=(
                    exercise_index
                ),
            )
        )

        expected_segment_indices = []

        if isinstance(
            startup_route,
            dict,
        ):
            raw_expected = (
                startup_route.get(
                    "expected_segment_indices"
                )
                or []
            )

            expected_segment_indices = [
                value
                for raw_value
                in raw_expected
                if (
                    value := _integer(
                        raw_value
                    )
                )
                is not None
            ]

        scan_start_segment_index = (
            max(
                expected_segment_indices
            )
            + 1
            if expected_segment_indices
            else 0
        )

        windows = [
            window
            for window
            in (
                route.get(
                    "windows"
                )
                or []
            )
            if (
                isinstance(
                    window,
                    dict,
                )
                and (
                    _integer(
                        window.get(
                            "start_segment_index"
                        )
                    )
                    or 0
                )
                >= scan_start_segment_index
            )
        ]

        evaluations = [
            _window_evaluation(
                window,
                thresholds=(
                    effective_thresholds
                ),
            )
            for window
            in windows
        ]

        run = _first_consecutive_run(
            evaluations,
            minimum_length=(
                minimum_run
            ),
        )

        anchor = None

        if run:
            first_window = run[0]

            anchor = {
                "waypoint_index": (
                    first_window.get(
                        "start_waypoint_index"
                    )
                ),
                "segment_index": (
                    first_window.get(
                        "start_segment_index"
                    )
                ),
                "exercise_elapsed_ms": (
                    first_window.get(
                        "start_exercise_elapsed_ms"
                    )
                ),
                "confirmation_window_start_segment_indices": [
                    item.get(
                        "start_segment_index"
                    )
                    for item in run
                ],
                "confirmation_window_count": (
                    len(run)
                ),
            }

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": (
                    exercise_index
                ),
                "available": (
                    route.get(
                        "available"
                    )
                    is True
                ),
                "criteria_version": (
                    CRITERIA_VERSION
                ),
                "scan_start_segment_index": (
                    scan_start_segment_index
                ),
                "evaluated_window_count": (
                    len(
                        evaluations
                    )
                ),
                "coherent_window_count": (
                    sum(
                        1
                        for evaluation
                        in evaluations
                        if evaluation.get(
                            "coherent"
                        )
                        is True
                    )
                ),
                "validated_forward_anchor_available": (
                    anchor is not None
                ),
                "reason": (
                    "GEOMETRY_SUPPORTED_CONSECUTIVE_WINDOW_RUN_FOUND"
                    if anchor is not None
                    else "NO_GEOMETRY_SUPPORTED_CONSECUTIVE_WINDOW_RUN_FOUND"
                ),
                "anchor": anchor,
                "inspection_windows": (
                    evaluations[
                        :inspection_limit
                    ]
                ),
            }
        )

    return {
        "provider": (
            path_geometry_evidence.get(
                "provider"
            )
        ),
        "criteria_version": (
            CRITERIA_VERSION
        ),
        "available": bool(
            route_results
        ),
        "thresholds": (
            effective_thresholds
        ),
        "route_count": len(
            route_results
        ),
        "routes": route_results,
    }


def build_forward_anchor_reconstruction_context(
    evidence: dict[str, Any],
) -> dict[int, dict[str, Any]]:
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

        result[
            route_index
        ] = {
            "forward_anchor_available": (
                route.get(
                    "validated_forward_anchor_available"
                )
                is True
            )
        }

    return result
