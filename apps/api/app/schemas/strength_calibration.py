"""Versioned measurements; planned test limits never truncate actual results."""
from typing import Literal

from pydantic import Field, model_validator

from app.planning.domain.calendar_constraints import calendar_day
from app.schemas.athlete_setup import Closed
from app.schemas.guided_strength import GuidedCommand, Progress
from app.schemas.initial_assessment import Number, SetObservation, Short
from app.schemas.planning_cycles import Day, Digest, Token

PROTOCOL = 'strength-calibration-v0.3'
SCHEMA = 'guided-strength-session-v0.2'
RULES = 'guided-strength-calibration-v0.3'


class Measurement(SetObservation):
    purpose: Literal['calibration', 'quality', 'repeatability']
    performed_on: Day
    performed_confirmed: bool = False
    trial_number: int = Field(ge=1, le=100)
    side: Literal['unknown', 'both', 'left', 'right', 'alternating'] = 'unknown'
    stop_reason: Literal['unknown', 'planned_cap', 'reserve_target', 'effort_limit', 'technique_limit',
                         'symptom', 'external_interruption', 'measurement_error'] = 'unknown'
    actual_rest_seconds: int | None = Field(default=None, ge=0, le=86400)
    setup_note: Short = ''
    duration_seconds: Number | None = None
    distance_m: Number | None = None
    measured_height_m: Number | None = None
    metric_name: Short = ''
    metric_unit: Short = ''
    metric_value: Number | None = None
    plate_configuration: Literal['not_applicable', 'unknown', 'shared', 'paired'] = 'not_applicable'
    left_plates_kg: Number | None = None
    right_plates_kg: Number | None = None
    shared_plates_kg: Number | None = None
    bar_kg: Number | None = None

    @model_validator(mode='after')
    def measurement_date(self):
        calendar_day(self.performed_on)
        if self.metric_value is not None and (not self.metric_name.strip() or not self.metric_unit.strip()):
            raise ValueError('A measured native metric retains its name and unit.')
        if self.plate_configuration == 'shared' and (self.left_plates_kg is not None or self.right_plates_kg is not None):
            raise ValueError('Shared and paired plate placements are separate configurations.')
        if self.plate_configuration == 'paired' and self.shared_plates_kg is not None:
            raise ValueError('Shared and paired plate placements are separate configurations.')
        return self


class CalibrationResult(Closed):
    entry_id: Token
    state: Literal['pending', 'recorded', 'skipped', 'stopped'] = 'pending'
    side: Literal['unknown', 'both', 'left', 'right', 'alternating'] = 'unknown'
    machine_note: Short = ''
    note: str = Field(default='', max_length=2000)
    observations: list[Measurement] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def identities(self):
        if len({v.id for v in self.observations}) != len(self.observations):
            raise ValueError('Each measurement has its own identity.')
        if len({(v.side, v.trial_number) for v in self.observations}) != len(self.observations):
            raise ValueError('Trial numbers are unique within each execution side.')
        return self


class CalibrationProgress(Progress):
    protocol_version: Literal['strength-calibration-v0.3']
    results: list[CalibrationResult] = Field(min_length=1, max_length=5)


class CalibrationCommand(GuidedCommand):
    protocol_version: Literal['strength-calibration-v0.3']
    protocol_hash: Digest
    measurement_mode: Literal['calibration', 'repeatability']
    progress: CalibrationProgress


def parse_command(value):
    """Legacy bytes remain legacy bytes; new defaults never enter old receipts."""
    cls = CalibrationCommand if isinstance(value, dict) and 'protocol_version' in value else GuidedCommand
    return cls.model_validate(value).model_dump(mode='json')
