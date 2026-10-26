"""Owned calendar projection and append-only explicit workout goal tags.

Source prescriptions remain intact. A separate labeled timetable estimate may
accompany a distance-only plan; it never authorizes a training dose.
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.entities import PlannedWorkout, TrainingPeriod, User, WorkoutSession
from app.planning.application import register_athlete_setup as setup
from app.planning.application import calendar_duration
from app.planning.domain import athlete_setup
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json, compute_content_hash
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.planning_calendar import WorkoutGoalInput
from app.schemas.workouts import WorkoutOut

SCHEMA = "calendar-workspace-v0.1"
GOAL_SCHEMA = "calendar-workout-goal-v0.1"
KIND = AuditArtifactKind.WORKOUT_GOAL_TAG
ROW_LIMIT = 4000


class CalendarRuleError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise CalendarRuleError(code)


def _now():
    return datetime.now(UTC)


def digest(value):
    return compute_content_hash(value, exclude_fields=frozenset())


def artifact_hash(artifact):
    return digest({key: value for key, value in artifact.items() if key != "content_hash"})


def scope(owner, entity_kind, entity_id):
    return "pt-workout-goal:" + digest(
        {"athlete_id": owner, "entity_kind": entity_kind, "entity_id": entity_id}
    )


def identity(owner, proposal):
    return scope(owner, proposal["entity_kind"], proposal["entity_id"]) + ":" + UUID(proposal["request_id"]).hex


def reference(artifact):
    return {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"]}


def decode(record, owner):
    artifact = json.loads(record.contract_json)
    proposal = WorkoutGoalInput.model_validate(artifact["proposal"]).model_dump(mode="json")
    require(
        record.athlete_id == owner
        and artifact["athlete_id"] == owner
        and artifact["schema_version"] == record.schema_version == GOAL_SCHEMA
        and record.artifact_kind == KIND
        and artifact["artifact_id"] == record.artifact_id == identity(owner, proposal)
        and artifact["proposal"] == proposal
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == artifact["content_hash"] == artifact_hash(artifact)
        and record.created_at == datetime.fromisoformat(artifact["created_at"])
        and record.persisted_at is not None
        and canonical_json(artifact) == record.contract_json
        and artifact["planning_authorized"] is False
        and artifact["workouts_changed"] is False
        and type(artifact["revision"]) is int
        and artifact["revision"] >= 1
        and (artifact["revision"] == 1) == (proposal["previous_reference"] is None),
        "CALENDAR_GOAL_STORAGE_INVALID",
    )
    return artifact


async def load_goal(repository, owner, artifact_id):
    record = await repository.get(artifact_kind=KIND, artifact_id=artifact_id)
    require(record is not None and record.athlete_id == owner, "CALENDAR_GOAL_NOT_FOUND")
    artifact = decode(record, owner)
    previous = artifact["proposal"]["previous_reference"]
    if previous:
        parent_record = await repository.get(artifact_kind=KIND, artifact_id=previous["artifact_id"])
        require(parent_record is not None and parent_record.athlete_id == owner, "CALENDAR_GOAL_STORAGE_INVALID")
        parent = decode(parent_record, owner)
        require(
            reference(parent) == previous
            and parent["proposal"]["entity_kind"] == artifact["proposal"]["entity_kind"]
            and parent["proposal"]["entity_id"] == artifact["proposal"]["entity_id"]
            and parent["revision"] + 1 == artifact["revision"]
            and parent["created_at"] < artifact["created_at"],
            "CALENDAR_GOAL_STORAGE_INVALID",
        )
    return artifact, record


def receipt(artifact, record, reused):
    return {
        "identity_scope": "APPLICATION_DEMO_USER", "artifact": artifact,
        "committed": True, "reused": reused,
        "durable_available_at": record.persisted_at.isoformat(),
        "planning_authorized": False, "workouts_changed": False,
    }


async def latest_goals(repository, session, owner, entities):
    if not entities:
        return {}
    prefixes = [scope(owner, kind, entity_id) for kind, entity_id in entities]
    prefix_length = len(prefixes[0])
    rows = (await session.execute(
        select(PlanningAuditArtifactRow.artifact_id)
        .where(
            PlanningAuditArtifactRow.athlete_id == UUID(owner),
            PlanningAuditArtifactRow.artifact_kind == KIND.value,
            func.substr(PlanningAuditArtifactRow.artifact_id, 1, prefix_length).in_(prefixes),
        )
        .order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id)
        .limit(ROW_LIMIT + 1)
    )).scalars().all()
    require(len(rows) <= ROW_LIMIT, "CALENDAR_RANGE_TOO_DENSE")
    result, known_scopes = {}, set()
    for artifact_id in rows:
        prefix = artifact_id.rsplit(":", 1)[0]
        if prefix in known_scopes:
            continue
        artifact, _ = await load_goal(repository, owner, artifact_id)
        proposal = artifact["proposal"]
        key = (proposal["entity_kind"], proposal["entity_id"])
        require(scope(owner, *key) == prefix and key in entities, "CALENDAR_GOAL_STORAGE_INVALID")
        result[key] = artifact
        known_scopes.add(prefix)
    return result


async def save_goal(*, owner, proposal, repository, session):
    setup._require_session(repository, session)
    try:
        await setup.lock_owner(session, owner)
        artifact_id = identity(owner, proposal)
        found_id = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
            PlanningAuditArtifactRow.athlete_id == UUID(owner),
            PlanningAuditArtifactRow.artifact_kind == KIND.value,
            PlanningAuditArtifactRow.artifact_id.endswith(":" + UUID(proposal["request_id"]).hex),
        ))).scalar_one_or_none()
        if found_id is not None:
            artifact, record = await load_goal(repository, owner, found_id)
            require(artifact["proposal"] == proposal, "CALENDAR_REQUEST_IDENTITY_CONFLICT")
            await setup.rollback(session)
            return receipt(artifact, record, True)
        entity_kind, entity_id = proposal["entity_kind"], proposal["entity_id"]
        model = PlannedWorkout if entity_kind == "planned" else WorkoutSession
        entity = (await session.execute(select(model.id).where(model.id == UUID(entity_id), model.user_id == UUID(owner)))).scalar_one_or_none()
        require(entity is not None, "CALENDAR_WORKOUT_NOT_FOUND")
        latest = await latest_goals(repository, session, owner, {(entity_kind, entity_id)})
        parent = latest.get((entity_kind, entity_id))
        require(proposal["previous_reference"] == (reference(parent) if parent else None), "CALENDAR_REVISION_CONFLICT_RELOAD")
        created_at = _now()
        if parent:
            created_at = max(created_at, datetime.fromisoformat(parent["created_at"]) + timedelta(microseconds=1))
        artifact = {
            "schema_version": GOAL_SCHEMA, "artifact_id": artifact_id,
            "athlete_id": owner, "proposal": proposal,
            "revision": parent["revision"] + 1 if parent else 1,
            "created_at": created_at.isoformat(), "planning_authorized": False,
            "workouts_changed": False,
        }
        artifact["content_hash"] = artifact_hash(artifact)
        saved = await repository.save(AuditArtifactRecord(
            artifact_kind=KIND, artifact_id=artifact_id, athlete_id=owner,
            schema_version=GOAL_SCHEMA, created_at=created_at,
            content_hash_algorithm=CONTENT_HASH_ALGORITHM, content_hash=artifact["content_hash"],
            contract_json=canonical_json(artifact),
        ))
        require(saved.status == AuditArtifactSaveStatus.CREATED, "CALENDAR_GOAL_STORAGE_INVALID")
        verified, record = await load_goal(repository, owner, artifact_id)
        require(verified == artifact, "CALENDAR_GOAL_STORAGE_INVALID")
        await setup.commit(session)
        return receipt(verified, record, False)
    except BaseException:
        await setup.rollback(session)
        raise


async def feed(*, owner, start, end, repository, session):
    setup._require_session(repository, session)
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        tz = ZoneInfo(user.timezone)
        now = _now()
        today = now.astimezone(tz).date()
        if start is None:
            first = today - timedelta(days=today.weekday())
            last = first + timedelta(days=6)
        else:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        require(date(1900, 1, 1) <= first <= last <= date(2100, 12, 31) and (last - first).days < 366, "CALENDAR_DATE_RANGE_INVALID")
        low = datetime.combine(first, time.min, tz).astimezone(UTC)
        high = datetime.combine(last + timedelta(days=1), time.min, tz).astimezone(UTC)
        planned_end = extract("epoch", PlannedWorkout.planned_start_time) + func.coalesce(PlannedWorkout.duration_sec, 0)
        plans = list((await session.execute(
            select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks))
            .where(PlannedWorkout.user_id == UUID(owner), or_(
                and_(PlannedWorkout.date >= first, PlannedWorkout.date <= last),
                and_(PlannedWorkout.planned_start_time >= low, PlannedWorkout.planned_start_time < high),
                and_(PlannedWorkout.planned_start_time < high, planned_end > low.timestamp()),
                and_(PlannedWorkout.duration_sec.is_(None), PlannedWorkout.planned_start_time >= low - timedelta(days=1),
                    PlannedWorkout.planned_start_time < low),
            )).order_by(PlannedWorkout.date, PlannedWorkout.id).limit(ROW_LIMIT + 1)
        )).scalars().unique())
        # SQLAlchemy compiles epoch extraction for both PostgreSQL and contract-test SQLite.
        duration_end = extract("epoch", WorkoutSession.started_at) + func.coalesce(WorkoutSession.duration_sec, 0)
        sessions = list((await session.execute(
            select(WorkoutSession).where(WorkoutSession.user_id == UUID(owner), WorkoutSession.started_at < high,
                or_(WorkoutSession.started_at >= low, WorkoutSession.ended_at > low,
                    and_(WorkoutSession.ended_at.is_(None), duration_end > low.timestamp())))
            .order_by(WorkoutSession.started_at, WorkoutSession.id).limit(ROW_LIMIT + 1)
        )).scalars())
        periods = list((await session.execute(
            select(TrainingPeriod).where(TrainingPeriod.user_id == UUID(owner), TrainingPeriod.start_date <= last, TrainingPeriod.end_date >= first)
            .order_by(TrainingPeriod.start_date, TrainingPeriod.id).limit(ROW_LIMIT + 1)
        )).scalars())
        require(max(len(plans), len(sessions), len(periods)) <= ROW_LIMIT, "CALENDAR_RANGE_TOO_DENSE")
        estimates = await calendar_duration.project(owner=owner, plans=plans, session=session, now=now, zone=user.timezone)
        plans = [p for p in plans if calendar_duration.reaches_view(p, first, last, low, high, estimates.get(str(p.id)))]
        linked_ids = {s.planned_workout_id for s in sessions if s.planned_workout_id}
        owned_links = set((await session.execute(select(PlannedWorkout.id).where(PlannedWorkout.user_id == UUID(owner), PlannedWorkout.id.in_(linked_ids)))).scalars()) if linked_ids else set()
        entities = {("planned", str(p.id)) for p in plans} | {("session", str(s.id)) for s in sessions} | {("planned", str(p)) for p in owned_links}
        goals = await latest_goals(repository, session, owner, entities)

        def tag(kind, entity_id):
            artifact = goals.get((kind, str(entity_id)))
            return None if artifact is None else {**reference(artifact), "primary_goal": artifact["proposal"]["primary_goal"]}

        planned = [{**WorkoutOut.model_validate(p).model_dump(mode="json"),
            "planned_start_time": aware(p.planned_start_time).isoformat() if p.planned_start_time else None,
            "goal_tag": tag("planned", p.id), "duration_estimate": estimates.get(str(p.id))} for p in plans]
        actual = []
        for s in sessions:
            item = {"id": str(s.id), "sport": s.sport.value, "name": s.name,
                "external_provider": s.external_provider, "external_id": s.external_id,
                **{key: getattr(s, key) for key in ("duration_sec", "distance_m", "calories",
                    "avg_hr", "max_hr", "avg_speed", "max_speed", "avg_power", "max_power",
                    "avg_cadence", "max_cadence", "cardio_load", "perceived_load")}}
            item["started_at"] = aware(s.started_at).isoformat()
            item["ended_at"] = aware(s.ended_at).isoformat() if s.ended_at else None
            item["rpe"] = s.rpe
            item["planned_workout_id"] = str(s.planned_workout_id) if s.planned_workout_id in owned_links else None
            item["goal_tag"] = tag("session", s.id)
            item["linked_goal_tag"] = tag("planned", s.planned_workout_id) if s.planned_workout_id in owned_links else None
            actual.append(item)
        availability = await setup.latest(repository, session, owner, "availability")
        calendar = availability[0]["proposal"]["data"] if availability else None
        resolved = athlete_setup.resolve_calendar(calendar) if calendar else None
        days = [d for d in resolved["days"] if first.isoformat() <= d["date"] <= last.isoformat()] if resolved else []
        # Include a preceding overnight window intersecting the first visible day.
        carry = []
        if resolved:
            for day in resolved["days"]:
                if day["date"] >= first.isoformat():
                    continue
                for window in day["windows"]:
                    if datetime.fromisoformat(window["end_at"]) > low:
                        carry.append({"date": day["date"], **window})
        return {
            "schema_version": SCHEMA, "athlete_id": owner,
            "timezone_name": user.timezone, "local_today": today.isoformat(),
            "start_date": first.isoformat(), "end_date": last.isoformat(),
            "retrieved_at": _now().isoformat(), "planned": planned, "sessions": actual,
            "availability": {"reference": athlete_setup.reference(availability[0]) if availability else None,
                "days": days, "carry_windows": carry, "absence_means_unavailable": False},
            "periods": [{"id": str(p.id), "title": p.title, "period_type": p.period_type.value,
                "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat()} for p in periods],
            "has_more": False, "planning_authorized": False, "workouts_changed": False,
        }
    finally:
        await setup.rollback(session)
