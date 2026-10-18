from datetime import datetime

from ..common.enums import DecisionRelevance
from ..context.models import AthletePlanningContextAggregate, TrainingSpaceStatus
from ..policy.models import (
    ExecutablePlanningPolicy,
    PlanningPolicySet,
    PolicyEffect,
    PolicyStrength,
    finalize_policy_execution_record,
)
from ..workout_family.models import FamilyEntryGateStatus
from .models import (
    AlternativeEvaluation,
    CandidateCoverageStatus,
    CandidateGenerationExclusion,
    CandidateStatus,
    EnvelopeCriticalUnknown,
    EnvelopeFamilyItem,
    PlannerActionCandidate,
    PlannerActionType,
    PlannerDecisionRequest,
    PlannerDecisionStatus,
    PlannerInputEnvelope,
    finalize_candidate_action_set,
    finalize_planner_decision,
    finalize_planner_input_envelope,
)


def build_planner_input_envelope(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
) -> PlannerInputEnvelope:
    if not context.verify_content_hash():
        raise ValueError("Planning context hash does not verify.")
    if request.context_id != context.context_id:
        raise ValueError("Decision request context_id mismatch.")
    if request.context_hash != context.content_hash:
        raise ValueError("Decision request context_hash mismatch.")
    if request.decision_purpose != context.decision_purpose:
        raise ValueError("Decision purpose mismatch.")
    if request.planning_scope != context.planning_scope:
        raise ValueError("Planning scope mismatch.")
    if request.requested_at < context.as_of:
        raise ValueError("Decision request cannot precede planning context as_of.")
    if context.runtime_projection is None:
        raise ValueError("P0.8 requires a runtime planning projection.")

    training_space = context.runtime_projection.training_space
    family_items = tuple(
        EnvelopeFamilyItem(
            family_key=item.family_key,
            family_version=item.family_version,
            entry_gate_status=item.entry_gate_status.value,
            build_authorized_by_entry_gate=item.build_authorized_by_entry_gate,
            dose_reduction_required=item.dose_reduction_required,
            reason_codes=item.reason_codes,
        )
        for item in training_space.families
    )
    high_unknowns = tuple(
        EnvelopeCriticalUnknown(
            domain=item.domain,
            question=item.question,
            decision_relevance=item.decision_relevance,
            fallback_policy=item.fallback_policy,
        )
        for item in context.critical_unknowns
        if item.decision_relevance
        in {DecisionRelevance.HIGH, DecisionRelevance.BLOCKING}
    )

    return finalize_planner_input_envelope(
        context_id=context.context_id,
        context_hash=context.content_hash,
        decision_purpose=context.decision_purpose,
        planning_scope=context.planning_scope,
        training_space_status=training_space.status,
        family_items=family_items,
        unresolved_dimensions=training_space.unresolved_dimensions,
        final_authorization=training_space.final_authorization,
        high_relevance_unknowns=high_unknowns,
    )


def _family_target(family_key: str, family_version: str) -> str:
    return f"workout_family:{family_key}@{family_version}"


