from datetime import datetime, timezone

import pytest

from app.planning.application.plan_mutation import (
    PlanMutationNotAuthorized,
    build_plan_mutation_instruction,
)
from app.planning.domain.decision.models import (
    PlannerActionCandidate,
    PlannerActionType,
    PlannerDecisionStatus,
    finalize_planner_decision,
)
from app.planning.domain.plan_revision.models import (
    PlanMutationOperation,
    create_workout_plan_contract_artifact,
)
from app.planning.domain.policy.builtins import (
    build_minimal_planning_policy_set,
)
from app.planning.domain.policy.models import (
    finalize_policy_execution_record,
)
from app.planning.domain.rationale.models import (
    finalize_decision_rationale,
)


def _dt(hour: int = 10):
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _decision(*, status, action):
    policy_set = build_minimal_planning_policy_set()
    execution = finalize_policy_execution_record(
        policy_set=policy_set,
        evaluations=(),
    )
    return finalize_planner_decision(
        decision_id="decision-1",
        request_id="request-1",
        context_id="context-1",
        context_hash="c" * 64,
        envelope_hash="e" * 64,
        candidate_set_hash="a" * 64,
        decision_time=_dt(),
        created_at=_dt(),
        status=status,
        selected_action=action,
        alternatives=(),
        policy_execution=execution,
        engine_version="planner_engine_v0.1",
    )


def _rationale(decision):
    return finalize_decision_rationale(
        rationale_id="rationale-1",
        decision_hash=decision.content_hash,
        context_hash=decision.context_hash,
        selected_action_id=(
            decision.selected_action.action_id
            if decision.selected_action
            else None
        ),
        decision_status=decision.status.value,
        primary_reason_codes=("TEST",),
        binding_constraint_codes=(),
        supporting_policy_refs=(),
        alternatives=(),
        critical_unknowns=(),
        unresolved_dimensions=(),
        accepted_tradeoffs=(),
        review_triggers=(),
        rationale_version="rationale_v0.1",
        created_at=_dt(),
    )


def _artifact():
    return create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-1",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"blocks":[]}',
        stable_occurrence_ids=(),
    )


def test_deferred_decision_cannot_mutate_plan() -> None:
    action = PlannerActionCandidate(
        action_id="action:defer",
        action_type=PlannerActionType.DEFER,
        target_ref=None,
        plan_mutation_authorized=False,
        parameters=(),
        reason_codes=(),
    )
    decision = _decision(
        status=PlannerDecisionStatus.DEFERRED_PENDING_CONTEXT,
        action=action,
    )

    with pytest.raises(PlanMutationNotAuthorized, match="status"):
        build_plan_mutation_instruction(
            instruction_id="i-1",
            decision=decision,
            rationale=_rationale(decision),
            operation=PlanMutationOperation.ADD,
            plan_id="plan-1",
            expected_current_revision_id=None,
            new_plan_artifact=_artifact(),
            effective_from=_dt(),
            created_at=_dt(),
        )


def test_selected_action_must_explicitly_authorize_mutation() -> None:
    action = PlannerActionCandidate(
        action_id="action:family",
        action_type=PlannerActionType.SELECT_WORKOUT_FAMILY,
        target_ref="workout_family:TEST@v0.1",
        plan_mutation_authorized=False,
        parameters=(),
        reason_codes=(),
    )
    decision = _decision(
        status=PlannerDecisionStatus.DECIDED,
        action=action,
    )

    with pytest.raises(PlanMutationNotAuthorized, match="not authorized"):
        build_plan_mutation_instruction(
            instruction_id="i-1",
            decision=decision,
            rationale=_rationale(decision),
            operation=PlanMutationOperation.ADD,
            plan_id="plan-1",
            expected_current_revision_id=None,
            new_plan_artifact=_artifact(),
            effective_from=_dt(),
            created_at=_dt(),
        )


def test_authorized_family_decision_creates_instruction() -> None:
    action = PlannerActionCandidate(
        action_id="action:family",
        action_type=PlannerActionType.SELECT_WORKOUT_FAMILY,
        target_ref="workout_family:TEST@v0.1",
        plan_mutation_authorized=True,
        parameters=(),
        reason_codes=(),
    )
    decision = _decision(
        status=PlannerDecisionStatus.DECIDED,
        action=action,
    )
    rationale = _rationale(decision)

    instruction = build_plan_mutation_instruction(
        instruction_id="i-1",
        decision=decision,
        rationale=rationale,
        operation=PlanMutationOperation.ADD,
        plan_id="plan-1",
        expected_current_revision_id=None,
        new_plan_artifact=_artifact(),
        effective_from=_dt(),
        created_at=_dt(),
    )

    assert instruction.decision_hash == decision.content_hash
    assert instruction.rationale_hash == rationale.content_hash
    assert instruction.selected_action_id == "action:family"
    assert instruction.verify_content_hash()
