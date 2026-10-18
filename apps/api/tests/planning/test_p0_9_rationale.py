from datetime import datetime, timezone

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
    PlannerDecisionRequest,
    finalize_planner_input_envelope,
)
from app.planning.domain.policy.builtins import (
    build_minimal_planning_policy_runtime,
    build_minimal_planning_policy_set,
)
from app.planning.domain.rationale.builder import build_decision_rationale
from app.planning.domain.rationale.models import AlternativeDisposition
from app.planning.domain.workout_family.models import FamilyEntryGateStatus


def _dt(hour: int):
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _run(*, high_unknown=False):
    envelope = finalize_planner_input_envelope(
        context_id="context-1",
        context_hash="c" * 64,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        planning_scope=PlanningScope.MICROCYCLE,
        training_space_status=TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED,
        family_items=(
            EnvelopeFamilyItem(
                family_key="KAYAK_EASY_TECHNICAL",
                family_version="v0.1",
                entry_gate_status=(
                    FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS.value
                ),
                build_authorized_by_entry_gate=False,
                dose_reduction_required=False,
                reason_codes=("GLOBAL_OPEN_WITH_CONSTRAINTS",),
            ),
        ),
        unresolved_dimensions=(
            UnresolvedPlanningDimension.PLANNING_AUTHORITY,
        ),
        final_authorization=False,
        high_relevance_unknowns=(
            (
                EnvelopeCriticalUnknown(
                    domain="CURRENT_LOAD_ANCHOR",
                    question="Current load anchor incomplete.",
                    decision_relevance=DecisionRelevance.HIGH,
                    fallback_policy="CONSERVATIVE_REANCHOR",
                ),
            )
            if high_unknown
            else ()
        ),
    )
    request = PlannerDecisionRequest(
        request_id="request-1",
        context_id=envelope.context_id,
        context_hash=envelope.context_hash,
        decision_purpose=envelope.decision_purpose,
        planning_scope=envelope.planning_scope,
        requested_at=_dt(7),
    )
    candidate_set = generate_candidate_action_set(envelope=envelope)
    policy_set = build_minimal_planning_policy_set()
    decision = run_planner_decision(
        decision_id="decision-1",
        request=request,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        policies=build_minimal_planning_policy_runtime(),
        decision_time=_dt(7),
        created_at=_dt(7),
        engine_version="planner_engine_v0.1",
    )
    rationale = build_decision_rationale(
        rationale_id="rationale-1",
        decision=decision,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        created_at=_dt(7),
    )
    return envelope, candidate_set, policy_set, decision, rationale


def test_rationale_hash_verifies() -> None:
    *_, rationale = _run()
    assert rationale.verify_content_hash()


def test_rationale_records_authorization_binding_reason() -> None:
    *_, rationale = _run()
    assert "FINAL_AUTHORIZATION_NOT_RESOLVED" in (
        rationale.binding_constraint_codes
    )


def test_generation_exclusion_is_retained_in_rationale() -> None:
    *_, rationale = _run()
    exclusions = [
        item for item in rationale.alternatives
        if item.disposition
        == AlternativeDisposition.EXCLUDED_DURING_GENERATION
    ]
    assert len(exclusions) == 1
    assert exclusions[0].target_ref == (
        "workout_family:KAYAK_EASY_TECHNICAL@v0.1"
    )


def test_high_unknown_is_retained_without_becoming_diagnosis() -> None:
    *_, rationale = _run(high_unknown=True)
    assert len(rationale.critical_unknowns) == 1
    assert rationale.critical_unknowns[0].domain == "CURRENT_LOAD_ANCHOR"
    assert (
        "REBUILD_CONTEXT_WHEN_CRITICAL_UNKNOWN_RESOLVES"
        in rationale.review_triggers
    )


def test_rationale_contains_no_post_outcome_fields() -> None:
    *_, rationale = _run()
    assert not hasattr(rationale, "observed_outcome")
    assert not hasattr(rationale, "outcome_quality")
    assert rationale.accepted_tradeoffs == ()


def test_rationale_semantic_hash_ignores_id_and_created_at() -> None:
    envelope, candidate_set, policy_set, decision, first = _run()
    second = build_decision_rationale(
        rationale_id="rationale-2",
        decision=decision,
        envelope=envelope,
        candidate_set=candidate_set,
        policy_set=policy_set,
        created_at=_dt(8),
    )
    assert first.content_hash == second.content_hash
