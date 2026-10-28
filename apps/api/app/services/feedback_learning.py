"""Revision- and information-cutoff-aware C11 self-report selection.

Select the latest *known* revision before filtering its observation date. Never
resurrect an older score when a correction removes a score or moves its time.
The audit history remains untouched; RPE is subjective, not a measured load.
"""
from datetime import UTC, datetime
from uuid import UUID, NAMESPACE_URL, uuid5
from sqlalchemy import select
from app.planning.application.calendar_workspace import require, digest
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.services import session_feedback as feedback

SCHEMA = "feedback-learning-v0.1"
SOURCE_SYSTEM = "current_app_revisioned_session_feedback"
ROW_LIMIT = 20000
METRICS = {"rpe":"self_reported_rpe_score", "fatigue":"self_reported_fatigue_score",
    "soreness":"self_reported_soreness_score", "recovery":"self_reported_recovery_score", "energy":"self_reported_energy_score"}

def _now():
    return datetime.now(UTC)

def source_id(a):
    return str(uuid5(NAMESPACE_URL, SOURCE_SYSTEM + ":" + a["athlete_id"] + ":" + a["artifact_id"]))

def response_id(a):
    from app.planning.application.ingest_authoritative_training_response import authoritative_training_response_artifact_id
    return authoritative_training_response_artifact_id(source_id(a))

def available(a, record):
    require(datetime.fromisoformat(a["submitted_at"]) >= datetime.fromisoformat(a["proposal"]["observed_at"]),
        "CALENDAR_FEEDBACK_STORAGE_INVALID")
    return max(datetime.fromisoformat(a["proposal"]["observed_at"]),
        datetime.fromisoformat(a["submitted_at"]), aware(record.persisted_at))

async def records(session, owner, session_id=None):
    query = select(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.athlete_id == UUID(owner),
        PlanningAuditArtifactRow.artifact_kind == feedback.KIND.value)
    if session_id is not None:
        query = query.where(PlanningAuditArtifactRow.contract_json.contains('"session_id":"' + str(UUID(session_id)) + '"'))
    rows = (await session.execute(query.limit(ROW_LIMIT + 1))).scalars().all()
    require(len(rows) <= ROW_LIMIT, "CALENDAR_FEEDBACK_LEARNING_HISTORY_LIMIT")
    return tuple(SqlAlchemyPlanningAuditRepository._from_row(row) for row in rows)

def select_revisions(rows, owner, cutoff):
    require(cutoff.tzinfo is not None and cutoff.utcoffset() is not None, "CALENDAR_FEEDBACK_LEARNING_CUTOFF_INVALID")
    groups = {}
    for record in rows:
        a = feedback.decode(record, owner)
        groups.setdefault((a["session_id"], a["proposal"]["timing"]), []).append((a, record))
    chosen = []
    for key, chain in sorted(groups.items()):
        chain.sort(key=lambda pair:pair[0]["revision"])
        previous = None
        for i,(a,record) in enumerate(chain,1):
            require(a["revision"] == i and a["previous_hash"] == previous, "CALENDAR_FEEDBACK_STORAGE_INVALID")
            previous = a["content_hash"]
        known = [pair for pair in chain if available(*pair) <= cutoff]
        if known:
            chosen.append(known[-1])
    return tuple(chosen)

def metrics(a):
    return [{"metric_key":metric, "knowledge_status":"known" if a["proposal"][field] is not None else "unknown",
        "value":a["proposal"][field], "unit":None} for field,metric in METRICS.items()]

def has_numeric(a):
    return any(a["proposal"][field] is not None for field in METRICS)

def observation(a, record):
    p = a["proposal"]
    observed = datetime.fromisoformat(p["observed_at"])
    submitted = datetime.fromisoformat(a["submitted_at"])
    known_at = available(a,record)
    return {"id":source_id(a), "workout_session_id":a["session_id"], "response_timing":p["timing"],
        "recorded_at":observed, "available_at":known_at, "submitted_at":submitted,
        "fatigue_score":p["fatigue"], "soreness_score":p["soreness"], "recovery_score":p["recovery"],
        "energy_score":p["energy"], "rpe_score":p["rpe"], "performance_metric":None, "performance_delta_percent":None,
        "extra_data":{"source_system":SOURCE_SYSTEM, "feedback_artifact_id":a["artifact_id"],
            "feedback_content_hash":a["content_hash"], "feedback_revision":a["revision"],
            "reporting_delay_seconds":int((submitted-observed).total_seconds()), "measurements":metrics(a)}}

async def daily_selection(session, owner, start, end, cutoff):
    selected = select_revisions(await records(session,owner),owner,cutoff)
    from app.models.entities import WorkoutSession
    owned_ids = set((await session.execute(select(WorkoutSession.id).where(WorkoutSession.user_id == UUID(owner)))).scalars().all())
    selected = [(a,r) for a,r in selected if UUID(a["session_id"]) in owned_ids]
    observations = [observation(a,record) for a,record in selected
        if start <= datetime.fromisoformat(a["proposal"]["observed_at"]) < end]
    return observations, {(a["session_id"], a["proposal"]["timing"]) for a,_ in selected}

async def daily_observations(session, owner, start, end, cutoff):
    return (await daily_selection(session,owner,start,end,cutoff))[0]

