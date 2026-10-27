"""Owner-locked start-time changes, explicit conflict review and immutable history."""
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import select, and_, or_, extract, func
from sqlalchemy.orm import selectinload
from app.models.entities import PlannedWorkout, User, WorkoutSession, WorkoutStatus, TrainingPeriod
from app.planning.application import register_athlete_setup as setup, calendar_constraints as constraints
from app.planning.domain import athlete_setup
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow, PlanningLogicalPlanRow
from app.schemas.calendar_moves import MoveProposal
from app.schemas.workouts import WorkoutOut
from app.planning.application.calendar_workspace import digest, require

SCHEMA = "calendar-workout-move-v0.1"
KIND = AuditArtifactKind.CALENDAR_WORKOUT_MOVE

def review_digest(value):
    raw = {k:v for k,v in value.items() if k != "review_hash"}
    estimate = raw.get("duration_estimate")
    raw["duration_estimate"] = {k:v for k,v in estimate.items() if k != "as_of"} if estimate else None
    return digest(raw)


def _now():
    return datetime.now(UTC)

def prefix(owner, plan_id):
    return "pt-workout-move:" + digest({"athlete_id": owner, "plan_id": plan_id}) + ":"

def ref(a):
    return {"artifact_id": a["artifact_id"], "content_hash": a["content_hash"]}

def schedule(p):
    return {"date": p.date.isoformat(), "planned_start_time": aware(p.planned_start_time).isoformat() if p.planned_start_time else None}

def source(p):
    workout = WorkoutOut.model_validate(p).model_dump(mode="json")
    workout["planned_start_time"] = schedule(p)["planned_start_time"]
    return {"workout": workout,
        "updated_at": aware(p.updated_at).isoformat(), "raw_data_hash": digest(p.raw_data)}

async def load(repository, owner, key):
    r = await repository.get(artifact_kind=KIND, artifact_id=key)
    require(r is not None and r.athlete_id == owner, "CALENDAR_MOVE_NOT_FOUND")
    a = json.loads(r.contract_json)
    proposal = MoveProposal.model_validate(a["proposal"]).model_dump(mode="json")
    require(r.schema_version == a["schema_version"] == SCHEMA and r.artifact_kind == KIND
        and a["athlete_id"] == owner and a["proposal"] == proposal
        and a["artifact_id"] == key == prefix(owner, proposal["plan_id"]) + UUID(proposal["request_id"]).hex
        and r.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and r.content_hash == a["content_hash"] == digest({k:v for k,v in a.items() if k != "content_hash"})
        and r.contract_json == canonical_json(a) and r.persisted_at is not None
        and r.created_at == datetime.fromisoformat(a["created_at"])
        and type(a["revision"]) is int and a["revision"] > 0
        and (a["revision"] == 1) == (proposal["previous_reference"] is None)
        and digest(a["source_before"]) == proposal["expected_source_hash"]
        and a["planning_authorized"] is False and a["training_dose_changed"] is False
        and a["calendar_timing_changed"] is True and a["provider_writeback"] is False,
        "CALENDAR_MOVE_STORAGE_INVALID")
    before = a["source_before"]["workout"]
    expected_start = athlete_setup.local_instant(proposal["date"], proposal["start_time"], proposal["timezone_name"], proposal["start_fold"]).isoformat() if proposal["start_time"] is not None else None
    require(before["id"] == proposal["plan_id"] and a["before"] == {k:before[k] for k in ("date","planned_start_time")}
        and a["after"] == {"date":proposal["date"],"planned_start_time":expected_start}
        and isinstance(a["review_hash"],str) and len(a["review_hash"]) == 64
        and a["review_hash"] == review_digest(a["review"]) == a["review"]["review_hash"]
        and a["review"]["proposal"] == proposal and a["review"]["before"] == a["before"] and a["review"]["after"] == a["after"]
        and a["review"]["athlete_id"] == owner and a["review"]["plan_id"] == proposal["plan_id"], "CALENDAR_MOVE_STORAGE_INVALID")
    return a, r

