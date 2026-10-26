"""Explicit presentation goals; these never authorize or change a training dose."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.planning.domain.goals.catalog import CapabilityKey


class GoalReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(pattern=r"^pt-workout-goal:[0-9a-f]{64}:[0-9a-f]{32}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkoutGoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    entity_kind: Literal["planned", "session"]
    entity_id: UUID
    previous_reference: GoalReference | None
    primary_goal: CapabilityKey | Literal["RECOVERY", "MIXED"] | None
