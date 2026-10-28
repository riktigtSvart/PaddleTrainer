"""Reviewed current-state adoption → identity link → immutable execution proof.

A single transaction records the existing domain contracts. No provider request,
source-row edit, retrospective plan-content claim or phase proof is introduced.
"""
import json
from datetime import UTC, datetime
from itertools import count
from uuid import UUID, NAMESPACE_URL, uuid5
from sqlalchemy import select
from app.models.entities import PlannedWorkout, User, WorkoutSession
from app.planning.application import register_athlete_setup as setup
from app.planning.application.calendar_workspace import require, digest
from app.planning.application.plan_adoption import preview_with_repository, prepare_current_state_adoption, PlanAdoptionStatus
from app.planning.application.polar_source_reconciliation import build_polar_source_reconciliation
from app.planning.application.build_authoritative_executed_training import assemble_authoritative_executed_training_with_repository
from app.planning.application.ingest_authoritative_executed_training import authoritative_executed_training_artifact_id, restore_authoritative_executed_training_audit_artifact, _audit_record
from app.planning.application.project_authoritative_executed_training import project_authoritative_executed_training_evidence
from app.planning.domain.common.serialization import canonical_json, CONTENT_HASH_ALGORITHM
from app.planning.domain.execution_link import resolve_execution_link_basis, finalize_authoritative_plan_execution_link, AuthoritativeExecutionLinkNotEligible
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.current_app_plan_read import capture_current_app_plan
from app.planning.infrastructure.adapters.locked_execution_source import CurrentAppLockedExecutionSource
from app.planning.infrastructure.repositories.postgres_authoritative_plan_revision import build_production_authoritative_plan_revision_repository
from app.planning.infrastructure.repositories.postgres_authoritative_plan_execution import build_production_authoritative_plan_execution_repository
from app.planning.infrastructure.repositories.postgres_authoritative_occurrence_execution import build_production_authoritative_occurrence_execution_repository
from app.planning.infrastructure.repositories.postgres_plan_reconciliation_audit import SqlAlchemyPlanReconciliationAuditRepository
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.planning.infrastructure.repositories.postgres_evidence import SqlAlchemyEvidenceRepository
from app.schemas.execution_connection import ExecutionConnectionInput
from app.services import session_feedback
from app.planning.infrastructure.adapters.athlete_history import aware

SCHEMA = "execution-connection-v0.1"
KIND = AuditArtifactKind.SESSION_EXECUTION_CONNECTION

def _now():
    return datetime.now(UTC)

def identity(owner, request):
    return "pt-execution-connection:" + digest({"athlete_id":owner,"request_id":request})

def reference(value, name):
    return {"artifact_id":getattr(value,name),"content_hash":value.content_hash}

async def existing_execution(repo, owner, session_id):
    record = await repo.get(artifact_kind=AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING,
        artifact_id=authoritative_executed_training_artifact_id(session_id))
    if record is None:
        return None
    artifact = restore_authoritative_executed_training_audit_artifact(record)
    require(artifact.athlete_id == owner and artifact.workout_session_id == session_id,
        "CALENDAR_EXECUTION_STORAGE_INVALID")
    return artifact

