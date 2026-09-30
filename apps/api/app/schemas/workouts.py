from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.entities import BlockType, Sport, WorkoutStatus


class WorkoutBlockCreate(BaseModel):
    position: int
    block_type: BlockType
    name: str | None = None
    duration_sec: int | None = Field(default=None, ge=1)
    distance_m: float | None = Field(default=None, gt=0)
    intensity_type: str | None = None
    intensity_min: float | None = None
    intensity_max: float | None = None
    repeat_count: int | None = Field(default=None, ge=1)
    parent_block_id: UUID | None = None


class WorkoutCreate(BaseModel):
    date: date
    planned_start_time: datetime | None = None
    sport: Sport
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    duration_sec: int | None = Field(default=None, ge=1)
    distance_m: float | None = Field(default=None, gt=0)
    intensity_type: str | None = None
    status: WorkoutStatus = WorkoutStatus.PLANNED
    blocks: list[WorkoutBlockCreate] = Field(default_factory=list)


class WorkoutBlockOut(WorkoutBlockCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class WorkoutOut(BaseModel):
    id: UUID
    date: date
    planned_start_time: datetime | None
    sport: Sport
    title: str
    description: str | None
    duration_sec: int | None
    distance_m: float | None
    intensity_type: str | None
    status: WorkoutStatus
    source: str
    polar_target_id: str | None
    training_period_id: UUID | None
    blocks: list[WorkoutBlockOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
