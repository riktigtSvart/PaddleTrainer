from __future__ import annotations

import math
from typing import Any


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


def _speed_change_sign(value: float | None) -> int | None:
    if value is None:
        return None

    if value > 0.0:
        return 1

    if value < 0.0:
        return -1

    return 0


def _build_trajectory_summary(
    trajectory: list[dict[str, Any]],
) -> dict[str, Any]:
    finite_speed_points = []

    for trajectory_position, item in enumerate(
        trajectory
    ):
        speed = _finite_number(
            item.get(
                "gps_ground_speed_mps"
            )
        )

        if speed is None:
            continue

        order_index = _integer(
            item.get(
                "order_index"
            )
        )

        finite_speed_points.append(
            {
                "order_index": (
                    order_index
                    if order_index is not None
                    else trajectory_position
                ),
                "speed": speed,
            }
        )

    speeds = [
        point["speed"]
        for point in finite_speed_points
    ]

    changes = [
        change
        for item in trajectory
        if (
            change := _finite_number(
                item.get(
                    "gps_speed_change_from_previous_mps"
                )
            )
        )
        is not None
    ]

    positive_change_count = sum(
        1
        for change in changes
        if change > 0.0
    )

    negative_change_count = sum(
        1
        for change in changes
        if change < 0.0
    )

    zero_change_count = sum(
        1
        for change in changes
        if change == 0.0
    )

    previous_nonzero_sign = None
    sign_reversal_count = 0

    for change in changes:
        sign = _speed_change_sign(change)

        if sign in (None, 0):
            continue

        if (
            previous_nonzero_sign is not None
            and sign != previous_nonzero_sign
        ):
            sign_reversal_count += 1

        previous_nonzero_sign = sign

    speed_change_count = len(changes)

    total_absolute_speed_change = (
        sum(
            abs(change)
            for change in changes
        )
        if changes
        else None
    )

    net_speed_change = (
        speeds[-1] - speeds[0]
        if speeds
        else None
    )

    largest_absolute_speed_change = (
        max(
            (
                abs(change)
                for change in changes
            ),
            default=None,
        )
        if changes
        else None
    )

    directionality_fraction = None

    if (
        total_absolute_speed_change is not None
        and total_absolute_speed_change > 0.0
        and net_speed_change is not None
    ):
        directionality_fraction = (
            abs(net_speed_change)
            / total_absolute_speed_change
        )

    positive_speed_change_fraction = (
        positive_change_count
        / speed_change_count
        if speed_change_count > 0
        else None
    )

    negative_speed_change_fraction = (
        negative_change_count
        / speed_change_count
        if speed_change_count > 0
        else None
    )

    zero_speed_change_fraction = (
        zero_change_count
        / speed_change_count
        if speed_change_count > 0
        else None
    )

    largest_absolute_speed_change_fraction_of_total = None

    if (
        total_absolute_speed_change is not None
        and total_absolute_speed_change > 0.0
        and largest_absolute_speed_change is not None
    ):
        largest_absolute_speed_change_fraction_of_total = (
            largest_absolute_speed_change
            / total_absolute_speed_change
        )

    minimum_speed_order_index = None
    maximum_speed_order_index = None
    peak_to_last_speed_change_mps = None
    peak_to_last_speed_drop_mps = None
    post_peak_absolute_speed_change_mps = None
    peak_to_last_drop_fraction_of_speed_range = None

    if finite_speed_points:
        minimum_speed = min(speeds)
        maximum_speed = max(speeds)

        minimum_speed_point_position = next(
            position
            for position, point in enumerate(
                finite_speed_points
            )
            if point["speed"] == minimum_speed
        )

        maximum_speed_point_position = next(
            position
            for position, point in enumerate(
                finite_speed_points
            )
            if point["speed"] == maximum_speed
        )

        minimum_speed_order_index = (
            finite_speed_points[
                minimum_speed_point_position
            ]["order_index"]
        )

        maximum_speed_order_index = (
            finite_speed_points[
                maximum_speed_point_position
            ]["order_index"]
        )

        peak_speed = (
            finite_speed_points[
                maximum_speed_point_position
            ]["speed"]
        )

        last_speed = (
            finite_speed_points[-1][
                "speed"
            ]
        )

        peak_to_last_speed_change_mps = (
            last_speed
            - peak_speed
        )

        peak_to_last_speed_drop_mps = max(
            peak_speed
            - last_speed,
            0.0,
        )

        post_peak_absolute_speed_change_mps = sum(
            abs(
                finite_speed_points[position][
                    "speed"
                ]
                - finite_speed_points[
                    position - 1
                ]["speed"]
            )
            for position in range(
                maximum_speed_point_position + 1,
                len(finite_speed_points),
            )
        )

        speed_range = (
            maximum_speed
            - minimum_speed
        )

        if speed_range > 0.0:
            peak_to_last_drop_fraction_of_speed_range = (
                peak_to_last_speed_drop_mps
                / speed_range
            )

    return {
        "finite_speed_count": len(speeds),
        "first_gps_ground_speed_mps": (
            speeds[0]
            if speeds
            else None
        ),
        "last_gps_ground_speed_mps": (
            speeds[-1]
            if speeds
            else None
        ),
        "minimum_gps_ground_speed_mps": (
            min(speeds)
            if speeds
            else None
        ),
        "maximum_gps_ground_speed_mps": (
            max(speeds)
            if speeds
            else None
        ),
        "gps_ground_speed_range_mps": (
            max(speeds) - min(speeds)
            if speeds
            else None
        ),
        "minimum_speed_order_index": (
            minimum_speed_order_index
        ),
        "maximum_speed_order_index": (
            maximum_speed_order_index
        ),
        "peak_to_last_speed_change_mps": (
            peak_to_last_speed_change_mps
        ),
        "peak_to_last_speed_drop_mps": (
            peak_to_last_speed_drop_mps
        ),
        "post_peak_absolute_speed_change_mps": (
            post_peak_absolute_speed_change_mps
        ),
        "peak_to_last_drop_fraction_of_speed_range": (
            peak_to_last_drop_fraction_of_speed_range
        ),
        "net_gps_ground_speed_change_mps": (
            net_speed_change
        ),
        "speed_change_count": (
            speed_change_count
        ),
        "directionality_fraction": (
            directionality_fraction
        ),
        "positive_speed_change_fraction": (
            positive_speed_change_fraction
        ),
        "negative_speed_change_fraction": (
            negative_speed_change_fraction
        ),
        "zero_speed_change_fraction": (
            zero_speed_change_fraction
        ),
        "positive_speed_change_count": (
            positive_change_count
        ),
        "negative_speed_change_count": (
            negative_change_count
        ),
        "zero_speed_change_count": (
            zero_change_count
        ),
        "speed_change_sign_reversal_count": (
            sign_reversal_count
        ),
        "total_absolute_speed_change_mps": (
            total_absolute_speed_change
        ),
        "largest_absolute_speed_change_mps": (
            largest_absolute_speed_change
        ),
        "largest_absolute_speed_change_fraction_of_total": (
            largest_absolute_speed_change_fraction_of_total
        ),
        "largest_positive_speed_change_mps": (
            max(
                (
                    change
                    for change in changes
                    if change > 0.0
                ),
                default=None,
            )
        ),
        "largest_negative_speed_change_mps": (
            min(
                (
                    change
                    for change in changes
                    if change < 0.0
                ),
                default=None,
            )
        ),
    }


