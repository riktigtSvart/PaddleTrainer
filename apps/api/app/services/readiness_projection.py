from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    AthleteReadiness,
    PhysiologicalMeasurement,
    User,
)


METRIC_TO_READINESS_FIELD = {
    "hrv_rmssd_ms": "hrv_rmssd_ms",
    "sleep_duration_sec": "sleep_duration_sec",
    "sleep_score": "sleep_score",
}

CONTEXT_METRIC_KEYS = {
    "background_hr_median_bpm",
}


def local_day_utc_bounds(
    recorded_date: date,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)

    local_start = datetime.combine(
        recorded_date,
        time.min,
        tzinfo=tz,
    )

    local_end = local_start + timedelta(days=1)

    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


async def project_readiness_for_date(
    db: AsyncSession,
    user: User,
    recorded_date: date,
) -> dict:
    utc_start, utc_end = local_day_utc_bounds(
        recorded_date,
        user.timezone,
    )

    result = await db.scalars(
        select(PhysiologicalMeasurement)
        .where(
            PhysiologicalMeasurement.user_id
            == user.id,
            PhysiologicalMeasurement.metric_key.in_(
                list(METRIC_TO_READINESS_FIELD.keys())
                + list(CONTEXT_METRIC_KEYS)
            ),
            PhysiologicalMeasurement.measured_at
            >= utc_start,
            PhysiologicalMeasurement.measured_at
            < utc_end,
        )
        .order_by(
            PhysiologicalMeasurement.measured_at.desc(),
            PhysiologicalMeasurement.created_at.desc(),
        )
    )

    measurements = list(result)

    # Ha ugyanabból a canonical metrikából
    # több provider/mérés van ugyanazon a napon,
    # egyelőre a legkésőbbi mérés nyer.
    selected: dict[
        str,
        PhysiologicalMeasurement,
    ] = {}

    for measurement in measurements:
        if (
            measurement.metric_key
            not in selected
        ):
            selected[
                measurement.metric_key
            ] = measurement

    if not selected:
        return {
            "recorded_date": recorded_date.isoformat(),
            "created": False,
            "updated_fields": [],
            "measurements_used": 0,
            "context_measurements_used": 0,
        }

    context_measurements_used = 0

    readiness = await db.scalar(
        select(AthleteReadiness).where(
            AthleteReadiness.user_id
            == user.id,
            AthleteReadiness.recorded_date
            == recorded_date,
        )
    )

    created = readiness is None

    if readiness is None:
        readiness = AthleteReadiness(
            user_id=user.id,
            recorded_date=recorded_date,
            source="PHYSIOLOGICAL_MEASUREMENTS",
            extra_data={},
        )

        db.add(readiness)

    updated_fields: list[str] = []

    provenance = dict(
        (
            readiness.extra_data
            or {}
        ).get(
            "objective_measurements",
            {}
        )
    )

    objective_context = dict(
        (readiness.extra_data or {}).get(
            "objective_context",
            {}
        )
    )

    for metric_key, measurement in selected.items():
        if measurement.value_float is None:
            continue

        availability = (
            (measurement.extra_data or {}).get(
                "availability"
            )
        )

        if metric_key in CONTEXT_METRIC_KEYS:
            objective_context[metric_key] = {
                "value": measurement.value_float,
                "unit": measurement.unit,
                "measurement_id": str(
                    measurement.id
                ),
                "provider": measurement.provider,
                "source_record_id": (
                    measurement.source_record_id
                ),
                "measured_at": (
                    measurement.measured_at.isoformat()
                ),
                "availability": availability,
            }

            context_measurements_used += 1
            continue

        field_name = (
            METRIC_TO_READINESS_FIELD[
                metric_key
            ]
        )

        value = measurement.value_float

        if field_name == "sleep_duration_sec":
            value = int(round(value))

        setattr(
            readiness,
            field_name,
            value,
        )

        updated_fields.append(field_name)

        provenance[metric_key] = {
            "measurement_id": str(
                measurement.id
            ),
            "provider": measurement.provider,
            "source_record_id": (
                measurement.source_record_id
            ),
            "measured_at": (
                measurement.measured_at.isoformat()
            ),
            "availability": availability,
        }

    extra_data = dict(readiness.extra_data or {})

    extra_data[
        "objective_measurements"
    ] = provenance

    extra_data["objective_context"] = (
        objective_context
    )

    readiness.extra_data = extra_data

    if not created:
        readiness.updated_at = (
            datetime.now(timezone.utc)
        )

    await db.commit()

    return {
        "recorded_date": recorded_date.isoformat(),
        "created": created,
        "updated_fields": sorted(
            updated_fields
        ),
        "measurements_used": len(
            updated_fields
        ),
        "context_measurements_used": (
            context_measurements_used
        ),
    }