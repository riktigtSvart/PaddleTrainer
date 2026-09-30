from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import AthleteReadiness
from app.services.users import get_or_create_demo_user
from app.services.readiness_evidence import (
    build_readiness_evidence,
)

router = APIRouter(
    prefix="/athlete-readiness",
    tags=["athlete-readiness"],
)


class AthleteReadinessUpdate(BaseModel):
    hrv_rmssd_ms: float | None = Field(
        default=None,
        ge=0,
    )

    resting_hr_bpm: float | None = Field(
        default=None,
        ge=0,
    )

    sleep_duration_sec: int | None = Field(
        default=None,
        ge=0,
    )

    sleep_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    energy_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    fatigue_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    stress_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    soreness_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    readiness_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    illness: bool = False
    travel: bool = False

    source: str = Field(
        default="MANUAL",
        min_length=1,
        max_length=32,
    )

    extra_data: dict[str, Any] = Field(
        default_factory=dict,
    )


SUBJECTIVE_FIELDS = {
    "energy_score",
    "fatigue_score",
    "stress_score",
    "soreness_score",
    "illness",
    "travel",
}


def merge_subjective_reported_fields(
    extra_data: dict[str, Any],
    payload: AthleteReadinessUpdate,
) -> dict[str, Any]:
    result = dict(extra_data)

    reported = set(
        result.get(
            "subjective_reported_fields",
            [],
        )
    )

    for field_name in SUBJECTIVE_FIELDS:
        if field_name not in payload.model_fields_set:
            continue

        value = getattr(
            payload,
            field_name,
        )

        if value is None:
            reported.discard(
                field_name
            )
        else:
            reported.add(
                field_name
            )

    result[
        "subjective_reported_fields"
    ] = sorted(reported)

    return result


def serialize_readiness(
    readiness: AthleteReadiness,
) -> dict:
    return {
        "id": str(readiness.id),
        "recorded_date": readiness.recorded_date,
        "hrv_rmssd_ms": readiness.hrv_rmssd_ms,
        "resting_hr_bpm": readiness.resting_hr_bpm,
        "sleep_duration_sec": readiness.sleep_duration_sec,
        "sleep_score": readiness.sleep_score,
        "energy_score": readiness.energy_score,
        "fatigue_score": readiness.fatigue_score,
        "stress_score": readiness.stress_score,
        "soreness_score": readiness.soreness_score,
        "readiness_score": readiness.readiness_score,
        "illness": readiness.illness,
        "travel": readiness.travel,
        "source": readiness.source,
        "extra_data": readiness.extra_data,
        "created_at": readiness.created_at,
        "updated_at": readiness.updated_at,
    }


@router.get("")
async def list_readiness(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    result = await db.scalars(
        select(AthleteReadiness)
        .where(
            AthleteReadiness.user_id == user.id
        )
        .order_by(
            AthleteReadiness.recorded_date.desc()
        )
    )

    return [
        serialize_readiness(item)
        for item in result
    ]


@router.get("/{recorded_date}/evidence")
async def get_readiness_evidence(
    recorded_date: date,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    readiness = await db.scalar(
        select(AthleteReadiness).where(
            AthleteReadiness.user_id == user.id,
            AthleteReadiness.recorded_date
            == recorded_date,
        )
    )

    if readiness is None:
        raise HTTPException(
            status_code=404,
            detail="Readiness record not found",
        )

    return build_readiness_evidence(
        readiness
    )


@router.put("/{recorded_date}")
async def upsert_readiness(
    recorded_date: date,
    payload: AthleteReadinessUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    readiness = await db.scalar(
        select(AthleteReadiness).where(
            AthleteReadiness.user_id == user.id,
            AthleteReadiness.recorded_date
            == recorded_date,
        )
    )

    if readiness is None:
        readiness = AthleteReadiness(
            user_id=user.id,
            recorded_date=recorded_date,
            hrv_rmssd_ms=payload.hrv_rmssd_ms,
            resting_hr_bpm=payload.resting_hr_bpm,
            sleep_duration_sec=payload.sleep_duration_sec,
            sleep_score=payload.sleep_score,
            energy_score=payload.energy_score,
            fatigue_score=payload.fatigue_score,
            stress_score=payload.stress_score,
            soreness_score=payload.soreness_score,
            readiness_score=payload.readiness_score,
            illness=payload.illness,
            travel=payload.travel,
            source=payload.source,
            extra_data=merge_subjective_reported_fields(
                payload.extra_data,
                payload,
            ),
        )

        db.add(readiness)

    else:
        updates = payload.model_dump(
            exclude_unset=True,
        )

        extra_data = updates.pop(
            "extra_data",
            None,
        )

        for field, value in updates.items():
            setattr(
                readiness,
                field,
                value,
            )

        merged_extra_data = {
            **(readiness.extra_data or {}),
            **(extra_data or {}),
        }

        readiness.extra_data = (
            merge_subjective_reported_fields(
                merged_extra_data,
                payload,
            )
        )

        readiness.updated_at = datetime.now(
            timezone.utc
        )

    await db.commit()

    return serialize_readiness(readiness)