def generate_candidate_action_set(*, envelope: PlannerInputEnvelope):
    if not envelope.verify_content_hash():
        raise ValueError("PlannerInputEnvelope hash does not verify.")

    candidates: list[PlannerActionCandidate] = [
        PlannerActionCandidate(
            action_id="action:defer",
            action_type=PlannerActionType.DEFER,
            target_ref=None,
            plan_mutation_authorized=False,
            parameters=(),
            reason_codes=("SAFE_FALLBACK_AVAILABLE",),
        )
    ]
    exclusions: list[CandidateGenerationExclusion] = []

    if envelope.high_relevance_unknowns:
        candidates.append(
            PlannerActionCandidate(
                action_id="action:request_information",
                action_type=PlannerActionType.REQUEST_INFORMATION,
                target_ref=None,
                plan_mutation_authorized=False,
                parameters=tuple(
                    (f"unknown_{index}", item.domain)
                    for index, item in enumerate(
                        envelope.high_relevance_unknowns, start=1
                    )
                ),
                reason_codes=("HIGH_RELEVANCE_UNKNOWN_PRESENT",),
            )
        )

    if envelope.training_space_status == TrainingSpaceStatus.ENTRY_GATE_REVIEW_REQUIRED:
        candidates.append(
            PlannerActionCandidate(
                action_id="action:request_review",
                action_type=PlannerActionType.REQUEST_REVIEW,
                target_ref=None,
                plan_mutation_authorized=False,
                parameters=(),
                reason_codes=("ENTRY_GATE_REVIEW_REQUIRED",),
            )
        )

    for item in envelope.family_items:
        target = _family_target(item.family_key, item.family_version)
        status = FamilyEntryGateStatus(item.entry_gate_status)

        if not envelope.final_authorization:
            exclusions.append(
                CandidateGenerationExclusion(
                    target_ref=target,
                    reason_codes=("FINAL_AUTHORIZATION_NOT_RESOLVED",),
                )
            )
            continue

        if status in {
            FamilyEntryGateStatus.NOT_ELIGIBLE,
            FamilyEntryGateStatus.DEFERRED_BY_GLOBAL_GATE,
            FamilyEntryGateStatus.REVIEW_REQUIRED,
        }:
            exclusions.append(
                CandidateGenerationExclusion(
                    target_ref=target,
                    reason_codes=(f"ENTRY_GATE_FAMILY_STATUS:{status.value}",),
                )
            )
            continue

        candidates.append(
            PlannerActionCandidate(
                action_id=(
                    f"action:select_family:{item.family_key}@{item.family_version}"
                ),
                action_type=PlannerActionType.SELECT_WORKOUT_FAMILY,
                target_ref=target,
                plan_mutation_authorized=True,
                parameters=(
                    ("family_key", item.family_key),
                    ("family_version", item.family_version),
                    (
                        "dose_reduction_required",
                        str(item.dose_reduction_required).lower(),
                    ),
                ),
                reason_codes=tuple(item.reason_codes),
            )
        )

    coverage = (
        CandidateCoverageStatus.LIMITED
        if envelope.unresolved_dimensions or not envelope.final_authorization
        else CandidateCoverageStatus.SUFFICIENT
    )
    return finalize_candidate_action_set(
        envelope_hash=envelope.content_hash,
        candidates=tuple(candidates),
        excluded_during_generation=tuple(exclusions),
        coverage_status=coverage,
    )


def _runtime_matches_set(
    *,
    policy_set: PlanningPolicySet,
    policies: tuple[ExecutablePlanningPolicy, ...],
) -> None:
    set_refs = {(p.policy_key, p.policy_version) for p in policy_set.policies}
    runtime_refs = {
        (p.definition.policy_key, p.definition.policy_version) for p in policies
    }
    if set_refs != runtime_refs:
        raise ValueError(
            "Executable policy runtime does not match PlanningPolicySet."
        )


