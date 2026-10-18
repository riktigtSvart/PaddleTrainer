from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    DecisionPurpose,
    DecisionRelevance,
    PlanningScope,
)
from app.planning.domain.context.models import (
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
)
from app.planning.domain.decision.engine import (
    generate_candidate_action_set,
    run_planner_decision,
)
from app.planning.domain.decision.models import (
    EnvelopeCriticalUnknown,
    EnvelopeFamilyItem,
    PlannerActionType,
    PlannerDecisionRequest,
    PlannerDecisionStatus,
    finalize_planner_input_envelope,
)
from app.planning.domain.policy.builtins import (
    build_minimal_planning_policy_runtime,
    build_minimal_planning_policy_set,
)
from app.planning.domain.workout_family.models import FamilyEntryGateStatus


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _envelope(
    *,
    final_authorization: bool,
    family_count: int = 1,
    status: TrainingSpaceStatus = TrainingSpaceStatus.ENTRY_GATE_OPEN,
    high_unknown: bool = False,
    family_status: FamilyEntryGateStatus = FamilyEntryGateStatus.ELIGIBLE,
):
    return finalize_planner_input_envelope(
        context_id="context-1",
        context_hash="c" * 64,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        planning_scope=PlanningScope.MICROCYCLE,
        training_space_status=status,
        family_items=tuple(
            EnvelopeFamilyItem(
                family_key=f"FAMILY_{index}",
                family_version="v0.1",
                entry_gate_status=family_status.value,
                build_authorized_by_entry_gate=True,
                dose_reduction_required=False,
                reason_codes=("ENTRY_GATE_ELIGIBLE",),
            )
            for index in range(family_count)
        ),
        unresolved_dimensions=(
            ()
            if final_authorization
            else (UnresolvedPlanningDimension.PLANNING_AUTHORITY,)
        ),
        final_authorization=final_authorization,
        high_relevance_unknowns=(
            (
                EnvelopeCriticalUnknown(
                    domain="CURRENT_LOAD_ANCHOR",
                    question="Current anchor uncertain.",
                    decision_relevance=DecisionRelevance.HIGH,
                    fallback_policy="CONSERVATIVE_REANCHOR",
                ),
            )
            if high_unknown
            else ()
        ),
    )


def _run(envelope):
    request = PlannerDecisionRequest(
        request_id="request-1",
        context_id=envelope.context_id,
        context_hash=envelope.context_hash,
        decision_purpose=envelope.decision_purpose,
        planning_scope=envelope.planning_scope,
        requested_at=_dt(7),
    )
    candidates = generate_candidate_action_set(envelope=envelope)
    return run_planner_decision(
        decision_id="decision-1",
        request=request,
        envelope=envelope,
        candidate_set=candidates,
        policy_set=build_minimal_planning_policy_set(),
        policies=build_minimal_planning_policy_runtime(),
        decision_time=_dt(7),
        created_at=_dt(7),
        engine_version="planner_engine_v0.1",
    )


def test_policy_set_is_deterministic_and_hash_verifies() -> None:
    first = build_minimal_planning_policy_set()
    second = build_minimal_planning_policy_set()
    assert first.content_hash == second.content_hash
    assert first.verify_content_hash()


def test_unresolved_authorization_excludes_family_candidates_early() -> None:
    envelope = _envelope(final_authorization=False)
    candidates = generate_candidate_action_set(envelope=envelope)

    assert all(
        candidate.action_type != PlannerActionType.SELECT_WORKOUT_FAMILY
        for candidate in candidates.candidates
    )
    assert len(candidates.excluded_during_generation) == 1
    assert candidates.coverage_status.value == "limited"


def test_finally_authorized_eligible_family_is_generated() -> None:
    candidates = generate_candidate_action_set(
        envelope=_envelope(final_authorization=True)
    )
    assert any(
        item.action_type == PlannerActionType.SELECT_WORKOUT_FAMILY
        for item in candidates.candidates
    )


