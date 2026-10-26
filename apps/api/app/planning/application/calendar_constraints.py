"""Owner-locked immutable calendar declarations, projections and idempotent writes."""

import json
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, extract, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.entities import PlannedWorkout, User, WorkoutSession, WorkoutStatus
from app.planning.application import register_athlete_setup as setup
from app.planning.application import calendar_duration
from app.planning.domain import athlete_setup, calendar_constraints as domain
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json, compute_content_hash
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.calendar_constraints import ScheduleInput

SCHEMA = "calendar-constraints-v0.1"
KIND = AuditArtifactKind.CALENDAR_CONSTRAINT_REVISION
ROW_LIMIT = 4000


def _now():
    return datetime.now(UTC)


def digest(value):
    return compute_content_hash(value, exclude_fields=frozenset())


def identity(owner, request_id):
    return "pt-calendar-constraints:" + UUID(owner).hex + ":" + UUID(request_id).hex


def reference(artifact):
    return {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"]}


def empty(zone):
    return {"timezone_name": zone, "rules": [], "exceptions": []}


def decode(record, owner):
    a = json.loads(record.contract_json)
    proposal = ScheduleInput.model_validate(a["proposal"]).model_dump(mode="json")
    raw = {k: v for k, v in a.items() if k != "content_hash"}
    domain.require(record.athlete_id == owner == a["athlete_id"] and record.artifact_kind == KIND
        and record.schema_version == a["schema_version"] == SCHEMA
        and record.artifact_id == a["artifact_id"] == identity(owner, proposal["request_id"])
        and a["proposal"] == proposal and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == a["content_hash"] == digest(raw)
        and record.created_at == datetime.fromisoformat(a["created_at"])
        and record.created_at.tzinfo is not None and record.persisted_at is not None
        and record.persisted_at.tzinfo is not None and record.contract_json == canonical_json(a)
        and type(a["revision"]) is int and a["revision"] >= 1
        and (a["revision"] == 1) == (proposal["previous_reference"] is None)
        and a["planning_authorized"] is False and a["workouts_changed"] is False,
        "CALENDAR_CONSTRAINT_STORAGE_INVALID")
    domain.validate_state(proposal["data"])
    return a


async def load(repository, owner, artifact_id):
    record = await repository.get(artifact_kind=KIND, artifact_id=artifact_id)
    domain.require(record is not None and record.athlete_id == owner, "CALENDAR_CONSTRAINT_NOT_FOUND")
    artifact = decode(record, owner)
    ref = artifact["proposal"]["previous_reference"]
    if ref:
        parent = await repository.get(artifact_kind=KIND, artifact_id=ref["artifact_id"])
        domain.require(parent is not None and parent.athlete_id == owner, "CALENDAR_CONSTRAINT_STORAGE_INVALID")
        previous = decode(parent, owner)
        domain.require(reference(previous) == ref and previous["revision"] + 1 == artifact["revision"]
            and previous["created_at"] < artifact["created_at"], "CALENDAR_CONSTRAINT_STORAGE_INVALID")
    return artifact, record


async def latest(repository, session, owner):
    key = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(1))).scalar_one_or_none()
    return await load(repository, owner, key) if key else None


def receipt(artifact, record, reused):
    return {"identity_scope": "APPLICATION_DEMO_USER", "artifact": artifact, "committed": True,
        "reused": reused, "durable_available_at": record.persisted_at.isoformat(),
        "planning_authorized": False, "workouts_changed": False}


