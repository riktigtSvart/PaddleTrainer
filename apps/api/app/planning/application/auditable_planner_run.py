from dataclasses import dataclass
from datetime import datetime

from ..domain.context.models import AthletePlanningContextAggregate
from ..domain.decision.engine import (
    build_planner_input_envelope,
    generate_candidate_action_set,
    run_planner_decision,
)
from ..domain.decision.models import (
    CandidateActionSet,
    PlannerDecision,
    PlannerDecisionRequest,
    PlannerInputEnvelope,
)
from ..domain.policy.builtins import (
    build_minimal_planning_policy_runtime,
    build_minimal_planning_policy_set,
)
from ..domain.policy.models import PlanningPolicySet
from ..domain.rationale.builder import (
    RATIONALE_VERSION,
    build_decision_rationale,
)
from ..domain.rationale.models import DecisionRationale
from ..domain.replay.models import (
    PlannerRunRecord,
    ReplayMode,
    finalize_planner_run_record,
)


CANDIDATE_GENERATION_VERSION = "candidate_generation_v0.1"


@dataclass(frozen=True)
class AuditablePlannerRun:
    envelope: PlannerInputEnvelope
    candidate_set: CandidateActionSet
    policy_set: PlanningPolicySet
    decision: PlannerDecision
    rationale: DecisionRationale
    run_record: PlannerRunRecord


def make_auditable_planner_run(
    *,
    context: AthletePlanningContextAggregate,
    request: PlannerDecisionRequest,
    run_id: str,
    decision_id: str,
    rationale_id: str,
    decision_time: datetime,
    created_at: datetime,
    engine_version: str = "planner_engine_v0.1",
) -> AuditablePlannerRun:
    envelope = build_planner_input_envelope(
        context=context,
        request=request,
    )
    candidate_set = generate_candidate_action_set(
        envelope=envelope,
    )
    policy_set = build_minimal_planning_policy_set()
    policies = build_minimal_planning_policy_runtime()

    decision = run_planner_decision(
        decision_id=decision_id,
        request=request,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        policies=policies,
        decision_time=decision_time,
        created_at=created_at,
        engine_version=engine_version,
    )
    rationale = build_decision_rationale(
        rationale_id=rationale_id,
        decision=decision,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        created_at=created_at,
    )
    run_record = finalize_planner_run_record(
        run_id=run_id,
        context_hash=context.content_hash,
        envelope_hash=envelope.content_hash,
        candidate_set_hash=candidate_set.content_hash,
        policy_set_hash=policy_set.content_hash,
        policy_execution_hash=decision.policy_execution.content_hash,
        decision_hash=decision.content_hash,
        rationale_hash=rationale.content_hash,
        engine_version=engine_version,
        policy_set_version=policy_set.policy_set_version,
        candidate_generation_version=CANDIDATE_GENERATION_VERSION,
        rationale_version=RATIONALE_VERSION,
        replay_mode=ReplayMode.DETERMINISTIC_EXACT,
        decision_time=decision_time,
        created_at=created_at,
    )
    return AuditablePlannerRun(
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        decision=decision,
        rationale=rationale,
        run_record=run_record,
    )