def test_not_eligible_family_is_excluded_during_generation() -> None:
    candidates = generate_candidate_action_set(
        envelope=_envelope(
            final_authorization=True,
            family_status=FamilyEntryGateStatus.NOT_ELIGIBLE,
        )
    )
    assert all(
        item.action_type != PlannerActionType.SELECT_WORKOUT_FAMILY
        for item in candidates.candidates
    )
    assert "not_eligible" in candidates.excluded_during_generation[0].reason_codes[0]


def test_high_unknown_adds_information_candidate() -> None:
    candidates = generate_candidate_action_set(
        envelope=_envelope(
            final_authorization=False,
            high_unknown=True,
        )
    )
    assert any(
        item.action_type == PlannerActionType.REQUEST_INFORMATION
        for item in candidates.candidates
    )


def test_unresolved_authorization_requires_defer() -> None:
    decision = _run(_envelope(final_authorization=False))
    assert decision.status == PlannerDecisionStatus.DEFERRED_PENDING_CONTEXT
    assert decision.selected_action is not None
    assert decision.selected_action.action_type == PlannerActionType.DEFER
    assert decision.verify_content_hash()
    assert decision.policy_execution.verify_content_hash()


def test_blocked_training_space_returns_blocked_decision() -> None:
    decision = _run(
        _envelope(
            final_authorization=False,
            status=TrainingSpaceStatus.ENTRY_GATE_BLOCKED,
        )
    )
    assert decision.status == PlannerDecisionStatus.BLOCKED_BY_CONSTRAINT


def test_review_required_selects_review_action() -> None:
    decision = _run(
        _envelope(
            final_authorization=True,
            family_count=0,
            status=TrainingSpaceStatus.ENTRY_GATE_REVIEW_REQUIRED,
        )
    )
    assert decision.status == PlannerDecisionStatus.REVIEW_REQUIRED
    assert decision.selected_action is not None
    assert decision.selected_action.action_type == PlannerActionType.REQUEST_REVIEW


def test_multiple_authorized_family_options_are_not_arbitrarily_ranked() -> None:
    decision = _run(
        _envelope(final_authorization=True, family_count=2)
    )
    assert decision.status == PlannerDecisionStatus.HUMAN_DECISION_REQUIRED
    assert decision.selected_action is None


def test_one_family_plus_defer_is_still_not_arbitrarily_ranked() -> None:
    decision = _run(
        _envelope(final_authorization=True, family_count=1)
    )
    assert decision.status == PlannerDecisionStatus.HUMAN_DECISION_REQUIRED
    assert decision.selected_action is None


def test_no_scalar_utility_score_exists() -> None:
    decision = _run(_envelope(final_authorization=False))
    assert not hasattr(decision, "utility_score")
    assert not hasattr(decision.policy_execution, "utility_score")


def test_policy_runtime_exactly_matches_policy_set() -> None:
    runtime = build_minimal_planning_policy_runtime()
    policy_set = build_minimal_planning_policy_set()
    assert {
        (p.definition.policy_key, p.definition.policy_version)
        for p in runtime
    } == {
        (p.policy_key, p.policy_version)
        for p in policy_set.policies
    }


def test_tampered_candidate_set_is_rejected() -> None:
    from dataclasses import replace

    envelope = _envelope(final_authorization=False)
    candidates = generate_candidate_action_set(envelope=envelope)
    request = PlannerDecisionRequest(
        request_id="request-1",
        context_id=envelope.context_id,
        context_hash=envelope.context_hash,
        decision_purpose=envelope.decision_purpose,
        planning_scope=envelope.planning_scope,
        requested_at=_dt(7),
    )
    tampered = replace(candidates, content_hash="0" * 64)

    with pytest.raises(ValueError, match="CandidateActionSet hash"):
        run_planner_decision(
            decision_id="decision-1",
            request=request,
            envelope=envelope,
            candidate_set=tampered,
            policy_set=build_minimal_planning_policy_set(),
            policies=build_minimal_planning_policy_runtime(),
            decision_time=_dt(7),
            created_at=_dt(7),
            engine_version="planner_engine_v0.1",
        )
