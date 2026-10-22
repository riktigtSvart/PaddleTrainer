"""Frozen measurement census and conditional, goal-specific change assessment.

Exact fractions decide boundaries. A declared error amount gives an arithmetic
sensitivity range, not a confidence interval or proof of physiological change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from fractions import Fraction
from hashlib import sha256
from uuid import UUID

from ..common.serialization import CONTENT_HASH_ALGORITHM, canonical_json, compute_content_hash
from ..common.time import to_utc
from ..persistence.audit import AuditArtifactKind
from ..planning_utility.decision_binding import _decode
from .catalog import (
    CapabilityKey,
    ImprovementDirection,
    MeasurementEvidenceKind,
    MeasurementScale,
    goal_metric,
)
from .protocol import (
    GOAL_HASH_EXCLUDE,
    CapabilityGoalRole,
    ChangeBasis,
    DurableGoalSourceReference,
    EndpointRole,
    GoalAuthorityBoundary,
    MeasurementProcedure,
    MesocycleGoalProtocol,
    decimal_text,
    require_typed,
)

GOAL_ASSESSMENT_SCHEMA = "mesocycle-goal-assessment-v0.1"
GOAL_ASSESSMENT_RULES = "goal-change-assessment-rules-v0.1"
MEASUREMENT_SOURCE_SCHEMA = "goal-measurement-source-v0.1"
MEASUREMENT_EXECUTION_SCHEMA = "goal-measurement-execution-v0.1"
MEASUREMENT_EXECUTION_KEY = "goal_measurement_execution"
GOAL_MEASUREMENT_CENSUS_LIMIT = 5000
GOAL_ASSESSMENT_ENDPOINT_LIMIT = 64
SOURCE_JSON_LIMIT = 65536


class GoalMeasurementSourceKind(StrEnum):
    ASSESSMENT_MEASUREMENT = "assessment_measurement"
    PHYSIOLOGICAL_MEASUREMENT = "physiological_measurement"


class ExecutionCompletion(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class ResultLevel(StrEnum):
    COMPLETE_PROTOCOL_RESULT = "complete_protocol_result"
    WITHIN_PROTOCOL_TRIAL = "within_protocol_trial"
    UNKNOWN = "unknown"


class ConditionStatus(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MeasurementConditionObservation:
    condition: str
    status: ConditionStatus
    observation: str
    evidence_reference: str


@dataclass(frozen=True)
class GoalMeasurementExecution:
    schema_version: str
    procedure: MeasurementProcedure
    evidence_kind: MeasurementEvidenceKind
    started_at: datetime
    ended_at: datetime
    completion: ExecutionCompletion
    result_level: ResultLevel
    conditions: tuple[MeasurementConditionObservation, ...]
    body_mass_kg: str | None
    execution_evidence_reference: str


@dataclass(frozen=True)
class CapturedGoalMeasurement:
    source_kind: GoalMeasurementSourceKind
    source_id: str
    source_json: str
    source_sha256: str


@dataclass(frozen=True)
class GoalMeasurementCensus:
    athlete_id: str
    interval_starts_at: datetime
    interval_ends_at: datetime
    capture_started_at: datetime
    captured_at: datetime
    sources: tuple[CapturedGoalMeasurement, ...]


class MeasurementWindowRole(StrEnum):
    BASELINE = "baseline"
    FOLLOWUP = "followup"
    OUTSIDE = "outside"


class MeasurementEligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNRESOLVED = "unresolved"


class GoalCriterionStatus(StrEnum):
    MET_UNDER_DECLARED_ERROR = "met_under_declared_error"
    NOT_MET_UNDER_DECLARED_ERROR = "not_met_under_declared_error"
    WITHHELD = "withheld"
    DESCRIPTIVE_ONLY = "descriptive_only"


@dataclass(frozen=True)
class ExactGoalChange:
    numerator: str
    denominator: str
    display_decimal: str


@dataclass(frozen=True)
class GoalMeasurementCandidate:
    source_kind: GoalMeasurementSourceKind
    source_id: str
    source_sha256: str
    window: MeasurementWindowRole
    eligibility: MeasurementEligibility
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class GoalEndpointAssessment:
    endpoint_key: str
    capability_key: CapabilityKey
    endpoint_role: EndpointRole
    metric_key: str
    metric_unit: str
    evidence_kind: MeasurementEvidenceKind
    interpretation_limit: str
    candidates: tuple[GoalMeasurementCandidate, ...]
    baseline_source: CapturedGoalMeasurement | None
    followup_source: CapturedGoalMeasurement | None
    baseline_value: str | None
    followup_value: str | None
    favourable_absolute_change: ExactGoalChange | None
    favourable_percent_change: ExactGoalChange | None
    comparison_basis: ChangeBasis | None
    point_requirement_met: bool | None
    declared_error_sensitivity_low: ExactGoalChange | None
    declared_error_sensitivity_high: ExactGoalChange | None
    criterion_status: GoalCriterionStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class GoalCapabilityAssessment:
    capability_key: CapabilityKey
    goal_role: CapabilityGoalRole
    primary_endpoint_keys: tuple[str, ...]
    criterion_status: GoalCriterionStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class MesocycleGoalAssessment:
    artifact_id: str
    schema_version: str
    rules_version: str
    athlete_id: str
    protocol_source: DurableGoalSourceReference
    activity_cutoff_at: datetime
    census: GoalMeasurementCensus
    endpoint_assessments: tuple[GoalEndpointAssessment, ...]
    capability_assessments: tuple[GoalCapabilityAssessment, ...]
    unassigned_capability_keys: tuple[CapabilityKey, ...]
    all_primary_criteria_status: GoalCriterionStatus
    source_availability_at_activity_cutoff_verified: bool
    execution_details_independently_verified: bool
    measurement_error_model_validated: bool
    authority: GoalAuthorityBoundary
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return compute_content_hash(self, exclude_fields=GOAL_HASH_EXCLUDE) == self.content_hash


SOURCE_FIELDS = frozenset(
    {
        "schema_version",
        "source_kind",
        "source_id",
        "athlete_id",
        "parent_id",
        "metric_key",
        "value_float_text",
        "value_text",
        "unit",
        "measured_at",
        "created_at",
        "parent_created_at",
        "sport",
        "parent_sport",
        "source_label",
        "extra_data",
        "parent_extra_data",
        "period_start",
        "period_end",
        "device_id",
        "device_model",
        "quality",
        "source_record_id",
        "parent_type",
        "parent_title",
        "parent_notes",
    }
)


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Measurement identities must be canonical UUIDs.")


def _time(value):
    if type(value) is not str:
        raise ValueError("Measurement source time must be a canonical UTC string.")
    parsed = to_utc(datetime.fromisoformat(value), field_name="source time")
    if parsed.isoformat(timespec="microseconds").replace("+00:00", "Z") != value:
        raise ValueError("Measurement source time is not canonical UTC.")
    return parsed


def measurement_packet(source: CapturedGoalMeasurement) -> dict:
    require_typed(source, CapturedGoalMeasurement)
    _uuid(source.source_id)
    if len(source.source_json.encode("utf-8")) > SOURCE_JSON_LIMIT:
        raise ValueError("Measurement source exceeds the supported snapshot size.")
    packet = json.loads(source.source_json)
    if (
        type(packet) is not dict
        or set(packet) != SOURCE_FIELDS
        or canonical_json(packet) != source.source_json
        or sha256(source.source_json.encode("utf-8")).hexdigest() != source.source_sha256
        or packet["schema_version"] != MEASUREMENT_SOURCE_SCHEMA
        or packet["source_kind"] != source.source_kind.value
        or packet["source_id"] != source.source_id
    ):
        raise ValueError("Measurement source identity, canonical payload or hash differs.")
    _uuid(packet["athlete_id"])
    if type(packet["metric_key"]) is not str or not packet["metric_key"].strip():
        raise ValueError("Measurement metric key is missing.")
    for key in SOURCE_FIELDS - {
        "schema_version",
        "source_kind",
        "source_id",
        "athlete_id",
        "metric_key",
        "extra_data",
        "parent_extra_data",
        "measured_at",
        "created_at",
    }:
        if packet[key] is not None and type(packet[key]) is not str:
            raise ValueError("Measurement source field type differs.")
    _time(packet["measured_at"])
    _time(packet["created_at"])
    for key in ("period_start", "period_end", "parent_created_at"):
        if packet[key] is not None:
            _time(packet[key])
    if type(packet["extra_data"]) is not dict:
        raise ValueError("Measurement metadata must be an object.")
    if source.source_kind == GoalMeasurementSourceKind.ASSESSMENT_MEASUREMENT:
        _uuid(packet["parent_id"])
        if packet["parent_created_at"] is None or type(packet["parent_extra_data"]) is not dict:
            raise ValueError("Assessment parent provenance is missing.")
    elif any(
        packet[key] is not None
        for key in (
            "parent_id",
            "parent_created_at",
            "parent_extra_data",
            "parent_sport",
            "parent_type",
            "parent_title",
            "parent_notes",
        )
    ):
        raise ValueError("Physiological measurement has unexpected assessment provenance.")
    return packet


def goal_assessment_id(athlete_id: str, protocol_id: str, activity_cutoff_at: datetime) -> str:
    _uuid(athlete_id)
    if (
        type(protocol_id) is not str
        or not protocol_id.startswith("pt-goal:")
        or len(protocol_id.removeprefix("pt-goal:")) != 64
        or any(c not in "0123456789abcdef" for c in protocol_id.removeprefix("pt-goal:"))
    ):
        raise ValueError("An exact committed mesocycle protocol identity is required.")
    cutoff = to_utc(activity_cutoff_at, field_name="activity_cutoff_at")
    return "pt-goal-assessment:" + compute_content_hash(
        {
            "slot": "mesocycle-goal-assessment-slot-v0.1",
            "athlete_id": athlete_id,
            "protocol_id": protocol_id,
            "activity_cutoff_at": cutoff,
        }
    )


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"


def _number(packet) -> Decimal:
    if packet["value_float_text"] is None or packet["value_text"] not in (None, ""):
        raise ValueError("A single numeric source result is required.")
    text = packet["value_float_text"]
    if len(text) > 80:
        raise ValueError("Measurement number is too long.")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Measurement value is not numeric.") from exc
    if not value.is_finite() or value.adjusted() > 78 or value.adjusted() < -78:
        raise ValueError("Measurement value is outside the supported finite decimal range.")
    return decimal_text(_plain(value))


def _exact(value: Fraction) -> ExactGoalChange:
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN, traps=[])):
        display = _plain(Decimal(value.numerator) / Decimal(value.denominator))
    return ExactGoalChange(str(value.numerator), str(value.denominator), display)


def _execution(packet) -> GoalMeasurementExecution:
    raw = packet["extra_data"].get(MEASUREMENT_EXECUTION_KEY)
    if type(raw) is not dict:
        raise ValueError("Execution details are missing.")
    result = _decode(raw, GoalMeasurementExecution)
    require_typed(result, GoalMeasurementExecution)
    if canonical_json(result) != canonical_json(raw):
        raise ValueError("Execution details are not exact canonical JSON.")
    if (
        result.schema_version != MEASUREMENT_EXECUTION_SCHEMA
        or not result.execution_evidence_reference.strip()
    ):
        raise ValueError("Execution schema or evidence is missing.")
    if result.started_at > result.ended_at:
        raise ValueError("Execution interval is inverted.")
    for condition in result.conditions:
        if not all(
            v.strip()
            for v in (condition.condition, condition.observation, condition.evidence_reference)
        ):
            raise ValueError("Condition observation or evidence is missing.")
    if result.body_mass_kg is not None and decimal_text(result.body_mass_kg) <= 0:
        raise ValueError("Recorded body mass must be positive.")
    return result


def _candidate(source, packet, endpoint):
    W, E = MeasurementWindowRole, MeasurementEligibility
    measured = _time(packet["measured_at"])
    window = W.OUTSIDE
    interval = None
    for key, candidate in (
        (W.BASELINE, endpoint.baseline_window),
        (W.FOLLOWUP, endpoint.followup_window),
    ):
        if candidate.starts_at <= measured <= candidate.ends_at:
            window, interval = key, candidate
    reasons = []
    eligibility = E.ELIGIBLE
    if packet["metric_key"] != endpoint.metric_key:
        reasons, eligibility = ["METRIC_MISMATCH"], E.INELIGIBLE
    elif interval is None:
        reasons, eligibility = ["OUTSIDE_ENDPOINT_WINDOWS"], E.INELIGIBLE
    elif packet["unit"] != goal_metric(endpoint.metric_key).unit:
        reasons, eligibility = ["UNIT_MISMATCH"], E.INELIGIBLE
    else:
        try:
            execution = _execution(packet)
            _number(packet)
        except (ValueError, TypeError, KeyError, OverflowError):
            reasons, eligibility = ["EXECUTION_OR_NUMERIC_RESULT_UNRESOLVED"], E.UNRESOLVED
        else:
            metric = goal_metric(endpoint.metric_key)
            if execution.procedure != endpoint.procedure:
                reasons.append("PROCEDURE_MODALITY_TASK_OR_PROCESSING_MISMATCH")
            if execution.evidence_kind != metric.evidence_kind:
                reasons.append("EVIDENCE_KIND_MISMATCH")
            if execution.completion == ExecutionCompletion.INCOMPLETE:
                reasons.append("INCOMPLETE_PROTOCOL_RESULT")
            if execution.result_level == ResultLevel.WITHIN_PROTOCOL_TRIAL:
                reasons.append("WITHIN_PROTOCOL_TRIAL_IS_NOT_A_COMPLETE_RESULT")
            if not (
                interval.starts_at
                <= execution.started_at
                <= measured
                <= execution.ended_at
                <= interval.ends_at
            ):
                reasons.append("COMPLETE_EXECUTION_OUTSIDE_WINDOW")
            if (packet["period_start"] is not None or packet["period_end"] is not None) and (
                packet["period_start"] is None
                or packet["period_end"] is None
                or _time(packet["period_start"]) != execution.started_at
                or _time(packet["period_end"]) != execution.ended_at
            ):
                reasons.append("SOURCE_INTERVAL_MISMATCH")
            if any(
                _time(packet[key]) < execution.ended_at
                for key in ("created_at", "parent_created_at")
                if packet[key] is not None
            ):
                reasons.append("COMPLETE_RESULT_RECORDED_BEFORE_EXECUTION_END")
            names = tuple(c.condition for c in execution.conditions)
            if names != endpoint.procedure.comparability_conditions:
                reasons.append("CONDITION_CENSUS_UNRESOLVED")
            if any(c.status == ConditionStatus.NOT_MET for c in execution.conditions):
                reasons.append("COMPARABILITY_CONDITION_NOT_MET")
            unknown = (
                execution.completion == ExecutionCompletion.UNKNOWN
                or execution.result_level == ResultLevel.UNKNOWN
                or any(c.status == ConditionStatus.UNKNOWN for c in execution.conditions)
            )
            if unknown:
                reasons.append("EXECUTION_OR_CONDITIONS_UNKNOWN")
            if (
                endpoint.metric_key in {"VO2MAX_RELATIVE", "VO2MAX_ESTIMATED_RELATIVE"}
                and execution.body_mass_kg is None
            ):
                reasons.append("BODY_MASS_NOT_RETAINED")
            if reasons:
                unresolved = (
                    unknown
                    or "CONDITION_CENSUS_UNRESOLVED" in reasons
                    or "BODY_MASS_NOT_RETAINED" in reasons
                )
                eligibility = E.UNRESOLVED if unresolved else E.INELIGIBLE
    return GoalMeasurementCandidate(
        source.source_kind,
        source.source_id,
        source.source_sha256,
        window,
        eligibility,
        tuple(reasons),
    )


def _endpoint_assessment(endpoint, sources, packets, cutoff):
    S, W, E = GoalCriterionStatus, MeasurementWindowRole, MeasurementEligibility
    metric = goal_metric(endpoint.metric_key)
    candidates = tuple(
        _candidate(source, packet, endpoint)
        for source, packet in zip(sources, packets, strict=True)
    )
    picked = {}
    reasons = []
    for window, interval in (
        (W.BASELINE, endpoint.baseline_window),
        (W.FOLLOWUP, endpoint.followup_window),
    ):
        eligible = [
            (source, packet)
            for source, packet, candidate in zip(sources, packets, candidates, strict=True)
            if candidate.window == window and candidate.eligibility == E.ELIGIBLE
        ]
        unresolved = any(c.window == window and c.eligibility == E.UNRESOLVED for c in candidates)
        if cutoff < interval.ends_at:
            reasons.append(f"{window.value.upper()}_WINDOW_NOT_CLOSED")
        elif unresolved:
            reasons.append(f"{window.value.upper()}_CANDIDATE_UNRESOLVED")
        elif not eligible:
            reasons.append(f"{window.value.upper()}_RESULT_MISSING")
        elif len(eligible) != 1:
            reasons.append(f"{window.value.upper()}_RESULT_AMBIGUOUS")
        else:
            picked[window] = eligible[0]
    base_source, base_packet = picked.get(W.BASELINE, (None, None))
    end_source, end_packet = picked.get(W.FOLLOWUP, (None, None))
    base = _number(base_packet) if base_packet is not None else None
    end = _number(end_packet) if end_packet is not None else None
    absolute = percent = point_met = sensitivity_low = sensitivity_high = None
    status = S.WITHHELD
    requirement = endpoint.change_requirement
    if not reasons:
        status = S.DESCRIPTIVE_ONLY
        if metric.scale != MeasurementScale.ORDINAL:
            absolute = Fraction(end) - Fraction(base)
            if metric.favourable_direction == ImprovementDirection.LOWER:
                absolute = -absolute
            if metric.scale == MeasurementScale.RATIO and base > 0:
                percent = absolute * 100 / Fraction(base)
        if endpoint.role == EndpointRole.PRIMARY:
            change = (
                absolute if requirement.basis == ChangeBasis.FAVOURABLE_ABSOLUTE_CHANGE else percent
            )
            status = S.WITHHELD
            if change is None:
                reasons.append("PERCENT_CHANGE_REQUIRES_POSITIVE_BASELINE")
            else:
                minimum = Fraction(decimal_text(requirement.minimum))
                maximum = (
                    Fraction(decimal_text(requirement.maximum))
                    if requirement.maximum is not None
                    else None
                )
                point_met = change >= minimum and (maximum is None or change <= maximum)
                if requirement.measurement_error_estimate is None:
                    reasons.append("CHANGE_UNCERTAINTY_UNQUANTIFIED")
                else:
                    error = Fraction(decimal_text(requirement.measurement_error_estimate))
                    sensitivity_low, sensitivity_high = change - error, change + error
                    if sensitivity_low >= minimum and (
                        maximum is None or sensitivity_high <= maximum
                    ):
                        status = S.MET_UNDER_DECLARED_ERROR
                    elif sensitivity_high < minimum or (
                        maximum is not None and sensitivity_low > maximum
                    ):
                        status = S.NOT_MET_UNDER_DECLARED_ERROR
                    else:
                        reasons.append("DECLARED_ERROR_RANGE_CROSSES_ACCEPTANCE_BOUNDARY")
    return GoalEndpointAssessment(
        endpoint.endpoint_key,
        endpoint.capability_key,
        endpoint.role,
        metric.metric_key,
        metric.unit,
        metric.evidence_kind,
        metric.interpretation_limit,
        candidates,
        base_source,
        end_source,
        _plain(base) if base is not None else None,
        _plain(end) if end is not None else None,
        _exact(absolute) if absolute is not None else None,
        _exact(percent) if percent is not None else None,
        requirement.basis if requirement else None,
        point_met,
        _exact(sensitivity_low) if sensitivity_low is not None else None,
        _exact(sensitivity_high) if sensitivity_high is not None else None,
        status,
        tuple(reasons),
    )


def _combine(statuses):
    if not statuses or GoalCriterionStatus.WITHHELD in statuses:
        return GoalCriterionStatus.WITHHELD
    if all(status == GoalCriterionStatus.MET_UNDER_DECLARED_ERROR for status in statuses):
        return GoalCriterionStatus.MET_UNDER_DECLARED_ERROR
    return GoalCriterionStatus.NOT_MET_UNDER_DECLARED_ERROR


def build_mesocycle_goal_assessment(
    *, protocol, protocol_source, activity_cutoff_at, census, created_at
):
    require_typed(protocol, MesocycleGoalProtocol)
    require_typed(protocol_source, DurableGoalSourceReference)
    require_typed(census, GoalMeasurementCensus)
    created = to_utc(created_at, field_name="created_at")
    cutoff = to_utc(activity_cutoff_at, field_name="activity_cutoff_at")
    if (
        protocol_source.artifact_kind != AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL
        or protocol_source.artifact_id != protocol.artifact_id
        or protocol_source.content_hash != protocol.content_hash
        or protocol_source.canonical_contract_sha256
        != sha256(canonical_json(protocol).encode("utf-8")).hexdigest()
        or not protocol.verify_content_hash()
        or not (
            protocol.created_at
            <= protocol_source.persisted_at
            <= census.capture_started_at
            <= census.captured_at
            <= created
        )
        or cutoff > census.capture_started_at
        or any(
            protocol_source.persisted_at >= e.baseline_window.starts_at
            for e in protocol.proposal.endpoints
        )
    ):
        raise ValueError("Goal protocol provenance or measurement chronology differs.")
    endpoints = protocol.proposal.endpoints
    if not endpoints or len(endpoints) > GOAL_ASSESSMENT_ENDPOINT_LIMIT:
        raise ValueError("Unsupported goal endpoint census size.")
    start = min(e.baseline_window.starts_at for e in endpoints)
    end = min(cutoff, max(e.followup_window.ends_at for e in endpoints))
    if cutoff < start:
        raise ValueError("Assessment cutoff precedes the first measurement window.")
    if (
        census.athlete_id != protocol.athlete_id
        or census.interval_starts_at != start
        or census.interval_ends_at != end
        or len(census.sources) >= GOAL_MEASUREMENT_CENSUS_LIMIT
    ):
        raise ValueError("Measurement census scope or completeness limit differs.")
    keys = [(s.source_kind.value, s.source_id) for s in census.sources]
    if keys != sorted(set(keys)):
        raise ValueError("Measurement census identities must be unique and sorted.")
    packets = tuple(measurement_packet(s) for s in census.sources)
    for packet in packets:
        if (
            packet["athlete_id"] != protocol.athlete_id
            or not (start <= _time(packet["measured_at"]) <= end)
            or any(
                _time(packet[key]) > census.capture_started_at
                for key in ("created_at", "parent_created_at")
                if packet[key] is not None
            )
        ):
            raise ValueError(
                "Measurement source crosses athlete, activity interval or capture boundary."
            )
    assessments = tuple(_endpoint_assessment(e, census.sources, packets, cutoff) for e in endpoints)
    capabilities = []
    for role in protocol.capability_roles:
        primary = tuple(
            e
            for e in assessments
            if e.capability_key == role.capability_key and e.endpoint_role == EndpointRole.PRIMARY
        )
        status = _combine(tuple(e.criterion_status for e in primary))
        capabilities.append(
            GoalCapabilityAssessment(
                role.capability_key,
                role.role,
                tuple(e.endpoint_key for e in primary),
                status,
                ("ALL_PRIMARY_ENDPOINTS_REQUIRED_NO_COMPOSITE_SCORE",),
            )
        )
    artifact = MesocycleGoalAssessment(
        goal_assessment_id(protocol.athlete_id, protocol.artifact_id, cutoff),
        GOAL_ASSESSMENT_SCHEMA,
        GOAL_ASSESSMENT_RULES,
        protocol.athlete_id,
        protocol_source,
        cutoff,
        census,
        assessments,
        tuple(capabilities),
        protocol.unassigned_capability_keys,
        _combine(tuple(c.criterion_status for c in capabilities)),
        False,
        False,
        False,
        GoalAuthorityBoundary(),
        created,
        CONTENT_HASH_ALGORITHM,
        "",
    )
    return replace(
        artifact, content_hash=compute_content_hash(artifact, exclude_fields=GOAL_HASH_EXCLUDE)
    )
