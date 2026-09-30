from datetime import (
    date,
    datetime,
    time,
    timedelta,
    timezone,
)
import statistics
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    PhysiologicalMeasurement,
    ProviderDataRecord,
    User,
)
from app.services.measurement_availability import (
    build_availability_metadata,
)


PROVIDER = "POLAR"
DATA_TYPE = "CONTINUOUS_HEART_RATE"
BACKGROUND_TRIGGER = "TRIGGER_TIMED_247"


def summarize_background_hr(
    item: dict,
) -> dict | None:
    samples = item.get("samples") or []

    values = [
        sample["heartRate"]
        for sample in samples
        if (
            sample.get("triggerType")
            == BACKGROUND_TRIGGER
            and isinstance(
                sample.get("heartRate"),
                int,
            )
        )
    ]

    if not values:
        return None

    return {
        "sample_count": len(values),
        "min_bpm": min(values),
        "max_bpm": max(values),
        "mean_bpm": statistics.mean(values),
        "median_bpm": statistics.median(values),
    }

def sample_datetime(
    sample_date: str,
    offset_millis: int,
    timezone_name: str,
) -> datetime:
    local_date = date.fromisoformat(
        sample_date
    )

    tz = ZoneInfo(timezone_name)

    local_midnight = datetime.combine(
        local_date,
        time.min,
        tzinfo=tz,
    )

    return local_midnight + timedelta(
        milliseconds=offset_millis
    )


async def save_continuous_hr_payload(
    db: AsyncSession,
    user: User,
    payload: dict,
) -> dict:
    items = payload.get(
        "heartRateSamplesPerDay",
        [],
    )

    imported = 0
    updated = 0
    skipped = 0

    fetched_at = datetime.now(timezone.utc)

    for item in items:
        sample_date = item.get("date")

        if not sample_date:
            skipped += 1
            continue

        device_ref = (
            item.get("deviceRef")
            or {}
        )

        device_id = device_ref.get(
            "deviceId"
        )

        provider_record_id = (
            f"{sample_date}:{device_id}"
            if device_id
            else sample_date
        )

        samples = item.get("samples") or []

        offsets = [
            sample.get("offsetMillis")
            for sample in samples
            if isinstance(
                sample.get("offsetMillis"),
                int,
            )
        ]

        if offsets:
            period_start = sample_datetime(
                sample_date,
                min(offsets),
                user.timezone,
            )

            period_end = sample_datetime(
                sample_date,
                max(offsets),
                user.timezone,
            )

            occurred_at = period_start

        else:
            period_start = None
            period_end = None
            occurred_at = None

        existing = await db.scalar(
            select(ProviderDataRecord).where(
                ProviderDataRecord.user_id
                == user.id,
                ProviderDataRecord.provider
                == PROVIDER,
                ProviderDataRecord.data_type
                == DATA_TYPE,
                ProviderDataRecord.provider_record_id
                == provider_record_id,
            )
        )

        if existing is None:
            record = ProviderDataRecord(
                user_id=user.id,
                provider=PROVIDER,
                data_type=DATA_TYPE,
                provider_record_id=(
                    provider_record_id
                ),
                occurred_at=occurred_at,
                period_start=period_start,
                period_end=period_end,
                raw_data=item,
                fetched_at=fetched_at,
            )

            db.add(record)
            imported += 1

        else:
            existing.occurred_at = (
                occurred_at
            )
            existing.period_start = (
                period_start
            )
            existing.period_end = (
                period_end
            )
            existing.raw_data = item
            existing.fetched_at = (
                fetched_at
            )

            updated += 1

    await db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total": len(items),
    }


METRIC_BACKGROUND_HR_MEDIAN = (
    "background_hr_median_bpm"
)


