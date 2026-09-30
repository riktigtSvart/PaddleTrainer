from datetime import datetime, timezone

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
DATA_TYPE = "SLEEP"


def parse_polar_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


async def save_sleep_payload(
    db: AsyncSession,
    user: User,
    payload: dict,
) -> dict:
    items = payload.get(
        "nightSleeps",
        [],
    )

    imported = 0
    updated = 0
    skipped = 0

    fetched_at = datetime.now(timezone.utc)

    for item in items:
        sleep_date = item.get("sleepDate")

        if not sleep_date:
            skipped += 1
            continue

        sleep_result = (
            item.get("sleepResult")
            or {}
        )

        hypnogram = (
            sleep_result.get("hypnogram")
            or {}
        )

        sleep_score = (
            item.get("sleepScore")
            or {}
        )

        period_start = parse_polar_datetime(
            hypnogram.get("sleepStart")
        )

        period_end = parse_polar_datetime(
            hypnogram.get("sleepEnd")
        )

        occurred_at = parse_polar_datetime(
            sleep_score.get("created")
        )

        existing = await db.scalar(
            select(ProviderDataRecord).where(
                ProviderDataRecord.user_id
                == user.id,
                ProviderDataRecord.provider
                == PROVIDER,
                ProviderDataRecord.data_type
                == DATA_TYPE,
                ProviderDataRecord.provider_record_id
                == sleep_date,
            )
        )

        if existing is None:
            record = ProviderDataRecord(
                user_id=user.id,
                provider=PROVIDER,
                data_type=DATA_TYPE,
                provider_record_id=sleep_date,
                occurred_at=occurred_at,
                period_start=period_start,
                period_end=period_end,
                raw_data=item,
                fetched_at=fetched_at,
            )

            db.add(record)
            imported += 1

        else:
            existing.occurred_at = occurred_at
            existing.period_start = period_start
            existing.period_end = period_end
            existing.raw_data = item
            existing.fetched_at = fetched_at

            updated += 1

    await db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total": len(items),
    }

def parse_polar_duration_seconds(
    value: str | None,
) -> float | None:
    if not value:
        return None

    if not value.endswith("s"):
        return None

    try:
        return float(value[:-1])
    except ValueError:
        return None


async def normalize_sleep_measurements(
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
        raw = record.raw_data or {}

        evaluation = (
            raw.get("sleepEvaluation")
            or {}
        )

        score_data = (
            raw.get("sleepScore")
            or {}
        )

        sleep_duration = (
            parse_polar_duration_seconds(
                evaluation.get(
                    "asleepDuration"
                )
            )
        )

        sleep_score = score_data.get(
            "sleepScore"
        )

        source_record_id = str(record.id)

        measured_at = (
            record.period_end
            or record.occurred_at
        )

        availability = build_availability_metadata(
            period_start=record.period_start,
            period_end=record.period_end,
            total_observation_count=1,
            metric_observation_count=1,
        )

        metrics = [
            (
                "sleep_duration_sec",
                sleep_duration,
                "s",
            ),
            (
                "sleep_score",
                (
                    float(sleep_score)
                    if sleep_score is not None
                    else None
                ),
                "score",
            ),
        ]

        for (
            metric_key,
            value,
            unit,
        ) in metrics:
            if value is None:
                skipped += 1
                continue

            existing = await db.scalar(
                select(
                    PhysiologicalMeasurement
                ).where(
                    PhysiologicalMeasurement.user_id
                    == user.id,
                    PhysiologicalMeasurement.provider
                    == PROVIDER,
                    PhysiologicalMeasurement.metric_key
                    == metric_key,
                    PhysiologicalMeasurement.source_record_id
                    == source_record_id,
                )
            )

            extra_data = {
                "data_type": DATA_TYPE,
                "provider_record_id": (
                    record.provider_record_id
                ),
                "sleep_date": (
                    raw.get("sleepDate")
                ),
                "availability": availability,
            }

            if existing is None:
                measurement = (
                    PhysiologicalMeasurement(
                        user_id=user.id,
                        provider=PROVIDER,
                        metric_key=metric_key,
                        value_float=value,
                        value_text=None,
                        unit=unit,
                        measured_at=measured_at,
                        period_start=(
                            record.period_start
                        ),
                        period_end=(
                            record.period_end
                        ),
                        device_id=None,
                        device_model=None,
                        quality=None,
                        source_record_id=(
                            source_record_id
                        ),
                        extra_data=extra_data,
                    )
                )

                db.add(measurement)
                imported += 1

            else:
                existing.value_float = value
                existing.unit = unit
                existing.measured_at = (
                    measured_at
                )
                existing.period_start = (
                    record.period_start
                )
                existing.period_end = (
                    record.period_end
                )
                existing.extra_data = (
                    extra_data
                )

                updated += 1

    await db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "records": len(records),
    }