async def review(*, owner, session_id, session):
    workout = await session_feedback.owned(session,owner,session_id)
    repo = SqlAlchemyPlanningAuditRepository(session)
    user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
    frozen = await existing_execution(repo,owner,session_id)
    value = {"schema_version":SCHEMA,"athlete_id":owner,"session_id":session_id,
        "state":"already_frozen" if frozen else "blocked", "blockers":[],
        "session_title":workout.name or workout.sport.value,"session_started_at":aware(workout.started_at).isoformat(),
        "timezone_name":user.timezone,
        "plan_id":None,"plan_title":None,"plan_date":None,
        "link_basis":None,"provider_target_id":None,"plan_adoption_required":False,
        "plan_reference":None,"execution_reference":reference(frozen,"artifact_id") if frozen else None,
        "source_workout_content_hash":None,"session_source_content_hash":None,
        "history_claim":"current_state_baseline_only","plan_content_at_execution_status":"unverified",
        "phase_alignment_verified":False,"provider_event_verified":False,"clock_alignment_verified":False,
        "training_dose_changed":False,"planning_authorized":False,"provider_writeback":False}
    if frozen:
        value["review_hash"] = digest(value)
        return value, None
    if workout.planned_workout_id is None:
        value["blockers"] = ["EXECUTION_OWNED_PLAN_REQUIRED"]
        value["review_hash"] = digest(value)
        return value, None
    p = (await session.execute(select(PlannedWorkout).where(PlannedWorkout.id == workout.planned_workout_id,
        PlannedWorkout.user_id == UUID(owner)))).scalar_one_or_none()
    if p is None:
        value["blockers"] = ["EXECUTION_OWNED_PLAN_REQUIRED"]
        value["review_hash"] = digest(value)
        return value, None
    value["plan_id"], value["plan_title"], value["plan_date"] = str(p.id), p.title, p.date.isoformat()
    locked = await CurrentAppLockedExecutionSource().lock_and_capture(session,athlete_id=owner,
        source_workout_id=str(p.id),workout_session_id=session_id)
    value["session_title"] = locked.session_snapshot.get("name") or locked.session_snapshot["sport"]
    value["session_started_at"] = locked.session_snapshot["started_at"]
    value["plan_title"], value["plan_date"] = p.title, p.date.isoformat()
    value["source_workout_content_hash"] = locked.source_workout_content_hash
    value["session_source_content_hash"] = locked.session_source_content_hash
    try:
        basis, provider_id = resolve_execution_link_basis(session_snapshot=locked.session_snapshot,
            source_workout_snapshot=locked.source_workout_snapshot)
    except AuthoritativeExecutionLinkNotEligible:
        value["blockers"] = ["EXECUTION_EXACT_IDENTITY_REQUIRED"]
        value["review_hash"] = digest(value)
        return value, None
    value["link_basis"], value["provider_target_id"] = basis.value, provider_id
    revision_repo = build_production_authoritative_plan_revision_repository(session)
    existing = await revision_repo.get_plan_for_update(logical_plan_id="planned-workout:"+str(p.id))
    link_repo = build_production_authoritative_plan_execution_repository(session)
    link = await link_repo.get_by_session(workout_session_id=session_id)
    if link:
        require(link.athlete_id == owner,"CALENDAR_EXECUTION_STORAGE_INVALID")
        if (link.source_workout_id != str(p.id) or link.source_workout_content_hash != locked.source_workout_content_hash
                or link.session_source_content_hash != locked.session_source_content_hash):
            value["blockers"] = ["EXECUTION_SOURCE_CHANGED_AFTER_LINK"]
            value["review_hash"] = digest(value)
            return value, None
    capture = None
    polar = None
    if existing is None or existing.current_revision_id is None:
        try:
            capture = await capture_current_app_plan(session,source_workout_id=str(p.id),athlete_id=owner,captured_at=_now())
            polar = build_polar_source_reconciliation(capture=capture,athlete_timezone=user.timezone) if capture.source_kind == "STORED_POLAR_TARGET" else None
            adoption = await preview_with_repository(capture=capture,repository=revision_repo,
                polar_reconciliation=polar,polar_reconciliation_audit_persistence_ready=True)
            if adoption.status != PlanAdoptionStatus.READY:
                value["blockers"] = list(adoption.blockers) or ["EXECUTION_PLAN_ADOPTION_BLOCKED"]
            else:
                value["plan_adoption_required"] = True
        except (ValueError, KeyError, TypeError) as exc:
            value["blockers"] = [getattr(exc,"code",str(exc)) or "EXECUTION_PLAN_CAPTURE_BLOCKED"]
    else:
        require(existing.athlete_id == owner and existing.source_workout_id == str(p.id) and existing.verify_content_hash(),
            "CALENDAR_EXECUTION_STORAGE_INVALID")
        rev = await revision_repo.get_revision(revision_id=existing.current_revision_id)
        require(rev is not None and rev.athlete_id == owner and rev.logical_plan_id == existing.logical_plan_id
            and rev.verify_content_hash() and rev.verify_contract_hash(),"CALENDAR_EXECUTION_STORAGE_INVALID")
        value["plan_reference"] = reference(rev,"revision_id")
    if not value["blockers"]:
        value["state"] = "ready_for_review"
    value["review_hash"] = digest(value)
    return value, (capture,polar,locked,existing,link,basis,provider_id)

async def preview(*, owner, session_id, session):
    try:
        value,_ = await review(owner=owner,session_id=session_id,session=session)
        return value
    finally:
        await session.rollback()

def restore(record, owner):
    require(record is not None,"CALENDAR_EXECUTION_STORAGE_INVALID")
    a = json.loads(record.contract_json)
    proposal = ExecutionConnectionInput.model_validate(a["proposal"]).model_dump(mode="json")
    require(record.artifact_kind == KIND and record.schema_version == a["schema_version"] == SCHEMA
        and record.athlete_id == a["athlete_id"] == owner
        and record.artifact_id == a["artifact_id"] == identity(owner,proposal["request_id"])
        and proposal == a["proposal"] and record.persisted_at is not None
        and record.created_at == datetime.fromisoformat(a["created_at"])
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == a["content_hash"] == digest({k:v for k,v in a.items() if k != "content_hash"})
        and canonical_json(a) == record.contract_json and a["planning_authorized"] is False
        and a["provider_writeback"] is False and a["training_dose_changed"] is False
        and a["history_claim"] == "current_state_baseline_only" and a["plan_content_at_execution_status"] == "unverified"
        and a["phase_alignment_verified"] is False and a["clock_alignment_verified"] is False and a["provider_event_verified"] is False
        and a["execution_reference"]["artifact_id"] == authoritative_executed_training_artifact_id(a["session_id"]),
        "CALENDAR_EXECUTION_STORAGE_INVALID")
    return a

