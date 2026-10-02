from datetime import date
from types import SimpleNamespace

import pytest

from app.services.personal_readiness_reference import (
    build_resting_hr_reference,
    compare_resting_hr_to_reference,
)


def test_resting_hr_reference_builds_personal_median_and_mad():
    values = [
        48.0,
        50.0,
        51.0,
        49.0,
        52.0,
    ]

    records = [
        SimpleNamespace(
            recorded_date=date(
                2026,
                9,
                20 + index,
            ),
            resting_hr_bpm=value,
        )
        for index, value in enumerate(values)
    ]

    result = build_resting_hr_reference(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result["sample_count"] == 5
    assert result["reference_value"] == 50.0
    assert (
        result["median_absolute_deviation"]
        == 1.0
    )


def test_resting_hr_comparison_preserves_deviation_without_interpretation():
    reference = {
        "method": "RECENT_MEDIAN",
        "sample_count": 5,
        "sample_support": {
            "sample_count": 5,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_value": 50.0,
        "median_absolute_deviation": 1.0,
    }

    result = compare_resting_hr_to_reference(
        current_value=55.0,
        reference=reference,
    )

    assert result[
        "metric_key"
    ] == "resting_hr_bpm"

    assert result[
        "relation"
    ] == "ABOVE_PERSONAL_REFERENCE"

    assert result[
        "difference_from_reference"
    ] == pytest.approx(5.0)

    assert result[
        "relative_difference_from_reference"
    ] == pytest.approx(0.1)

    assert result[
        "difference_in_reference_mad_units"
    ] == pytest.approx(5.0)