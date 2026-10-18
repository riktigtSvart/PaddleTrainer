from datetime import datetime

from ..domain.context.models import AthletePlanningContextAggregate
from ..domain.decision.engine import (
    build_planner_input_envelope,
    generate_candidate_action_set,
    run_planner_decision,
)
from ..domain.decision.models import PlannerDecisionRequest
from ..domain.policy.builtins import (
    build_minimal_planning_policy_runtime,
    build_minimal_planning_policy_set,
)
from ..domain.rationale.builder import build_decision_rationale
from ..domain.replay.models import (
    PlannerRunRecord,
    ReplayMode,
    ReplayVerification,
)


def replay_planner_run(
    *,
    record: PlannerRunRecord,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    replay_created_at: datetime,
) -> ReplayVerification:
    if not record.verify_content_hash():
        raise ValueError("PlannerRunRecord hash does not verify.")
    if record.replay_mode != ReplayMode.DETERMINISTIC_EXACT:
        raise ValueError(
            "Exact replay requested for a non-deterministic/audit-only run."
        )
    if context.content_hash != record.context_hash:
        raise ValueError("Replay context hash does not match run record.")
    if request.context_hash != record.context_hash:
        raise ValueError("Replay request context hash mismatch.")

    policy_set = build_minimal_planning_policy_set()
    if policy_set.policy_set_version != record.policy_set_version:
        raise ValueError("Replay policy set version mismatch.")
    if policy_set.content_hash != record.policy_set_hash:
        raise ValueError("Replay policy set hash mismatch.")

    envelope = build_planner_input_envelope(
        context=context,
        request=request,
    )
    candidate_set = generate_candidate_action_set(
        envelope=envelope,
    )
    decision = run_planner_decision(
        decision_id=f"replay:{record.run_id}:decision",
        request=request,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        policies=build_minimal_planning_policy_runtime(),
        decision_time=record.decision_time,
        created_at=replay_created_at,
        engine_version=record.engine_version,
    )
    rationale = build_decision_rationale(
        rationale_id=f"replay:{record.run_id}:rationale",
        decision=decision,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        created_at=replay_created_at,
    )

    checks = dict(
        context_match=(context.content_hash == record.context_hash),
        envelope_match=(envelope.content_hash == record.envelope_hash),
        candidate_set_match=(
            candidate_set.content_hash == record.candidate_set_hash
        ),
        policy_set_match=(policy_set.content_hash == record.policy_set_hash),
        policy_execution_match=(
            decision.policy_execution.content_hash
            == record.policy_execution_hash
        ),
        decision_match=(decision.content_hash == record.decision_hash),
        rationale_match=(rationale.content_hash == record.rationale_hash),
    )
    return ReplayVerification(
        **checks,
        exact_replay_verified=all(checks.values()),
    )
