from datetime import datetime

from ..decision.models import (
    CandidateActionSet,
    CandidateStatus,
    PlannerDecision,
    PlannerDecisionStatus,
    PlannerInputEnvelope,
)
from ..policy.models import PolicyEffect, PlanningPolicySet
from .models import (
    AlternativeDisposition,
    AlternativeRationale,
    RationaleUnknown,
    finalize_decision_rationale,
)


RATIONALE_VERSION = "decision_rationale_v0.1"


def _policy_ref(policy_key: str, policy_version: str) -> str:
    return f"{policy_key}@{policy_version}"


def _alternative_disposition(status: CandidateStatus) -> AlternativeDisposition:
    if status == CandidateStatus.ELIMINATED:
        return AlternativeDisposition.ELIMINATED_BY_POLICY
    if status == CandidateStatus.PREFERRED:
        return AlternativeDisposition.PREFERRED_NOT_SELECTED
    if status == CandidateStatus.REQUIRED:
        return AlternativeDisposition.REQUIRED_NOT_SELECTED
    return AlternativeDisposition.VIABLE_NOT_SELECTED


def build_decision_rationale(
    *,
    rationale_id: str,
    decision: PlannerDecision,
    envelope: PlannerInputEnvelope,
    candidate_set: CandidateActionSet,
    policy_set: PlanningPolicySet,
    created_at: datetime,
):
    if not decision.verify_content_hash():
        raise ValueError("PlannerDecision hash does not verify.")
    if not envelope.verify_content_hash():
        raise ValueError("PlannerInputEnvelope hash does not verify.")
    if not candidate_set.verify_content_hash():
        raise ValueError("CandidateActionSet hash does not verify.")
    if not policy_set.verify_content_hash():
        raise ValueError("PlanningPolicySet hash does not verify.")
    if decision.context_hash != envelope.context_hash:
        raise ValueError("Decision/envelope context hash mismatch.")
    if decision.envelope_hash != envelope.content_hash:
        raise ValueError("Decision/envelope hash mismatch.")
    if decision.candidate_set_hash != candidate_set.content_hash:
        raise ValueError("Decision/candidate set hash mismatch.")
    if decision.policy_execution.policy_set_hash != policy_set.content_hash:
        raise ValueError("Decision/policy set hash mismatch.")

    selected_action_id = (
        decision.selected_action.action_id
        if decision.selected_action is not None
        else None
    )

    selected_evaluations = tuple(
        item
        for item in decision.policy_execution.evaluations
        if item.action_id == selected_action_id
    )
    primary_reasons = []
    binding = []

    if decision.selected_action is not None:
        primary_reasons.extend(decision.selected_action.reason_codes)

    for item in selected_evaluations:
        if item.effect in {PolicyEffect.REQUIRE, PolicyEffect.PREFER}:
            primary_reasons.extend(item.reason_codes)
        if item.effect in {PolicyEffect.REQUIRE, PolicyEffect.PROHIBIT}:
            binding.extend(item.reason_codes)

    # The decision status itself is structured evidence about why the planner
    # stopped/selected. It is stored as a code, not retroactive prose.
    primary_reasons.append(f"DECISION_STATUS:{decision.status.value}")

    candidates_by_id = {
        item.action_id: item for item in candidate_set.candidates
    }
    alternatives = []

    for exclusion in candidate_set.excluded_during_generation:
        alternatives.append(
            AlternativeRationale(
                action_id=None,
                target_ref=exclusion.target_ref,
                disposition=(
                    AlternativeDisposition.EXCLUDED_DURING_GENERATION
                ),
                reason_codes=exclusion.reason_codes,
            )
        )

    for item in decision.alternatives:
        if item.action_id == selected_action_id:
            continue
        candidate = candidates_by_id.get(item.action_id)
        reasons = tuple(
            dict.fromkeys(
                item.binding_reason_codes
                + item.preference_reason_codes
                + item.restriction_reason_codes
                + (() if candidate is None else candidate.reason_codes)
            )
        )
        alternatives.append(
            AlternativeRationale(
                action_id=item.action_id,
                target_ref=(
                    None if candidate is None else candidate.target_ref
                ),
                disposition=_alternative_disposition(item.status),
                reason_codes=reasons,
            )
        )

    critical_unknowns = tuple(
        RationaleUnknown(
            domain=item.domain,
            question=item.question,
            decision_relevance=item.decision_relevance,
            fallback_policy=item.fallback_policy,
        )
        for item in envelope.high_relevance_unknowns
    )

    review_triggers = []
    if envelope.unresolved_dimensions:
        review_triggers.append(
            "REBUILD_CONTEXT_WHEN_UNRESOLVED_DIMENSIONS_CHANGE"
        )
    if envelope.high_relevance_unknowns:
        review_triggers.append(
            "REBUILD_CONTEXT_WHEN_CRITICAL_UNKNOWN_RESOLVES"
        )
    if decision.status == PlannerDecisionStatus.REVIEW_REQUIRED:
        review_triggers.append("REVIEW_COMPLETED")
    if decision.status == PlannerDecisionStatus.HUMAN_DECISION_REQUIRED:
        review_triggers.append("HUMAN_PRIORITY_OR_AUTHORITY_INPUT_AVAILABLE")

    supporting_policy_refs = tuple(
        _policy_ref(item.policy_key, item.policy_version)
        for item in policy_set.policies
    )

    return finalize_decision_rationale(
        rationale_id=rationale_id,
        decision_hash=decision.content_hash,
        context_hash=decision.context_hash,
        selected_action_id=selected_action_id,
        decision_status=decision.status.value,
        primary_reason_codes=tuple(primary_reasons),
        binding_constraint_codes=tuple(binding),
        supporting_policy_refs=supporting_policy_refs,
        alternatives=tuple(alternatives),
        critical_unknowns=critical_unknowns,
        unresolved_dimensions=tuple(
            item.value for item in envelope.unresolved_dimensions
        ),
        # P0.8 has no validated value/trade-off resolver yet. Empty is more
        # honest than inventing a trade-off after the decision.
        accepted_tradeoffs=(),
        review_triggers=tuple(review_triggers),
        rationale_version=RATIONALE_VERSION,
        created_at=created_at,
    )
