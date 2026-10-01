from collections.abc import Iterable
from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    AthleteReadiness,
    User,
)


DEFAULT_HRV_REFERENCE_WINDOW_DAYS = 28


def build_hrv_reference(
    readiness_records: Iterable[AthleteReadiness],
    as_of_date: date,
    window_days: int = DEFAULT_HRV_REFERENCE_WINDOW_DAYS,
) -> dict:
    window_start = (
        as_of_date
        - timedelta(days=window_days)
    )

    window_end = (
        as_of_date
        - timedelta(days=1)
    )

    values = [
        float(record.hrv_rmssd_ms)
        for record in readiness_records
        if (
            window_start
            <= record.recorded_date
            < as_of_date
            and record.hrv_rmssd_ms
            is not None
        )
    ]

    reference_value = (
        float(median(values))
        if values
        else None
    )

    return {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "window_days": window_days,
        "window_start": window_start,
        "window_end": window_end,
        "sample_count": len(values),
        "reference_value": reference_value,
    }


async def get_hrv_reference(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    window_days: int = DEFAULT_HRV_REFERENCE_WINDOW_DAYS,
) -> dict:
    window_start = (
        as_of_date
        - timedelta(days=window_days)
    )

    result = await db.execute(
        select(AthleteReadiness)
        .where(
            AthleteReadiness.user_id
            == user.id,
            AthleteReadiness.recorded_date
            >= window_start,
            AthleteReadiness.recorded_date
            < as_of_date,
            AthleteReadiness.hrv_rmssd_ms
            .is_not(None),
        )
        .order_by(
            AthleteReadiness.recorded_date
        )
    )

    records = result.scalars().all()

    return build_hrv_reference(
        readiness_records=records,
        as_of_date=as_of_date,
        window_days=window_days,
    )


def compare_hrv_to_reference(
    current_value: float | None,
    reference: dict,
) -> dict:
    reference_value = reference.get(
        "reference_value"
    )

    relation = None

    if (
        current_value is not None
        and reference_value is not None
    ):
        if current_value > reference_value:
            relation = "ABOVE_PERSONAL_REFERENCE"
        elif current_value < reference_value:
            relation = "BELOW_PERSONAL_REFERENCE"
        else:
            relation = "AT_PERSONAL_REFERENCE"

    return {
        "metric_key": "hrv_rmssd_ms",
        "current_value": current_value,
        "reference_value": reference_value,
        "relation": relation,
        "reference_method": reference.get(
            "method"
        ),
        "reference_sample_count": reference.get(
            "sample_count",
            0,
        ),
    }