async def context(*, owner, session_id, session, cutoff=None):
    from app.planning.domain.persistence.audit import AuditArtifactKind
    from app.planning.application.ingest_authoritative_executed_training import (
        authoritative_executed_training_artifact_id, restore_authoritative_executed_training_audit_artifact)
    from app.planning.application.ingest_authoritative_training_response import restore_authoritative_training_response_audit_artifact
    repo = SqlAlchemyPlanningAuditRepository(session)
    try:
        await feedback.owned(session,owner,session_id)
        now = _now()
        cutoff = cutoff or now
        require(cutoff.tzinfo is not None and cutoff <= now, "CALENDAR_FEEDBACK_LEARNING_CUTOFF_INVALID")
        selected = select_revisions(await records(session,owner,session_id),owner,cutoff)
        executed_record = await repo.get(artifact_kind=AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING,
            artifact_id=authoritative_executed_training_artifact_id(session_id))
        execution = restore_authoritative_executed_training_audit_artifact(executed_record) if executed_record else None
        if execution:
            require(execution.athlete_id == owner and execution.workout_session_id == session_id,
                "CALENDAR_FEEDBACK_LEARNING_STORAGE_INVALID")
        items = []
        for a,record in selected:
            obs = observation(a,record)
            frozen_record = await repo.get(artifact_kind=AuditArtifactKind.AUTHORITATIVE_TRAINING_RESPONSE, artifact_id=response_id(a))
            frozen = restore_authoritative_training_response_audit_artifact(frozen_record) if frozen_record else None
            if frozen:
                require(frozen.athlete_id == owner and frozen.workout_session_id == session_id
                    and frozen.source_system == SOURCE_SYSTEM and frozen.source_record_version == a["artifact_id"]
                    and frozen.source_content_hash == a["content_hash"], "CALENDAR_FEEDBACK_LEARNING_STORAGE_INVALID")
            projection_ready = False
            if frozen:
                from app.planning.application.project_authoritative_training_response import project_authoritative_training_response_evidence
                from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningEvidenceItemRow
                from app.planning.infrastructure.repositories.postgres_evidence import SqlAlchemyEvidenceRepository
                require(execution is not None and frozen.executed_training_evidence_id == execution.artifact_id
                    and frozen.executed_training_evidence_hash == execution.content_hash, "CALENDAR_FEEDBACK_LEARNING_STORAGE_INVALID")
                expected = project_authoritative_training_response_evidence(frozen,created_at=max(now,frozen.created_at))
                row = (await session.execute(select(PlanningEvidenceItemRow).where(PlanningEvidenceItemRow.evidence_id == expected.evidence_id,
                    PlanningEvidenceItemRow.athlete_id == UUID(owner)))).scalar_one_or_none()
                if row:
                    restored = SqlAlchemyEvidenceRepository._from_row(row)
                    require(restored.content_hash == expected.content_hash, "CALENDAR_FEEDBACK_LEARNING_STORAGE_INVALID")
                    projection_ready = restored.available_at <= cutoff
            state = "no_numeric_answers" if not has_numeric(a) else "waiting_for_execution" if execution is None or execution.created_at > cutoff else "ready" if frozen and frozen.created_at <= cutoff and projection_ready else "ready_to_freeze"
            items.append({"timing":a["proposal"]["timing"], "revision":a["revision"], "state":state,
                "feedback_reference":{"artifact_id":a["artifact_id"],"content_hash":a["content_hash"]},
                "response_source_id":source_id(a), "observed_at":obs["recorded_at"].isoformat(),
                "submitted_at":obs["submitted_at"].isoformat(), "available_at":obs["available_at"].isoformat(),
                "reporting_delay_seconds":obs["extra_data"]["reporting_delay_seconds"], "measurements":metrics(a),
                "response_reference":{"artifact_id":frozen.artifact_id,"content_hash":frozen.content_hash} if state == "ready" else None})
        result = {"schema_version":SCHEMA,"athlete_id":owner,"session_id":session_id,"information_cutoff_at":cutoff.isoformat(),
            "selection_policy":"latest_known_revision_per_session_and_timing", "items":items,
            "planning_authorized":False,"model_updated":False,"provider_writeback":False}
        result["content_hash"] = digest(result)
        return result
    finally:
        await session.rollback()

async def refresh(*, owner, session_id, session):
    from app.planning.application.ingest_authoritative_training_response import ingest_authoritative_training_response
    from app.planning.infrastructure.adapters.session_feedback_source import LockedSessionFeedbackSource
    from app.planning.infrastructure.repositories.postgres_evidence import SqlAlchemyEvidenceRepository
    current = await context(owner=owner,session_id=session_id,session=session)
    for item in current["items"]:
        if item["state"] in ("ready", "ready_to_freeze"):
            await ingest_authoritative_training_response(athlete_id=owner,response_source_id=item["response_source_id"],
                response_source=LockedSessionFeedbackSource(item["feedback_reference"]["artifact_id"], item["feedback_reference"]["content_hash"]),
                audit_repository=SqlAlchemyPlanningAuditRepository(session),evidence_repository=SqlAlchemyEvidenceRepository(session),
                session=session,created_at=_now())
    return await context(owner=owner,session_id=session_id,session=session)