def run_planner_decision(
    *,
    decision_id: str,
    request: PlannerDecisionRequest,
    envelope: PlannerInputEnvelope,
    candidate_set,
    policy_set: PlanningPolicySet,
    policies: tuple[ExecutablePlanningPolicy, ...],
    decision_time: datetime,
    created_at: datetime,
    engine_version: str,
):
    if request.context_hash != envelope.context_hash:
        raise ValueError("Request/envelope context hash mismatch.")
    if candidate_set.envelope_hash != envelope.content_hash:
        raise ValueError("Candidate set/envelope hash mismatch.")
    if not envelope.verify_content_hash():
        raise ValueError("PlannerInputEnvelope hash does not verify.")
    if not candidate_set.verify_content_hash():
        raise ValueError("CandidateActionSet hash does not verify.")
    if not policy_set.verify_content_hash():
        raise ValueError("PlanningPolicySet hash does not verify.")
    _runtime_matches_set(policy_set=policy_set, policies=policies)

    evaluations = []
    per_action: dict[str, list] = {
        candidate.action_id: [] for candidate in candidate_set.candidates
    }
    for candidate in candidate_set.candidates:
        for policy in policies:
            evaluation = policy.evaluate(envelope=envelope, candidate=candidate)
            evaluations.append(evaluation)
            per_action[candidate.action_id].append(evaluation)

    execution = finalize_policy_execution_record(
        policy_set=policy_set,
        evaluations=tuple(evaluations),
    )

    alternatives = []
    required = []
    preferred = []
    viable = []

    for candidate in candidate_set.candidates:
        action_evaluations = per_action[candidate.action_id]
        hard_prohibit = any(
            item.effect == PolicyEffect.PROHIBIT
            and item.strength == PolicyStrength.HARD
            for item in action_evaluations
        )
        hard_require = any(
            item.effect == PolicyEffect.REQUIRE
            and item.strength == PolicyStrength.HARD
            for item in action_evaluations
        )
        has_preference = any(
            item.effect == PolicyEffect.PREFER for item in action_evaluations
        )

        binding = tuple(
            dict.fromkeys(
                reason
                for item in action_evaluations
                if item.effect in {PolicyEffect.PROHIBIT, PolicyEffect.REQUIRE}
                for reason in item.reason_codes
            )
        )
        pref = tuple(
            dict.fromkeys(
                reason
                for item in action_evaluations
                if item.effect == PolicyEffect.PREFER
                for reason in item.reason_codes
            )
        )
        restrictions = tuple(
            dict.fromkeys(
                reason
                for item in action_evaluations
                if item.effect
                in {
                    PolicyEffect.RESTRICT,
                    PolicyEffect.DISFAVOR,
                    PolicyEffect.REQUEST_INFORMATION,
                }
                for reason in item.reason_codes
            )
        )

        if hard_prohibit:
            candidate_status = CandidateStatus.ELIMINATED
        elif hard_require:
            candidate_status = CandidateStatus.REQUIRED
            required.append(candidate)
            viable.append(candidate)
        elif has_preference:
            candidate_status = CandidateStatus.PREFERRED
            preferred.append(candidate)
            viable.append(candidate)
        else:
            candidate_status = CandidateStatus.VIABLE
            viable.append(candidate)

        alternatives.append(
            AlternativeEvaluation(
                action_id=candidate.action_id,
                status=candidate_status,
                binding_reason_codes=binding,
                preference_reason_codes=pref,
                restriction_reason_codes=restrictions,
            )
        )

    selected = None
    if len(required) == 1:
        selected = required[0]
    elif len(required) > 1:
        status = PlannerDecisionStatus.HUMAN_DECISION_REQUIRED
    elif len(preferred) == 1:
        selected = preferred[0]
    elif len(preferred) > 1:
        status = PlannerDecisionStatus.HUMAN_DECISION_REQUIRED
    elif len(viable) == 1:
        selected = viable[0]
    elif len(viable) == 0:
        status = PlannerDecisionStatus.NO_FEASIBLE_ACTION
    else:
        status = PlannerDecisionStatus.HUMAN_DECISION_REQUIRED

    if selected is not None:
        if selected.action_type == PlannerActionType.DEFER:
            status = (
                PlannerDecisionStatus.BLOCKED_BY_CONSTRAINT
                if envelope.training_space_status
                == TrainingSpaceStatus.ENTRY_GATE_BLOCKED
                else PlannerDecisionStatus.DEFERRED_PENDING_CONTEXT
            )
        elif selected.action_type == PlannerActionType.REQUEST_REVIEW:
            status = PlannerDecisionStatus.REVIEW_REQUIRED
        elif selected.action_type == PlannerActionType.NO_CHANGE:
            status = PlannerDecisionStatus.NO_CHANGE
        elif envelope.unresolved_dimensions:
            status = PlannerDecisionStatus.DECIDED_WITH_CONSTRAINTS
        else:
            status = PlannerDecisionStatus.DECIDED

    return finalize_planner_decision(
        decision_id=decision_id,
        request_id=request.request_id,
        context_id=request.context_id,
        context_hash=request.context_hash,
        envelope_hash=envelope.content_hash,
        candidate_set_hash=candidate_set.content_hash,
        decision_time=decision_time,
        created_at=created_at,
        status=status,
        selected_action=selected,
        alternatives=tuple(alternatives),
        policy_execution=execution,
        engine_version=engine_version,
    )
