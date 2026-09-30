from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    AthleteCapacity,
    User,
)


def serialize_capacity_observation(
    capacity: AthleteCapacity,
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
        "capacity_type": (
            capacity.capacity_type.value
        ),
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
        "extra_data": capacity.extra_data,
    }


async def get_capacity_observations(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
) -> list[dict]:
    local_timezone = ZoneInfo(
        timezone_name
    )

    day_end = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    result = await db.scalars(
        select(AthleteCapacity)
        .where(
            AthleteCapacity.user_id == user.id,
            AthleteCapacity.estimated_at < day_end,
        )
        .order_by(
            AthleteCapacity.estimated_at.desc()
        )
    )

    return [
        serialize_capacity_observation(item)
        for item in result
    ]

def build_capacity_evidence(
    observations: list[dict],
) -> dict:
    groups: dict[
        tuple[str, str | None],
        dict,
    ] = {}

    for observation in observations:
        key = (
            observation["capacity_type"],
            observation["sport"],
        )

        if key not in groups:
            groups[key] = {
                "capacity_type": (
                    observation["capacity_type"]
                ),
                "sport": observation["sport"],
                "observations": [],
            }

        groups[key]["observations"].append(
            observation
        )

    return {
        "groups": list(groups.values()),
    }