from __future__ import annotations

import math
from typing import Any


SPEED_METRIC_KEY = "speed_kmh"
DISTANCE_METRIC_KEY = "distance_m"


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


def _find_series(
    normalized_samples: dict[str, Any],
    *,
    exercise_index: int,
    metric_key: str,
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
            == metric_key
        ):
            return series

    return None


def _summarize_intervals(
    *,
    speed_values: list[float | None],
    distance_values: list[float | None],
    interval_ms: int,
    start_slot: int,
    end_slot_exclusive: int,
) -> dict[str, Any]:
    slot_count = min(
        len(speed_values),
        len(distance_values),
    )

    interval_end = min(
        end_slot_exclusive,
        slot_count - 1,
    )

    candidate_interval_count = max(
        0,
        interval_end - start_slot,
    )

    paired_interval_count = 0
    negative_distance_delta_count = 0

    observed_distance_m = 0.0
    integrated_distance_m = 0.0

    dt_sec = interval_ms / 1000

    for index in range(
        start_slot,
        interval_end,
    ):
        speed_0 = speed_values[index]
        speed_1 = speed_values[index + 1]

        distance_0 = distance_values[index]
        distance_1 = distance_values[index + 1]

        if (
            speed_0 is None
            or speed_1 is None
            or distance_0 is None
            or distance_1 is None
        ):
            continue

        distance_delta = (
            distance_1 - distance_0
        )

        if distance_delta < 0:
            negative_distance_delta_count += 1

        mean_speed_mps = (
            (speed_0 + speed_1)
            / 2
            / 3.6
        )

        observed_distance_m += (
            distance_delta
        )

        integrated_distance_m += (
            mean_speed_mps * dt_sec
        )

        paired_interval_count += 1

    difference_m = (
        integrated_distance_m
        - observed_distance_m
    )

    relative_difference_fraction = None

    if observed_distance_m != 0:
        relative_difference_fraction = (
            difference_m
            / observed_distance_m
        )

    return {
        "start_slot": start_slot,
        "end_slot_exclusive": (
            end_slot_exclusive
        ),
        "candidate_interval_count": (
            candidate_interval_count
        ),
        "paired_interval_count": (
            paired_interval_count
        ),
        "paired_interval_fraction": (
            paired_interval_count
            / candidate_interval_count
            if candidate_interval_count
            else None
        ),
        "observed_distance_m_on_"
        "paired_intervals": (
            observed_distance_m
        ),
        "trapezoidal_speed_distance_m_on_"
        "paired_intervals": (
            integrated_distance_m
        ),
        "integrated_minus_observed_"
        "distance_m": (
            difference_m
        ),
        "relative_difference_fraction": (
            relative_difference_fraction
        ),
        "negative_distance_delta_count": (
            negative_distance_delta_count
        ),
    }


def build_exercise_speed_distance_consistency(
    normalized_samples: dict[str, Any],
) -> dict[str, Any]:
    raw_series = (
        normalized_samples.get("series")
        or []
    )

    exercise_indices = sorted(
        {
            series["exercise_index"]
            for series in raw_series
            if (
                isinstance(series, dict)
                and isinstance(
                    series.get("exercise_index"),
                    int,
                )
            )
        }
    )

    exercises: list[dict[str, Any]] = []

    for exercise_index in exercise_indices:
        speed_series = _find_series(
            normalized_samples,
            exercise_index=exercise_index,
            metric_key=SPEED_METRIC_KEY,
        )

        distance_series = _find_series(
            normalized_samples,
            exercise_index=exercise_index,
            metric_key=DISTANCE_METRIC_KEY,
        )

        if speed_series is None:
            exercises.append(
                {
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": "SPEED_SERIES_MISSING",
                }
            )
            continue

        if distance_series is None:
            exercises.append(
                {
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": "DISTANCE_SERIES_MISSING",
                }
            )
            continue

        speed_interval = speed_series.get(
            "interval_ms"
        )

        distance_interval = distance_series.get(
            "interval_ms"
        )

        if not (
            isinstance(speed_interval, int)
            and speed_interval > 0
            and speed_interval
            == distance_interval
        ):
            exercises.append(
                {
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": "INTERVAL_MISMATCH",
                    "speed_interval_ms": (
                        speed_interval
                    ),
                    "distance_interval_ms": (
                        distance_interval
                    ),
                }
            )
            continue

        speed_values = [
            _finite_number(value)
            for value in (
                speed_series.get("values")
                or []
            )
        ]

        distance_values = [
            _finite_number(value)
            for value in (
                distance_series.get("values")
                or []
            )
        ]

        aligned_slot_count = min(
            len(speed_values),
            len(distance_values),
        )

        overall = _summarize_intervals(
            speed_values=speed_values,
            distance_values=distance_values,
            interval_ms=speed_interval,
            start_slot=0,
            end_slot_exclusive=(
                aligned_slot_count
            ),
        )

        segments: list[dict[str, Any]] = []

        for segment_index in range(5):
            start = (
                aligned_slot_count
                * segment_index
                // 5
            )

            end = (
                aligned_slot_count
                * (segment_index + 1)
                // 5
            )

            segment = _summarize_intervals(
                speed_values=speed_values,
                distance_values=distance_values,
                interval_ms=speed_interval,
                start_slot=start,
                end_slot_exclusive=end,
            )

            segments.append(
                {
                    "segment_index": (
                        segment_index
                    ),
                    **segment,
                }
            )

        exercises.append(
            {
                "exercise_index": exercise_index,
                "available": True,
                "reason": None,
                "interval_ms": speed_interval,
                "aligned_slot_count": (
                    aligned_slot_count
                ),
                "overall": overall,
                "segments": segments,
            }
        )

    return {
        "provider": normalized_samples.get(
            "provider"
        ),
        "speed_metric_key": SPEED_METRIC_KEY,
        "distance_metric_key": (
            DISTANCE_METRIC_KEY
        ),
        "available": any(
            exercise.get("available")
            for exercise in exercises
        ),
        "exercise_count": len(exercises),
        "exercises": exercises,
    }