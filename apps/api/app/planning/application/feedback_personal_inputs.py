"""C12 entry point: use selected C11 revisions in the existing P2.2 chain.

All durable revisions remain available for audit. A selection is recomputed at
an explicit information cutoff; older frozen revisions never increase support.
"""
from app.services import feedback_learning as learning, session_feedback as feedback
from app.planning.application.calendar_workspace import require
from app.planning.infrastructure.repositories.postgres_evidence import SqlAlchemyEvidenceRepository
from app.planning.application.build_training_dynamics_history import build_training_dynamics_history_from_evidence
from app.planning.application.assemble_personal_association_datasets import assemble_personal_association_datasets
from app.planning.domain.training_dynamics.history import TrainingDynamicsHistoryCoverage
from app.planning.domain.training_state.evidence import SESSION_FEEDBACK

class RevisionAwareFeedbackEvidenceRepository:
    def __init__(self, session):
        self.session = session
        self.repository = SqlAlchemyEvidenceRepository(session)

    async def list_available(self, *, athlete_id, information_cutoff_at):
        items = await self.repository.list_available(athlete_id=athlete_id,information_cutoff_at=information_cutoff_at)
        rows = await learning.records(self.session,athlete_id)
        selected = learning.select_revisions(rows,athlete_id,information_cutoff_at)
        all_ids = {learning.response_id(feedback.decode(r,athlete_id)) for r in rows}
        allowed = {learning.response_id(a) for a,_ in selected if learning.has_numeric(a)}
        # Do not silently treat orphaned C12 freezes as unrelated legacy data.
        from sqlalchemy import select
        from uuid import UUID
        from app.planning.domain.persistence.audit import AuditArtifactKind
        from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
        from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
        from app.planning.application.ingest_authoritative_training_response import restore_authoritative_training_response_audit_artifact
        frozen_rows = (await self.session.execute(select(PlanningAuditArtifactRow).where(
            PlanningAuditArtifactRow.athlete_id == UUID(athlete_id),
            PlanningAuditArtifactRow.artifact_kind == AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE.value,
            PlanningAuditArtifactRow.contract_json.contains(learning.SOURCE_SYSTEM)).limit(learning.ROW_LIMIT+1))).scalars().all()
        require(len(frozen_rows) <= learning.ROW_LIMIT, "CALENDAR_FEEDBACK_LEARNING_HISTORY_LIMIT")
        for row in frozen_rows:
            frozen = restore_authoritative_training_response_audit_artifact(SqlAlchemyPlanningAuditRepository._from_row(row))
            if frozen.source_system == learning.SOURCE_SYSTEM:
                require(frozen.artifact_id in all_ids, "CALENDAR_FEEDBACK_LEARNING_STORAGE_INVALID")
        replaced = {(a["session_id"], a["proposal"]["timing"].lower()) for a,_ in selected}
        def keep(item):
            if item.evidence_type != SESSION_FEEDBACK:
                return True
            if item.source_ref.source_record_id in all_ids:
                return item.source_ref.source_record_id in allowed
            return (item.payload.get("session_id"), item.payload.get("response_timing")) not in replaced
        return tuple(item for item in items if keep(item))

async def assemble_feedback_personal_inputs(*, session, athlete_id, history_id, window_start_at, as_of,
        information_cutoff_at, predictor_keys, created_at):
    require(window_start_at <= as_of <= created_at and information_cutoff_at <= created_at,
        "CALENDAR_FEEDBACK_LEARNING_CUTOFF_INVALID")
    items = await RevisionAwareFeedbackEvidenceRepository(session).list_available(
        athlete_id=athlete_id,information_cutoff_at=information_cutoff_at)
    history = build_training_dynamics_history_from_evidence(items=items,history_id=history_id,athlete_id=athlete_id,
        window_start_at=window_start_at,as_of=as_of,information_cutoff_at=information_cutoff_at,
        stimulus_coverage=TrainingDynamicsHistoryCoverage.UNKNOWN,response_coverage=TrainingDynamicsHistoryCoverage.PARTIAL,
        created_at=created_at)
    return assemble_personal_association_datasets(history=history,response_evidence_items=items,
        predictor_keys=predictor_keys,created_at=created_at)