async def save(*, owner, proposal, repository, session):
    setup._require_session(repository, session)
    try:
        user = await setup.lock_owner(session, owner)
        key = identity(owner, proposal["request_id"])
        found = await repository.get(artifact_kind=KIND, artifact_id=key)
        if found is not None:
            artifact, stored = await load(repository, owner, key)
            domain.require(artifact["proposal"] == proposal, "CALENDAR_CONSTRAINT_REQUEST_CONFLICT")
            await setup.rollback(session)
            return receipt(artifact, stored, True)
        current = await latest(repository, session, owner)
        parent = current[0] if current else None
        domain.require(proposal["previous_reference"] == (reference(parent) if parent else None), "CALENDAR_CONSTRAINT_REVISION_CONFLICT")
        domain.require(proposal["data"]["timezone_name"] == user.timezone, "CALENDAR_CONSTRAINT_TIMEZONE_CHANGED")
        domain.validate_state(proposal["data"])
        # A dated event/exception is known now: reject invalid civil instants.
        dated = [(r["start_date"], r["details"]) for r in proposal["data"]["rules"] if r["repeat"] == "once"]
        dated += [(e["date"], e["replacement"]) for e in proposal["data"]["exceptions"] if e["replacement"]]
        for day, details in dated:
            end = (domain.calendar_day(day) + timedelta(days=int(details["ends_next_day"]))).isoformat()
            a = athlete_setup.local_instant(day, details["start_time"], user.timezone, details["start_fold"])
            b = athlete_setup.local_instant(end, details["end_time"], user.timezone, details["end_fold"])
            domain.require(0 < (b - a).total_seconds() / 60 <= 1500, "CALENDAR_CONSTRAINT_DURATION_INVALID")
            domain.require(details["max_minutes"] is None or details["max_minutes"] <= (b - a).total_seconds() / 60,
                "CALENDAR_CONSTRAINT_CAPACITY_INVALID")
        created = _now()
        if parent:
            created = max(created, datetime.fromisoformat(parent["created_at"]) + timedelta(microseconds=1))
        artifact = {"schema_version": SCHEMA, "artifact_id": key, "athlete_id": owner,
            "created_at": created.isoformat(), "revision": parent["revision"] + 1 if parent else 1,
            "proposal": proposal, "planning_authorized": False, "workouts_changed": False}
        artifact["content_hash"] = digest(artifact)
        result = await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key, athlete_id=owner,
            schema_version=SCHEMA, created_at=created, content_hash_algorithm=CONTENT_HASH_ALGORITHM,
            content_hash=artifact["content_hash"], contract_json=canonical_json(artifact)))
        domain.require(result.status == AuditArtifactSaveStatus.CREATED, "CALENDAR_CONSTRAINT_STORAGE_INVALID")
        verified, stored = await load(repository, owner, key)
        domain.require(verified == artifact, "CALENDAR_CONSTRAINT_STORAGE_INVALID")
        await setup.commit(session)
        return receipt(verified, stored, False)
    except BaseException:
        await setup.rollback(session)
        raise


