from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import (
    AthleteResponse,
    ResponseTiming,
    WorkoutSession,
)
from app.services.users import get_or_create_demo_user


router = APIRouter(
    prefix="/athlete-responses",
    tags=["athlete-responses"],
)


class AthleteResponseCreate(BaseModel):
    workout_session_id: UUID

    response_timing: ResponseTiming

    recorded_at: datetime

    fatigue_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    soreness_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    recovery_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    energy_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    performance_metric: str | None = Field(
        default=None,
        max_length=64,
    )

    performance_delta_percent: float | None = None

    extra_data: dict = Field(
        default_factory=dict,
    )


def serialize_response(
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
        "created_at": response.created_at,
    }


@router.get("")
async def list_responses(
    workout_session_id: UUID | None = Query(
        default=None
    ),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    query = (
        select(AthleteResponse)
        .where(
            AthleteResponse.user_id == user.id
        )
        .order_by(
            AthleteResponse.recorded_at.asc()
        )
    )

    if workout_session_id is not None:
        query = query.where(
            AthleteResponse.workout_session_id
            == workout_session_id
        )

    result = await db.scalars(query)

    return [
        serialize_response(response)
        for response in result
    ]


@router.post(
    "",
    status_code=201,
)
async def create_response(
    payload: AthleteResponseCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    session = await db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.id
            == payload.workout_session_id,
            WorkoutSession.user_id
            == user.id,
        )
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Workout session not found",
        )

    response = AthleteResponse(
        user_id=user.id,
        workout_session_id=(
            payload.workout_session_id
        ),
        response_timing=payload.response_timing,
        recorded_at=payload.recorded_at,
        fatigue_score=payload.fatigue_score,
        soreness_score=payload.soreness_score,
        recovery_score=payload.recovery_score,
        energy_score=payload.energy_score,
        performance_metric=(
            payload.performance_metric
        ),
        performance_delta_percent=(
            payload.performance_delta_percent
        ),
        extra_data=payload.extra_data,
    )

    db.add(response)

    await db.commit()

    return serialize_response(response)