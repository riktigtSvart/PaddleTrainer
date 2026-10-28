"""Explicit immutable C11 revision → existing authoritative response capture."""
from uuid import UUID
from sqlalchemy import select
from app.models.entities import WorkoutSession
from app.services import feedback_learning as learning, session_feedback as feedback
from app.planning.application import register_athlete_setup as setup
from app.planning.application.calendar_workspace import require
from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.response_evidence import TrainingResponseKind, TrainingResponseTiming, TrainingResponseMeasurement
from app.planning.domain.response_evidence.source_capture import build_training_response_source_capture
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository

class LockedSessionFeedbackSource:
    def __init__(self, artifact_id, expected_hash):
        self.artifact_id, self.expected_hash = artifact_id, expected_hash

    async def lock_and_capture(self, session, *, athlete_id, response_source_id):
        await setup.lock_owner(session,athlete_id)
        record = await SqlAlchemyPlanningAuditRepository(session).get(artifact_kind=feedback.KIND,artifact_id=self.artifact_id)
        a = feedback.decode(record,athlete_id)
        require(a["content_hash"] == self.expected_hash and learning.source_id(a) == response_source_id,
            "CALENDAR_FEEDBACK_LEARNING_SOURCE_CHANGED")
        workout = (await session.execute(select(WorkoutSession).where(WorkoutSession.id == UUID(a["session_id"]),
            WorkoutSession.user_id == UUID(athlete_id)).with_for_update())).scalar_one_or_none()
        require(workout is not None,"CALENDAR_SESSION_NOT_FOUND")
        require(learning.has_numeric(a),"CALENDAR_FEEDBACK_NO_NUMERIC_ANSWERS")
        from datetime import datetime
        return build_training_response_source_capture(athlete_id=athlete_id,workout_session_id=a["session_id"],
            response_source_id=response_source_id,response_kind=TrainingResponseKind.SESSION_FEEDBACK,
            response_timing=TrainingResponseTiming(a["proposal"]["timing"].lower()),
            observed_at=datetime.fromisoformat(a["proposal"]["observed_at"]),available_at=learning.available(a,record),
            source_system=learning.SOURCE_SYSTEM,source_record_id=response_source_id,source_record_version=a["artifact_id"],
            source_content_hash=a["content_hash"],measurements=tuple(TrainingResponseMeasurement(
                metric_key=x["metric_key"],knowledge_status=KnowledgeStatus(x["knowledge_status"]),value=x["value"],unit=None)
                for x in learning.metrics(a)))