async def projected(*, owner, repository, session, first, last, proposal=None, availability_proposal=None):
    setup._require_session(repository, session)
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        now = _now()
        today = now.astimezone(ZoneInfo(user.timezone)).date()
        if first is None:
            first = (today - timedelta(days=today.weekday())).isoformat()
            last = (today - timedelta(days=today.weekday()) + timedelta(days=6)).isoformat()
        a, b = domain.bounded_range(first, last)
        saved = await latest(repository, session, owner)
        if proposal:
            domain.require(proposal["previous_reference"] == (reference(saved[0]) if saved else None), "CALENDAR_CONSTRAINT_REVISION_CONFLICT")
            domain.require(proposal["data"]["timezone_name"] == user.timezone, "CALENDAR_CONSTRAINT_TIMEZONE_CHANGED")
        state = proposal["data"] if proposal else saved[0]["proposal"]["data"] if saved else empty(user.timezone)
        domain.validate_state(state)
        occurrences = domain.expand(state, first, last, user.timezone)
        availability = await setup.latest(repository, session, owner, "availability")
        calendar = availability[0]["proposal"]["data"] if availability else None
        if availability_proposal:
            domain.require(availability_proposal["previous_reference"] == (athlete_setup.reference(availability[0]) if availability else None),
                "CALENDAR_CONSTRAINT_AVAILABILITY_CHANGED")
            domain.require(availability_proposal["data"]["timezone_name"] == user.timezone, "CALENDAR_CONSTRAINT_TIMEZONE_CHANGED")
            calendar = availability_proposal["data"]
            athlete_setup.resolve_calendar(calendar)
        low = datetime.combine(a, time.min, ZoneInfo(user.timezone)).astimezone(UTC)
        high = datetime.combine(b + timedelta(days=1), time.min, ZoneInfo(user.timezone)).astimezone(UTC)
        plan_end = extract("epoch", PlannedWorkout.planned_start_time) + func.coalesce(PlannedWorkout.duration_sec, 0)
        linked = exists(select(WorkoutSession.id).where(WorkoutSession.user_id == UUID(owner),
            WorkoutSession.planned_workout_id == PlannedWorkout.id))
        rows = list((await session.execute(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
            PlannedWorkout.user_id == UUID(owner),
            PlannedWorkout.status.in_([WorkoutStatus.DRAFT, WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED]),
            ~linked,
            or_(and_(PlannedWorkout.date >= a, PlannedWorkout.date <= b),
                and_(PlannedWorkout.planned_start_time < high, plan_end > low.timestamp()),
                and_(PlannedWorkout.duration_sec.is_(None), PlannedWorkout.planned_start_time >= low - timedelta(days=1),
                    PlannedWorkout.planned_start_time < low)),
        ).order_by(PlannedWorkout.date, PlannedWorkout.id).limit(ROW_LIMIT + 1))).scalars())
        domain.require(len(rows) <= ROW_LIMIT, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
        estimates = await calendar_duration.project(owner=owner, plans=rows, session=session, now=now, zone=user.timezone)
        rows = [p for p in rows if calendar_duration.reaches_view(p, a, b, low, high, estimates.get(str(p.id)))]
        estimates = {str(p.id): estimates[str(p.id)] for p in rows if str(p.id) in estimates}
        plans = [{"id": str(p.id), "title": p.title,
            "date": aware(p.planned_start_time).astimezone(ZoneInfo(user.timezone)).date().isoformat() if p.planned_start_time else p.date.isoformat(),
            "start_at": aware(p.planned_start_time).isoformat() if p.planned_start_time else None,
            "duration_sec": p.duration_sec, "duration_estimate": estimates.get(str(p.id))} for p in rows]
        groups = domain.opportunities(calendar, occurrences, first, last, user.timezone)
        domain.require(len(groups) <= domain.MAX_OCCURRENCES, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
        zone_review = state["timezone_name"] != user.timezone or calendar is not None and calendar["timezone_name"] != user.timezone
        if zone_review:
            for group in groups:
                group.update(known=False, usable_minutes=None, intervals=[])
        impacts = domain.conflicts(plans, occurrences)
        impacts += domain.opportunity_conflicts(plans, groups, calendar, {c["plan_id"] for c in impacts if c["severity"] == "fixed"})
        domain.require(len(impacts) <= domain.MAX_OCCURRENCES, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
        return {"schema_version": SCHEMA, "athlete_id": owner, "timezone_name": user.timezone,
            "local_today": today.isoformat(), "start_date": first, "end_date": last,
            "retrieved_at": _now().isoformat(), "reference": reference(saved[0]) if saved else None,
            "saved": receipt(*saved, True) if saved else None, "data": state,
            "availability": setup.receipt(*availability, True) if availability else None,
            "occurrences": occurrences, "conflicts": impacts,
            "duration_estimates": estimates,
            "opportunities": groups, "timezone_review_required": bool(zone_review),
            "proposal_hash": digest(proposal) if proposal else None,
            "availability_proposal_hash": digest(availability_proposal) if availability_proposal else None,
            "has_more": False, "absence_means_free": False, "opportunities_are_required": False,
            "planning_authorized": False, "workouts_changed": False}
    finally:
        await setup.rollback(session)
