from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.enums import (
    ConfidenceLevel,
    DecisionPurpose,
    DecisionRelevance,
    Freshness,
    PlanningScope,
    SnapshotStatus,
)
from ..common.refs import SourceSnapshotRef, VersionRef
from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from ..common.time import to_utc
from ..entry_gate.models import (
    EntryMode,
    GlobalEntryGate,
    StimulusGateStatus,
)
from ..training_state.models import EvidenceCoverage, LoadAnchorStatus
from ..workout_family.models import FamilyEntryGateStatus


@dataclass(frozen=True)
class CriticalUnknown:
    domain: str
    question: str
    decision_relevance: DecisionRelevance
    fallback_policy: str | None = None


@dataclass(frozen=True)
class EvidenceConflict:
    domain: str
    description: str
    decision_impact: DecisionRelevance


@dataclass(frozen=True)
class PlanningAssumption:
    statement: str
    impact_if_wrong: DecisionRelevance
    review_trigger: str | None = None


@dataclass(frozen=True)
class DomainFreshness:
    domain: str
    freshness: Freshness
    confidence: ConfidenceLevel


class TrainingSpaceStatus(StrEnum):
    ENTRY_GATE_OPEN = "entry_gate_open"
    ENTRY_GATE_CONSTRAINED = "entry_gate_constrained"
    ENTRY_GATE_HOLD = "entry_gate_hold"
    ENTRY_GATE_BLOCKED = "entry_gate_blocked"
    ENTRY_GATE_REVIEW_REQUIRED = "entry_gate_review_required"


class UnresolvedPlanningDimension(StrEnum):
    GOAL_PRIORITY = "goal_priority"
    OBJECTIVE_REGIME = "objective_regime"
    SPORT_READINESS = "sport_readiness"
    PLANNING_AUTHORITY = "planning_authority"
    DETAILED_AVAILABILITY = "detailed_availability"
    ENVIRONMENT = "environment"


@dataclass(frozen=True)
class CurrentStateContextProjection:
    current_training_state_hash: str
    load_anchor_status: LoadAnchorStatus
    recent_source_coverage: EvidenceCoverage
    recent_observed_session_count: int
    recent_known_duration_s: int
    recent_complete_window_duration_s: int | None
    latest_training_observed_at: datetime | None


@dataclass(frozen=True)
class StimulusGateContextProjection:
    stimulus_key: str
    status: StimulusGateStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EntryGateContextProjection:
    entry_gate_decision_hash: str
    global_gate: GlobalEntryGate
    entry_mode: EntryMode
    reason_codes: tuple[str, ...]
    stimulus_gates: tuple[StimulusGateContextProjection, ...]


@dataclass(frozen=True)
class WorkoutFamilySpaceItem:
    family_key: str
    family_version: str
    modality_key: str
    sport_key: str | None
    entry_gate_status: FamilyEntryGateStatus
    build_authorized_by_entry_gate: bool
    dose_reduction_required: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class TrainingSpaceProjection:
    projection_scope: str
    status: TrainingSpaceStatus
    families: tuple[WorkoutFamilySpaceItem, ...]
    unresolved_dimensions: tuple[UnresolvedPlanningDimension, ...]
    final_authorization: bool


@dataclass(frozen=True)
class RuntimePlanningProjection:
    current_state: CurrentStateContextProjection
    entry_gate: EntryGateContextProjection
    workout_family_registry_version: str
    workout_family_registry_hash: str
    training_space: TrainingSpaceProjection


CONTEXT_HASH_EXCLUDE_FIELDS = frozenset(
    {
        "content_hash",
        "context_id",
        "created_at",
        # Source object IDs are audit references, while each source's content
        # hash carries the semantic state used by the planner.
        "object_id",
    }
)


