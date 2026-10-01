from datetime import date
from types import SimpleNamespace

import uuid

import pytest

from app.services.personal_readiness_reference import (
    build_hrv_reference,
    get_hrv_reference,
    compare_hrv_to_reference,
    compare_sleep_duration_to_reference,
    build_sleep_duration_reference,
    get_sleep_duration_reference,
    describe_reference_sample_support,
    calculate_median_absolute_deviation,
)

def test_build_hrv_reference_uses_only_prior_values_inside_window():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 1),
            hrv_rmssd_ms=999.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 24),
            hrv_rmssd_ms=68.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 25),
            hrv_rmssd_ms=73.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 26),
            hrv_rmssd_ms=58.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 27),
            hrv_rmssd_ms=49.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 28),
            hrv_rmssd_ms=50.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            hrv_rmssd_ms=44.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 30),
            hrv_rmssd_ms=1000.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 10, 1),
            hrv_rmssd_ms=2000.0,
        ),
    ]

    result = build_hrv_reference(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "window_days": 28,
        "window_start": date(2026, 9, 2),
        "window_end": date(2026, 9, 29),
        "sample_count": 6,
        "sample_support": {
            "sample_count": 6,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_value": 54.0,
        "median_absolute_deviation": 7.5,
    }


def test_build_hrv_reference_returns_no_value_when_window_has_no_hrv_samples():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            hrv_rmssd_ms=None,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 30),
            hrv_rmssd_ms=58.0,
        ),
    ]

    result = build_hrv_reference(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "window_days": 28,
        "window_start": date(2026, 9, 2),
        "window_end": date(2026, 9, 29),
        "sample_count": 0,
        "sample_support": {
            "sample_count": 0,
            "state": "NO_SAMPLES",
        },
        "reference_value": None,
        "median_absolute_deviation": None,
    }


def test_build_hrv_reference_respects_custom_window_days():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 20),
            hrv_rmssd_ms=80.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 27),
            hrv_rmssd_ms=49.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 28),
            hrv_rmssd_ms=50.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            hrv_rmssd_ms=44.0,
        ),
    ]

    result = build_hrv_reference(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
        window_days=3,
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "window_days": 3,
        "window_start": date(2026, 9, 27),
        "window_end": date(2026, 9, 29),
        "sample_count": 3,
        "sample_support": {
            "sample_count": 3,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_value": 49.0,
        "median_absolute_deviation": 1.0,
    }


@pytest.mark.asyncio
async def test_get_hrv_reference_builds_reference_from_database_records():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 27),
            hrv_rmssd_ms=49.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 28),
            hrv_rmssd_ms=50.0,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            hrv_rmssd_ms=44.0,
        ),
    ]

    class FakeScalarResult:
        def all(self):
            return records

    class FakeResult:
        def scalars(self):
            return FakeScalarResult()

    class FakeDb:
        def __init__(self):
            self.statement = None

        async def execute(self, statement):
            self.statement = statement
            return FakeResult()

    db = FakeDb()

    user = SimpleNamespace(
        id=uuid.uuid4(),
    )

    result = await get_hrv_reference(
        db=db,
        user=user,
        as_of_date=date(2026, 9, 30),
        window_days=3,
    )

    assert db.statement is not None

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "window_days": 3,
        "window_start": date(2026, 9, 27),
        "window_end": date(2026, 9, 29),
        "sample_count": 3,
        "sample_support": {
            "sample_count": 3,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_value": 49.0,
        "median_absolute_deviation": 1.0,
    }


