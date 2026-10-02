from __future__ import annotations

import math
import statistics
from typing import Any


HR_METRIC_KEY = "heart_rate_bpm"
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


def build_exercise_hr_speed_alignment(
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
                    series.get(
                        "exercise_index"
                    ),
                    int,
                )
            )
        }
    )

    exercises: list[dict[str, Any]] = []

    for exercise_index in exercise_indices:
        hr_series = _find_series(
            normalized_samples,
            exercise_index=exercise_index,
            metric_key=HR_METRIC_KEY,
        )

        speed_series = _find_series(
            normalized_samples,
            exercise_index=exercise_index,
            metric_key=SPEED_METRIC_KEY,
        )

        if hr_series is None:
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "aligned": False,
                    "reason": (
                        "HEART_RATE_SERIES_MISSING"
                    ),
                }
            )
            continue

        if speed_series is None:
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "aligned": False,
                    "reason": (
                        "SPEED_SERIES_MISSING"
                    ),
                }
            )
            continue

        hr_interval = hr_series.get(
            "interval_ms"
        )
        speed_interval = speed_series.get(
            "interval_ms"
        )

        if not (
            isinstance(hr_interval, int)
            and hr_interval > 0
            and isinstance(
                speed_interval,
                int,
            )
            and speed_interval > 0
        ):
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "aligned": False,
                    "reason": (
                        "INTERVAL_UNAVAILABLE"
                    ),
                    "hr_interval_ms": (
                        hr_interval
                    ),
                    "speed_interval_ms": (
                        speed_interval
                    ),
                }
            )
            continue

        if hr_interval != speed_interval:
            exercises.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "aligned": False,
                    "reason": (
                        "INTERVAL_MISMATCH"
                    ),
                    "hr_interval_ms": (
                        hr_interval
                    ),
                    "speed_interval_ms": (
                        speed_interval
                    ),
                }
            )
            continue

        hr_values = [
            _finite_number(value)
            for value in (
                hr_series.get("values")
                or []
            )
        ]

        speed_values = [
            _finite_number(value)
            for value in (
                speed_series.get("values")
                or []
            )
        ]

        aligned_slot_count = min(
            len(hr_values),
            len(speed_values),
        )

        paired: list[
            tuple[int, float, float]
        ] = []

        for index in range(
            aligned_slot_count
        ):
            hr = hr_values[index]
            speed = speed_values[index]

            if (
                hr is None
                or speed is None
            ):
                continue

            paired.append(
                (
                    index,
                    hr,
                    speed,
                )
            )

        paired_sample_count = len(paired)

        first_paired_elapsed_sec = None
        last_paired_elapsed_sec = None
        mean_hr_bpm = None
        mean_speed_kmh = None

        if paired:
            first_paired_elapsed_sec = (
                paired[0][0]
                * hr_interval
                / 1000
            )

            last_paired_elapsed_sec = (
                paired[-1][0]
                * hr_interval
                / 1000
            )

            mean_hr_bpm = statistics.mean(
                item[1]
                for item in paired
            )

            mean_speed_kmh = (
                statistics.mean(
                    item[2]
                    for item in paired
                )
            )

        exercises.append(
            {
                "exercise_index": (
                    exercise_index
                ),
                "aligned": True,
                "reason": None,
                "interval_ms": (
                    hr_interval
                ),
                "hr_slot_count": len(
                    hr_values
                ),
                "speed_slot_count": len(
                    speed_values
                ),
                "aligned_slot_count": (
                    aligned_slot_count
                ),
                "paired_sample_count": (
                    paired_sample_count
                ),
                "paired_fraction": (
                    paired_sample_count
                    / aligned_slot_count
                    if aligned_slot_count
                    else None
                ),
                "first_paired_elapsed_sec": (
                    first_paired_elapsed_sec
                ),
                "last_paired_elapsed_sec": (
                    last_paired_elapsed_sec
                ),
                "mean_hr_bpm_on_"
                "paired_slots": (
                    mean_hr_bpm
                ),
                "mean_speed_kmh_on_"
                "paired_slots": (
                    mean_speed_kmh
                ),
            }
        )

    return {
        "provider": normalized_samples.get(
            "provider"
        ),
        "hr_metric_key": HR_METRIC_KEY,
        "external_metric_key": (
            SPEED_METRIC_KEY
        ),
        "available": any(
            exercise.get("aligned")
            and exercise.get(
                "paired_sample_count",
                0,
            )
            > 0
            for exercise in exercises
        ),
        "exercise_count": len(
            exercises
        ),
        "exercises": exercises,
    }