def receipt(a, record, reused):
    return {"artifact":a,"committed":True,"reused":reused,"durable_available_at":record.persisted_at.isoformat()}

async def connect(*, owner, session_id, proposal, session):
    repo = SqlAlchemyPlanningAuditRepository(session)
    setup._require_session(repo,session)
    try:
        await setup.lock_owner(session,owner)
        await session_feedback.owned(session,owner,session_id)
        key = identity(owner,proposal["request_id"])
        found = await repo.get(artifact_kind=KIND,artifact_id=key)
        if found:
            a = restore(found,owner)
            require(a["session_id"] == session_id and a["proposal"] == proposal,"CALENDAR_EXECUTION_REQUEST_CONFLICT")
            frozen = await existing_execution(repo,owner,session_id)
            require(frozen is not None and reference(frozen,"artifact_id") == a["execution_reference"],"CALENDAR_EXECUTION_STORAGE_INVALID")
            await setup.rollback(session)
            return receipt(a,found,True)
        value, prepared = await review(owner=owner,session_id=session_id,session=session)
        require(value["review_hash"] == proposal["review_hash"],"CALENDAR_EXECUTION_REVIEW_CHANGED")
        require(value["state"] == "ready_for_review" and prepared is not None,"CALENDAR_EXECUTION_NOT_ELIGIBLE")
        capture,polar,locked,existing,link,basis,provider_id = prepared
        revision_repo = build_production_authoritative_plan_revision_repository(session)
        clock = _now()
        sequence = count()
        make_id = lambda: uuid5(NAMESPACE_URL,key+":"+str(next(sequence)))
        if value["plan_adoption_required"]:
            adopted = prepare_current_state_adoption(capture=capture,authority_established_at=clock,
                existing_plan=existing,polar_reconciliation=polar,polar_reconciliation_audit_persistence_ready=True,id_factory=make_id)
            await revision_repo.adopt_current_state(binding=adopted.binding,revision=adopted.revision)
            if adopted.polar_reconciliation_audit:
                await SqlAlchemyPlanReconciliationAuditRepository(session).persist_polar_audit(record=adopted.polar_reconciliation_audit)
            revision = adopted.revision
        else:
            revision = await revision_repo.get_revision(revision_id=existing.current_revision_id)
        link_repo = build_production_authoritative_plan_execution_repository(session)
        if link is None:
            link = finalize_authoritative_plan_execution_link(link_id="pt-exec-link:"+str(make_id()),athlete_id=owner,
                logical_plan_id=revision.logical_plan_id,observed_revision_id=revision.revision_id,
                workout_session_id=session_id,source_workout_id=value["plan_id"],link_basis=basis,provider_target_id=provider_id,
                source_workout_content_hash=locked.source_workout_content_hash,session_source_content_hash=locked.session_source_content_hash,
                observed_revision_content_hash=revision.content_hash,created_at=clock)
            await link_repo.save(link)
        frozen = await assemble_authoritative_executed_training_with_repository(athlete_id=owner,workout_session_id=session_id,
            execution_link_repository=link_repo,occurrence_execution_repository=build_production_authoritative_occurrence_execution_repository(session),
            execution_source=CurrentAppLockedExecutionSource(),session=session,created_at=clock,id_factory=lambda:"session:"+session_id)
        await repo.save(_audit_record(frozen))
        await SqlAlchemyEvidenceRepository(session).save(project_authoritative_executed_training_evidence(frozen,created_at=clock))
        a = {"schema_version":SCHEMA,"artifact_id":key,"athlete_id":owner,"session_id":session_id,"proposal":proposal,
            "created_at":clock.isoformat(),"execution_reference":reference(frozen,"artifact_id"),
            "plan_reference":reference(revision,"revision_id"),"link_reference":reference(link,"link_id"),
            "plan_adopted":value["plan_adoption_required"],"source_workout_content_hash":locked.source_workout_content_hash,
            "session_source_content_hash":locked.session_source_content_hash,"history_claim":"current_state_baseline_only",
            "plan_content_at_execution_status":"unverified","phase_alignment_verified":False,"clock_alignment_verified":False,
            "provider_event_verified":False,"planning_authorized":False,"training_dose_changed":False,"provider_writeback":False}
        a["content_hash"] = digest(a)
        saved = await repo.save(AuditArtifactRecord(artifact_kind=KIND,artifact_id=key,athlete_id=owner,schema_version=SCHEMA,
            created_at=clock,content_hash_algorithm=CONTENT_HASH_ALGORITHM,content_hash=a["content_hash"],contract_json=canonical_json(a)))
        require(saved.status == AuditArtifactSaveStatus.CREATED,"CALENDAR_EXECUTION_STORAGE_INVALID")
        record = await repo.get(artifact_kind=KIND,artifact_id=key)
        require(restore(record,owner) == a,"CALENDAR_EXECUTION_STORAGE_INVALID")
        await setup.commit(session)
        return receipt(a,record,False)
    except BaseException:
        await setup.rollback(session)
        raise
