"""Closed, owned intake and dated availability inputs; unknown never means zero."""

from decimal import Decimal
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator, model_serializer

from app.schemas.planning_cycles import Day, Digest, Key, Title, Token


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Identity = Annotated[str, StringConstraints(pattern=r"^pt-athlete:[0-9a-f]{64}$")]
SourceIdentity = Annotated[str, StringConstraints(pattern=r"^pt-source:[0-9a-f]{64}$")]
Clock = Annotated[str, StringConstraints(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
Number = Annotated[str, StringConstraints(pattern=r"^(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,6})?$")]
Metric = Literal[
    "training_sessions",
    "training_minutes",
    "sleep_duration_sec",
    "sleep_score",
    "daily_steps",
    "background_hr_mean_bpm",
    "background_hr_median_bpm",
    "resting_hr_bpm",
    "hrv_rmssd_ms",
    "body_mass_kg",
    "vo2max_ml_kg_min",
    "strength_load_kg",
    "test_duration_sec",
    "test_distance_m",
]
Method = Literal[
    "unknown",
    "self_report",
    "laboratory",
    "field_test",
    "device_estimate",
    "device_measurement",
    "recorded_activity",
]


class Reference(Closed):
    artifact_id: Identity
    content_hash: Digest


class SourceReference(Closed):
    artifact_id: SourceIdentity
    content_hash: Digest


class SportPlanningContext(Closed):
    version: Literal['sport-planning-context-v0.1']
    supported_sports: list[Title] = Field(max_length=16)
    purposes: list[Literal['aerobic_substitution', 'strength', 'muscular_endurance',
        'speed_power', 'technique', 'mobility', 'general_conditioning', 'recovery', 'other']] = Field(max_length=9)
    proficiency: Literal['unknown', 'learning', 'independent', 'experienced']

    @model_validator(mode='after')
    def unique_choices(self):
        if len(set(self.supported_sports)) != len(self.supported_sports) or len(set(self.purposes)) != len(self.purposes):
            raise ValueError('Use each supported sport and purpose once.')
        return self


class SportPerformance(Closed):
    result_id: Token
    kind: Literal['personal_best', 'recent']
    distance_m: Number | None = None
    time: Annotated[str, StringConstraints(max_length=24)] | None = None
    recorded_on: Day | None
    year: int | None = Field(ge=1900, le=2100)
    conditions: Short
    source: Literal['self_report', 'official', 'device']
    protocol: Literal['distance_time', 'cooper_12min', 'strength_1rm', 'repetitions', 'timed_repetitions'] | None = None
    exercise: Short | None = None
    repetitions: int | None = Field(default=None, ge=0, le=100000)
    load_kind: Literal['bodyweight', 'external_kg'] | None = None
    load_kg: Number | None = None
    load_basis: Literal['total_external', 'per_hand', 'additional_to_bodyweight', 'machine_display'] | None = None

    @model_serializer(mode='wrap')
    def preserve_older_shape(self, handler):
        return {k: v for k, v in handler(self).items() if v is not None or k in {'recorded_on', 'year'}}

    @model_validator(mode='after')
    def meaningful(self):
        seconds = None
        if self.time is not None:
            clock = re.fullmatch(r'(?:(\d{1,3}):)?(\d{1,3}):([0-5]\d(?:\.\d{1,3})?)', self.time)
            if clock is None or (clock[1] is not None and int(clock[2]) > 59):
                raise ValueError('Use m:ss or h:mm:ss, with up to three fractional second digits.')
            seconds = Decimal(clock[1] or 0) * 3600 + Decimal(clock[2]) * 60 + Decimal(clock[3])
            if not 0 < seconds <= 604800: raise ValueError('Duration must be positive and bounded to seven days.')
        protocol = self.protocol or 'distance_time'
        if protocol in {'distance_time', 'cooper_12min'}:
            if seconds is None or self.distance_m is None or Decimal(self.distance_m) <= 0:
                raise ValueError('A distance result needs positive metres and time.')
            if protocol == 'cooper_12min' and seconds != 720: raise ValueError('Cooper duration is exactly 12 minutes.')
            if any(v is not None for v in (self.exercise, self.repetitions, self.load_kind, self.load_kg, self.load_basis)):
                raise ValueError('A distance result cannot claim strength fields.')
        else:
            if not self.exercise or not self.exercise.strip() or self.repetitions is None or self.load_kind is None or self.distance_m is not None:
                raise ValueError('Strength results need an exercise, repetitions and a declared load kind; no distance.')
            if (protocol == 'timed_repetitions') != (seconds is not None): raise ValueError('Only timed repetitions need a duration.')
            if self.load_kind == 'bodyweight':
                if self.load_kg is not None or self.load_basis is not None: raise ValueError('Bodyweight without added load has no external kilograms.')
            elif self.load_kg is None or Decimal(self.load_kg) <= 0 or self.load_basis is None:
                raise ValueError('External load needs positive kilograms and an explicit basis.')
            if protocol == 'strength_1rm' and (self.repetitions != 1 or self.load_kind != 'external_kg'):
                raise ValueError('A recorded single-repetition maximum needs one repetition with a declared load.')
        if self.recorded_on is not None and self.year is not None:
            raise ValueError('Use an exact day or an approximate year, not both.')
        return self


class SportHistory(Closed):
    sport: Title
    discipline: Short = ""
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    current: bool
    last_active_date: Day | None = None
    level: Literal["unknown", "beginner", "recreational", "competitive", "professional"]
    usual_sessions_per_week: int | None = Field(default=None, ge=0, le=28)
    notes: Text = ""
    role: Literal['unknown', 'primary', 'secondary', 'recreation', 'paused'] | None = None
    current_level: Literal['unknown', 'beginner', 'recreational', 'competitive', 'professional'] | None = None
    planning: SportPlanningContext | None = None
    performances: list[SportPerformance] | None = Field(default=None, max_length=16)

    @model_serializer(mode='wrap')
    def preserve_older_shape(self, handler):
        value = handler(self)
        return {k: v for k, v in value.items() if k not in {'role', 'current_level', 'planning', 'performances'} or v is not None}

    @model_validator(mode='after')
    def unique_results(self):
        values = self.performances or []
        if len({r.result_id for r in values}) != len(values):
            raise ValueError('Performance identities must be unique within a sport.')
        return self


class FunctionalConstraint(Closed):
    key: Key
    duration: Literal["permanent", "temporary"]
    area: Literal["movement", "vision", "hearing", "medical", "other"]
    affected_area: Short = ""
    restricted_activities: list[Title] = Field(default_factory=list, max_length=32)
    adaptations: Text = ""
    professional_guidance: Text = ""
    starts_on: Day | None = None
    review_on: Day | None = None

    @model_validator(mode="after")
    def review_order(self):
        if self.starts_on and self.review_on and self.review_on < self.starts_on:
            raise ValueError("Review cannot precede the declared start.")
        return self


class ManualObservation(Closed):
    observation_id: Token
    metric: Metric
    value: Number
    start_date: Day
    end_date: Day
    method: Method
    aggregation: Literal["single", "total", "mean", "median"] = "single"
    sport: Short = ""
    protocol: Short = ""
    conditions: Text = ""
    supersedes_candidate_id: SourceIdentity | None = None

    @model_validator(mode="after")
    def meaningful(self):
        if self.start_date > self.end_date:
            raise ValueError("The observation window is reversed.")
        if self.start_date != self.end_date and self.aggregation == "single":
            raise ValueError("A multi-day observation needs an explicit aggregation.")
        if (
            self.metric in {"training_sessions", "daily_steps"}
            and self.aggregation in {"single", "total"}
            and Decimal(self.value) % 1
        ):
            raise ValueError("Counts must be whole numbers.")
        if (
            self.metric
            in {
                "body_mass_kg",
                "vo2max_ml_kg_min",
                "strength_load_kg",
                "test_duration_sec",
                "test_distance_m",
            }
            and Decimal(self.value) <= 0
        ):
            raise ValueError("This metric must be positive.")
        return self


class SourceWindow(Closed):
    start_date: Day
    end_date: Day


class ProfileData(Closed):
    birth_date: Day | None = None
    sex_reference: Literal["unknown", "female", "male", "intersex", "prefer_not_to_say"] = "unknown"
    competition_category: Short = ""
    target_sport: Short = ""
    sport_history_status: Literal["unknown", "none", "recorded"] = "unknown"
    sport_history: list[SportHistory] = Field(default_factory=list, max_length=32)
    constraint_status: Literal["unknown", "none_known", "present"] = "unknown"
    constraints: list[FunctionalConstraint] = Field(default_factory=list, max_length=32)
    participation: Literal[
        "unknown", "unrestricted", "adapted", "professional_review", "paused"
    ] = "unknown"
    interruption: Literal["unknown", "none", "returning"] = "unknown"
    last_training_date: Day | None = None
    typical_days_per_week: int | None = Field(default=None, ge=0, le=7)
    typical_minutes_per_week: int | None = Field(default=None, ge=0, le=10080)
    resources: list[Title] = Field(default_factory=list, max_length=32)
    duration_doubling_slowdown_pct: int | None = Field(default=None, ge=0, le=20, strict=True)
    accessibility_needs: Text = ""
    recovery_notes: Text = ""
    manual_observations: list[ManualObservation] = Field(default_factory=list, max_length=200)
    source_window: SourceWindow | None = None
    source_selections: list[SourceReference] = Field(default_factory=list, max_length=1000)
    body_mass_kg: Number | None = None
    height_cm: Number | None = None
    body_measurements_recorded_on: Day | None = None
    body_mass_recorded_on: Day | None = None

    @model_serializer(mode='wrap')
    def preserve_older_shape(self, handler):
        value = handler(self)
        return {k: v for k, v in value.items() if k not in {'body_mass_kg', 'height_cm', 'body_measurements_recorded_on', 'body_mass_recorded_on'} or v is not None}

    @model_validator(mode="after")
    def consistent(self):
        if any(v is not None and Decimal(v) <= 0 for v in (self.body_mass_kg, self.height_cm)):
            raise ValueError('Body measurements must be positive.')
        if (self.body_mass_kg is not None and not (self.body_mass_recorded_on or self.body_measurements_recorded_on)) or (self.height_cm is not None and self.body_measurements_recorded_on is None):
            raise ValueError('Body measurements need their observation date.')
        if (self.sport_history_status == "recorded") != bool(self.sport_history):
            raise ValueError(
                "Recorded sport history needs entries; none and unknown must have none."
            )
        if (self.constraint_status == "present") != bool(self.constraints):
            raise ValueError(
                "Present constraints require details; unknown and none must have no entries."
            )
        if len({c.key for c in self.constraints}) != len(self.constraints):
            raise ValueError("Constraint keys must be unique.")
        if len({o.observation_id for o in self.manual_observations}) != len(
            self.manual_observations
        ):
            raise ValueError("Observation identities must be unique.")
        if len({r.artifact_id for r in self.source_selections}) != len(self.source_selections):
            raise ValueError("Selected source identities must be unique.")
        for o in self.manual_observations:
            if o.supersedes_candidate_id and o.supersedes_candidate_id not in {
                r.artifact_id for r in self.source_selections
            }:
                raise ValueError("A correction must retain the selected original source.")
        return self


class ProfileInput(Closed):
    request_id: Token
    previous_reference: Reference | None
    data: ProfileData


class SessionWindow(Closed):
    key: Key
    start_time: Clock
    end_time: Clock
    ends_next_day: bool = False
    start_fold: Literal[0, 1] | None = None
    end_fold: Literal[0, 1] | None = None
    max_minutes: int = Field(ge=1, le=1440)
    sport_scope: Literal["unknown", "any", "specified"] = "any"
    sports: list[Title] = Field(default_factory=list, max_length=16)
    effort_cap: Literal["unknown", "easy", "moderate", "any"] = "any"
    resources: list[Title] = Field(default_factory=list, max_length=32)
    location: Short = ""
    notes: Text = ""

    @model_validator(mode="before")
    @classmethod
    def fold_is_an_integer(cls, value):
        if isinstance(value, dict):
            for key in ("start_fold", "end_fold"):
                if value.get(key) is not None and type(value[key]) is not int:
                    raise ValueError("A DST fold must be an integer, not a boolean or float.")
        return value

    @model_validator(mode="after")
    def sports_match(self):
        if (self.sport_scope == "specified") != bool(self.sports) or len(set(self.sports)) != len(
            self.sports
        ):
            raise ValueError("Specified sports need a unique nonempty list.")
        return self


class AvailabilityDay(Closed):
    date: Day
    status: Literal["unknown", "unavailable", "available"]
    max_total_minutes: int | None = Field(default=None, ge=1, le=1440)
    windows: list[SessionWindow] = Field(default_factory=list, max_length=8)
    notes: Text = ""

    @model_validator(mode="after")
    def window_state(self):
        if (self.status == "available") != bool(self.windows):
            raise ValueError("Only an available day has session opportunities.")
        if self.status != "available" and self.max_total_minutes is not None:
            raise ValueError("A day without windows cannot claim a time budget.")
        if len({w.key for w in self.windows}) != len(self.windows):
            raise ValueError("Window keys must be unique within a day.")
        return self


class AvailabilityData(Closed):
    timezone_name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    start_date: Day
    end_date: Day
    mesocycle_id: Token | None = None
    days: list[AvailabilityDay] = Field(min_length=1, max_length=366)


class AvailabilityInput(Closed):
    request_id: Token
    previous_reference: Reference | None
    data: AvailabilityData


class PolarImportInput(Closed):
    request_id: Token
    day: Day
    domain: Literal["sessions", "sleep", "nightly_recharge", "continuous_hr", "activity", "tests"]
