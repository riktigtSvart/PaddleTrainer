from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    AthleteResponse,
    User,
)


def serialize_response_observation(
    response: AthleteResponse,
) -> dict:
    return {
        "id": str(response.id),
        "workout_session_id": (
            str(response.workout_session_id)
            if response.workout_session_id
            else None
        ),
        "response_timing": (
            response.response_timing.value
        ),
        "recorded_at": response.recorded_at,
        "fatigue_score": response.fatigue_score,
        "soreness_score": response.soreness_score,
        "recovery_score": response.recovery_score,
        "energy_score": response.energy_score,
        "performance_metric": (
            response.performance_metric
        ),
        "performance_delta_percent": (
            response.performance_delta_percent
        ),
        "extra_data": response.extra_data,
    }


async def get_daily_response_observations(
    db: AsyncSession,
    user: User,
    recorded_date: date,
    timezone_name: str,
) -> list[dict]:
    local_timezone = ZoneInfo(
        timezone_name
    )

    day_start = datetime.combine(
        recorded_date,
        time.min,
        tzinfo=local_timezone,
    )

    day_end = datetime.combine(
        recorded_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    result = await db.scalars(
        select(AthleteResponse)
        .where(
            AthleteResponse.user_id == user.id,
            AthleteResponse.recorded_at >= day_start,
            AthleteResponse.recorded_at < day_end,
        )
        .order_by(
            AthleteResponse.recorded_at.asc()
        )
    )

    return [
        serialize_response_observation(item)
        for item in result
    ]

def build_response_trajectories(
    observations: list[dict],
) -> dict:
    trajectories_by_session: dict[str, dict] = {}
    unlinked_observations: list[dict] = []

    for observation in observations:
        workout_session_id = observation.get(
            "workout_session_id"
        )

        if workout_session_id is None:
            unlinked_observations.append(
                observation
            )
            continue

        if workout_session_id not in trajectories_by_session:
            trajectories_by_session[
                workout_session_id
            ] = {
                "workout_session_id": (
                    workout_session_id
                ),
                "observations": [],
            }

        trajectories_by_session[
            workout_session_id
        ]["observations"].append(
            observation
        )

    return {
        "by_workout_session": list(
            trajectories_by_session.values()
        ),
        "unlinked_observations": (
            unlinked_observations
        ),
    }