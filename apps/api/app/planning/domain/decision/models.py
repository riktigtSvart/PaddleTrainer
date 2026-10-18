from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.enums import DecisionPurpose, DecisionRelevance, PlanningScope
from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from ..common.time import to_utc
from ..context.models import TrainingSpaceStatus, UnresolvedPlanningDimension
from ..policy.models import PolicyExecutionRecord


INPUT_ENVELOPE_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})
CANDIDATE_SET_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})
PLANNER_DECISION_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "decision_id", "created_at", "request_id"}
)


class PlannerActionType(StrEnum):
    SELECT_WORKOUT_FAMILY = "select_workout_family"
    NO_CHANGE = "no_change"
    DEFER = "defer"
    REQUEST_INFORMATION = "request_information"
    REQUEST_REVIEW = "request_review"


class CandidateCoverageStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    UNKNOWN = "unknown"


class CandidateStatus(StrEnum):
    ELIMINATED = "eliminated"
    VIABLE = "viable"
    PREFERRED = "preferred"
    REQUIRED = "required"
    INCOMPARABLE = "incomparable"


class PlannerDecisionStatus(StrEnum):
    DECIDED = "decided"
    DECIDED_WITH_CONSTRAINTS = "decided_with_constraints"
    NO_CHANGE = "no_change"
    DEFERRED_PENDING_CONTEXT = "deferred_pending_context"
    HUMAN_DECISION_REQUIRED = "human_decision_required"
    BLOCKED_BY_CONSTRAINT = "blocked_by_constraint"
    NO_FEASIBLE_ACTION = "no_feasible_action"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class PlannerDecisionRequest:
    request_id: str
    context_id: str
    context_hash: str
    decision_purpose: DecisionPurpose
    planning_scope: PlanningScope
    requested_at: datetime

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id must be non-empty.")
        if not self.context_id.strip():
            raise ValueError("context_id must be non-empty.")
        object.__setattr__(
            self,
            "requested_at",
            to_utc(self.requested_at, field_name="requested_at"),
        )


@dataclass(frozen=True)
class EnvelopeFamilyItem:
    family_key: str
    family_version: str
    entry_gate_status: str
    build_authorized_by_entry_gate: bool
    dose_reduction_required: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EnvelopeCriticalUnknown:
    domain: str
    question: str
    decision_relevance: DecisionRelevance
    fallback_policy: str | None


