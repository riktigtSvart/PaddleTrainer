from datetime import datetime, timezone

from app.planning.application.auditable_planner_run import (
    make_auditable_planner_run,
)
from app.planning.application.persist_audit import (
    persist_auditable_planner_run,
)
from app.planning.domain.common.enums import (
    DecisionPurpose,
    PlanningScope,
)
from app.planning.domain.common.refs import VersionRef
from app.planning.domain.context.models import (
    CurrentStateContextProjection,
    EntryGateContextProjection,
    RuntimePlanningProjection,
    TrainingSpaceProjection,
    TrainingSpaceStatus,
    UnresolvedPlanningDimension,
    create_planning_context,
)
from app.planning.domain.decision.models import PlannerDecisionRequest
from app.planning.domain.entry_gate.models import EntryMode, GlobalEntryGate
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactSaveStatus,
)
from app.planning.domain.training_state.models import (
    EvidenceCoverage,
    LoadAnchorStatus,
)
from app.planning.infrastructure.repositories.sqlite import (
    PlanningSqliteDatabase,
    SqlitePlanningAuditRepository,
    SqlitePlanningSnapshotRepository,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _context():
    runtime = RuntimePlanningProjection(
        current_state=CurrentStateContextProjection(
            current_training_state_hash="s" * 64,
            load_anchor_status=LoadAnchorStatus.PARTIAL_EXPOSURE,
            recent_source_coverage=EvidenceCoverage.PARTIAL,
            recent_observed_session_count=1,
            recent_known_duration_s=0,
            recent_complete_window_duration_s=None,
            latest_training_observed_at=_dt(5),
        ),
        entry_gate=EntryGateContextProjection(
            entry_gate_decision_hash="g" * 64,
            global_gate=GlobalEntryGate.OPEN_WITH_CONSTRAINTS,
            entry_mode=EntryMode.CONSERVATIVE_REANCHOR,
            reason_codes=("REANCHOR_REQUIRED",),
            stimulus_gates=(),
        ),
        workout_family_registry_version="workout_family_registry_v0.1",
        workout_family_registry_hash="w" * 64,
        training_space=TrainingSpaceProjection(
            projection_scope="ENTRY_GATE_FAMILY_SPACE_V0.1",
            status=TrainingSpaceStatus.ENTRY_GATE_CONSTRAINED,
            families=(),
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


def _run(context):
    request = PlannerDecisionRequest(
        request_id="request-1",
        context_id=context.context_id,
        context_hash=context.content_hash,
        decision_purpose=context.decision_purpose,
        planning_scope=context.planning_scope,
        requested_at=_dt(7),
    )
    return make_auditable_planner_run(
        context=context,
        request=request,
        run_id="run-1",
        decision_id="decision-1",
        rationale_id="rationale-1",
        decision_time=_dt(7),
        created_at=_dt(7),
    )


def test_auditable_run_persists_complete_chain(tmp_path) -> None:
    context = _context()
    run = _run(context)
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    snapshots = SqlitePlanningSnapshotRepository(database)
    audit = SqlitePlanningAuditRepository(database)

    result = persist_auditable_planner_run(
        context=context,
        run=run,
        snapshots=snapshots,
        audit=audit,
    )

    assert len(result.artifacts) == 6
    assert all(
        item.status == AuditArtifactSaveStatus.CREATED
        for item in result.artifacts
    )
    stored_run = audit.get(
        artifact_kind=AuditArtifactKind.PLANNER_RUN_RECORD,
        artifact_id="run-1",
    )
    stored_decision = audit.get(
        artifact_kind=AuditArtifactKind.PLANNER_DECISION,
        artifact_id="decision-1",
    )
    assert stored_run is not None
    assert stored_decision is not None
    assert stored_run.content_hash == run.run_record.content_hash
    assert stored_decision.content_hash == run.decision.content_hash


def test_auditable_run_persistence_is_idempotent(tmp_path) -> None:
    context = _context()
    run = _run(context)
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    snapshots = SqlitePlanningSnapshotRepository(database)
    audit = SqlitePlanningAuditRepository(database)

    persist_auditable_planner_run(
        context=context,
        run=run,
        snapshots=snapshots,
        audit=audit,
    )
    second = persist_auditable_planner_run(
        context=context,
        run=run,
        snapshots=snapshots,
        audit=audit,
    )

    assert all(
        item.status == AuditArtifactSaveStatus.ALREADY_PRESENT
        for item in second.artifacts
    )


def test_artifact_listing_is_kind_filterable(tmp_path) -> None:
    context = _context()
    run = _run(context)
    database = PlanningSqliteDatabase(tmp_path / "planning.sqlite3")
    audit = SqlitePlanningAuditRepository(database)
    persist_auditable_planner_run(
        context=context,
        run=run,
        snapshots=SqlitePlanningSnapshotRepository(database),
        audit=audit,
    )

    items = audit.list_for_athlete(
        athlete_id="athlete-1",
        artifact_kind=AuditArtifactKind.PLANNER_DECISION,
    )

    assert len(items) == 1
    assert items[0].artifact_id == "decision-1"
