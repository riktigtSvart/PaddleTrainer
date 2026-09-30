from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.users import get_or_create_demo_user
from app.services.workout_comparison import (
    get_workout_comparisons,
)


router = APIRouter(
    prefix="/coach",
    tags=["coach"],
)


@router.get("/workouts")
async def list_workout_comparisons(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    return await get_workout_comparisons(
        db,
        user,
    )

@router.get("/workouts/{workout_id}")
async def get_workout_detail(
    workout_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    workouts = await get_workout_comparisons(
        db,
        user,
    )

    workout = next(
        (
            item
            for item in workouts
            if item["planned"]["id"]
            == str(workout_id)
        ),
        None,
    )

    if workout is None:
        raise HTTPException(
            status_code=404,
            detail="Workout not found",
        )

    return workout