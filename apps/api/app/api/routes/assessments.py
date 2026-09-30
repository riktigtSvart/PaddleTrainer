from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import (
    Assessment,
    AssessmentType,
    Measurement,
    Sport,
)
from app.services.users import get_or_create_demo_user


router = APIRouter(
    prefix="/assessments",
    tags=["assessments"],
)


class MeasurementCreate(BaseModel):
    metric_key: str = Field(
        min_length=1,
        max_length=64,
    )

    value_float: float | None = None
    value_text: str | None = None

    unit: str | None = Field(
        default=None,
        max_length=32,
    )

    sport: Sport | None = None

    extra_data: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_value(self):
        has_float = self.value_float is not None

        has_text = (
            self.value_text is not None
            and self.value_text.strip() != ""
        )

        if not has_float and not has_text:
            raise ValueError(
                "Measurement requires "
                "value_float or value_text"
            )

        if has_float and has_text:
            raise ValueError(
                "Measurement cannot contain both "
                "value_float and value_text"
            )

        return self


class AssessmentCreate(BaseModel):
    assessment_type: AssessmentType

    sport: Sport | None = None

    title: str | None = Field(
        default=None,
        max_length=200,
    )

    performed_at: datetime

    source: str = Field(
        default="MANUAL",
        min_length=1,
        max_length=32,
    )

    notes: str | None = None

    extra_data: dict[str, Any] = Field(
        default_factory=dict,
    )

    measurements: list[
        MeasurementCreate
    ] = Field(
        min_length=1,
    )


def serialize_measurement(
    measurement: Measurement,
) -> dict:
    return {
        "id": str(measurement.id),
        "metric_key": measurement.metric_key,
        "value_float": measurement.value_float,
        "value_text": measurement.value_text,
        "unit": measurement.unit,
        "sport": (
            measurement.sport.value
            if measurement.sport
            else None
        ),
        "extra_data": measurement.extra_data,
        "created_at": measurement.created_at,
    }


def serialize_assessment(
    assessment: Assessment,
    measurements: list[Measurement],
) -> dict:
    return {
        "id": str(assessment.id),
        "assessment_type": (
            assessment.assessment_type.value
        ),
        "sport": (
            assessment.sport.value
            if assessment.sport
            else None
        ),
        "title": assessment.title,
        "performed_at": assessment.performed_at,
        "source": assessment.source,
        "notes": assessment.notes,
        "extra_data": assessment.extra_data,
        "created_at": assessment.created_at,
        "measurements": [
            serialize_measurement(measurement)
            for measurement in measurements
        ],
    }


@router.get("")
async def list_assessments(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    result = await db.scalars(
        select(Assessment)
        .where(
            Assessment.user_id == user.id
        )
        .order_by(
            Assessment.performed_at.desc()
        )
    )

    assessments = list(result)

    if not assessments:
        return []

    assessment_ids = [
        assessment.id
        for assessment in assessments
    ]

    measurement_result = await db.scalars(
        select(Measurement)
        .where(
            Measurement.assessment_id.in_(
                assessment_ids
            )
        )
        .order_by(
            Measurement.created_at.asc()
        )
    )

    measurements_by_assessment = {
        assessment_id: []
        for assessment_id in assessment_ids
    }

    for measurement in measurement_result:
        measurements_by_assessment[
            measurement.assessment_id
        ].append(measurement)

    return [
        serialize_assessment(
            assessment,
            measurements_by_assessment[
                assessment.id
            ],
        )
        for assessment in assessments
    ]


@router.post(
    "",
    status_code=201,
)
async def create_assessment(
    payload: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    assessment = Assessment(
        user_id=user.id,
        assessment_type=payload.assessment_type,
        sport=payload.sport,
        title=payload.title,
        performed_at=payload.performed_at,
        source=payload.source,
        notes=payload.notes,
        extra_data=payload.extra_data,
    )

    db.add(assessment)

    await db.flush()

    for item in payload.measurements:
        db.add(
            Measurement(
                assessment_id=assessment.id,
                metric_key=item.metric_key,
                value_float=item.value_float,
                value_text=item.value_text,
                unit=item.unit,
                sport=item.sport,
                extra_data=item.extra_data,
            )
        )

    await db.commit()

    measurement_result = await db.scalars(
        select(Measurement)
        .where(
            Measurement.assessment_id
            == assessment.id
        )
        .order_by(
            Measurement.created_at.asc()
        )
    )

    measurements = list(
        measurement_result
    )

    return serialize_assessment(
        assessment,
        measurements,
    )