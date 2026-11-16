"""Actual work sets, distinct from a plan or a formal assessment."""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.schemas.athlete_setup import Closed
from app.schemas.initial_assessment import ExerciseEntry, Text
from app.schemas.planning_cycles import Token


class StrengthWorkoutInput(Closed):
    request_id: Token
    expected_revision: int = Field(ge=0, strict=True)
    purpose: Literal['training', 'assessment']
    exercises: list[ExerciseEntry] = Field(min_length=1, max_length=16)
    note: Text = ''
    confirmed_actual: Literal[True]

    @field_validator('confirmed_actual', mode='before')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('Explicit actual confirmation is required')
        return value

    @model_validator(mode='after')
    def actual(self):
        if len({e.id for e in self.exercises}) != len(self.exercises):
            raise ValueError('Duplicate exercises')
        if any(not e.exercise_id or not e.location_id or not e.performed_on or not e.sets
               or e.side == 'unknown' for e in self.exercises):
            raise ValueError('Actual exercise, venue, day, side and sets are required')
        if any(s.repetitions is None and s.hold_seconds is None for e in self.exercises for s in e.sets):
            raise ValueError('Record actual repetitions or hold duration for each set')
        return self
