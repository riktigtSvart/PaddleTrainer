from datetime import date
from types import SimpleNamespace

import pytest

from app.services.personal_readiness_reference import (
    build_hrv_trend_evidence,
    calculate_ln_rmssd,
)


def test_calculate_ln_rmssd_requires_positive_value():
    assert calculate_ln_rmssd(None) is None
    assert calculate_ln_rmssd(0.0) is None
    assert calculate_ln_rmssd(-1.0) is None


def test_hrv_trend_evidence_builds_rolling_lnrmssd_mean_and_cv():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 23),
            hrv_rmssd_ms=100.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 24),
            hrv_rmssd_ms=50.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 27),
            hrv_rmssd_ms=55.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 30),
            hrv_rmssd_ms=60.0,
        ),
    ]

    result = build_hrv_trend_evidence(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result["window_start"] == date(
        2026,
        9,
        24,
    )
    assert result["window_end"] == date(
        2026,
        9,
        30,
    )

    assert result["sample_count"] == 3

    assert result["sample_support"] == {
        "sample_count": 3,
        "state": "MULTIPLE_SAMPLES",
    }

    assert result["current_ln_rmssd"] == pytest.approx(
        4.0943445622
    )

    assert result[
        "rolling_mean_ln_rmssd"
    ] == pytest.approx(
        4.0045669176
    )

    assert result[
        "rolling_cv_percent"
    ] == pytest.approx(
        2.2772063288
    )


def test_hrv_trend_evidence_preserves_missing_variability_with_single_sample():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 30),
            hrv_rmssd_ms=60.0,
        ),
    ]

    result = build_hrv_trend_evidence(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result["sample_count"] == 1
    assert result["rolling_mean_ln_rmssd"] is not None
    assert result["rolling_cv_percent"] is None