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
DATA_TYPE = "NIGHTLY_RECHARGE"


def parse_polar_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


async def save_nightly_recharge_payload(
    db: AsyncSession,
    user: User,
    payload: dict,
) -> dict:
    items = payload.get(
        "nightlyRechargeResults",
        [],
    )

    imported = 0
    updated = 0
    skipped = 0

    fetched_at = datetime.now(timezone.utc)

    for item in items:
        sleep_result_date = item.get(
            "sleepResultDate"
        )

        if not sleep_result_date:
            skipped += 1
            continue

        existing = await db.scalar(
            select(ProviderDataRecord).where(
                ProviderDataRecord.user_id
                == user.id,
                ProviderDataRecord.provider
                == PROVIDER,
                ProviderDataRecord.data_type
                == DATA_TYPE,
                ProviderDataRecord.provider_record_id
                == sleep_result_date,
            )
        )

        occurred_at = parse_polar_datetime(
            item.get("created")
        )

        if existing is None:
            record = ProviderDataRecord(
                user_id=user.id,
                provider=PROVIDER,
                data_type=DATA_TYPE,
                provider_record_id=(
                    sleep_result_date
                ),
                occurred_at=occurred_at,
                period_start=None,
                period_end=None,
                raw_data=item,
                fetched_at=fetched_at,
            )

            db.add(record)
            imported += 1

        else:
            existing.occurred_at = occurred_at
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

async def normalize_nightly_recharge_measurements(
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
        rmssd = record.raw_data.get(
            "meanNightlyRecoveryRmssd"
        )

        if rmssd is None:
            skipped += 1
            continue

        source_record_id = str(record.id)

        availability = build_availability_metadata(
            period_start=record.period_start,
            period_end=record.period_end,
            total_observation_count=1,
            metric_observation_count=1,
        )

        existing = await db.scalar(
            select(PhysiologicalMeasurement).where(
                PhysiologicalMeasurement.user_id
                == user.id,
                PhysiologicalMeasurement.provider
                == PROVIDER,
                PhysiologicalMeasurement.metric_key
                == "hrv_rmssd_ms",
                PhysiologicalMeasurement.source_record_id
                == source_record_id,
            )
        )

        extra_data = {
            "data_type": DATA_TYPE,
            "provider_record_id": (
                record.provider_record_id
            ),
            "sleep_result_date": (
                record.raw_data.get(
                    "sleepResultDate"
                )
            ),
            "availability": availability,
        }

        if existing is None:
            measurement = PhysiologicalMeasurement(
                user_id=user.id,
                provider=PROVIDER,
                metric_key="hrv_rmssd_ms",
                value_float=float(rmssd),
                value_text=None,
                unit="ms",
                measured_at=record.occurred_at,
                period_start=record.period_start,
                period_end=record.period_end,
                device_id=None,
                device_model=None,
                quality=None,
                source_record_id=source_record_id,
                extra_data=extra_data,
            )

            db.add(measurement)
            imported += 1

        else:
            existing.value_float = float(rmssd)
            existing.unit = "ms"
            existing.measured_at = record.occurred_at
            existing.period_start = record.period_start
            existing.period_end = record.period_end
            existing.extra_data = extra_data

            updated += 1

    await db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total": len(records),
    }