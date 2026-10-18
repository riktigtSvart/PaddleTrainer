from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    DecisionPurpose,
    DecisionRelevance,
    PlanningScope,
)
from app.planning.domain.common.refs import VersionRef
from app.planning.domain.context.models import (
    CriticalUnknown,
    CurrentStateContextProjection,
    EntryGateContextProjection,
    RuntimePlanningProjection,
    TrainingSpaceProjection,
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    WorkoutFamilySpaceItem,
    create_planning_context,
)
from app.planning.domain.decision.engine import build_planner_input_envelope
from app.planning.domain.decision.models import PlannerDecisionRequest
from app.planning.domain.entry_gate.models import EntryMode, GlobalEntryGate
from app.planning.domain.training_state.models import EvidenceCoverage, LoadAnchorStatus
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
                    entry_gate_status=FamilyEntryGateStatus.ELIGIBLE_WITH_CONSTRAINTS,
                    build_authorized_by_entry_gate=False,
                    dose_reduction_required=False,
                    reason_codes=("GLOBAL_OPEN_WITH_CONSTRAINTS",),
                ),
            ),
            unresolved_dimensions=(
                UnresolvedPlanningDimension.GOAL_PRIORITY,
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
        critical_unknowns=(
            CriticalUnknown(
                domain="CURRENT_LOAD_ANCHOR",
                question="Current anchor partial.",
                decision_relevance=DecisionRelevance.HIGH,
                fallback_policy="CONSERVATIVE_REANCHOR",
            ),
        ),
        runtime_projection=runtime,
    )


def _request(context, *, context_hash=None, requested_at=None):
    return PlannerDecisionRequest(
        request_id="request-1",
        context_id=context.context_id,
        context_hash=context_hash or context.content_hash,
        decision_purpose=context.decision_purpose,
        planning_scope=context.planning_scope,
        requested_at=requested_at or _dt(7),
    )


def test_context_projects_to_cut_down_input_envelope() -> None:
    context = _context()
    envelope = build_planner_input_envelope(
        context=context,
        request=_request(context),
    )
    assert envelope.context_hash == context.content_hash
    assert envelope.final_authorization is False
    assert len(envelope.family_items) == 1
    assert len(envelope.high_relevance_unknowns) == 1
    assert envelope.verify_content_hash()


def test_context_hash_mismatch_is_rejected() -> None:
    context = _context()
    with pytest.raises(ValueError, match="context_hash mismatch"):
        build_planner_input_envelope(
            context=context,
            request=_request(context, context_hash="x" * 64),
        )


def test_request_before_context_as_of_is_rejected() -> None:
    context = _context()
    with pytest.raises(ValueError, match="precede"):
        build_planner_input_envelope(
            context=context,
            request=_request(context, requested_at=_dt(4)),
        )
