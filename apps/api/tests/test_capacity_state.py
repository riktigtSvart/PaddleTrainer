from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services.capacity_state import (
    calculate_capacity_age_days,
    select_latest_capacity_records,
)


def test_select_latest_capacity_records_keeps_latest_per_dimension():
    records = [
        {
            "capacity_type": "GENERAL_AEROBIC",
            "sport": None,
            "value": 68.2,
            "unit": "ml/kg/min",
            "source": "MANUAL",
            "confidence": 0.5,
            "estimated_at": datetime(
                2026,
                9,
                30,
                6,
                30,
                tzinfo=timezone.utc,
            ),
        },
        {
            "capacity_type": "GENERAL_AEROBIC",
            "sport": None,
            "value": 68.2,
            "unit": "ml/kg/min",
            "source": "ASSESSMENT",
            "confidence": 0.95,
            "estimated_at": datetime(
                2026,
                9,
                30,
                7,
                0,
                tzinfo=timezone.utc,
            ),
        },
    ]

    result = select_latest_capacity_records(
        records
    )

    assert len(result) == 1

    assert result[0]["capacity_type"] == (
        "GENERAL_AEROBIC"
    )
    assert result[0]["sport"] is None
    assert result[0]["source"] == "ASSESSMENT"
    assert result[0]["confidence"] == 0.95
    assert result[0]["estimated_at"] == datetime(
        2026,
        9,
        30,
        7,
        0,
        tzinfo=timezone.utc,
    )


def test_capacity_age_days_uses_user_local_date():
    estimated_at = datetime(
        2026,
        9,
        29,
        22,
        30,
        tzinfo=timezone.utc,
    )

    result = calculate_capacity_age_days(
        estimated_at=estimated_at,
        as_of_date=date(
            2026,
            9,
            30,
        ),
        user_timezone=ZoneInfo(
            "Europe/Budapest"
        ),
    )

    assert result == 0