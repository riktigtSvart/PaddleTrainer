"""Closed inputs for explicit, atomically created training-cycle structures."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_serializer,
    model_validator,
)


def canonical_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or not 1900 <= parsed.year <= 2100:
        raise ValueError("Use an ISO calendar date.")
    return value


def canonical_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Use a canonical UUID.")
    return value


Day = Annotated[str, AfterValidator(canonical_date)]
Token = Annotated[str, AfterValidator(canonical_uuid)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
ArtifactID = Annotated[str, StringConstraints(pattern=r"^pt-cycle:[0-9a-f]{64}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GoalKey = Literal[
    "performance",
    "aerobic_fitness",
    "strength",
    "regular_activity",
    "weight_loss",
    "weight_maintenance",
    "wellbeing",
    "mobility",
]


class ClosedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler):
        value = handler(self)
        # New optional extension fields must not rewrite a v0.1 audit or pending body.
        for key in (
            "body_mass",
            "profile",
            "planning_basis",
            "details",
            "athlete_context",
            "target_kg",
        ):
            if value.get(key) is None:
                value.pop(key, None)
        return value


class CycleReference(ClosedInput):
    artifact_id: ArtifactID
    content_hash: Digest


PositiveDecimal = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,3})?$"),
    AfterValidator(lambda value: value if Decimal(value) > 0 else _positive_error()),
]


def _positive_error():
    raise ValueError("Use a positive decimal string.")


class BodyMassGoal(ClosedInput):
    current_kg: PositiveDecimal
    target_kg: PositiveDecimal | None = None


class PlanningBasis(ClosedInput):
    version: Literal["cycle-planning-basis-v0.1"]
    mesocycle_dates: Literal["provisional"]
    initial_mesocycle_days: int = Field(ge=1, le=366)


class CompetitionProfile(ClosedInput):
    discipline: Title
    event_type: Literal["sprint", "endurance", "technical", "strength", "mixed", "other"]
    distance_status: Literal["specified", "unknown", "not_applicable"]
    distance_value: PositiveDecimal | None = None
    distance_unit: Literal["m", "km"] | None = None
    expected_duration_minutes: PositiveDecimal | None = None
    course_description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = (
        ""
    )
    capability_basis: Literal["unassessed", "coach_declared", "icf_sprint_v0_1"] = "unassessed"
    capability_keys: list[str] = Field(default_factory=list, max_length=13)

    @model_validator(mode="after")
    def meaningful_profile(self):
        from app.planning.domain.cycle_program_context import validate_profile

        validate_profile(self.model_dump())
        return self


class GoalDetails(ClosedInput):
    version: Literal["cycle-goal-fields-v0.1"]
    direction: Literal["improve", "maintain"] | None = None
    weekly_sessions: int | None = Field(default=None, ge=1, le=28)
    event_keys: list[Key] = Field(default_factory=list, max_length=64)
    result_target: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)] = ""


class AthleteReference(ClosedInput):
    artifact_id: Annotated[str, StringConstraints(pattern=r"^pt-athlete:[0-9a-f]{64}$")]
    content_hash: Digest


class AthleteContext(ClosedInput):
    profile_reference: AthleteReference | None
    availability_reference: AthleteReference | None


class ProgramGoal(ClosedInput):
    key: GoalKey
    target_description: Note
    body_mass: BodyMassGoal | None = None
    details: GoalDetails | None = None

    @model_validator(mode="after")
    def weight_fields(self):
        if (
            self.key == "weight_maintenance"
            and self.details is not None
            and self.body_mass is not None
            and self.body_mass.target_kg is not None
        ):
            raise ValueError("Structured maintenance uses the current body mass only.")
        if (
            self.body_mass is not None
            and self.body_mass.target_kg is None
            and (self.key != "weight_maintenance" or self.details is None)
        ):
            raise ValueError("Only the structured maintenance goal omits a target weight.")
        return self


class CompetitionInput(ClosedInput):
    key: Key
    title: Title
    start_date: Day
    end_date: Day
    precision: Literal["exact", "window"]
    priority: Literal["main", "supporting"]
    status: Literal["planned", "cancelled"] = "planned"
    profile: CompetitionProfile | None = None


class PeriodInput(ClosedInput):
    key: Key
    title: Title
    start_date: Day
    end_date: Day


class MacrocycleInput(PeriodInput):
    season_key: Key | None = None
    mesocycles: list[PeriodInput] = Field(min_length=1, max_length=64)


class CycleProgramInput(ClosedInput):
    program_id: Token
    mode: Literal["olympic", "season", "race", "recreation"]
    title: Title
    sport: Title
    start_date: Day
    end_date: Day | None
    olympic_key: Literal["la-2028", "alpes-2030", "brisbane-2032", "utah-2034"] | None = None
    seasons: list[PeriodInput] = Field(default_factory=list, max_length=8)
    macrocycles: list[MacrocycleInput] = Field(min_length=1, max_length=24)
    competitions: list[CompetitionInput] = Field(default_factory=list, max_length=64)
    goals: list[ProgramGoal] = Field(min_length=1, max_length=8)
    continued_from: CycleReference | None = None
    planning_basis: PlanningBasis | None = None
    athlete_context: AthleteContext | None = None


class CompetitionRevisionInput(ClosedInput):
    program_reference: CycleReference
    revision: int = Field(ge=1, le=64)
    previous_reference: CycleReference | None = None
    competitions: list[CompetitionInput] = Field(max_length=64)
    rationale: Note


class BoundaryRevisionInput(ClosedInput):
    program_reference: CycleReference
    revision: int = Field(ge=1, le=64)
    previous_reference: CycleReference | None = None
    competition_reference: CycleReference
    left_period_id: Token
    right_period_id: Token
    new_end_date: Day
    reason: Literal["fatigue", "progress_continues", "plateau", "calendar", "other"]
    observations: Note
    rationale: Note
    review_training_load: Literal[True]
