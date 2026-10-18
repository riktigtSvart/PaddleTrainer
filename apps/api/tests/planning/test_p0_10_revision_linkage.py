from datetime import datetime, timezone

from app.planning.application.plan_mutation import (
    apply_plan_mutation,
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
    PlanRevisionApplyStatus,
    create_workout_plan_contract_artifact,
)
from app.planning.domain.policy.builtins import build_minimal_planning_policy_set
from app.planning.domain.policy.models import finalize_policy_execution_record
from app.planning.domain.rationale.models import finalize_decision_rationale
from app.planning.infrastructure.workout_plan.in_memory import (
    InMemoryWorkoutPlanRevisionGateway,
)


def _dt(hour: int = 10):
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _decision_and_rationale():
    action = PlannerActionCandidate(
        action_id="action:family",
        action_type=PlannerActionType.SELECT_WORKOUT_FAMILY,
        target_ref="workout_family:TEST@v0.1",
        plan_mutation_authorized=True,
        parameters=(),
        reason_codes=("TEST",),
    )
    policy_set = build_minimal_planning_policy_set()
    execution = finalize_policy_execution_record(
        policy_set=policy_set,
        evaluations=(),
    )
    decision = finalize_planner_decision(
        decision_id="decision-1",
        request_id="request-1",
        context_id="context-1",
        context_hash="c" * 64,
        envelope_hash="e" * 64,
        candidate_set_hash="a" * 64,
        decision_time=_dt(),
        created_at=_dt(),
        status=PlannerDecisionStatus.DECIDED,
        selected_action=action,
        alternatives=(),
        policy_execution=execution,
        engine_version="planner_engine_v0.1",
    )
    rationale = finalize_decision_rationale(
        rationale_id="rationale-1",
        decision_hash=decision.content_hash,
        context_hash=decision.context_hash,
        selected_action_id=action.action_id,
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
    return decision, rationale


def test_apply_creates_auditable_revision_link() -> None:
    decision, rationale = _decision_and_rationale()
    artifact = create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-1",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"plan_id":"plan-1","blocks":[]}',
        stable_occurrence_ids=(),
    )
    instruction = build_plan_mutation_instruction(
        instruction_id="instruction-1",
        decision=decision,
        rationale=rationale,
        operation=PlanMutationOperation.ADD,
        plan_id="plan-1",
        expected_current_revision_id=None,
        new_plan_artifact=artifact,
        effective_from=_dt(),
        created_at=_dt(),
    )
    gateway = InMemoryWorkoutPlanRevisionGateway()

    result, link = apply_plan_mutation(
        link_id="link-1",
        instruction=instruction,
        gateway=gateway,
        applied_at=_dt(11),
    )

    assert result.status == PlanRevisionApplyStatus.CREATED
    assert link is not None
    assert link.decision_hash == decision.content_hash
    assert link.rationale_hash == rationale.content_hash
    assert link.context_hash == decision.context_hash
    assert link.plan_ref.revision_id == "rev-1"
    assert link.verify_content_hash()


def test_revision_link_semantic_hash_ignores_link_id_and_apply_time() -> None:
    decision, rationale = _decision_and_rationale()
    artifact = create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-1",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"blocks":[]}',
        stable_occurrence_ids=(),
    )

    # two independent gateways avoid idempotency affecting the linkage test
    links = []
    for suffix, hour in (("a", 11), ("b", 12)):
        instruction = build_plan_mutation_instruction(
            instruction_id=f"instruction-{suffix}",
            decision=decision,
            rationale=rationale,
            operation=PlanMutationOperation.ADD,
            plan_id="plan-1",
            expected_current_revision_id=None,
            new_plan_artifact=artifact,
            effective_from=_dt(),
            created_at=_dt(),
        )
        _, link = apply_plan_mutation(
            link_id=f"link-{suffix}",
            instruction=instruction,
            gateway=InMemoryWorkoutPlanRevisionGateway(),
            applied_at=_dt(hour),
        )
        links.append(link)

    assert links[0] is not None and links[1] is not None
    assert links[0].content_hash == links[1].content_hash
