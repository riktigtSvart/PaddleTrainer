from __future__ import annotations

import math
from typing import Any


PROVIDER = "POLAR"

POLAR_SAMPLE_TYPE_MAP = {
    "HEART_RATE": {
        "metric_key": "heart_rate_bpm",
        "unit": "bpm",
    },
    "SPEED": {
        "metric_key": "speed_kmh",
        "unit": "km/h",
    },
    "DISTANCE": {
        "metric_key": "distance_m",
        "unit": "m",
    },
}


def _numeric_or_none(
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


def _get_raw_series(
    exercise: dict[str, Any],
) -> list[dict[str, Any]]:
    container = exercise.get("samples") or {}

    # Polar normally wraps sample series as:
    #
    # "samples": {
    #     "samples": [...]
    # }
    #
    # Keep the parser tolerant in case the provider
    # representation changes to a direct list.
    if isinstance(container, list):
        return [
            item
            for item in container
            if isinstance(item, dict)
        ]

    if not isinstance(container, dict):
        return []

    items = container.get("samples") or []

    if not isinstance(items, list):
        return []

    return [
        item
        for item in items
        if isinstance(item, dict)
    ]


def normalize_polar_training_samples(
    raw_data: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_data = raw_data or {}

    exercises = (
        raw_data.get("exerciseSamples")
        or []
    )

    if not isinstance(exercises, list):
        exercises = []

    source_types: set[str] = set()
    normalized_series: list[dict[str, Any]] = []

    for exercise_index, exercise in enumerate(
        exercises
    ):
        if not isinstance(exercise, dict):
            continue

        for raw_series in _get_raw_series(
            exercise
        ):
            source_type = raw_series.get("type")

            if not isinstance(source_type, str):
                continue

            source_types.add(source_type)

            mapping = POLAR_SAMPLE_TYPE_MAP.get(
                source_type
            )

            if mapping is None:
                continue

            interval_ms = raw_series.get(
                "intervalMillis"
            )

            if not (
                isinstance(interval_ms, int)
                and interval_ms > 0
            ):
                interval_ms = None

            raw_values = (
                raw_series.get("values")
                or []
            )

            if not isinstance(raw_values, list):
                raw_values = []

            values = [
                _numeric_or_none(value)
                for value in raw_values
            ]

            normalized_series.append(
                {
                    "exercise_index": (
                        exercise_index
                    ),
                    "metric_key": (
                        mapping["metric_key"]
                    ),
                    "unit": mapping["unit"],
                    "source_type": source_type,
                    "interval_ms": interval_ms,
                    "slot_count": len(values),
                    "valid_sample_count": sum(
                        value is not None
                        for value in values
                    ),
                    "values": values,
                }
            )

    return {
        "provider": PROVIDER,
        "exercise_count": len(exercises),
        "source_types": sorted(source_types),
        "series": normalized_series,
    }