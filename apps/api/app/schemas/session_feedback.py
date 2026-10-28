"""Explicit self reports; omission is unknown, never a zero score."""
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer, model_validator

class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    request_id: UUID
    timing: Literal["IMMEDIATE", "NEXT_MORNING"]
    expected_revision: int = Field(ge=0, strict=True)
    observed_at: datetime
    rpe: float | None = Field(default=None, ge=0, le=10)
    fatigue: float | None = Field(default=None, ge=0, le=10)
    soreness: float | None = Field(default=None, ge=0, le=10)
    recovery: float | None = Field(default=None, ge=0, le=10)
    energy: float | None = Field(default=None, ge=0, le=10)
    comment: str = Field(default="", max_length=2000, strict=True)

    @field_validator("rpe", "fatigue", "soreness", "recovery", "energy", mode="before")
    @classmethod
    def number(cls, value):
        if value is not None and (type(value) not in (int, float)):
            raise ValueError("Scores must be numbers or null")
        if value is not None and value != round(value, 1):
            raise ValueError("Use at most one decimal place")
        return value

    @field_serializer("rpe", "fatigue", "soreness", "recovery", "energy")
    def score_json(self, value):
        return int(value) if value is not None and value.is_integer() else value

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("An explicit timezone is required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.comment.strip() and all(getattr(self, k) is None for k in ("rpe", "fatigue", "soreness", "recovery", "energy")):
            raise ValueError("At least one answer is required")
        return self
