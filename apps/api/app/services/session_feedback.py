"""Append-only owned self reports, serialized by the existing owner row lock.

These records are deliberately separate from provider summaries and legacy
AthleteResponse sources. The C12 adapter selects an explicit immutable revision;
revisions must never count as independent training responses.
"""
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.entities import User, WorkoutSession
from app.planning.application import register_athlete_setup as setup
from app.planning.application.calendar_workspace import digest, require
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.session_feedback import FeedbackInput

SCHEMA = "session-feedback-v0.1"
KIND = AuditArtifactKind.SESSION_FEEDBACK
LIMIT = 2000

def _now():
    return datetime.now(UTC)

def identity(owner, request_id):
    return "pt-session-feedback:" + digest({"athlete_id": owner, "request_id": request_id})

async def owned(session, owner, session_id):
    found = (await session.execute(select(WorkoutSession).where(
        WorkoutSession.id == UUID(session_id), WorkoutSession.user_id == UUID(owner)))).scalar_one_or_none()
    require(found is not None, "CALENDAR_SESSION_NOT_FOUND")
    return found

def decode(record, owner):
    require(record is not None, "CALENDAR_FEEDBACK_STORAGE_INVALID")
    a = json.loads(record.contract_json)
    proposal = FeedbackInput.model_validate(a["proposal"]).model_dump(mode="json")
    require(record.athlete_id == a["athlete_id"] == owner
        and record.artifact_kind == KIND and record.schema_version == a["schema_version"] == SCHEMA
        and record.artifact_id == a["artifact_id"] == identity(owner, proposal["request_id"])
        and a["proposal"] == proposal and str(UUID(a["session_id"])) == a["session_id"]
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == a["content_hash"] == digest({k:v for k,v in a.items() if k != "content_hash"})
        and record.contract_json == canonical_json(a) and record.persisted_at is not None
        and record.created_at == datetime.fromisoformat(a["submitted_at"])
        and type(a["revision"]) is int and a["revision"] == proposal["expected_revision"] + 1
        and a["planning_authorized"] is False and a["provider_writeback"] is False,
        "CALENDAR_FEEDBACK_STORAGE_INVALID")
    return a

async def history(repository, session, owner, session_id):
    # An exact JSON session filter avoids scanning every session's history.
    keys = list((await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner),
        PlanningAuditArtifactRow.artifact_kind == KIND.value,
        PlanningAuditArtifactRow.contract_json.contains('"session_id":"' + session_id + '"'),
    ).limit(LIMIT + 1))).scalars().all())
    require(len(keys) <= LIMIT, "CALENDAR_FEEDBACK_HISTORY_LIMIT")
    items = [decode(await repository.get(artifact_kind=KIND, artifact_id=key), owner) for key in keys]
    items.sort(key=lambda a: (a["proposal"]["timing"], a["revision"]))
    for timing in ("IMMEDIATE", "NEXT_MORNING"):
        chain = [a for a in items if a["proposal"]["timing"] == timing]
        previous = None
        for i, a in enumerate(chain, 1):
            require(a["session_id"] == session_id and a["revision"] == i
                and a["previous_hash"] == previous, "CALENDAR_FEEDBACK_STORAGE_INVALID")
            previous = a["content_hash"]
    return items

def view(owner, session_id, items):
    return {"schema_version": SCHEMA, "athlete_id": owner, "session_id": session_id,
        "history": items, "current": {timing: next((a for a in reversed(items) if a["proposal"]["timing"] == timing), None)
        for timing in ("IMMEDIATE", "NEXT_MORNING")}, "planning_authorized": False, "provider_writeback": False}

async def context(*, owner, session_id, repository, session):
    setup._require_session(repository, session)
    try:
        await owned(session, owner, session_id)
        return view(owner, session_id, await history(repository, session, owner, session_id))
    finally:
        await setup.rollback(session)

async def save(*, owner, session_id, proposal, repository, session):
    setup._require_session(repository, session)
    try:
        user = await setup.lock_owner(session, owner)
        workout = await owned(session, owner, session_id)
        key = identity(owner, proposal["request_id"])
        record = await repository.get(artifact_kind=KIND, artifact_id=key)
        if record is not None:
            artifact = decode(record, owner)
            require(artifact["proposal"] == proposal and artifact["session_id"] == session_id,
                "CALENDAR_FEEDBACK_REQUEST_CONFLICT")
            await setup.rollback(session)
            return {"committed": True, "reused": True, "artifact": artifact,
                "durable_available_at": record.persisted_at.isoformat()}
        now = _now()
        observed = datetime.fromisoformat(proposal["observed_at"])
        end = aware(workout.ended_at or workout.started_at)
        require(end <= observed <= now, "CALENDAR_FEEDBACK_OBSERVATION_TIME_INVALID")
        if proposal["timing"] == "NEXT_MORNING":
            zone = ZoneInfo(user.timezone)
            require(observed.astimezone(zone).date() == end.astimezone(zone).date() + timedelta(days=1),
                "CALENDAR_FEEDBACK_NEXT_DAY_REQUIRED")
        items = await history(repository, session, owner, session_id)
        previous = view(owner, session_id, items)["current"][proposal["timing"]]
        require(proposal["expected_revision"] == (previous["revision"] if previous else 0),
            "CALENDAR_FEEDBACK_REVISION_CONFLICT")
        require(len(items) < LIMIT, "CALENDAR_FEEDBACK_HISTORY_LIMIT")
        artifact = {"schema_version": SCHEMA, "artifact_id": key, "athlete_id": owner,
            "session_id": session_id, "proposal": proposal, "revision": proposal["expected_revision"] + 1,
            "previous_hash": previous["content_hash"] if previous else None,
            "submitted_at": now.isoformat(), "timezone_name": user.timezone,
            "planning_authorized": False, "provider_writeback": False}
        artifact["content_hash"] = digest(artifact)
        stored = await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key,
            athlete_id=owner, schema_version=SCHEMA, created_at=now, content_hash_algorithm=CONTENT_HASH_ALGORITHM,
            content_hash=artifact["content_hash"], contract_json=canonical_json(artifact)))
        require(stored.status == AuditArtifactSaveStatus.CREATED, "CALENDAR_FEEDBACK_STORAGE_INVALID")
        record = await repository.get(artifact_kind=KIND, artifact_id=key)
        require(decode(record, owner) == artifact, "CALENDAR_FEEDBACK_STORAGE_INVALID")
        await setup.commit(session)
        return {"committed": True, "reused": False, "artifact": artifact,
            "durable_available_at": record.persisted_at.isoformat()}
    except BaseException:
        await setup.rollback(session)
        raise