def test_compare_hrv_to_reference_describes_current_value_above_reference():
    reference = {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "sample_count": 6,
        "reference_value": 54.0,
        "sample_support": {
            "sample_count": 6,
            "state": "MULTIPLE_SAMPLES",
        },
        "median_absolute_deviation": 7.5,
    }

    result = compare_hrv_to_reference(
        current_value=58.4,
        reference=reference,
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "current_value": 58.4,
        "reference_value": 54.0,
        "relation": "ABOVE_PERSONAL_REFERENCE",
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 6,
        "reference_sample_support": {
            "sample_count": 6,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_median_absolute_deviation": 7.5,
    }


def test_compare_hrv_to_reference_does_not_infer_relation_without_reference():
    reference = {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "sample_count": 0,
        "reference_value": None,
    }

    result = compare_hrv_to_reference(
        current_value=58.4,
        reference=reference,
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "current_value": 58.4,
        "reference_value": None,
        "relation": None,
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 0,
        "reference_sample_support": None,
        "reference_median_absolute_deviation": None,
    }


def test_compare_hrv_to_reference_does_not_infer_relation_without_current_value():
    reference = {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "sample_count": 6,
        "reference_value": 54.0,
    }

    result = compare_hrv_to_reference(
        current_value=None,
        reference=reference,
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "current_value": None,
        "reference_value": 54.0,
        "relation": None,
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 6,
        "reference_sample_support": None,
        "reference_median_absolute_deviation": None,
    }


def test_build_sleep_duration_reference_uses_only_prior_values_inside_window():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 1),
            sleep_duration_sec=99999,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 27),
            sleep_duration_sec=25200,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 28),
            sleep_duration_sec=27000,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            sleep_duration_sec=23400,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 30),
            sleep_duration_sec=1,
        ),
    ]

    result = build_sleep_duration_reference(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result == {
        "metric_key": "sleep_duration_sec",
        "method": "RECENT_MEDIAN",
        "window_days": 28,
        "window_start": date(2026, 9, 2),
        "window_end": date(2026, 9, 29),
        "sample_count": 3,
        "sample_support": {
            "sample_count": 3,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_value": 25200.0,
        "median_absolute_deviation": 1800.0,
    }


@pytest.mark.asyncio
async def test_get_sleep_duration_reference_builds_reference_from_database_records():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 27),
            sleep_duration_sec=25200,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 28),
            sleep_duration_sec=27000,
        ),
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            sleep_duration_sec=23400,
        ),
    ]

    class FakeScalarResult:
        def all(self):
            return records

    class FakeResult:
        def scalars(self):
            return FakeScalarResult()

    class FakeDb:
        async def execute(self, statement):
            return FakeResult()

    db = FakeDb()

    user = SimpleNamespace(
        id=uuid.uuid4(),
    )

    result = await get_sleep_duration_reference(
        db=db,
        user=user,
        as_of_date=date(2026, 9, 30),
        window_days=3,
    )

    assert result == {
        "metric_key": "sleep_duration_sec",
        "method": "RECENT_MEDIAN",
        "window_days": 3,
        "window_start": date(2026, 9, 27),
        "window_end": date(2026, 9, 29),
        "sample_count": 3,
        "sample_support": {
            "sample_count": 3,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_value": 25200.0,
        "median_absolute_deviation": 1800.0,
    }


def test_describe_reference_sample_support_is_descriptive_only():
    assert describe_reference_sample_support(
        0
    ) == {
        "sample_count": 0,
        "state": "NO_SAMPLES",
    }

    assert describe_reference_sample_support(
        1
    ) == {
        "sample_count": 1,
        "state": "SINGLE_SAMPLE",
    }

    assert describe_reference_sample_support(
        6
    ) == {
        "sample_count": 6,
        "state": "MULTIPLE_SAMPLES",
    }


def test_sleep_reference_exposes_single_sample_support():
    records = [
        SimpleNamespace(
            recorded_date=date(2026, 9, 29),
            sleep_duration_sec=20790,
        ),
    ]

    result = build_sleep_duration_reference(
        readiness_records=records,
        as_of_date=date(2026, 9, 30),
    )

    assert result["sample_support"] == {
        "sample_count": 1,
        "state": "SINGLE_SAMPLE",
    }


def test_compare_sleep_duration_to_reference_preserves_single_sample_support():
    reference = {
        "metric_key": "sleep_duration_sec",
        "method": "RECENT_MEDIAN",
        "sample_count": 1,
        "reference_value": 20790.0,
        "sample_support": {
            "sample_count": 1,
            "state": "SINGLE_SAMPLE",
        },
    }

    result = compare_sleep_duration_to_reference(
        current_value=27600.0,
        reference=reference,
    )

    assert result == {
        "metric_key": "sleep_duration_sec",
        "current_value": 27600.0,
        "reference_value": 20790.0,
        "relation": "ABOVE_PERSONAL_REFERENCE",
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 1,
        "reference_sample_support": {
            "sample_count": 1,
            "state": "SINGLE_SAMPLE",
        },
        "reference_median_absolute_deviation": None,
    }


def test_calculate_median_absolute_deviation_for_hrv_reference_values():
    values = [
        68.0,
        73.0,
        58.0,
        49.0,
        50.0,
        44.0,
    ]

    result = (
        calculate_median_absolute_deviation(
            values
        )
    )

    assert result == 7.5