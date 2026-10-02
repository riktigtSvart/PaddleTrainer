from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AthleteCapacity, User


def calculate_capacity_age_days(
    *,
    estimated_at: datetime,
    as_of_date: date,
    user_timezone: ZoneInfo,
) -> int:
    estimated_local_date = (
        estimated_at.astimezone(
            user_timezone
        ).date()
    )

    return (
        as_of_date
        - estimated_local_date
    ).days


def serialize_capacity_state_item(
    capacity: AthleteCapacity,
    *,
    as_of_date: date,
    user_timezone: ZoneInfo,
) -> dict:
    return {
        "id": str(capacity.id),
        "assessment_id": (
            str(capacity.assessment_id)
            if capacity.assessment_id
            else None
        ),
        "measurement_id": (
            str(capacity.measurement_id)
            if capacity.measurement_id
            else None
        ),
        "capacity_type": capacity.capacity_type.value,
        "sport": (
            capacity.sport.value
            if capacity.sport
            else None
        ),
        "value": capacity.value,
        "unit": capacity.unit,
        "source": capacity.source.value,
        "confidence": capacity.confidence,
        "estimated_at": capacity.estimated_at,
        "age_days": calculate_capacity_age_days(
            estimated_at=capacity.estimated_at,
            as_of_date=as_of_date,
            user_timezone=user_timezone,
        ),
    }


def select_latest_capacity_records(
    records: list[dict],
) -> list[dict]:
    latest_by_dimension: dict[
        tuple[str, str | None],
        dict,
    ] = {}

    for record in records:
        key = (
            record["capacity_type"],
            record["sport"],
        )

        current = latest_by_dimension.get(key)

        if (
            current is None
            or record["estimated_at"]
            > current["estimated_at"]
        ):
            latest_by_dimension[key] = record

    return sorted(
        latest_by_dimension.values(),
        key=lambda record: record["estimated_at"],
        reverse=True,
    )


async def get_current_capacity_state(
    *,
    db: AsyncSession,
    user: User,
    as_of_date: date,
) -> list[dict]:
    user_timezone = ZoneInfo(user.timezone)

    next_local_midnight = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=user_timezone,
    )

    cutoff_utc = next_local_midnight.astimezone(
        timezone.utc
    )

    result = await db.scalars(
        select(AthleteCapacity)
        .where(
            AthleteCapacity.user_id == user.id,
            AthleteCapacity.estimated_at < cutoff_utc,
        )
        .order_by(
            AthleteCapacity.estimated_at.desc(),
            AthleteCapacity.created_at.desc(),
        )
    )

    records = [
        serialize_capacity_state_item(
            capacity,
            as_of_date=as_of_date,
            user_timezone=user_timezone,
        )
        for capacity in result
    ]

    return select_latest_capacity_records(
        records
    )