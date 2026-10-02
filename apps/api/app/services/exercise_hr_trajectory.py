from __future__ import annotations

import math
import statistics
from typing import Any


METRIC_HEART_RATE = "heart_rate_bpm"

DEFAULT_WINDOW_SEC = (
    60,
    120,
    300,
)


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


def _summarize_values(
    values: list[float | None],
) -> dict[str, Any]:
    numeric = [
        value
        for value in values
        if value is not None
    ]

    if not numeric:
        return {
            "slot_count": len(values),
            "valid_sample_count": 0,
            "mean_bpm": None,
            "median_bpm": None,
            "min_bpm": None,
            "max_bpm": None,
        }

    return {
        "slot_count": len(values),
        "valid_sample_count": len(numeric),
        "mean_bpm": statistics.mean(
            numeric
        ),
        "median_bpm": statistics.median(
            numeric
        ),
        "min_bpm": min(numeric),
        "max_bpm": max(numeric),
    }


def _window_slot_count(
    window_sec: int,
    interval_ms: int,
) -> int:
    return math.ceil(
        window_sec * 1000 / interval_ms
    )


def build_exercise_hr_trajectory_evidence(
    normalized_samples: dict[str, Any],
) -> dict[str, Any]:
    raw_series = (
        normalized_samples.get("series")
        or []
    )

    exercises: list[dict[str, Any]] = []

    for series in raw_series:
        if not isinstance(series, dict):
            continue

        if (
            series.get("metric_key")
            != METRIC_HEART_RATE
        ):
            continue

        raw_values = (
            series.get("values")
            or []
        )

        if not isinstance(raw_values, list):
            raw_values = []

        values = [
            _finite_number(value)
            for value in raw_values
        ]

        interval_ms = series.get(
            "interval_ms"
        )

        valid_interval = (
            isinstance(interval_ms, int)
            and interval_ms > 0
        )

        windows: dict[str, Any] = {}

        if valid_interval:
            for window_sec in (
                DEFAULT_WINDOW_SEC
            ):
                slots = _window_slot_count(
                    window_sec,
                    interval_ms,
                )

                windows[
                    f"first_{window_sec}_sec"
                ] = _summarize_values(
                    values[:slots]
                )

                windows[
                    f"last_{window_sec}_sec"
                ] = _summarize_values(
                    values[-slots:]
                )

        quintiles: list[dict[str, Any]] = []

        total_slots = len(values)

        if total_slots:
            for index in range(5):
                start = (
                    total_slots
                    * index
                    // 5
                )

                end = (
                    total_slots
                    * (index + 1)
                    // 5
                )

                summary = _summarize_values(
                    values[start:end]
                )

                quintiles.append(
                    {
                        "segment_index": index,
                        "start_slot": start,
                        "end_slot_exclusive": end,
                        **summary,
                    }
                )

        first_60 = windows.get(
            "first_60_sec"
        )

        last_60 = windows.get(
            "last_60_sec"
        )

        first_to_last_60_difference = None

        if (
            first_60
            and last_60
            and first_60["mean_bpm"]
            is not None
            and last_60["mean_bpm"]
            is not None
        ):
            first_to_last_60_difference = (
                last_60["mean_bpm"]
                - first_60["mean_bpm"]
            )

        exercises.append(
            {
                "exercise_index": (
                    series.get(
                        "exercise_index"
                    )
                ),
                "metric_key": (
                    METRIC_HEART_RATE
                ),
                "unit": series.get("unit"),
                "source_type": (
                    series.get(
                        "source_type"
                    )
                ),
                "interval_ms": interval_ms,
                "slot_count": total_slots,
                "windows": windows,
                "quintiles": quintiles,
                "last_60_minus_"
                "first_60_mean_bpm": (
                    first_to_last_60_difference
                ),
                "observations_available": any(
                    value is not None
                    for value in values
                ),
            }
        )

    return {
        "metric_key": METRIC_HEART_RATE,
        "provider": normalized_samples.get(
            "provider"
        ),
        "available": any(
            exercise["observations_available"]
            for exercise in exercises
        ),
        "exercise_count": len(exercises),
        "exercises": exercises,

    }