from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    AthleteReadiness,
    User,
)
from app.services.readiness_evidence import (
    build_readiness_evidence,
)
from app.services.training_load import (
    get_training_load_proxies,
)
from app.services.response_observations import (
    build_response_trajectories,
    get_daily_response_observations,
)
from app.services.capacity_observations import (
    build_capacity_evidence,
    get_capacity_observations,
)


async def get_athlete_state(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
) -> dict:
    training_load = await get_training_load_proxies(
        db=db,
        user=user,
        as_of_date=as_of_date,
        timezone_name=timezone_name,
    )

    readiness = await db.scalar(
        select(AthleteReadiness).where(
            AthleteReadiness.user_id == user.id,
            AthleteReadiness.recorded_date
            == as_of_date,
        )
    )

    readiness_evidence = (
        build_readiness_evidence(readiness)
        if readiness is not None
        else None
    )

    responses = await get_daily_response_observations(
        db=db,
        user=user,
        recorded_date=as_of_date,
        timezone_name=timezone_name,
    )

    response_trajectories = (
        build_response_trajectories(
            responses
        )
    )

    capacity_observations = (
        await get_capacity_observations(
            db=db,
            user=user,
            as_of_date=as_of_date,
            timezone_name=timezone_name,
        )
    )

    capacity_evidence = build_capacity_evidence(
        capacity_observations
    )

    return {
        "as_of_date": as_of_date,
        "training_load": training_load,
        "readiness": readiness_evidence,
        "responses": responses,
        "response_trajectories": (
            response_trajectories
        ),
        "capacity_observations": (
            capacity_observations
        ),
        "capacity_evidence": (
            capacity_evidence
        ),
    }