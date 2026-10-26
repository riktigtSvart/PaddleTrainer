"""Closed, owned intake and dated availability inputs; unknown never means zero."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class SportHistory(Closed):
    sport: Title
    discipline: Short = ""
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    current: bool
    last_active_date: Day | None = None
    level: Literal["unknown", "beginner", "recreational", "competitive", "professional"]
    usual_sessions_per_week: int | None = Field(default=None, ge=0, le=28)
    notes: Text = ""


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
    accessibility_needs: Text = ""
    recovery_notes: Text = ""
    manual_observations: list[ManualObservation] = Field(default_factory=list, max_length=200)
    source_window: SourceWindow | None = None
    source_selections: list[SourceReference] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def consistent(self):
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
    sport_scope: Literal["unknown", "any", "specified"] = "unknown"
    sports: list[Title] = Field(default_factory=list, max_length=16)
    effort_cap: Literal["unknown", "easy", "moderate", "any"] = "unknown"
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
