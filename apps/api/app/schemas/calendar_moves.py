"""Explicit, source-pinned timetable edits; no training-dose fields."""
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")

class MoveReference(Closed):
    artifact_id: str = Field(pattern=r"^pt-workout-move:[a-f0-9]{64}:[a-f0-9]{32}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

class MoveProposal(Closed):
    request_id: UUID
    plan_id: UUID
    expected_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    previous_reference: MoveReference | None
    timezone_name: str = Field(min_length=1, max_length=100)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str | None = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")
    start_fold: Literal[0, 1] | None

    @field_validator("date")
    @classmethod
    def calendar_date(cls, value):
        day = date.fromisoformat(value)
        if not date(1900,1,1) <= day <= date(2100,12,31):
            raise ValueError("Date outside supported calendar.")
        return value

    @model_validator(mode="before")
    @classmethod
    def strict_fold(cls, value):
        if isinstance(value, dict) and value.get("start_fold") is not None and type(value["start_fold"]) is not int:
            raise ValueError("Fold must be an integer.")
        return value

class MoveSave(Closed):
    proposal: MoveProposal
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
