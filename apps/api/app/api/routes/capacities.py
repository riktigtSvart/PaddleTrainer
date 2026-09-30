from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import (
    Assessment,
    AthleteCapacity,
    CapacitySource,
    CapacityType,
    Measurement,
    Sport,
)
from app.services.users import get_or_create_demo_user


router = APIRouter(
    prefix="/athlete-capacities",
    tags=["athlete-capacities"],
)


class AthleteCapacityCreate(BaseModel):
    assessment_id: UUID | None = None
    measurement_id: UUID | None = None

    capacity_type: CapacityType
    sport: Sport | None = None

    value: float

    unit: str = Field(
        min_length=1,
        max_length=32,
    )

    source: CapacitySource

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    estimated_at: datetime

    extra_data: dict[str, Any] = Field(
        default_factory=dict,
    )


def serialize_capacity(
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
        "extra_data": capacity.extra_data,
        "created_at": capacity.created_at,
    }


@router.get("")
async def list_capacities(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    result = await db.scalars(
        select(AthleteCapacity)
        .where(
            AthleteCapacity.user_id == user.id
        )
        .order_by(
            AthleteCapacity.estimated_at.desc()
        )
    )

    return [
        serialize_capacity(capacity)
        for capacity in result
    ]


@router.post(
    "",
    status_code=201,
)
async def create_capacity(
    payload: AthleteCapacityCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    if payload.assessment_id is not None:
        assessment = await db.scalar(
            select(Assessment).where(
                Assessment.id
                == payload.assessment_id,
                Assessment.user_id
                == user.id,
            )
        )

        if assessment is None:
            raise HTTPException(
                status_code=404,
                detail="Assessment not found",
            )

    resolved_assessment_id = payload.assessment_id

    if payload.measurement_id is not None:
        measurement = await db.scalar(
            select(Measurement)
            .join(
                Assessment,
                Assessment.id
                == Measurement.assessment_id,
            )
            .where(
                Measurement.id
                == payload.measurement_id,
                Assessment.user_id
                == user.id,
            )
        )

        if measurement is None:
            raise HTTPException(
                status_code=404,
                detail="Measurement not found",
            )

        if (
            resolved_assessment_id is not None
            and resolved_assessment_id
            != measurement.assessment_id
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Measurement does not belong "
                    "to the specified assessment"
                ),
            )

        resolved_assessment_id = (
            measurement.assessment_id
        )

    capacity = AthleteCapacity(
        user_id=user.id,
        assessment_id=resolved_assessment_id,
        measurement_id=payload.measurement_id,
        capacity_type=payload.capacity_type,
        sport=payload.sport,
        value=payload.value,
        unit=payload.unit,
        source=payload.source,
        confidence=payload.confidence,
        estimated_at=payload.estimated_at,
        extra_data=payload.extra_data,
    )

    db.add(capacity)
    await db.commit()

    return serialize_capacity(capacity)