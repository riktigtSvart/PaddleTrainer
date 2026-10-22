"""Strict HTTP inputs; server identities, procedures and authority are not client fields."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
)

from app.planning.domain.common.time import to_utc
from app.planning.domain.goals.assessment import (
    ConditionStatus,
    ExecutionCompletion,
    ResultLevel,
)
from app.planning.domain.goals.catalog import CapabilityKey
from app.planning.domain.goals.measurement_registration import (
    GoalMeasurementProposal,
    measurement_float,
)
from app.planning.domain.goals.protocol import (
    CapabilityGoalRole,
    ChangeBasis,
    EndpointRole,
    MacrocyclePlanProposal,
    MesocycleProtocolProposal,
    ProtocolOrigin,
    decimal_text,
)
from app.planning.domain.planning_utility.decision_binding import _decode


def _nonblank(value):
    if not value.strip():
        raise ValueError("Text must not be blank.")
    return value


def _uuid(value):
    if str(UUID(value)) != value:
        raise ValueError("Use a canonical UUID string.")
    return value


def _decimal(value):
    decimal_text(value)
    return value


def _scalar(value):
    measurement_float(value)
    return value


def _time_input(value):
    if type(value) is str:
        datetime.fromisoformat(value)
    elif type(value) is not datetime:
        raise ValueError("Use an ISO datetime with an explicit UTC offset.")
    return value


Text = Annotated[
    StrictStr, StringConstraints(min_length=1, max_length=4000), AfterValidator(_nonblank)
]
Key = Annotated[
    StrictStr, StringConstraints(min_length=1, max_length=200), AfterValidator(_nonblank)
]
CanonicalUUID = Annotated[StrictStr, AfterValidator(_uuid)]
DecimalText = Annotated[StrictStr, AfterValidator(_decimal)]
ScalarText = Annotated[StrictStr, AfterValidator(_scalar)]
UtcTimestamp = Annotated[
    AwareDatetime,
    BeforeValidator(_time_input),
    AfterValidator(lambda v: to_utc(v, field_name="HTTP datetime")),
]
Digest = Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GoalIdentity = Annotated[StrictStr, StringConstraints(pattern=r"^pt-goal:[0-9a-f]{64}$")]
Revision = Annotated[StrictInt, Field(ge=1, le=64)]


class GoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalReferenceInput(GoalInput):
    artifact_id: GoalIdentity
    content_hash: Digest


class CapabilityGoalInput(GoalInput):
    capability_key: CapabilityKey
    role: CapabilityGoalRole
    rationale: Text


class MesocycleDirectiveInput(CapabilityGoalInput):
    mesocycle_period_id: CanonicalUUID


class MacrocyclePlanInput(GoalInput):
    macrocycle_period_id: CanonicalUUID
    revision: Revision
    supersedes: GoalReferenceInput | None = None
    goals: Annotated[list[CapabilityGoalInput], Field(min_length=1, max_length=13)]
    mesocycle_directives: Annotated[
        list[MesocycleDirectiveInput], Field(min_length=1, max_length=4096)
    ]
    rationale: Text

    def to_domain(self):
        return _decode(self.model_dump(mode="json"), MacrocyclePlanProposal)


class MeasurementProcedureInput(GoalInput):
    protocol_key: Key
    protocol_version: Key
    origin: ProtocolOrigin
    source_reference: Text
    modality_key: Key
    exercise_or_task: Text
    procedure: Text
    equipment_and_processing: Text
    comparability_conditions: Annotated[list[Text], Field(min_length=1, max_length=32)]


class MeasurementWindowInput(GoalInput):
    starts_at: UtcTimestamp
    ends_at: UtcTimestamp


class ChangeRequirementInput(GoalInput):
    basis: ChangeBasis
    minimum: DecimalText
    maximum: DecimalText | None = None
    measurement_error_estimate: DecimalText | None = None
    measurement_error_source: Text | None = None


class MeasurementEndpointInput(GoalInput):
    endpoint_key: Key
    capability_key: CapabilityKey
    metric_key: Key
    role: EndpointRole
    procedure: MeasurementProcedureInput
    baseline_window: MeasurementWindowInput
    followup_window: MeasurementWindowInput
    change_requirement: ChangeRequirementInput | None = None


class MesocycleProtocolInput(GoalInput):
    mesocycle_period_id: CanonicalUUID
    revision: Revision
    supersedes: GoalReferenceInput | None = None
    macrocycle_plan: GoalReferenceInput
    endpoints: Annotated[list[MeasurementEndpointInput], Field(min_length=1, max_length=64)]
    rationale: Text

    def to_domain(self):
        return _decode(self.model_dump(mode="json"), MesocycleProtocolProposal)


class ConditionObservationInput(GoalInput):
    condition: Text
    status: ConditionStatus
    observation: Text
    evidence_reference: Text


class ExecutionObservationInput(GoalInput):
    started_at: UtcTimestamp
    ended_at: UtcTimestamp
    completion: ExecutionCompletion
    result_level: ResultLevel
    conditions: Annotated[list[ConditionObservationInput], Field(min_length=1, max_length=32)]
    body_mass_kg: DecimalText | None = None
    execution_evidence_reference: Text


class GoalMeasurementInput(GoalInput):
    client_request_id: CanonicalUUID
    protocol_reference: GoalReferenceInput
    endpoint_key: Key
    value: ScalarText
    observation: ExecutionObservationInput

    def to_domain(self):
        return _decode(self.model_dump(mode="json"), GoalMeasurementProposal)


class GoalAssessmentInput(GoalInput):
    protocol_reference: GoalReferenceInput
    activity_cutoff_at: UtcTimestamp


class GoalArtifactResponse(BaseModel):
    identity_scope: Literal["APPLICATION_DEMO_USER"]
    artifact: dict[str, Any]
    durable_available_at: AwareDatetime
    reused: bool
    committed: Literal[True]
    measurement_schedule_preregistered: bool
    physiological_adaptation_established: Literal[False]
    planning_utility_supported: Literal[False]
    planning_authorized: Literal[False]


class GoalArtifactListResponse(BaseModel):
    identity_scope: Literal["APPLICATION_DEMO_USER"]
    items: list[GoalArtifactResponse]
    limit: int
    offset: int
    has_more: bool
