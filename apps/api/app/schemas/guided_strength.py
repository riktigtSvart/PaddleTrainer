"""Commands for a real, non-maximal, guided strength reference occasion."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.planning.domain.calendar_constraints import calendar_day
from app.schemas.athlete_setup import Closed
from app.schemas.initial_assessment import Reference, SetObservation
from app.schemas.planning_cycles import Day, Digest, Token

Instant = Annotated[str, StringConstraints(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$')]
Note = Annotated[str, StringConstraints(max_length=2000)]


class Observation(SetObservation):
    purpose: Literal['practice', 'reference']
    performed_on: Day

    @model_validator(mode='after')
    def valid_date(self):
        calendar_day(self.performed_on)
        return self


class ExerciseResult(Closed):
    entry_id: Token
    state: Literal['pending', 'recorded', 'skipped', 'stopped'] = 'pending'
    side: Literal['unknown', 'both', 'left', 'right', 'alternating'] = 'unknown'
    machine_note: str = Field(default='', max_length=200)
    note: Note = ''
    observations: list[Observation] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def unique_observations(self):
        if len({v.id for v in self.observations}) != len(self.observations) or len({v.purpose for v in self.observations}) != len(self.observations):
            raise ValueError('At most one practice and one reference observation per movement.')
        return self


class Progress(Closed):
    phase: Literal['warmup', 'movements', 'review'] = 'warmup'
    current_index: int = Field(default=0, ge=0, le=4)
    warmup_completed: bool = False
    results: list[ExerciseResult] = Field(min_length=1, max_length=5)
    note: Note = ''

    @model_validator(mode='after')
    def unique_results(self):
        if len({v.entry_id for v in self.results}) != len(self.results):
            raise ValueError('Movement results must be unique.')
        return self


class GuidedCommand(Closed):
    request_id: Token
    action: Literal['start', 'checkpoint', 'finish', 'abandon', 'apply']
    previous_reference: Reference | None
    assessment_reference: Reference
    source_hash: Digest
    location_id: Token
    selected_entry_ids: list[Token] = Field(min_length=1, max_length=5)
    recording_mode: Literal['device', 'manual']
    precheck_confirmed: bool
    progress: Progress
    actual_start_at: Instant | None = None
    actual_end_at: Instant | None = None
    workout_session_id: Token | None = None
    no_other_recording_confirmed: bool = False
    reviewed: bool = False

    @model_validator(mode='after')
    def coherent(self):
        if len(set(self.selected_entry_ids)) != len(self.selected_entry_ids):
            raise ValueError('Selected movement identities must be unique.')
        if [v.entry_id for v in self.progress.results] != self.selected_entry_ids:
            raise ValueError('Results retain the ordered selection.')
        if self.progress.current_index >= len(self.selected_entry_ids):
            raise ValueError('Current movement is outside the selection.')
        if (self.action == 'start') != (self.previous_reference is None):
            raise ValueError('A started session requires its previous revision.')
        for value in [self.actual_start_at, self.actual_end_at]:
            if value is not None and datetime.fromisoformat(value).tzinfo is None:
                raise ValueError('An aware clock is required.')
        return self
