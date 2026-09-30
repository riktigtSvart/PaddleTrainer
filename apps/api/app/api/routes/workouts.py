from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.entities import (
    PeriodType,
    PlannedWorkout,
    TrainingPeriod,
    WorkoutBlock,
)
from app.schemas.workouts import WorkoutCreate, WorkoutOut
from app.services.users import get_or_create_demo_user

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.get("", response_model=list[WorkoutOut])
async def list_workouts(db: AsyncSession = Depends(get_db)):
    user = await get_or_create_demo_user(db)
    result = await db.scalars(
        select(PlannedWorkout)
        .options(selectinload(PlannedWorkout.blocks))
        .where(PlannedWorkout.user_id == user.id)
        .order_by(PlannedWorkout.date)
    )
    return list(result.unique())


@router.post("", response_model=WorkoutOut, status_code=201)
async def create_workout(payload: WorkoutCreate, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_demo_user(db)
    workout = PlannedWorkout(
        user_id=user.id,
        date=payload.date,
        planned_start_time=payload.planned_start_time,
        sport=payload.sport,
        title=payload.title,
        description=payload.description,
        duration_sec=payload.duration_sec,
        distance_m=payload.distance_m,
        intensity_type=payload.intensity_type,
        status=payload.status,
    )
    db.add(workout)
    await db.flush()
    for block in payload.blocks:
        db.add(
            WorkoutBlock(
                workout_id=workout.id,
                position=block.position,
                block_type=block.block_type,
                name=block.name,
                duration_sec=block.duration_sec,
                distance_m=block.distance_m,
                intensity_type=block.intensity_type,
                intensity_min=block.intensity_min,
                intensity_max=block.intensity_max,
                repeat_count=block.repeat_count,
                parent_block_id=block.parent_block_id,
            )
        )
    await db.commit()
    result = await db.scalar(
        select(PlannedWorkout)
        .options(selectinload(PlannedWorkout.blocks))
        .where(PlannedWorkout.id == workout.id)
    )
    return result

class WorkoutTrainingPeriodUpdate(BaseModel):
    training_period_id: UUID | None


@router.patch("/{workout_id}/training-period")
async def set_workout_training_period(
    workout_id: UUID,
    payload: WorkoutTrainingPeriodUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    workout = await db.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.id == workout_id,
            PlannedWorkout.user_id == user.id,
        )
    )

    if workout is None:
        raise HTTPException(
            status_code=404,
            detail="Workout not found",
        )

    if payload.training_period_id is None:
        workout.training_period_id = None
        await db.commit()

        return {
            "workout_id": str(workout.id),
            "workout_date": workout.date,
            "training_period_id": None,
        }

    period = await db.scalar(
        select(TrainingPeriod).where(
            TrainingPeriod.id
            == payload.training_period_id,
            TrainingPeriod.user_id == user.id,
        )
    )

    if period is None:
        raise HTTPException(
            status_code=404,
            detail="Training period not found",
        )

    if period.period_type != PeriodType.MESOCYCLE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Workouts can currently only be "
                "assigned directly to a MESOCYCLE"
            ),
        )

    if (
        workout.date < period.start_date
        or workout.date > period.end_date
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Workout date must fall inside "
                "the training period"
            ),
        )

    workout.training_period_id = period.id

    await db.commit()

    return {
        "workout_id": str(workout.id),
        "workout_date": workout.date,
        "training_period_id": str(period.id),
        "training_period_title": period.title,
        "training_period_start_date": period.start_date,
        "training_period_end_date": period.end_date,
    }