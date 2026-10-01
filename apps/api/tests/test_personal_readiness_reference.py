from datetime import date
from types import SimpleNamespace

import uuid

import pytest

from app.services.personal_readiness_reference import (
    build_hrv_reference,
    get_hrv_reference,
    compare_hrv_to_reference,
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
        "reference_value": 54.0,
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
        "reference_value": None,
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
        "reference_value": 49.0,
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
        "reference_value": 49.0,
    }


def test_compare_hrv_to_reference_describes_current_value_above_reference():
    reference = {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "sample_count": 6,
        "reference_value": 54.0,
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
    }