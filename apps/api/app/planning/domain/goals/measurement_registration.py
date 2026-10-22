"""Server-bound scalar observations for an exact preregistered endpoint."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from uuid import NAMESPACE_URL, UUID, uuid5

from ..common.serialization import CONTENT_HASH_ALGORITHM, canonical_json, compute_content_hash
from ..common.time import to_utc
from ..persistence.audit import AuditArtifactKind
from .assessment import (
    MEASUREMENT_EXECUTION_SCHEMA,
    ExecutionCompletion,
    GoalMeasurementExecution,
    MeasurementConditionObservation,
    ResultLevel,
)
from .catalog import goal_metric
from .protocol import (
    GOAL_HASH_EXCLUDE,
    DurableGoalSourceReference,
    GoalAuthorityBoundary,
    GoalVersionReference,
    MesocycleGoalProtocol,
    decimal_text,
    require_typed,
)

GOAL_MEASUREMENT_SCHEMA = "goal-measurement-registration-v0.1"
GOAL_MEASUREMENT_RULES = "goal-measurement-ingestion-rules-v0.1"


@dataclass(frozen=True)
class GoalExecutionObservation:
    started_at: datetime
    ended_at: datetime
    completion: ExecutionCompletion
    result_level: ResultLevel
    conditions: tuple[MeasurementConditionObservation, ...]
    body_mass_kg: str | None
    execution_evidence_reference: str


@dataclass(frozen=True)
class GoalMeasurementProposal:
    client_request_id: str
    protocol_reference: GoalVersionReference
    endpoint_key: str
    value: str
    observation: GoalExecutionObservation


@dataclass(frozen=True)
class GoalMeasurementRegistration:
    artifact_id: str
    schema_version: str
    rules_version: str
    athlete_id: str
    proposal: GoalMeasurementProposal
    protocol_source: DurableGoalSourceReference
    assessment_id: str
    measurement_id: str
    metric_key: str
    metric_unit: str
    execution: GoalMeasurementExecution
    execution_details_independently_verified: bool
    source_rows_immutable: bool
    authority: GoalAuthorityBoundary
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self):
        return compute_content_hash(self, exclude_fields=GOAL_HASH_EXCLUDE) == self.content_hash


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Goal measurement identities must be canonical UUIDs.")


def goal_measurement_id(athlete_id, client_request_id):
    _uuid(athlete_id)
    _uuid(client_request_id)
    return "pt-goal-measurement:" + compute_content_hash(
        {
            "slot": GOAL_MEASUREMENT_SCHEMA,
            "athlete_id": athlete_id,
            "client_request_id": client_request_id,
        }
    )


def measurement_float(value):
    parsed = decimal_text(value)
    numeric = float(parsed)
    if (
        not isfinite(numeric)
        or Decimal(str(numeric)) != parsed
        or (parsed and not -78 <= parsed.adjusted() <= 78)
    ):
        raise ValueError("Goal measurement cannot be retained without decimal-representation loss.")
    return numeric


def build_goal_measurement_registration(
    *, athlete_id, proposal, protocol, protocol_source, created_at
):
    require_typed(proposal, GoalMeasurementProposal)
    require_typed(protocol, MesocycleGoalProtocol)
    require_typed(protocol_source, DurableGoalSourceReference)
    created = to_utc(created_at, field_name="created_at")
    identity = goal_measurement_id(athlete_id, proposal.client_request_id)
    if (
        protocol.athlete_id != athlete_id
        or not protocol.verify_content_hash()
        or proposal.protocol_reference
        != GoalVersionReference(protocol.artifact_id, protocol.content_hash)
        or protocol_source.artifact_kind != AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL
        or protocol_source.artifact_id != protocol.artifact_id
        or protocol_source.content_hash != protocol.content_hash
        or protocol_source.canonical_contract_sha256
        != sha256(canonical_json(protocol).encode()).hexdigest()
        or not protocol.created_at <= protocol_source.persisted_at <= created
        or any(
            protocol_source.persisted_at >= e.baseline_window.starts_at
            for e in protocol.proposal.endpoints
        )
    ):
        raise ValueError("Goal measurement protocol provenance or registration time differs.")
    endpoints = [e for e in protocol.proposal.endpoints if e.endpoint_key == proposal.endpoint_key]
    if len(endpoints) != 1:
        raise ValueError("Measurement endpoint is outside the exact goal protocol.")
    endpoint = endpoints[0]
    observation = proposal.observation
    start = to_utc(observation.started_at, field_name="observation.started_at")
    end = to_utc(observation.ended_at, field_name="observation.ended_at")
    if not start <= end <= created or not any(
        window.starts_at <= start <= end <= window.ends_at
        for window in (endpoint.baseline_window, endpoint.followup_window)
    ):
        raise ValueError("Goal measurement must fit one scheduled window and end before recording.")
    if (
        tuple(c.condition for c in observation.conditions)
        != endpoint.procedure.comparability_conditions
    ):
        raise ValueError("Goal measurement condition census differs from the registered procedure.")
    for condition in observation.conditions:
        if not all(
            value.strip()
            for value in (condition.condition, condition.observation, condition.evidence_reference)
        ):
            raise ValueError("Goal measurement condition observations need explicit evidence.")
    if not observation.execution_evidence_reference.strip():
        raise ValueError("Goal measurement execution evidence is required.")
    if observation.body_mass_kg is not None and decimal_text(observation.body_mass_kg) <= 0:
        raise ValueError("Recorded body mass must be positive.")
    measurement_float(proposal.value)
    metric = goal_metric(endpoint.metric_key)
    execution = GoalMeasurementExecution(
        MEASUREMENT_EXECUTION_SCHEMA,
        endpoint.procedure,
        metric.evidence_kind,
        start,
        end,
        observation.completion,
        observation.result_level,
        observation.conditions,
        observation.body_mass_kg,
        observation.execution_evidence_reference,
    )
    registration = GoalMeasurementRegistration(
        identity,
        GOAL_MEASUREMENT_SCHEMA,
        GOAL_MEASUREMENT_RULES,
        athlete_id,
        proposal,
        protocol_source,
        str(uuid5(NAMESPACE_URL, "paddletrainer:goal-assessment-row:" + identity)),
        str(uuid5(NAMESPACE_URL, "paddletrainer:goal-measurement-row:" + identity)),
        metric.metric_key,
        metric.unit,
        execution,
        False,
        False,
        GoalAuthorityBoundary(),
        created,
        CONTENT_HASH_ALGORITHM,
        "",
    )
    return replace(
        registration,
        content_hash=compute_content_hash(registration, exclude_fields=GOAL_HASH_EXCLUDE),
    )
