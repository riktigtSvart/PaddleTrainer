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


def make_minimal_planner_decision(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    decision_id: str,
    decision_time: datetime,
    created_at: datetime,
    engine_version: str = "planner_engine_v0.1",
):
    """P0.8 orchestration only. No plan mutation occurs here."""
    envelope = build_planner_input_envelope(
        context=context,
        request=request,
    )
    candidates = generate_candidate_action_set(envelope=envelope)
    return run_planner_decision(
        decision_id=decision_id,
        request=request,
        envelope=envelope,
        candidate_set=candidates,
        policy_set=build_minimal_planning_policy_set(),
        policies=build_minimal_planning_policy_runtime(),
        decision_time=decision_time,
        created_at=created_at,
        engine_version=engine_version,
    )