async def latest(repository, session, owner, plan_id):
    key = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
        PlanningAuditArtifactRow.artifact_id.startswith(prefix(owner, plan_id)),
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(1))).scalar_one_or_none()
    if not key:
        return None
    a, r = await load(repository, owner, key)
    previous = a["proposal"]["previous_reference"]
    if previous:
        parent, _ = await load(repository, owner, previous["artifact_id"])
        require(ref(parent) == previous and parent["proposal"]["plan_id"] == plan_id
            and parent["revision"] + 1 == a["revision"] and parent["created_at"] < a["created_at"], "CALENDAR_MOVE_STORAGE_INVALID")
    return a, r

async def blocked(session, owner, p):
    if p.status not in (WorkoutStatus.DRAFT, WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED):
        return "CALENDAR_MOVE_STATUS_BLOCKED"
    if (await session.execute(select(WorkoutSession.id).where(WorkoutSession.planned_workout_id == p.id).limit(1))).scalar_one_or_none():
        return "CALENDAR_MOVE_ALREADY_EXECUTED"
    if (await session.execute(select(PlanningLogicalPlanRow.logical_plan_id).where(
        PlanningLogicalPlanRow.source_workout_id == p.id).limit(1))).scalar_one_or_none():
        return "CALENDAR_MOVE_APPROVED_PLAN_REVIEW_REQUIRED"
    return None