async def normalize_continuous_hr_measurements(
    db: AsyncSession,
    user: User,
) -> dict:
    result = await db.scalars(
        select(ProviderDataRecord).where(
            ProviderDataRecord.user_id == user.id,
            ProviderDataRecord.provider == PROVIDER,
            ProviderDataRecord.data_type == DATA_TYPE,
        )
    )

    records = list(result)

    imported = 0
    updated = 0
    skipped = 0

    for record in records:
        summary = summarize_background_hr(
            record.raw_data
        )

        if summary is None:
            skipped += 1
            continue

        coverage = summarize_continuous_hr_coverage(
            record.raw_data
        )

        availability = build_availability_metadata(
            period_start=record.period_start,
            period_end=record.period_end,
            total_observation_count=(
                coverage["all_sample_count"]
            ),
            metric_observation_count=(
                summary["sample_count"]
            ),
            max_observation_gap_sec=(
                coverage["max_gap_all_min"] * 60
                if coverage["max_gap_all_min"]
                   is not None
                else None
            ),
            max_metric_observation_gap_sec=(
                coverage["max_gap_timed_min"] * 60
                if coverage["max_gap_timed_min"]
                   is not None
                else None
            ),
        )

        source_record_id = str(record.id)

        existing = await db.scalar(
            select(
                PhysiologicalMeasurement
            ).where(
                PhysiologicalMeasurement.user_id
                == user.id,
                PhysiologicalMeasurement.provider
                == PROVIDER,
                PhysiologicalMeasurement.metric_key
                == METRIC_BACKGROUND_HR_MEDIAN,
                PhysiologicalMeasurement.source_record_id
                == source_record_id,
            )
        )

        raw = record.raw_data or {}

        device_id = (
            raw.get("deviceRef") or {}
        ).get("deviceId")

        measured_at = (
            record.period_end
            or record.occurred_at
        )

        extra_data = {
            "data_type": DATA_TYPE,
            "provider_record_id": (
                record.provider_record_id
            ),
            "sample_date": raw.get("date"),
            "sample_count": (
                summary["sample_count"]
            ),
            "source_trigger_type": (
                BACKGROUND_TRIGGER
            ),
            "min_bpm": summary["min_bpm"],
            "max_bpm": summary["max_bpm"],
            "mean_bpm": summary["mean_bpm"],
            "availability": availability,
        }

        if existing is None:
            measurement = (
                PhysiologicalMeasurement(
                    user_id=user.id,
                    provider=PROVIDER,
                    metric_key=(
                        METRIC_BACKGROUND_HR_MEDIAN
                    ),
                    value_float=(
                        summary["median_bpm"]
                    ),
                    unit="bpm",
                    measured_at=measured_at,
                    period_start=record.period_start,
                    period_end=record.period_end,
                    device_id=device_id,
                    source_record_id=(
                        source_record_id
                    ),
                    extra_data=extra_data,
                )
            )

            db.add(measurement)
            imported += 1

        else:
            existing.value_float = (
                summary["median_bpm"]
            )
            existing.unit = "bpm"
            existing.measured_at = measured_at
            existing.period_start = (
                record.period_start
            )
            existing.period_end = (
                record.period_end
            )
            existing.device_id = device_id
            existing.extra_data = extra_data

            updated += 1

    await db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total": len(records),
    }

def max_gap_minutes(
    offsets: list[int],
) -> float | None:
    if len(offsets) < 2:
        return None

    offsets = sorted(offsets)

    max_gap_ms = max(
        current - previous
        for previous, current in zip(
            offsets,
            offsets[1:],
        )
    )

    return max_gap_ms / 60000


def summarize_continuous_hr_coverage(
    item: dict,
) -> dict:
    samples = item.get("samples") or []

    all_offsets = [
        sample["offsetMillis"]
        for sample in samples
        if isinstance(
            sample.get("offsetMillis"),
            int,
        )
    ]

    timed_offsets = [
        sample["offsetMillis"]
        for sample in samples
        if (
            sample.get("triggerType")
            == BACKGROUND_TRIGGER
            and isinstance(
                sample.get("offsetMillis"),
                int,
            )
        )
    ]

    if all_offsets:
        span_hours = (
            max(all_offsets)
            - min(all_offsets)
        ) / 3_600_000
    else:
        span_hours = None

    return {
        "span_hours": span_hours,
        "all_sample_count": len(all_offsets),
        "timed_sample_count": len(timed_offsets),
        "max_gap_all_min": max_gap_minutes(
            all_offsets
        ),
        "max_gap_timed_min": max_gap_minutes(
            timed_offsets
        ),
    }