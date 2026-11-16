"""Declared assessment inputs; missing measurements remain explicit nulls."""
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, StringConstraints, model_validator

from app.planning.domain.calendar_constraints import calendar_day
from app.schemas.athlete_setup import Closed
from app.schemas.planning_cycles import Day, Digest, Token

Text = Annotated[str, StringConstraints(max_length=2000)]
Short = Annotated[str, StringConstraints(max_length=200)]
Key = Annotated[str, StringConstraints(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')]
Number = Annotated[str, StringConstraints(pattern=r'^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$')]


class Reference(Closed):
    artifact_id: str = Field(min_length=1, max_length=160)
    content_hash: Digest


class SportEntry(Closed):
    sport_key: Key
    role: Literal['unknown', 'primary', 'secondary', 'recreation', 'paused'] = 'unknown'
    discipline: Short = ''
    goal: Short = ''
    notes: Text = ''


class SetObservation(Closed):
    id: Token
    repetitions: int | None = Field(default=None, ge=0, le=10000)
    hold_seconds: Number | None = None
    load_kind: Literal['unknown', 'bodyweight', 'external_kg', 'assistance_kg', 'machine_level', 'band'] = 'unknown'
    load_value: Number | None = None
    load_basis: Literal['unknown', 'total', 'per_hand', 'machine_display', 'assistance', 'not_applicable'] = 'unknown'
    load_note: Short = ''
    rir: Literal['unknown', '0', '1', '2', '3', '4', '5_plus'] = 'unknown'
    technique: Literal['unknown', 'stable', 'uncertain', 'breakdown'] = 'unknown'
    symptoms: Literal['unknown', 'none', 'discomfort', 'pain'] = 'unknown'

    @model_validator(mode='after')
    def coherent(self):
        if self.repetitions is not None and self.hold_seconds is not None:
            raise ValueError('Choose repetition count or hold duration for one set.')
        if self.load_kind in {'unknown', 'bodyweight', 'band'} and self.load_value is not None:
            raise ValueError('This load type has no kilogram/level value.')
        if self.load_kind == 'bodyweight' and self.load_basis != 'not_applicable':
            raise ValueError('Bodyweight is not an inferred kilogram load.')
        allowed = {'unknown': {'unknown'}, 'bodyweight': {'not_applicable'}, 'band': {'unknown', 'not_applicable'},
                   'external_kg': {'unknown', 'total', 'per_hand', 'machine_display'},
                   'assistance_kg': {'unknown', 'assistance'}, 'machine_level': {'unknown', 'machine_display'}}
        if self.load_basis not in allowed[self.load_kind]:
            raise ValueError('Load basis does not match the declared load kind.')
        return self


class ExerciseEntry(Closed):
    id: Token
    pattern: Literal['pull', 'push', 'knee', 'hip', 'core']
    exercise_id: Key | None = None
    location_id: Token | None = None
    familiarity: Literal['unknown', 'unfamiliar', 'assisted', 'independent', 'regular'] = 'unknown'
    comfort: Literal['unknown', 'none', 'uncertain', 'symptoms', 'avoid', 'no_experience'] = 'unknown'
    performed_on: Day | None = None
    side: Literal['unknown', 'both', 'left', 'right', 'alternating'] = 'unknown'
    machine_note: Short = ''
    notes: Text = ''
    sets: list[SetObservation] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unique_sets(self):
        if len({v.id for v in self.sets}) != len(self.sets):
            raise ValueError('Set identities must be unique.')
        return self


class SportReference(Closed):
    id: Token
    sport_key: Key
    performed_on: Day | None = None
    protocol: Short = ''
    location_id: Token | None = None
    distance_m: Number | None = None
    duration_minutes: Number | None = None
    duration_basis: Literal['unknown', 'elapsed', 'active'] = 'unknown'
    power_w: Number | None = None
    heart_rate_bpm: int | None = Field(default=None, ge=0, le=300)
    rpe: int | None = Field(default=None, ge=0, le=10)
    elevation_gain_m: Number | None = None
    pool_length_m: Number | None = None
    equipment: Short = ''
    conditions: Text = ''
    source: Literal['self_report'] = 'self_report'


class AssessmentData(Closed):
    timezone_name: str = Field(min_length=1, max_length=64)
    assessment_date: Day
    program_reference: Reference | None = None
    goal_label: Short = ''
    state_change: Literal['unknown', 'unchanged', 'changed', 'review_needed'] = 'unknown'
    state_notes: Text = ''
    experience: Literal['unknown', 'none', 'occasional', 'returning', 'regular'] = 'unknown'
    strength_frequency: Literal['unknown', 'none', 'less_than_weekly', 'weekly_1', 'weekly_2', 'weekly_3_plus'] = 'unknown'
    last_strength_date: Day | None = None
    usual_strength_minutes: int | None = Field(default=None, ge=0, le=1440)
    supervision: Literal['unknown', 'self', 'supervised', 'mixed', 'needed'] = 'unknown'
    default_location_id: Token | None = None
    sports: list[SportEntry] = Field(default_factory=list, max_length=32)
    exercises: list[ExerciseEntry] = Field(default_factory=list, max_length=64)
    sport_references: list[SportReference] = Field(default_factory=list, max_length=100)
    references_reviewed: bool = False
    reviewed: bool = False

    @model_validator(mode='after')
    def coherent(self):
        try:
            ZoneInfo(self.timezone_name)
        except (KeyError, ValueError):
            raise ValueError('Unknown time zone.') from None
        calendar_day(self.assessment_date)
        if len({v.sport_key for v in self.sports}) != len(self.sports):
            raise ValueError('Selected sports must be unique.')
        if len({v.id for v in self.exercises}) != len(self.exercises) or len({v.id for v in self.sport_references}) != len(self.sport_references):
            raise ValueError('Observation identities must be unique.')
        if any(v.sport_key not in {s.sport_key for s in self.sports} for v in self.sport_references):
            raise ValueError('A sport reference retains its selected sport.')
        dates = [self.last_strength_date, *[v.performed_on for v in self.exercises], *[v.performed_on for v in self.sport_references]]
        for value in dates:
            if value is not None:
                calendar_day(value)
        if any(value and value > self.assessment_date for value in dates):
            raise ValueError('Observed dates cannot follow the assessment date.')
        # Decimal strings preserve exact digits across Python and browser hashes.
        if any(v.load_value is not None and Decimal(v.load_value) > 100000 for e in self.exercises for v in e.sets):
            raise ValueError('Load value outside the recording limit.')
        return self


class AssessmentInput(Closed):
    request_id: Token
    previous_reference: Reference | None
    source_hash: Digest
    data: AssessmentData
