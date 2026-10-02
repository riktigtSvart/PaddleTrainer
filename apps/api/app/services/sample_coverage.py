from __future__ import annotations

import math
from typing import Any


def _is_valid_numeric(
    value: Any,
) -> bool:
    if isinstance(value, bool):
        return False

    if not isinstance(value, (int, float)):
        return False

    return math.isfinite(float(value))


def _elapsed_sec(
    index: int,
    interval_ms: int | None,
) -> float | None:
    if not (
        isinstance(interval_ms, int)
        and interval_ms > 0
    ):
        return None

    return index * interval_ms / 1000


def _max_missing_run(
    valid_flags: list[bool],
) -> int:
    longest = 0
    current = 0

    for valid in valid_flags:
        if valid:
            current = 0
            continue

        current += 1
        longest = max(longest, current)

    return longest


def build_sample_coverage_evidence(
    normalized_samples: dict[str, Any],
    *,
    session_duration_sec: float | None = None,
) -> dict[str, Any]:
    raw_series = (
        normalized_samples.get("series")
        or []
    )

    series_evidence: list[dict[str, Any]] = []

    for series in raw_series:
        if not isinstance(series, dict):
            continue

        values = series.get("values") or []

        if not isinstance(values, list):
            values = []

        interval_ms = series.get(
            "interval_ms"
        )

        valid_flags = [
            _is_valid_numeric(value)
            for value in values
        ]

        slot_count = len(values)

        valid_sample_count = sum(
            valid_flags
        )

        missing_sample_count = (
            slot_count - valid_sample_count
        )

        valid_indices = [
            index
            for index, valid
            in enumerate(valid_flags)
            if valid
        ]

        if valid_indices:
            first_valid_index = (
                valid_indices[0]
            )
            last_valid_index = (
                valid_indices[-1]
            )

            leading_missing_slots = (
                first_valid_index
            )

            trailing_missing_slots = (
                slot_count
                - last_valid_index
                - 1
            )

        else:
            first_valid_index = None
            last_valid_index = None

            leading_missing_slots = (
                slot_count
            )

            trailing_missing_slots = (
                slot_count
            )

        first_slot_elapsed_sec = (
            _elapsed_sec(0, interval_ms)
            if slot_count
            else None
        )

        last_slot_elapsed_sec = (
            _elapsed_sec(
                slot_count - 1,
                interval_ms,
            )
            if slot_count
            else None
        )

        first_valid_elapsed_sec = (
            _elapsed_sec(
                first_valid_index,
                interval_ms,
            )
            if first_valid_index
            is not None
            else None
        )

        last_valid_elapsed_sec = (
            _elapsed_sec(
                last_valid_index,
                interval_ms,
            )
            if last_valid_index
            is not None
            else None
        )

        sample_grid_span_sec = (
            last_slot_elapsed_sec
            - first_slot_elapsed_sec
            if (
                first_slot_elapsed_sec
                is not None
                and last_slot_elapsed_sec
                is not None
            )
            else None
        )

        maximum_missing_run_slots = (
            _max_missing_run(
                valid_flags
            )
        )

        maximum_missing_run_sec = (
            maximum_missing_run_slots
            * interval_ms
            / 1000
            if (
                maximum_missing_run_slots
                and isinstance(
                    interval_ms,
                    int,
                )
                and interval_ms > 0
            )
            else (
                0.0
                if (
                    maximum_missing_run_slots
                    == 0
                    and isinstance(
                        interval_ms,
                        int,
                    )
                    and interval_ms > 0
                )
                else None
            )
        )

        session_end_minus_last_slot_sec = (
            session_duration_sec
            - last_slot_elapsed_sec
            if (
                session_duration_sec
                is not None
                and last_slot_elapsed_sec
                is not None
            )
            else None
        )

        session_end_minus_last_valid_sec = (
            session_duration_sec
            - last_valid_elapsed_sec
            if (
                session_duration_sec
                is not None
                and last_valid_elapsed_sec
                is not None
            )
            else None
        )

        sample_grid_span_fraction = (
            sample_grid_span_sec
            / session_duration_sec
            if (
                sample_grid_span_sec
                is not None
                and session_duration_sec
                is not None
                and session_duration_sec > 0
            )
            else None
        )

        series_evidence.append(
            {
                "exercise_index": (
                    series.get(
                        "exercise_index"
                    )
                ),
                "metric_key": (
                    series.get("metric_key")
                ),
                "unit": series.get("unit"),
                "source_type": (
                    series.get(
                        "source_type"
                    )
                ),
                "interval_ms": interval_ms,
                "slot_count": slot_count,
                "valid_sample_count": (
                    valid_sample_count
                ),
                "missing_sample_count": (
                    missing_sample_count
                ),
                "value_completeness_fraction": (
                    valid_sample_count
                    / slot_count
                    if slot_count
                    else None
                ),
                "first_slot_elapsed_sec": (
                    first_slot_elapsed_sec
                ),
                "last_slot_elapsed_sec": (
                    last_slot_elapsed_sec
                ),
                "sample_grid_span_sec": (
                    sample_grid_span_sec
                ),
                "sample_grid_span_fraction": (
                    sample_grid_span_fraction
                ),
                "first_valid_elapsed_sec": (
                    first_valid_elapsed_sec
                ),
                "last_valid_elapsed_sec": (
                    last_valid_elapsed_sec
                ),
                "leading_missing_slots": (
                    leading_missing_slots
                ),
                "trailing_missing_slots": (
                    trailing_missing_slots
                ),
                "maximum_consecutive_"
                "missing_slots": (
                    maximum_missing_run_slots
                ),
                "maximum_consecutive_"
                "missing_sec": (
                    maximum_missing_run_sec
                ),
                "session_end_minus_"
                "last_slot_sec": (
                    session_end_minus_last_slot_sec
                ),
                "session_end_minus_"
                "last_valid_sec": (
                    session_end_minus_last_valid_sec
                ),
            }
        )

    return {
        "provider": normalized_samples.get(
            "provider"
        ),
        "session_duration_sec": (
            session_duration_sec
        ),
        "series_count": len(
            series_evidence
        ),
        "series": series_evidence,
    }