@dataclass(frozen=True)
class PlannerInputEnvelope:
    context_id: str
    context_hash: str
    decision_purpose: DecisionPurpose
    planning_scope: PlanningScope
    training_space_status: TrainingSpaceStatus
    family_items: tuple[EnvelopeFamilyItem, ...]
    unresolved_dimensions: tuple[UnresolvedPlanningDimension, ...]
    final_authorization: bool
    high_relevance_unknowns: tuple[EnvelopeCriticalUnknown, ...]
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=INPUT_ENVELOPE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_planner_input_envelope(
    *,
    context_id: str,
    context_hash: str,
    decision_purpose: DecisionPurpose,
    planning_scope: PlanningScope,
    training_space_status: TrainingSpaceStatus,
    family_items: tuple[EnvelopeFamilyItem, ...],
    unresolved_dimensions: tuple[UnresolvedPlanningDimension, ...],
    final_authorization: bool,
    high_relevance_unknowns: tuple[EnvelopeCriticalUnknown, ...],
) -> PlannerInputEnvelope:
    provisional = PlannerInputEnvelope(
        context_id=context_id,
        context_hash=context_hash,
        decision_purpose=decision_purpose,
        planning_scope=planning_scope,
        training_space_status=training_space_status,
        family_items=tuple(family_items),
        unresolved_dimensions=tuple(unresolved_dimensions),
        final_authorization=final_authorization,
        high_relevance_unknowns=tuple(high_relevance_unknowns),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=INPUT_ENVELOPE_HASH_EXCLUDE_FIELDS,
    )
    return PlannerInputEnvelope(
        context_id=provisional.context_id,
        context_hash=provisional.context_hash,
        decision_purpose=provisional.decision_purpose,
        planning_scope=provisional.planning_scope,
        training_space_status=provisional.training_space_status,
        family_items=provisional.family_items,
        unresolved_dimensions=provisional.unresolved_dimensions,
        final_authorization=provisional.final_authorization,
        high_relevance_unknowns=provisional.high_relevance_unknowns,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class PlannerActionCandidate:
    action_id: str
    action_type: PlannerActionType
    target_ref: str | None
    plan_mutation_authorized: bool
    parameters: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateGenerationExclusion:
    target_ref: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateActionSet:
    envelope_hash: str
    candidates: tuple[PlannerActionCandidate, ...]
    excluded_during_generation: tuple[CandidateGenerationExclusion, ...]
    coverage_status: CandidateCoverageStatus
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=CANDIDATE_SET_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_candidate_action_set(
    *,
    envelope_hash: str,
    candidates: tuple[PlannerActionCandidate, ...],
    excluded_during_generation: tuple[CandidateGenerationExclusion, ...],
    coverage_status: CandidateCoverageStatus,
) -> CandidateActionSet:
    candidate_ids = tuple(item.action_id for item in candidates)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Candidate action IDs must be unique.")

    provisional = CandidateActionSet(
        envelope_hash=envelope_hash,
        candidates=tuple(sorted(candidates, key=lambda item: item.action_id)),
        excluded_during_generation=tuple(
            sorted(excluded_during_generation, key=lambda item: item.target_ref)
        ),
        coverage_status=coverage_status,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=CANDIDATE_SET_HASH_EXCLUDE_FIELDS,
    )
    return CandidateActionSet(
        envelope_hash=provisional.envelope_hash,
        candidates=provisional.candidates,
        excluded_during_generation=provisional.excluded_during_generation,
        coverage_status=provisional.coverage_status,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class AlternativeEvaluation:
    action_id: str
    status: CandidateStatus
    binding_reason_codes: tuple[str, ...]
    preference_reason_codes: tuple[str, ...]
    restriction_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PlannerDecision:
    decision_id: str
    request_id: str
    context_id: str
    context_hash: str
    envelope_hash: str
    candidate_set_hash: str
    decision_time: datetime
    created_at: datetime
    status: PlannerDecisionStatus
    selected_action: PlannerActionCandidate | None
    alternatives: tuple[AlternativeEvaluation, ...]
    policy_execution: PolicyExecutionRecord
    engine_version: str
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_planner_decision(
    *,
    decision_id: str,
    request_id: str,
    context_id: str,
    context_hash: str,
    envelope_hash: str,
    candidate_set_hash: str,
    decision_time: datetime,
    created_at: datetime,
    status: PlannerDecisionStatus,
    selected_action: PlannerActionCandidate | None,
    alternatives: tuple[AlternativeEvaluation, ...],
    policy_execution: PolicyExecutionRecord,
    engine_version: str,
) -> PlannerDecision:
    decision_time_utc = to_utc(decision_time, field_name="decision_time")
    created_at_utc = to_utc(created_at, field_name="created_at")
    if created_at_utc < decision_time_utc:
        raise ValueError("created_at must not precede decision_time.")

    provisional = PlannerDecision(
        decision_id=decision_id,
        request_id=request_id,
        context_id=context_id,
        context_hash=context_hash,
        envelope_hash=envelope_hash,
        candidate_set_hash=candidate_set_hash,
        decision_time=decision_time_utc,
        created_at=created_at_utc,
        status=status,
        selected_action=selected_action,
        alternatives=tuple(alternatives),
        policy_execution=policy_execution,
        engine_version=engine_version,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
    )
    return PlannerDecision(
        decision_id=provisional.decision_id,
        request_id=provisional.request_id,
        context_id=provisional.context_id,
        context_hash=provisional.context_hash,
        envelope_hash=provisional.envelope_hash,
        candidate_set_hash=provisional.candidate_set_hash,
        decision_time=provisional.decision_time,
        created_at=provisional.created_at,
        status=provisional.status,
        selected_action=provisional.selected_action,
        alternatives=provisional.alternatives,
        policy_execution=provisional.policy_execution,
        engine_version=provisional.engine_version,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
