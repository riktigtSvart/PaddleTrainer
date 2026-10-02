from __future__ import annotations

import math
import statistics
from typing import Any


SPEED_METRIC_KEY = "speed_kmh"


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


def _find_speed_series(
    normalized_samples: dict[str, Any],
    *,
    exercise_index: int,
) -> dict[str, Any] | None:
    for series in (
        normalized_samples.get("series")
        or []
    ):
        if not isinstance(series, dict):
            continue

        if (
            series.get("exercise_index")
            == exercise_index
            and series.get("metric_key")
            == SPEED_METRIC_KEY
        ):
            return series

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


def _ceil_slot_index(
    elapsed_ms: int,
    interval_ms: int,
) -> int:
    return math.ceil(
        elapsed_ms / interval_ms
    )


def build_exercise_speed_gps_consistency(
    normalized_samples: dict[str, Any],
    motion_evidence: dict[str, Any],
) -> dict[str, Any]:
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
                    route.get("exercise_index"),
                    int,
                )
            )
        }
        | {
            series["exercise_index"]
            for series in (
                normalized_samples.get("series")
                or []
            )
            if (
                isinstance(series, dict)
                and isinstance(
                    series.get(
                        "exercise_index"
                    ),
                    int,
                )
            )
        }
    )

    exercises: list[
        dict[str, Any]
    ] = []

    for exercise_index in exercise_indices:
        speed_series = _find_speed_series(
            normalized_samples,
            exercise_index=exercise_index,
        )

        motion_route = _find_motion_route(
            motion_evidence,
            exercise_index=exercise_index,
        )

        if speed_series is None:
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "available": False,
                    "reason": (
                        "SPEED_SERIES_MISSING"
                    ),
                }
            )
            continue

        if motion_route is None:
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "available": False,
                    "reason": (
                        "ROUTE_MOTION_MISSING"
                    ),
                }
            )
            continue

        interval_ms = speed_series.get(
            "interval_ms"
        )

        if not (
            isinstance(interval_ms, int)
            and not isinstance(
                interval_ms,
                bool,
            )
            and interval_ms > 0
        ):
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "available": False,
                    "reason": (
                        "SPEED_INTERVAL_UNAVAILABLE"
                    ),
                }
            )
            continue

        values = (
            speed_series.get("values")
            or []
        )

        if not isinstance(values, list):
            values = []

        raw_segments = (
            motion_route.get("segments")
            or []
        )

        if not isinstance(
            raw_segments,
            list,
        ):
            raw_segments = []

        candidate_segments: list[
            dict[str, Any]
        ] = []

        for segment in raw_segments:
            if not isinstance(
                segment,
                dict,
            ):
                continue

            if (
                segment.get(
                    "motion_available"
                )
                is not True
            ):
                continue

            start_ms = _elapsed_ms(
                segment.get(
                    "start_exercise_elapsed_ms"
                )
            )
            end_ms = _elapsed_ms(
                segment.get(
                    "end_exercise_elapsed_ms"
                )
            )

            gps_speed_mps = (
                _finite_number(
                    segment.get(
                        "gps_ground_speed_mps"
                    )
                )
            )

            if (
                start_ms is None
                or end_ms is None
                or end_ms <= start_ms
                or gps_speed_mps is None
            ):
                continue

            candidate_segments.append(
                segment
            )

        comparisons: list[
            dict[str, Any]
        ] = []

        for segment in candidate_segments:
            start_ms = _elapsed_ms(
                segment.get(
                    "start_exercise_elapsed_ms"
                )
            )
            end_ms = _elapsed_ms(
                segment.get(
                    "end_exercise_elapsed_ms"
                )
            )

            gps_speed_mps = (
                _finite_number(
                    segment.get(
                        "gps_ground_speed_mps"
                    )
                )
            )

            assert start_ms is not None
            assert end_ms is not None
            assert gps_speed_mps is not None

            first_slot = max(
                0,
                _ceil_slot_index(
                    start_ms,
                    interval_ms,
                ),
            )

            end_slot_exclusive = min(
                len(values),
                _ceil_slot_index(
                    end_ms,
                    interval_ms,
                ),
            )

            valid_samples: list[
                float
            ] = []

            valid_sample_indices: list[
                int
            ] = []

            for slot_index in range(
                first_slot,
                end_slot_exclusive,
            ):
                value = _finite_number(
                    values[slot_index]
                )

                if value is None:
                    continue

                valid_samples.append(
                    value / 3.6
                )
                valid_sample_indices.append(
                    slot_index
                )

            if not valid_samples:
                continue

            polar_sample_mean_mps = (
                statistics.mean(
                    valid_samples
                )
            )

            difference_mps = (
                gps_speed_mps
                - polar_sample_mean_mps
            )

            comparisons.append(
                {
                    "segment_index": (
                        segment.get(
                            "segment_index"
                        )
                    ),
                    "start_exercise_elapsed_ms": (
                        start_ms
                    ),
                    "end_exercise_elapsed_ms": (
                        end_ms
                    ),
                    "interval_ms": (
                        end_ms - start_ms
                    ),
                    "gps_ground_speed_mps": (
                        gps_speed_mps
                    ),
                    "polar_speed_sample_count": (
                        len(valid_samples)
                    ),
                    "first_polar_speed_slot_index": (
                        valid_sample_indices[0]
                    ),
                    "last_polar_speed_slot_index": (
                        valid_sample_indices[-1]
                    ),
                    "polar_speed_sample_mean_mps": (
                        polar_sample_mean_mps
                    ),
                    "difference_mps": (
                        difference_mps
                    ),
                    "absolute_difference_mps": (
                        abs(
                            difference_mps
                        )
                    ),
                }
            )

        paired_count = len(comparisons)
        candidate_count = len(
            candidate_segments
        )

        gps_speeds = [
            comparison[
                "gps_ground_speed_mps"
            ]
            for comparison in comparisons
        ]

        polar_speeds = [
            comparison[
                "polar_speed_sample_mean_mps"
            ]
            for comparison in comparisons
        ]

        differences = [
            comparison[
                "difference_mps"
            ]
            for comparison in comparisons
        ]

        absolute_differences = [
            comparison[
                "absolute_difference_mps"
            ]
            for comparison in comparisons
        ]

        exercises.append(
            {
                "exercise_index": (
                    exercise_index
                ),
                "available": (
                    paired_count > 0
                ),
                "reason": (
                    None
                    if paired_count > 0
                    else "NO_PAIRED_OBSERVATIONS"
                ),
                "speed_metric_key": (
                    SPEED_METRIC_KEY
                ),
                "speed_unit": (
                    speed_series.get("unit")
                ),
                "speed_interval_ms": (
                    interval_ms
                ),
                "candidate_motion_segment_count": (
                    candidate_count
                ),
                "paired_segment_count": (
                    paired_count
                ),
                "unpaired_segment_count": (
                    candidate_count
                    - paired_count
                ),
                "paired_fraction": (
                    paired_count
                    / candidate_count
                    if candidate_count
                    else None
                ),
                "polar_speed_sample_observation_count": (
                    sum(
                        comparison[
                            "polar_speed_sample_count"
                        ]
                        for comparison
                        in comparisons
                    )
                ),
                "first_paired_start_elapsed_ms": (
                    comparisons[0][
                        "start_exercise_elapsed_ms"
                    ]
                    if comparisons
                    else None
                ),
                "last_paired_end_elapsed_ms": (
                    comparisons[-1][
                        "end_exercise_elapsed_ms"
                    ]
                    if comparisons
                    else None
                ),
                "mean_gps_ground_speed_mps": (
                    statistics.mean(
                        gps_speeds
                    )
                    if gps_speeds
                    else None
                ),
                "median_gps_ground_speed_mps": (
                    statistics.median(
                        gps_speeds
                    )
                    if gps_speeds
                    else None
                ),
                "mean_polar_speed_sample_mps": (
                    statistics.mean(
                        polar_speeds
                    )
                    if polar_speeds
                    else None
                ),
                "median_polar_speed_sample_mps": (
                    statistics.median(
                        polar_speeds
                    )
                    if polar_speeds
                    else None
                ),
                "mean_difference_mps": (
                    statistics.mean(
                        differences
                    )
                    if differences
                    else None
                ),
                "median_difference_mps": (
                    statistics.median(
                        differences
                    )
                    if differences
                    else None
                ),
                "mean_absolute_difference_mps": (
                    statistics.mean(
                        absolute_differences
                    )
                    if absolute_differences
                    else None
                ),
                "median_absolute_difference_mps": (
                    statistics.median(
                        absolute_differences
                    )
                    if absolute_differences
                    else None
                ),
                "maximum_absolute_difference_mps": (
                    max(
                        absolute_differences
                    )
                    if absolute_differences
                    else None
                ),
                "comparisons": comparisons,
            }
        )

    return {
        "provider": (
            normalized_samples.get(
                "provider"
            )
        ),
        "speed_metric_key": (
            SPEED_METRIC_KEY
        ),
        "available": any(
            exercise.get("available")
            is True
            for exercise in exercises
        ),
        "exercise_count": len(
            exercises
        ),
        "exercises": exercises,
    }