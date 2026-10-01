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
DEFAULT_SLEEP_DURATION_REFERENCE_WINDOW_DAYS = 28


def calculate_median_absolute_deviation(
    values: Iterable[float],
) -> float | None:
    values = [
        float(value)
        for value in values
    ]

    if not values:
        return None

    center = float(
        median(values)
    )

    absolute_deviations = [
        abs(value - center)
        for value in values
    ]

    return float(
        median(absolute_deviations)
    )


def _build_recent_median_reference(
    readiness_records: Iterable[AthleteReadiness],
    as_of_date: date,
    metric_key: str,
    window_days: int,
) -> dict:
    window_start = (
        as_of_date
        - timedelta(days=window_days)
    )

    window_end = (
        as_of_date
        - timedelta(days=1)
    )

    values = []

    for record in readiness_records:
        if not (
            window_start
            <= record.recorded_date
            < as_of_date
        ):
            continue

        value = getattr(
            record,
            metric_key,
            None,
        )

        if value is None:
            continue

        values.append(float(value))

    reference_value = (
        float(median(values))
        if values
        else None
    )

    median_absolute_deviation = (
        calculate_median_absolute_deviation(
            values
        )
        if len(values) >= 2
        else None
    )

    return {
        "metric_key": metric_key,
        "method": "RECENT_MEDIAN",
        "window_days": window_days,
        "window_start": window_start,
        "window_end": window_end,
        "sample_count": len(values),
        "reference_value": reference_value,
        "sample_support": (
            describe_reference_sample_support(
                len(values)
            )
        ),
        "median_absolute_deviation": (
            median_absolute_deviation
        ),
    }


def build_hrv_reference(
    readiness_records: Iterable[AthleteReadiness],
    as_of_date: date,
    window_days: int = DEFAULT_HRV_REFERENCE_WINDOW_DAYS,
) -> dict:
    return _build_recent_median_reference(
        readiness_records=readiness_records,
        as_of_date=as_of_date,
        metric_key="hrv_rmssd_ms",
        window_days=window_days,
    )


def build_sleep_duration_reference(
    readiness_records: Iterable[AthleteReadiness],
    as_of_date: date,
    window_days: int = (
        DEFAULT_SLEEP_DURATION_REFERENCE_WINDOW_DAYS
    ),
) -> dict:
    return _build_recent_median_reference(
        readiness_records=readiness_records,
        as_of_date=as_of_date,
        metric_key="sleep_duration_sec",
        window_days=window_days,
    )


async def _get_reference_records(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    window_days: int,
    metric_column,
) -> list[AthleteReadiness]:
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
            metric_column.is_not(None),
        )
        .order_by(
            AthleteReadiness.recorded_date
        )
    )

    return list(
        result.scalars().all()
    )


async def get_hrv_reference(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    window_days: int = DEFAULT_HRV_REFERENCE_WINDOW_DAYS,
) -> dict:
    records = await _get_reference_records(
        db=db,
        user=user,
        as_of_date=as_of_date,
        window_days=window_days,
        metric_column=(
            AthleteReadiness.hrv_rmssd_ms
        ),
    )

    return build_hrv_reference(
        readiness_records=records,
        as_of_date=as_of_date,
        window_days=window_days,
    )


async def get_sleep_duration_reference(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    window_days: int = (
        DEFAULT_SLEEP_DURATION_REFERENCE_WINDOW_DAYS
    ),
) -> dict:
    records = await _get_reference_records(
        db=db,
        user=user,
        as_of_date=as_of_date,
        window_days=window_days,
        metric_column=(
            AthleteReadiness.sleep_duration_sec
        ),
    )

    return build_sleep_duration_reference(
        readiness_records=records,
        as_of_date=as_of_date,
        window_days=window_days,
    )


def _compare_metric_to_reference(
    current_value: float | None,
    reference: dict,
    metric_key: str,
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

    difference_from_reference = (
        round(
            float(current_value)
            - float(reference_value),
            10,
        )
        if (
                current_value is not None
                and reference_value is not None
        )
        else None
    )

    return {
        "metric_key": metric_key,
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
        "reference_sample_support": reference.get(
            "sample_support"
        ),
        "reference_median_absolute_deviation": (
            reference.get(
                "median_absolute_deviation"
            )
        ),
        "difference_from_reference": (
            difference_from_reference
        ),
    }


def compare_hrv_to_reference(
    current_value: float | None,
    reference: dict,
) -> dict:
    return _compare_metric_to_reference(
        current_value=current_value,
        reference=reference,
        metric_key="hrv_rmssd_ms",
    )


def compare_sleep_duration_to_reference(
    current_value: float | None,
    reference: dict,
) -> dict:
    return _compare_metric_to_reference(
        current_value=current_value,
        reference=reference,
        metric_key="sleep_duration_sec",
    )


def describe_reference_sample_support(
    sample_count: int,
) -> dict:
    if sample_count <= 0:
        state = "NO_SAMPLES"
    elif sample_count == 1:
        state = "SINGLE_SAMPLE"
    else:
        state = "MULTIPLE_SAMPLES"

    return {
        "sample_count": sample_count,
        "state": state,
    }