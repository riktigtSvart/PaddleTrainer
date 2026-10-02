from __future__ import annotations

import math
import statistics
from typing import Any


HR_METRIC_KEY = "heart_rate_bpm"
SPEED_METRIC_KEY = "speed_kmh"
DEFAULT_WINDOW_SEC = 120


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


def build_exercise_hr_speed_windows(
    normalized_samples: dict[str, Any],
    *,
    window_sec: int = DEFAULT_WINDOW_SEC,
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
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": "HEART_RATE_SERIES_MISSING",
                }
            )
            continue

        if speed_series is None:
            exercises.append(
                {
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": "SPEED_SERIES_MISSING",
                }
            )
            continue

        hr_interval = hr_series.get("interval_ms")
        speed_interval = speed_series.get(
            "interval_ms"
        )

        if not (
            isinstance(hr_interval, int)
            and hr_interval > 0
            and hr_interval == speed_interval
        ):
            exercises.append(
                {
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": "INTERVAL_MISMATCH",
                    "hr_interval_ms": hr_interval,
                    "speed_interval_ms": (
                        speed_interval
                    ),
                }
            )
            continue

        window_ms = window_sec * 1000

        if (
            window_sec <= 0
            or window_ms % hr_interval != 0
        ):
            exercises.append(
                {
                    "exercise_index": exercise_index,
                    "available": False,
                    "reason": (
                        "WINDOW_INTERVAL_NOT_DIVISIBLE"
                    ),
                    "interval_ms": hr_interval,
                    "window_sec": window_sec,
                }
            )
            continue

        slots_per_window = (
            window_ms // hr_interval
        )

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

        windows: list[dict[str, Any]] = []

        for start in range(
            0,
            aligned_slot_count,
            slots_per_window,
        ):
            end = min(
                start + slots_per_window,
                aligned_slot_count,
            )

            paired = [
                (
                    index,
                    hr_values[index],
                    speed_values[index],
                )
                for index in range(start, end)
                if (
                    hr_values[index]
                    is not None
                    and speed_values[index]
                    is not None
                )
            ]

            hr_paired = [
                item[1]
                for item in paired
            ]

            speed_paired = [
                item[2]
                for item in paired
            ]

            slot_count = end - start
            paired_count = len(paired)

            windows.append(
                {
                    "window_index": len(windows),
                    "start_slot": start,
                    "end_slot_exclusive": end,
                    "start_elapsed_sec": (
                        start
                        * hr_interval
                        / 1000
                    ),
                    "end_elapsed_sec_exclusive": (
                        end
                        * hr_interval
                        / 1000
                    ),
                    "slot_count": slot_count,
                    "window_complete": (
                        slot_count
                        == slots_per_window
                    ),
                    "paired_sample_count": (
                        paired_count
                    ),
                    "paired_fraction": (
                        paired_count
                        / slot_count
                        if slot_count
                        else None
                    ),
                    "first_paired_elapsed_sec": (
                        paired[0][0]
                        * hr_interval
                        / 1000
                        if paired
                        else None
                    ),
                    "last_paired_elapsed_sec": (
                        paired[-1][0]
                        * hr_interval
                        / 1000
                        if paired
                        else None
                    ),
                    "mean_hr_bpm": (
                        statistics.mean(
                            hr_paired
                        )
                        if hr_paired
                        else None
                    ),
                    "median_hr_bpm": (
                        statistics.median(
                            hr_paired
                        )
                        if hr_paired
                        else None
                    ),
                    "mean_speed_kmh": (
                        statistics.mean(
                            speed_paired
                        )
                        if speed_paired
                        else None
                    ),
                    "median_speed_kmh": (
                        statistics.median(
                            speed_paired
                        )
                        if speed_paired
                        else None
                    ),
                }
            )

        exercises.append(
            {
                "exercise_index": exercise_index,
                "available": any(
                    window[
                        "paired_sample_count"
                    ] > 0
                    for window in windows
                ),
                "reason": None,
                "interval_ms": hr_interval,
                "window_sec": window_sec,
                "slots_per_window": (
                    slots_per_window
                ),
                "aligned_slot_count": (
                    aligned_slot_count
                ),
                "window_count": len(windows),
                "windows": windows,
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
        "window_sec": window_sec,
        "available": any(
            exercise.get("available")
            for exercise in exercises
        ),
        "exercise_count": len(exercises),
        "exercises": exercises,
    }