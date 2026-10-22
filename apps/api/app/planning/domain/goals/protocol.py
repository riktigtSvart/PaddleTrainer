"""Explicit macrocycle decomposition and frozen mesocycle measurement intent.

No rule here derives roles from legacy weights or fabricates scientific
thresholds. A missing capability is unassigned, never permission to decline.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from re import fullmatch
from types import UnionType
from typing import get_args, get_origin, get_type_hints
from uuid import UUID
from zoneinfo import ZoneInfo

from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from ..common.time import to_utc
from ..persistence.audit import AuditArtifactKind
from .catalog import (
    GOAL_CATALOG_HASH,
    GOAL_CATALOG_VERSION,
    CapabilityKey,
    MeasurementEvidenceKind,
    MeasurementScale,
    goal_metric,
)

MACROCYCLE_PLAN_SCHEMA = "macrocycle-capability-plan-v0.1"
MESOCYCLE_PROTOCOL_SCHEMA = "mesocycle-goal-protocol-v0.1"
GOAL_PROTOCOL_RULES = "explicit-cycle-goal-rules-v0.1"
GOAL_HASH_EXCLUDE = frozenset({"artifact_id", "created_at", "content_hash"})
LEGACY_OBJECTIVE_TYPES = frozenset(
    {"ENDURANCE", "SPEED", "STRENGTH", "TECHNIQUE", "RECOVERY", "MOBILITY", "RACE_SPECIFIC"}
)


class GoalPeriodType(StrEnum):
    OLYMPIC_CYCLE = "OLYMPIC_CYCLE"
    SEASON = "SEASON"
    MACROCYCLE = "MACROCYCLE"
    MESOCYCLE = "MESOCYCLE"


class CapabilityGoalRole(StrEnum):
    PRIMARY_DEVELOPMENT = "primary_development"
    SECONDARY_DEVELOPMENT = "secondary_development"
    MAINTENANCE = "maintenance"
    PERMITTED_DECLINE = "permitted_decline"


class EndpointRole(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    CONTEXT = "context"


class ChangeBasis(StrEnum):
    FAVOURABLE_ABSOLUTE_CHANGE = "favourable_absolute_change"
    FAVOURABLE_PERCENT_CHANGE = "favourable_percent_change"


class ProtocolOrigin(StrEnum):
    EXPLICIT_CUSTOM = "explicit_custom"
    EXTERNAL_REFERENCE = "external_reference"


@dataclass(frozen=True)
class GoalAuthorityBoundary:
    shadow_only: bool = True
    capability_change_established: bool = False
    physiological_adaptation_established: bool = False
    comparative_utility_endpoint_preregistered: bool = False
    planning_utility_supported: bool = False
    causal_attribution_established: bool = False
    planning_authorized: bool = False
    planner_runtime_modified: bool = False


@dataclass(frozen=True)
class LegacyObjectiveSnapshot:
    objective_type: str
    weight: str


@dataclass(frozen=True)
class TrainingPeriodGoalSnapshot:
    period_id: str
    athlete_id: str
    parent_id: str | None
    period_type: GoalPeriodType
    title: str
    start_date: str
    end_date: str
    legacy_objectives: tuple[LegacyObjectiveSnapshot, ...]


@dataclass(frozen=True)
class TrainingGoalSourceSnapshot:
    athlete_id: str
    timezone_name: str
    hierarchy: tuple[TrainingPeriodGoalSnapshot, ...]
    mesocycles: tuple[TrainingPeriodGoalSnapshot, ...]


@dataclass(frozen=True)
class GoalVersionReference:
    artifact_id: str
    content_hash: str


@dataclass(frozen=True)
class DurableGoalSourceReference:
    artifact_kind: AuditArtifactKind
    artifact_id: str
    content_hash: str
    canonical_contract_sha256: str
    persisted_at: datetime


@dataclass(frozen=True)
class MacrocycleCapabilityGoal:
    capability_key: CapabilityKey
    role: CapabilityGoalRole
    rationale: str


@dataclass(frozen=True)
class MesocycleRoleDirective:
    mesocycle_period_id: str
    capability_key: CapabilityKey
    role: CapabilityGoalRole
    rationale: str


@dataclass(frozen=True)
class MacrocyclePlanProposal:
    macrocycle_period_id: str
    revision: int
    supersedes: GoalVersionReference | None
    goals: tuple[MacrocycleCapabilityGoal, ...]
    mesocycle_directives: tuple[MesocycleRoleDirective, ...]
    rationale: str


@dataclass(frozen=True)
class MeasurementProcedure:
    protocol_key: str
    protocol_version: str
    origin: ProtocolOrigin
    source_reference: str
    modality_key: str
    exercise_or_task: str
    procedure: str
    equipment_and_processing: str
    comparability_conditions: tuple[str, ...]


@dataclass(frozen=True)
class MeasurementWindow:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class GoalChangeRequirement:
    # Positive means favourable change, regardless of the raw metric direction.
    basis: ChangeBasis
    minimum: str
    maximum: str | None
    measurement_error_estimate: str | None
    measurement_error_source: str | None


@dataclass(frozen=True)
class GoalMeasurementEndpoint:
    endpoint_key: str
    capability_key: CapabilityKey
    metric_key: str
    role: EndpointRole
    procedure: MeasurementProcedure
    baseline_window: MeasurementWindow
    followup_window: MeasurementWindow
    change_requirement: GoalChangeRequirement | None


@dataclass(frozen=True)
class MesocycleProtocolProposal:
    mesocycle_period_id: str
    revision: int
    supersedes: GoalVersionReference | None
    macrocycle_plan: GoalVersionReference
    endpoints: tuple[GoalMeasurementEndpoint, ...]
    rationale: str


@dataclass(frozen=True)
class MacrocycleCapabilityPlan:
    artifact_id: str
    schema_version: str
    rules_version: str
    athlete_id: str
    catalog_version: str
    catalog_content_hash: str
    proposal: MacrocyclePlanProposal
    sources: TrainingGoalSourceSnapshot
    previous_source: DurableGoalSourceReference | None
    unassigned_capability_keys: tuple[CapabilityKey, ...]
    authority: GoalAuthorityBoundary
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return compute_content_hash(self, exclude_fields=GOAL_HASH_EXCLUDE) == self.content_hash


@dataclass(frozen=True)
class MesocycleGoalProtocol:
    artifact_id: str
    schema_version: str
    rules_version: str
    athlete_id: str
    catalog_version: str
    catalog_content_hash: str
    proposal: MesocycleProtocolProposal
    macrocycle_source: DurableGoalSourceReference
    previous_source: DurableGoalSourceReference | None
    sources: TrainingGoalSourceSnapshot
    capability_roles: tuple[MesocycleRoleDirective, ...]
    unassigned_capability_keys: tuple[CapabilityKey, ...]
    missing_data_rule: str
    uncertainty_rule: str
    comparison_rule: str
    combination_rule: str
    measurement_selection_rule: str
    nonpositive_baseline_rule: str
    standardization_validated: bool
    authority: GoalAuthorityBoundary
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return compute_content_hash(self, exclude_fields=GOAL_HASH_EXCLUDE) == self.content_hash


def require_typed(value, expected) -> None:
    """Reject mutable containers, bool-as-int and untyped enum/UTC substitutions."""
    origin, args = get_origin(expected), get_args(expected)
    if origin is UnionType:
        if value is None and type(None) in args:
            return
        non_none = tuple(item for item in args if item is not type(None))
        if len(non_none) != 1:
            raise ValueError("Unsupported goal contract union.")
        return require_typed(value, non_none[0])
    if origin is tuple:
        if type(value) is not tuple:
            raise ValueError("Goal contracts require immutable tuples.")
        if len(args) == 2 and args[1] is Ellipsis:
            for item in value:
                require_typed(item, args[0])
        else:
            if len(value) != len(args):
                raise ValueError("Goal contract tuple arity differs.")
            for item, kind in zip(value, args, strict=True):
                require_typed(item, kind)
        return
    if type(value) is not expected:
        raise ValueError("Goal contract field type differs.")
    if expected is datetime:
        to_utc(value, field_name="goal datetime")
    elif is_dataclass(value):
        hints = get_type_hints(expected)
        for field in fields(value):
            require_typed(getattr(value, field.name), hints[field.name])


def _text(value: str) -> None:
    if not value.strip():
        raise ValueError("Goal text must be non-empty.")


def _uuid(value: str) -> None:
    if str(UUID(value)) != value:
        raise ValueError("Goal source identifiers must be canonical UUIDs.")


def _hash(value: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Goal references require a lowercase SHA-256 digest.")


def decimal_text(value: str) -> Decimal:
    if (
        type(value) is not str
        or len(value) > 80
        or fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None
    ):
        raise ValueError("Goal numbers must be canonical decimal strings.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid goal decimal.") from exc
    if not parsed.is_finite():
        raise ValueError("Goal numbers must be finite.")
    normalized = value.rstrip("0").rstrip(".") if "." in value else value
    if not parsed:
        normalized = "0"
    if normalized != value:
        raise ValueError("Goal numbers must use canonical plain decimal notation.")
    return parsed


def goal_artifact_id(
    kind: AuditArtifactKind, athlete_id: str, period_id: str, revision: int
) -> str:
    if (
        kind
        not in {
            AuditArtifactKind.MACROCYCLE_CAPABILITY_PLAN,
            AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL,
        }
        or type(revision) is not int
        or revision < 1
    ):
        raise ValueError("Invalid goal artifact identity.")
    _uuid(athlete_id)
    _uuid(period_id)
    return "pt-goal:" + compute_content_hash(
        {
            "identity": "cycle-goal-slot-v0.1",
            "kind": kind,
            "athlete": athlete_id,
            "period": period_id,
            "revision": revision,
        }
    )


def _validate_previous(proposal, source, kind, athlete_id, period_id, created):
    if proposal.revision < 1 or (proposal.revision == 1) != (proposal.supersedes is None):
        raise ValueError("Goal revisions start at one and explicitly supersede the previous slot.")
    if (proposal.supersedes is None) != (source is None):
        raise ValueError("Previous goal version provenance is missing.")
    if source is not None:
        require_typed(source, DurableGoalSourceReference)
        _hash(source.content_hash)
        _hash(source.canonical_contract_sha256)
        expected = goal_artifact_id(kind, athlete_id, period_id, proposal.revision - 1)
        if (
            source.artifact_kind != kind
            or source.artifact_id != expected
            or source.artifact_id != proposal.supersedes.artifact_id
            or source.content_hash != proposal.supersedes.content_hash
            or to_utc(source.persisted_at, field_name="previous.persisted_at") > created
        ):
            raise ValueError("Previous goal version identity or chronology differs.")


def validate_goal_sources(sources: TrainingGoalSourceSnapshot, macrocycle_id: str) -> None:
    require_typed(sources, TrainingGoalSourceSnapshot)
    _uuid(sources.athlete_id)
    ZoneInfo(sources.timezone_name)
    if not sources.hierarchy or len(sources.hierarchy) > 4 or not sources.mesocycles:
        raise ValueError("Goal source hierarchy or mesocycle census is missing.")
    nodes = sources.hierarchy + sources.mesocycles
    if len({p.period_id for p in nodes}) != len(nodes):
        raise ValueError("Goal period source identity is ambiguous.")
    ranks = {key: i for i, key in enumerate(GoalPeriodType)}
    previous = None
    for node in nodes:
        _uuid(node.period_id)
        _text(node.title)
        if node.parent_id is not None:
            _uuid(node.parent_id)
        if node.athlete_id != sources.athlete_id:
            raise ValueError("Goal source crosses athletes.")
        start, end = date.fromisoformat(node.start_date), date.fromisoformat(node.end_date)
        if start.isoformat() != node.start_date or end.isoformat() != node.end_date or start > end:
            raise ValueError("Invalid goal period dates.")
        keys = [item.objective_type for item in node.legacy_objectives]
        if keys != sorted(set(keys)) or not set(keys) <= LEGACY_OBJECTIVE_TYPES:
            raise ValueError("Invalid legacy objective census.")
        weights = [decimal_text(item.weight) for item in node.legacy_objectives]
        if any(w < 0 or w > 1 for w in weights) or sum(weights) > Decimal("1.000001"):
            raise ValueError("Invalid legacy objective weights.")
    for node in sources.hierarchy:
        if previous is None:
            if node.parent_id is not None:
                raise ValueError("Goal ancestor is missing.")
        elif (
            node.parent_id != previous.period_id
            or ranks[node.period_type] <= ranks[previous.period_type]
            or not (previous.start_date <= node.start_date <= node.end_date <= previous.end_date)
        ):
            raise ValueError("Goal hierarchy types, links or containment differ.")
        previous = node
    macro = sources.hierarchy[-1]
    if macro.period_id != macrocycle_id or macro.period_type != GoalPeriodType.MACROCYCLE:
        raise ValueError("Goal source does not end at the requested macrocycle.")
    ordered = tuple(sorted(sources.mesocycles, key=lambda p: (p.start_date, p.period_id)))
    if ordered != sources.mesocycles:
        raise ValueError("Mesocycle census order differs.")
    previous_end = None
    for child in ordered:
        if (
            child.period_type != GoalPeriodType.MESOCYCLE
            or child.parent_id != macro.period_id
            or not (macro.start_date <= child.start_date <= child.end_date <= macro.end_date)
            or (previous_end is not None and child.start_date <= previous_end)
        ):
            raise ValueError("Mesocycle hierarchy, dates or non-overlap differs.")
        previous_end = child.end_date


def build_macrocycle_capability_plan(*, athlete_id, proposal, sources, previous_source, created_at):
    require_typed(proposal, MacrocyclePlanProposal)
    created = to_utc(created_at, field_name="created_at")
    validate_goal_sources(sources, proposal.macrocycle_period_id)
    if athlete_id != sources.athlete_id:
        raise ValueError("Macrocycle goal athlete differs.")
    _text(proposal.rationale)
    keys = [item.capability_key for item in proposal.goals]
    if not keys or len(set(keys)) != len(keys):
        raise ValueError("Macrocycle capability goals must be non-empty and unique.")
    for item in proposal.goals:
        _text(item.rationale)
    expected = {(p.period_id, key) for p in sources.mesocycles for key in keys}
    actual = [(d.mesocycle_period_id, d.capability_key) for d in proposal.mesocycle_directives]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Every macrocycle capability needs an explicit role in every mesocycle.")
    for directive in proposal.mesocycle_directives:
        _text(directive.rationale)
    _validate_previous(
        proposal,
        previous_source,
        AuditArtifactKind.MACROCYCLE_CAPABILITY_PLAN,
        athlete_id,
        proposal.macrocycle_period_id,
        created,
    )
    artifact = MacrocycleCapabilityPlan(
        goal_artifact_id(
            AuditArtifactKind.MACROCYCLE_CAPABILITY_PLAN,
            athlete_id,
            proposal.macrocycle_period_id,
            proposal.revision,
        ),
        MACROCYCLE_PLAN_SCHEMA,
        GOAL_PROTOCOL_RULES,
        athlete_id,
        GOAL_CATALOG_VERSION,
        GOAL_CATALOG_HASH,
        proposal,
        sources,
        previous_source,
        tuple(key for key in CapabilityKey if key not in keys),
        GoalAuthorityBoundary(),
        created,
        CONTENT_HASH_ALGORITHM,
        "",
    )
    return replace(
        artifact, content_hash=compute_content_hash(artifact, exclude_fields=GOAL_HASH_EXCLUDE)
    )


def _validate_endpoint(endpoint, role, period, timezone_name, created):
    _text(endpoint.endpoint_key)
    metric = goal_metric(endpoint.metric_key)
    if metric.capability_key != endpoint.capability_key:
        raise ValueError("Goal endpoint capability/metric pairing differs.")
    procedure = endpoint.procedure
    for value in (
        procedure.protocol_key,
        procedure.protocol_version,
        procedure.source_reference,
        procedure.modality_key,
        procedure.exercise_or_task,
        procedure.procedure,
        procedure.equipment_and_processing,
    ):
        _text(value)
    if not procedure.comparability_conditions or len(
        set(procedure.comparability_conditions)
    ) != len(procedure.comparability_conditions):
        raise ValueError("Explicit unique measurement comparability conditions are required.")
    for condition in procedure.comparability_conditions:
        _text(condition)
    base, end = endpoint.baseline_window, endpoint.followup_window
    times = tuple(
        to_utc(t, field_name="measurement window")
        for t in (base.starts_at, base.ends_at, end.starts_at, end.ends_at)
    )
    if not (created < times[0] <= times[1] < times[2] <= times[3]):
        raise ValueError("Measurement windows must be prospective and non-overlapping.")
    zone = ZoneInfo(timezone_name)
    if not (
        period.start_date <= times[0].astimezone(zone).date().isoformat()
        and times[3].astimezone(zone).date().isoformat() <= period.end_date
    ):
        raise ValueError("Measurement windows must fit the mesocycle in its source timezone.")
    requirement = endpoint.change_requirement
    if (
        metric.evidence_kind == MeasurementEvidenceKind.SUBJECTIVE_CONTEXT
        and endpoint.role != EndpointRole.CONTEXT
    ):
        raise ValueError("Subjective state measurements are context only.")
    if endpoint.role != EndpointRole.PRIMARY:
        if requirement is not None:
            raise ValueError("Only preregistered primary endpoints carry acceptance requirements.")
        return
    if not metric.primary_endpoint_eligible or requirement is None:
        raise ValueError("Primary endpoint or explicit change requirement is unavailable.")
    if (
        requirement.basis == ChangeBasis.FAVOURABLE_PERCENT_CHANGE
        and metric.scale != MeasurementScale.RATIO
    ):
        raise ValueError("Percentage change requires a ratio-scale metric and a positive baseline.")
    low = decimal_text(requirement.minimum)
    high = decimal_text(requirement.maximum) if requirement.maximum is not None else None
    if high is not None and high < low:
        raise ValueError("Goal acceptance interval is inverted.")
    if role in {CapabilityGoalRole.PRIMARY_DEVELOPMENT, CapabilityGoalRole.SECONDARY_DEVELOPMENT}:
        if low <= 0:
            raise ValueError("Development requires an explicit positive favourable-change target.")
    elif role == CapabilityGoalRole.MAINTENANCE:
        if high is None or not (low <= 0 <= high):
            raise ValueError("Maintenance requires a finite interval containing no change.")
    elif low >= 0 or (high is not None and high < 0):
        raise ValueError("Permitted decline requires a negative floor and must allow no decline.")
    if (requirement.measurement_error_estimate is None) != (
        requirement.measurement_error_source is None
    ):
        raise ValueError("Measurement uncertainty estimate and source must occur together.")
    if requirement.measurement_error_estimate is not None:
        if decimal_text(requirement.measurement_error_estimate) < 0:
            raise ValueError("Measurement uncertainty cannot be negative.")
        _text(requirement.measurement_error_source)


def build_mesocycle_goal_protocol(
    *,
    athlete_id,
    proposal,
    macrocycle_plan,
    macrocycle_source,
    sources,
    previous_source,
    created_at,
):
    require_typed(proposal, MesocycleProtocolProposal)
    require_typed(macrocycle_source, DurableGoalSourceReference)
    created = to_utc(created_at, field_name="created_at")
    expected_macro = build_macrocycle_capability_plan(
        athlete_id=macrocycle_plan.athlete_id,
        proposal=macrocycle_plan.proposal,
        sources=macrocycle_plan.sources,
        previous_source=macrocycle_plan.previous_source,
        created_at=macrocycle_plan.created_at,
    )
    if macrocycle_plan != expected_macro or athlete_id != macrocycle_plan.athlete_id:
        raise ValueError("Macrocycle goal contract does not replay.")
    _hash(macrocycle_source.canonical_contract_sha256)
    if (
        macrocycle_source.artifact_kind != AuditArtifactKind.MACROCYCLE_CAPABILITY_PLAN
        or macrocycle_source.artifact_id != macrocycle_plan.artifact_id
        or macrocycle_source.content_hash != macrocycle_plan.content_hash
        or proposal.macrocycle_plan
        != GoalVersionReference(macrocycle_plan.artifact_id, macrocycle_plan.content_hash)
        or not (macrocycle_plan.created_at <= macrocycle_source.persisted_at <= created)
    ):
        raise ValueError("Macrocycle plan reference or durable chronology differs.")
    if sources != macrocycle_plan.sources:
        raise ValueError("Mutable period goals changed; register a new macrocycle plan revision.")
    matches = [p for p in sources.mesocycles if p.period_id == proposal.mesocycle_period_id]
    if len(matches) != 1:
        raise ValueError("Requested mesocycle is outside the frozen macrocycle.")
    _text(proposal.rationale)
    roles = tuple(
        d
        for d in macrocycle_plan.proposal.mesocycle_directives
        if d.mesocycle_period_id == proposal.mesocycle_period_id
    )
    by_capability = {d.capability_key: d.role for d in roles}
    keys = [e.endpoint_key for e in proposal.endpoints]
    if len(set(keys)) != len(keys):
        raise ValueError("Measurement endpoint keys must be unique.")
    primaries = set()
    procedures = {}
    for endpoint in proposal.endpoints:
        if endpoint.capability_key not in by_capability:
            raise ValueError("Endpoint capability is not assigned by the macrocycle.")
        _validate_endpoint(
            endpoint,
            by_capability[endpoint.capability_key],
            matches[0],
            sources.timezone_name,
            created,
        )
        procedure_key = (endpoint.procedure.protocol_key, endpoint.procedure.protocol_version)
        if procedure_key in procedures and procedures[procedure_key] != endpoint.procedure:
            raise ValueError("One protocol key/version has conflicting procedure definitions.")
        procedures[procedure_key] = endpoint.procedure
        if endpoint.role == EndpointRole.PRIMARY:
            primaries.add(endpoint.capability_key)
    if primaries != set(by_capability):
        raise ValueError("Every assigned capability requires at least one primary endpoint.")
    _validate_previous(
        proposal,
        previous_source,
        AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL,
        athlete_id,
        proposal.mesocycle_period_id,
        created,
    )
    artifact = MesocycleGoalProtocol(
        goal_artifact_id(
            AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL,
            athlete_id,
            proposal.mesocycle_period_id,
            proposal.revision,
        ),
        MESOCYCLE_PROTOCOL_SCHEMA,
        GOAL_PROTOCOL_RULES,
        athlete_id,
        GOAL_CATALOG_VERSION,
        GOAL_CATALOG_HASH,
        proposal,
        macrocycle_source,
        previous_source,
        sources,
        roles,
        macrocycle_plan.unassigned_capability_keys,
        "WITHHOLD_ASSESSMENT_IF_MISSING",
        "WITHHOLD_IF_UNQUANTIFIED_OR_INCONCLUSIVE",
        "EXACT_PROTOCOL_MODALITY_UNIT_AND_CONDITIONS",
        "ALL_PRIMARY_ENDPOINTS_REQUIRED_NO_COMPOSITE_SCORE",
        "EXACTLY_ONE_ELIGIBLE_COMPLETE_RESULT_PER_WINDOW_OTHERWISE_WITHHOLD",
        "WITHHOLD_PERCENT_CHANGE_IF_BASELINE_NOT_POSITIVE",
        False,
        GoalAuthorityBoundary(),
        created,
        CONTENT_HASH_ALGORITHM,
        "",
    )
    return replace(
        artifact, content_hash=compute_content_hash(artifact, exclude_fields=GOAL_HASH_EXCLUDE)
    )
