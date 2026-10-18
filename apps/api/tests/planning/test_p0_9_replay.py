from datetime import datetime, timezone
from dataclasses import replace

import pytest

from app.planning.application.auditable_planner_run import (
    make_auditable_planner_run,
)
from app.planning.application.replay_planner_run import replay_planner_run
from app.planning.domain.common.enums import DecisionPurpose, PlanningScope
from app.planning.domain.common.refs import VersionRef
from app.planning.domain.context.models import (
    CurrentStateContextProjection,
    EntryGateContextProjection,
    RuntimePlanningProjection,
    TrainingSpaceProjection,
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    WorkoutFamilySpaceItem,
    create_planning_context,
)
from app.planning.domain.decision.models import PlannerDecisionRequest
from app.planning.domain.entry_gate.models import EntryMode, GlobalEntryGate
from app.planning.domain.replay.models import ReplayMode
from app.planning.domain.training_state.models import (
    EvidenceCoverage,
    LoadAnchorStatus,
)
from app.planning.domain.workout_family.models import FamilyEntryGateStatus


def _dt(hour: int):
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _context():
    runtime = RuntimePlanningProjection(
        current_state=CurrentStateContextProjection(
            current_training_state_hash="s" * 64,
            load_anchor_status=LoadAnchorStatus.PARTIAL_EXPOSURE,
            recent_source_coverage=EvidenceCoverage.PARTIAL,
            recent_observed_session_count=1,
            recent_known_duration_s=3600,
            recent_complete_window_duration_s=None,
            latest_training_observed_at=_dt(5),
        ),
        entry_gate=EntryGateContextProjection(
            entry_gate_decision_hash="g" * 64,
            global_gate=GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            entry_mode=EntryMode.CONSERVATIVE_REANCHOR,
            reason_codes=("RECENT_EXPOSURE_STALE",),
            stimulus_gates=(),
        ),
        workout_family_registry_version="workout_family_registry_v0.1",
        workout_family_registry_hash="w" * 64,
        training_space=TrainingSpaceProjection(
            projection_scope="ENTRY_GATE_FAMILY_SPACE_V0.1",
            status=TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED,
            families=(
                WorkoutFamilySpaceItem(
                    family_key="KAYAK_EASY_TECHNICAL",
                    family_version="v0.1",
                    modality_key="KAYAK",
                    sport_key="KAYAK",
                    entry_gate_status=(
                        FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS
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
        ),
    )
    return create_planning_context(
        context_id="context-1",
        athlete_id="athlete-1",
        schema_version="apc_v0.1",
        as_of=_dt(6),
        information_cutoff_at=_dt(5),
        created_at=_dt(6),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        source_snapshot_refs=(),
        engine_version=VersionRef("engine", "v0.1"),
        rules_version=VersionRef("rules", "v0.1"),
        evidence_pack_version=VersionRef("evidence", "v0.1"),
        runtime_projection=runtime,
    )


def _request(context):
    return PlannerDecisionRequest(
        request_id="request-original",
        context_id=context.context_id,
        context_hash=context.content_hash,
        decision_purpose=context.decision_purpose,
        planning_scope=context.planning_scope,
        requested_at=_dt(7),
    )


def _run():
    context = _context()
    request = _request(context)
    run = make_auditable_planner_run(
        context=context,
        request=request,
        run_id="run-1",
        decision_id="decision-original",
        rationale_id="rationale-original",
        decision_time=_dt(7),
        created_at=_dt(7),
    )
    return context, request, run


def test_run_record_links_exact_contract_hashes() -> None:
    context, _, run = _run()
    record = run.run_record
    assert record.context_hash == context.content_hash
    assert record.envelope_hash == run.envelope.content_hash
    assert record.candidate_set_hash == run.candidate_set.content_hash
    assert record.policy_set_hash == run.policy_set.content_hash
    assert record.policy_execution_hash == (
        run.decision.policy_execution.content_hash
    )
    assert record.decision_hash == run.decision.content_hash
    assert record.rationale_hash == run.rationale.content_hash
    assert record.verify_content_hash()


def test_current_engine_declares_exact_deterministic_replay() -> None:
    *_, run = _run()
    assert run.run_record.replay_mode == ReplayMode.DETERMINISTIC_EXACT


def test_exact_replay_verifies_all_semantic_outputs() -> None:
    context, request, run = _run()
    verification = replay_planner_run(
        record=run.run_record,
        context=context,
        request=request,
        replay_created_at=_dt(9),
    )
    assert verification.exact_replay_verified is True
    assert verification.decision_match is True
    assert verification.rationale_match is True


def test_replay_can_use_different_nonsemantic_request_id() -> None:
    context, request, run = _run()
    replay_request = replace(request, request_id="request-replay")
    verification = replay_planner_run(
        record=run.run_record,
        context=context,
        request=replay_request,
        replay_created_at=_dt(9),
    )
    assert verification.exact_replay_verified is True


def test_replay_rejects_wrong_context() -> None:
    context, request, run = _run()
    tampered = replace(context, content_hash="0" * 64)
    with pytest.raises(ValueError, match="context hash"):
        replay_planner_run(
            record=run.run_record,
            context=tampered,
            request=request,
            replay_created_at=_dt(9),
        )


def test_replay_rejects_tampered_run_record() -> None:
    context, request, run = _run()
    tampered = replace(run.run_record, content_hash="0" * 64)
    with pytest.raises(ValueError, match="RunRecord hash"):
        replay_planner_run(
            record=tampered,
            context=context,
            request=request,
            replay_created_at=_dt(9),
        )
