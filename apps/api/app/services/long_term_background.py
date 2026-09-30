from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    Assessment,
    AssessmentType,
    Measurement,
    User,
)


def serialize_background_measurement(
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
    }


def serialize_background_assessment(
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
        "measurements": [
            serialize_background_measurement(item)
            for item in measurements
        ],
    }


async def get_long_term_background(
    db: AsyncSession,
    user: User,
    as_of_date: date,
    timezone_name: str,
) -> dict:
    local_timezone = ZoneInfo(
        timezone_name
    )

    day_end = datetime.combine(
        as_of_date + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )

    assessment_result = await db.scalars(
        select(Assessment)
        .where(
            Assessment.user_id == user.id,
            Assessment.assessment_type
            == AssessmentType.TRAINING_HISTORY,
            Assessment.performed_at < day_end,
        )
        .order_by(
            Assessment.performed_at.desc()
        )
    )

    assessments = list(
        assessment_result
    )

    if not assessments:
        return {
            "assessments": [],
        }

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
        ].append(
            measurement
        )

    return {
        "assessments": [
            serialize_background_assessment(
                assessment,
                measurements_by_assessment[
                    assessment.id
                ],
            )
            for assessment in assessments
        ],
    }

def build_long_term_background_evidence(
    background: dict,
) -> dict:
    by_sport: dict[str, dict] = {}
    unscoped_assessments: list[dict] = []

    for assessment in background.get(
        "assessments",
        [],
    ):
        sport = assessment.get("sport")

        if sport is None:
            unscoped_assessments.append(
                assessment
            )
            continue

        if sport not in by_sport:
            by_sport[sport] = {
                "sport": sport,
                "assessments": [],
            }

        by_sport[sport][
            "assessments"
        ].append(
            assessment
        )

    return {
        "by_sport": list(
            by_sport.values()
        ),
        "unscoped_assessments": (
            unscoped_assessments
        ),
    }