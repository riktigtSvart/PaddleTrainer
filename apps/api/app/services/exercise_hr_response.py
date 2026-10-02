from __future__ import annotations

import math
import statistics
from typing import Any


METRIC_HEART_RATE = "heart_rate_bpm"


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


def build_exercise_hr_response_evidence(
    normalized_samples: dict[str, Any],
) -> dict[str, Any]:
    provider = normalized_samples.get(
        "provider"
    )

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

        valid_samples = [
            (index, value)
            for index, value in enumerate(
                values
            )
            if value is not None
        ]

        slot_count = len(values)
        valid_count = len(valid_samples)
        missing_count = (
            slot_count - valid_count
        )

        evidence: dict[str, Any] = {
            "exercise_index": (
                series.get("exercise_index")
            ),
            "metric_key": METRIC_HEART_RATE,
            "unit": series.get("unit"),
            "source_type": (
                series.get("source_type")
            ),
            "interval_ms": interval_ms,
            "slot_count": slot_count,
            "valid_sample_count": (
                valid_count
            ),
            "missing_sample_count": (
                missing_count
            ),
            "coverage_fraction": (
                valid_count / slot_count
                if slot_count
                else None
            ),
            "last_slot_elapsed_sec": (
                (
                    (slot_count - 1)
                    * interval_ms
                    / 1000
                )
                if (
                    slot_count > 0
                    and isinstance(
                        interval_ms,
                        int,
                    )
                    and interval_ms > 0
                )
                else None
            ),
            "observations_available": (
                bool(valid_samples)
            ),
        }

        if valid_samples:
            first_index, first_value = (
                valid_samples[0]
            )

            last_index, last_value = (
                valid_samples[-1]
            )

            numeric_values = [
                value
                for _, value
                in valid_samples
            ]

            minimum = min(numeric_values)
            maximum = max(numeric_values)

            minimum_indices = [
                index
                for index, value
                in valid_samples
                if value == minimum
            ]

            maximum_indices = [
                index
                for index, value
                in valid_samples
                if value == maximum
            ]

            def elapsed(
                index: int,
            ) -> float | None:
                if not (
                    isinstance(
                        interval_ms,
                        int,
                    )
                    and interval_ms > 0
                ):
                    return None

                return (
                    index
                    * interval_ms
                    / 1000
                )

            evidence.update(
                {
                    "first_value": (
                        first_value
                    ),
                    "first_value_elapsed_sec": (
                        elapsed(first_index)
                    ),
                    "last_value": last_value,
                    "last_value_elapsed_sec": (
                        elapsed(last_index)
                    ),
                    "minimum_value": minimum,
                    "minimum_first_elapsed_sec": (
                        elapsed(
                            minimum_indices[0]
                        )
                    ),
                    "maximum_value": maximum,
                    "maximum_first_elapsed_sec": (
                        elapsed(
                            maximum_indices[0]
                        )
                    ),
                    "maximum_last_elapsed_sec": (
                        elapsed(
                            maximum_indices[-1]
                        )
                    ),
                    "maximum_sample_count": (
                        len(maximum_indices)
                    ),
                    "mean_value": (
                        statistics.mean(
                            numeric_values
                        )
                    ),
                    "median_value": (
                        statistics.median(
                            numeric_values
                        )
                    ),
                }
            )

        exercises.append(evidence)

    return {
        "metric_key": METRIC_HEART_RATE,
        "provider": provider,
        "available": any(
            exercise[
                "observations_available"
            ]
            for exercise in exercises
        ),
        "exercise_count": len(exercises),
        "exercises": exercises,
    }