async def plan(session, owner, plan_id, lock=False):
    q = select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
        PlannedWorkout.user_id == UUID(owner), PlannedWorkout.id == UUID(plan_id))
    p = (await session.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
    require(p is not None, "CALENDAR_WORKOUT_NOT_FOUND")
    return p

async def context(*, owner, plan_id, repository, session):
    setup._require_session(repository, session)
    try:
        p = await plan(session, owner, plan_id)
        u = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        saved = await latest(repository, session, owner, plan_id)
        reason = await blocked(session, owner, p)
        return {"schema_version": SCHEMA, "athlete_id": owner, "plan_id": plan_id, "title": p.title,
            "timezone_name": u.timezone, "current": schedule(p), "source_hash": digest(source(p)),
            "previous_reference": ref(saved[0]) if saved else None,
            "restore": saved[0]["before"] if saved else None,
            "allowed": reason is None, "blocked_reason": reason,
            "planning_authorized": False, "training_dose_changed": False, "provider_writeback": False}
    finally:
        await setup.rollback(session)

async def review(*, owner, proposal, repository, session, p, user):
    reason = await blocked(session, owner, p)
    require(reason is None, reason or "CALENDAR_MOVE_BLOCKED")
    require(proposal["timezone_name"] == user.timezone, "CALENDAR_MOVE_TIMEZONE_CHANGED")
    day = date.fromisoformat(proposal["date"])
    require(date(1900,1,1) <= day <= date(2100,12,31), "CALENDAR_DATE_RANGE_INVALID")
    current = await latest(repository, session, owner, proposal["plan_id"])
    require(proposal["previous_reference"] == (ref(current[0]) if current else None), "CALENDAR_MOVE_REVISION_CONFLICT")
    captured = source(p)
    require(digest(captured) == proposal["expected_source_hash"], "CALENDAR_MOVE_SOURCE_CHANGED")
    require(proposal["start_time"] is not None or proposal["start_fold"] is None, "CALENDAR_INPUT_INVALID")
    instant = athlete_setup.local_instant(proposal["date"], proposal["start_time"], user.timezone, proposal["start_fold"]) if proposal["start_time"] is not None else None
    require(instant != (aware(p.planned_start_time) if p.planned_start_time else None) or day != p.date, "CALENDAR_MOVE_NO_CHANGE")
    moved = SimpleNamespace(**{k:getattr(p,k) for k in ("id","date","planned_start_time","title","duration_sec","distance_m","sport","status","blocks")})
    moved.date, moved.planned_start_time = day, instant
    # The projector leaves locks/transaction ownership to this workflow.
    preview = await constraints.projected(owner=owner, repository=repository, session=session,
        first=day.isoformat(), last=min(date(2100,12,31),day+timedelta(days=max(1, int((p.duration_sec or 0) // 86400)+1))).isoformat(), plan_override=moved, close_transaction=False, include_timings=True)
    impacts = [c for c in preview["conflicts"] if c["plan_id"] == str(p.id)]
    estimate = preview["duration_estimates"].get(str(p.id))
    from app.planning.domain.calendar_constraints import duration_bounds
    own_timing = next(t for t in preview["_plan_timings"] if t["id"] == str(p.id))
    _, upper, estimated = duration_bounds(own_timing)
    if instant is None or upper is None:
        impacts.append({"plan_id":str(p.id),"plan_title":p.title,"occurrence_key":"move:unknown-time",
            "constraint_title":"Edzés időadatai","date":day.isoformat(),"severity":"review",
            "code":"PLAN_TIME_UNKNOWN" if instant is None else "PLAN_END_UNKNOWN"})
    if instant is not None:
        if upper is not None and upper > 0:
            finish = instant + timedelta(seconds=upper)
            def collision(key, title, code, severity):
                impacts.append({"plan_id":str(p.id), "plan_title":p.title, "occurrence_key":key,
                    "constraint_title":title, "date":day.isoformat(), "severity":severity, "code":code})
            for other in preview["_plan_timings"]:
                if other["id"] == str(p.id) or not other["start_at"]:
                    continue
                other_start = datetime.fromisoformat(other["start_at"])
                _, other_upper, other_estimated = duration_bounds(other)
                other_end = other_start + timedelta(seconds=other_upper or 0)
                if instant <= other_start < finish or other_upper is not None and other_start < finish and other_end > instant or other_upper is None and other_start < finish:
                    uncertain = estimated or other_estimated or other_upper is None
                    collision("plan:"+other["id"]+":"+digest({k:v for k,v in other.items() if k != "duration_estimate"}), other["title"],
                        "OTHER_TRAINING_TIME_UNKNOWN" if other_upper is None else "ESTIMATED_TRAINING_OVERLAP" if uncertain else "TRAINING_OVERLAP", "review" if uncertain else "fixed")
            ended = extract("epoch", WorkoutSession.started_at) + func.coalesce(WorkoutSession.duration_sec,0)
            actuals = list((await session.execute(select(WorkoutSession).where(WorkoutSession.user_id == UUID(owner),
                WorkoutSession.started_at < finish, or_(WorkoutSession.ended_at > instant, ended > instant.timestamp(),
                    and_(WorkoutSession.started_at >= instant - timedelta(days=1), WorkoutSession.ended_at.is_(None), WorkoutSession.duration_sec.is_(None))))
                .order_by(WorkoutSession.started_at,WorkoutSession.id).limit(4001))).scalars())
            require(len(actuals) <= 4000, "CALENDAR_RANGE_TOO_DENSE")
            for actual in actuals:
                unknown_end = actual.ended_at is None and actual.duration_sec is None
                collision("session:"+str(actual.id)+":"+digest({"start":aware(actual.started_at).isoformat(),"end":aware(actual.ended_at).isoformat() if actual.ended_at else None,"duration":actual.duration_sec}), actual.name or actual.sport.value,
                    "OTHER_TRAINING_TIME_UNKNOWN" if unknown_end else "ESTIMATED_TRAINING_OVERLAP" if estimated else "TRAINING_OVERLAP", "review" if estimated or unknown_end else "fixed")
    require(len(impacts) <= 4000, "CALENDAR_RANGE_TOO_DENSE")
    period = (await session.execute(select(TrainingPeriod).where(TrainingPeriod.id == p.training_period_id, TrainingPeriod.user_id == UUID(owner)))).scalar_one_or_none() if p.training_period_id else None
    result = {"schema_version": SCHEMA, "athlete_id": owner, "plan_id": str(p.id), "title": p.title,
        "proposal": proposal, "proposal_hash": digest(proposal), "before": schedule(p), "after": schedule(moved),
        "constraints_reference": preview["reference"],
        "availability_reference": athlete_setup.reference(preview["availability"]["artifact"]) if preview["availability"] else None,
        "conflicts": impacts, "duration_estimate": estimate,
        "period_context": {"title":period.title,"start_date":period.start_date.isoformat(),"end_date":period.end_date.isoformat()} if period else None,
        "period_warning": "Az új nap az edzéshez rendelt felkészülési időszakon kívülre esik." if period and not period.start_date <= day <= period.end_date else None,
        "timezone_review_required": preview["timezone_review_required"],
        "planning_authorized": False, "training_dose_changed": False, "provider_writeback": False}
    require(not preview["timezone_review_required"], "CALENDAR_MOVE_TIMEZONE_CHANGED")
    result["review_hash"] = review_digest(result)
    return result, captured, current

def receipt(a, r, reused):
    return {"identity_scope":"APPLICATION_DEMO_USER", "artifact":a, "committed":True, "reused":reused,
        "durable_available_at":r.persisted_at.isoformat(), "planning_authorized":False,
        "training_dose_changed":False, "provider_writeback":False}

async def preview(*, owner, proposal, repository, session):
    setup._require_session(repository, session)
    try:
        p = await plan(session, owner, proposal["plan_id"])
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        result, _, _ = await review(owner=owner, proposal=proposal, repository=repository, session=session, p=p, user=user)
        return result
    finally:
        await setup.rollback(session)

async def save(*, owner, proposal, review_hash, repository, session):
    setup._require_session(repository, session)
    try:
        user = await setup.lock_owner(session, owner)
        found = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
            PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
            PlanningAuditArtifactRow.artifact_id.endswith(":"+UUID(proposal["request_id"]).hex)))).scalar_one_or_none()
        if found:
            a, r = await load(repository, owner, found)
            require(a["proposal"] == proposal and a["review_hash"] == review_hash, "CALENDAR_MOVE_REQUEST_CONFLICT")
            await setup.rollback(session)
            return receipt(a,r,True)
        p = await plan(session, owner, proposal["plan_id"], True)
        result, captured, current = await review(owner=owner, proposal=proposal, repository=repository, session=session, p=p, user=user)
        require(result["review_hash"] == review_hash, "CALENDAR_MOVE_REVIEW_CHANGED")
        created = _now()
        if current:
            created = max(created, datetime.fromisoformat(current[0]["created_at"])+timedelta(microseconds=1))
        a = {"schema_version":SCHEMA, "artifact_id":prefix(owner,proposal["plan_id"])+UUID(proposal["request_id"]).hex,
            "athlete_id":owner, "proposal":proposal, "revision":current[0]["revision"]+1 if current else 1,
            "created_at":created.isoformat(), "before":result["before"], "after":result["after"],
            "source_before":captured, "review_hash":review_hash, "review":result,
            "planning_authorized":False, "training_dose_changed":False, "calendar_timing_changed":True, "provider_writeback":False}
        a["content_hash"] = digest(a)
        p.date = date.fromisoformat(a["after"]["date"])
        p.planned_start_time = datetime.fromisoformat(a["after"]["planned_start_time"]) if a["after"]["planned_start_time"] else None
        p.updated_at = created
        stored = await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=a["artifact_id"], athlete_id=owner,
            schema_version=SCHEMA,created_at=created,content_hash_algorithm=CONTENT_HASH_ALGORITHM,
            content_hash=a["content_hash"],contract_json=canonical_json(a)))
        require(stored.status == AuditArtifactSaveStatus.CREATED, "CALENDAR_MOVE_STORAGE_INVALID")
        verified,r = await load(repository,owner,a["artifact_id"])
        require(verified == a,"CALENDAR_MOVE_STORAGE_INVALID")
        await setup.commit(session)
        return receipt(a,r,False)
    except BaseException:
        await setup.rollback(session)
        raise
