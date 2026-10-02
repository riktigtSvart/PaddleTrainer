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


def build_exercise_hr_speed_segments(
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

        if hr_series is None or speed_series is None:
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

        slot_count = min(
            len(hr_values),
            len(speed_values),
        )

        segments: list[dict[str, Any]] = []

        for segment_index in range(5):
            start = (
                slot_count
                * segment_index
                // 5
            )

            end = (
                slot_count
                * (segment_index + 1)
                // 5
            )

            paired = [
                (
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

            paired_count = len(paired)
            segment_slot_count = end - start

            hr_numeric = [
                hr
                for hr, _ in paired
            ]

            speed_numeric = [
                speed
                for _, speed in paired
            ]

            segments.append(
                {
                    "segment_index": (
                        segment_index
                    ),
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
                    "slot_count": (
                        segment_slot_count
                    ),
                    "paired_sample_count": (
                        paired_count
                    ),
                    "paired_fraction": (
                        paired_count
                        / segment_slot_count
                        if segment_slot_count
                        else None
                    ),
                    "mean_hr_bpm": (
                        statistics.mean(
                            hr_numeric
                        )
                        if hr_numeric
                        else None
                    ),
                    "median_hr_bpm": (
                        statistics.median(
                            hr_numeric
                        )
                        if hr_numeric
                        else None
                    ),
                    "mean_speed_kmh": (
                        statistics.mean(
                            speed_numeric
                        )
                        if speed_numeric
                        else None
                    ),
                    "median_speed_kmh": (
                        statistics.median(
                            speed_numeric
                        )
                        if speed_numeric
                        else None
                    ),
                }
            )

        exercises.append(
            {
                "exercise_index": (
                    exercise_index
                ),
                "interval_ms": hr_interval,
                "aligned_slot_count": (
                    slot_count
                ),
                "segment_count": len(
                    segments
                ),
                "segments": segments,
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
        "available": bool(exercises),
        "exercise_count": len(
            exercises
        ),
        "exercises": exercises,
    }