@dataclass(frozen=True)
class AthletePlanningContextAggregate:
    context_id: str
    athlete_id: str
    schema_version: str
    as_of: datetime
    information_cutoff_at: datetime
    created_at: datetime
    planning_scope: PlanningScope
    decision_purpose: DecisionPurpose
    source_snapshot_refs: tuple[SourceSnapshotRef, ...]
    critical_unknowns: tuple[CriticalUnknown, ...]
    evidence_conflicts: tuple[EvidenceConflict, ...]
    assumptions: tuple[PlanningAssumption, ...]
    domain_freshness: tuple[DomainFreshness, ...]
    engine_version: VersionRef
    rules_version: VersionRef
    evidence_pack_version: VersionRef
    sport_profile_versions: tuple[VersionRef, ...]
    policy_versions: tuple[VersionRef, ...]
    status: SnapshotStatus
    content_hash_algorithm: str
    content_hash: str
    runtime_projection: RuntimePlanningProjection | None = None

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=CONTEXT_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def create_planning_context(
    *,
    context_id: str,
    athlete_id: str,
    schema_version: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
    planning_scope: PlanningScope,
    decision_purpose: DecisionPurpose,
    source_snapshot_refs: tuple[SourceSnapshotRef, ...],
    engine_version: VersionRef,
    rules_version: VersionRef,
    evidence_pack_version: VersionRef,
    sport_profile_versions: tuple[VersionRef, ...] = (),
    policy_versions: tuple[VersionRef, ...] = (),
    critical_unknowns: tuple[CriticalUnknown, ...] = (),
    evidence_conflicts: tuple[EvidenceConflict, ...] = (),
    assumptions: tuple[PlanningAssumption, ...] = (),
    domain_freshness: tuple[DomainFreshness, ...] = (),
    runtime_projection: RuntimePlanningProjection | None = None,
) -> AthletePlanningContextAggregate:
    for field_name, value in (
        ("context_id", context_id),
        ("athlete_id", athlete_id),
        ("schema_version", schema_version),
    ):
        if not value or not value.strip():
            raise ValueError(f"{field_name} must be non-empty.")

    as_of_utc = to_utc(as_of, field_name="as_of")
    cutoff_utc = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )
    created_utc = to_utc(created_at, field_name="created_at")

    if cutoff_utc > as_of_utc:
        raise ValueError(
            "information_cutoff_at must not be after as_of."
        )

    for ref in source_snapshot_refs:
        if ref.information_cutoff_at > cutoff_utc:
            raise ValueError(
                "Source snapshot contains information after the "
                "planning context cutoff."
            )
        if ref.as_of > as_of_utc:
            raise ValueError(
                "Source snapshot as_of is after the planning context as_of."
            )
        # A derived snapshot may be calculated after the evidence cutoff. That
        # is valid as long as it uses only cutoff-safe information and exists
        # by the decision-time as_of instant.
        if ref.available_at > as_of_utc:
            raise ValueError(
                "Source snapshot was not available at the planning "
                "context as_of time."
            )

    provisional = AthletePlanningContextAggregate(
        context_id=context_id,
        athlete_id=athlete_id,
        schema_version=schema_version,
        as_of=as_of_utc,
        information_cutoff_at=cutoff_utc,
        created_at=created_utc,
        planning_scope=planning_scope,
        decision_purpose=decision_purpose,
        source_snapshot_refs=tuple(source_snapshot_refs),
        critical_unknowns=tuple(critical_unknowns),
        evidence_conflicts=tuple(evidence_conflicts),
        assumptions=tuple(assumptions),
        domain_freshness=tuple(domain_freshness),
        engine_version=engine_version,
        rules_version=rules_version,
        evidence_pack_version=evidence_pack_version,
        sport_profile_versions=tuple(sport_profile_versions),
        policy_versions=tuple(policy_versions),
        status=SnapshotStatus.FROZEN,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
        runtime_projection=runtime_projection,
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=CONTEXT_HASH_EXCLUDE_FIELDS,
    )

    return AthletePlanningContextAggregate(
        context_id=provisional.context_id,
        athlete_id=provisional.athlete_id,
        schema_version=provisional.schema_version,
        as_of=provisional.as_of,
        information_cutoff_at=provisional.information_cutoff_at,
        created_at=provisional.created_at,
        planning_scope=provisional.planning_scope,
        decision_purpose=provisional.decision_purpose,
        source_snapshot_refs=provisional.source_snapshot_refs,
        critical_unknowns=provisional.critical_unknowns,
        evidence_conflicts=provisional.evidence_conflicts,
        assumptions=provisional.assumptions,
        domain_freshness=provisional.domain_freshness,
        engine_version=provisional.engine_version,
        rules_version=provisional.rules_version,
        evidence_pack_version=provisional.evidence_pack_version,
        sport_profile_versions=provisional.sport_profile_versions,
        policy_versions=provisional.policy_versions,
        status=provisional.status,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
        runtime_projection=provisional.runtime_projection,
    )