def build_speed_trajectory_summary(
    trajectory: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the descriptive speed-trajectory summary for a supplied trajectory."""
    return _build_trajectory_summary(
        trajectory
    )


def _build_candidate_trajectory(
    candidate: dict[str, Any],
    observations_by_segment_index: dict[
        int,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    start_segment_index = _integer(
        candidate.get(
            "window_start_segment_index"
        )
    )

    end_segment_index = _integer(
        candidate.get(
            "window_end_segment_index"
        )
    )

    result = {
        "inspection_rank": (
            candidate.get(
                "inspection_rank"
            )
        ),
        "center_segment_index": (
            candidate.get(
                "center_segment_index"
            )
        ),
        "center_time_since_route_start_ms": (
            candidate.get(
                "center_time_since_route_start_ms"
            )
        ),
        "window_start_segment_index": (
            start_segment_index
        ),
        "window_end_segment_index": (
            end_segment_index
        ),
        "ranking_gps_ground_speed_range_mps": (
            candidate.get(
                "gps_ground_speed_range_mps"
            )
        ),
    }

    if (
        start_segment_index is None
        or end_segment_index is None
        or end_segment_index
        < start_segment_index
    ):
        return {
            **result,
            "available": False,
            "reason": (
                "WINDOW_SEGMENT_RANGE_UNAVAILABLE"
            ),
            "expected_segment_count": None,
            "trajectory_observation_count": 0,
            "missing_segment_indices": [],
            "trajectory": [],
            "summary": (
                _build_trajectory_summary([])
            ),
        }

    expected_segment_indices = list(
        range(
            start_segment_index,
            end_segment_index + 1,
        )
    )

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

        trajectory.append(
            {
                "order_index": (
                    order_index
                ),
                "segment_index": (
                    segment_index
                ),
                "start_exercise_elapsed_ms": (
                    observation.get(
                        "start_exercise_elapsed_ms"
                    )
                ),
                "end_exercise_elapsed_ms": (
                    observation.get(
                        "end_exercise_elapsed_ms"
                    )
                ),
                "interval_ms": (
                    observation.get(
                        "interval_ms"
                    )
                ),
                "gps_ground_speed_mps": (
                    speed
                ),
                "gps_speed_change_from_previous_mps": (
                    speed_change
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

    return {
        **result,
        "available": bool(
            trajectory
        ),
        "reason": (
            None
            if trajectory
            else "TRAJECTORY_OBSERVATIONS_UNAVAILABLE"
        ),
        "expected_segment_count": (
            len(
                expected_segment_indices
            )
        ),
        "trajectory_observation_count": (
            len(trajectory)
        ),
        "missing_segment_indices": (
            missing_segment_indices
        ),
        "trajectory": trajectory,
        "summary": (
            _build_trajectory_summary(
                trajectory
            )
        ),
    }


def build_route_motion_speed_trajectories(
    motion_anomaly_evidence: dict[
        str,
        Any,
    ],
    motion_evidence_ranking: dict[
        str,
        Any,
    ],
) -> dict[str, Any]:
    anomaly_routes = {}

    for route_position, route in enumerate(
        motion_anomaly_evidence.get(
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

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

        anomaly_routes[
            (
                route_index
                if route_index is not None
                else route_position,
                exercise_index,
            )
        ] = route

    route_results = []

    for ranking_position, ranking_route in enumerate(
        motion_evidence_ranking.get(
            "routes"
        )
        or []
    ):
        if not isinstance(
            ranking_route,
            dict,
        ):
            continue

        route_index = _integer(
            ranking_route.get(
                "route_index"
            )
        )

        exercise_index = _integer(
            ranking_route.get(
                "exercise_index"
            )
        )

        anomaly_route = anomaly_routes.get(
            (
                route_index
                if route_index is not None
                else ranking_position,
                exercise_index,
            )
        )

        if anomaly_route is None:
            matching_routes = [
                route
                for (
                    _key,
                    route
                )
                in anomaly_routes.items()
                if _integer(
                    route.get(
                        "exercise_index"
                    )
                )
                == exercise_index
            ]

            anomaly_route = (
                matching_routes[0]
                if len(
                    matching_routes
                )
                == 1
                else None
            )

        observations_by_segment_index = {}

        if anomaly_route is not None:
            for observation in (
                anomaly_route.get(
                    "observations"
                )
                or []
            ):
                if not isinstance(
                    observation,
                    dict,
                ):
                    continue

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

        speed_transition_candidates = [
            candidate
            for candidate in (
                ranking_route.get(
                    "speed_transition"
                )
                or []
            )
            if isinstance(
                candidate,
                dict,
            )
        ]

        trajectories = [
            _build_candidate_trajectory(
                candidate,
                observations_by_segment_index,
            )
            for candidate
            in speed_transition_candidates
        ]

        route_results.append(
            {
                "route_index": (
                    route_index
                    if route_index is not None
                    else ranking_position
                ),
                "exercise_index": (
                    exercise_index
                ),
                "available": any(
                    item.get(
                        "available"
                    )
                    for item in trajectories
                ),
                "speed_transition_candidate_count": (
                    len(
                        speed_transition_candidates
                    )
                ),
                "trajectory_count": (
                    len(trajectories)
                ),
                "trajectories": (
                    trajectories
                ),
            }
        )

    return {
        "provider": (
            motion_evidence_ranking.get(
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
        "route_count": (
            len(route_results)
        ),
        "routes": route_results,
    }
