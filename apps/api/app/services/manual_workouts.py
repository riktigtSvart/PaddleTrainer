"""Fast local authoring; no planner, provider call or inferred exercise capacity.

The authored dose and its goal tag commit together. Retries retain the request
identity, and edits pin both the workout and its independently editable goal.
"""
import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import (
    BlockType, PeriodType, PlannedWorkout, TrainingPeriod, User, WorkoutBlock,
    WorkoutStatus,
)
from app.planning.application import calendar_moves, calendar_workspace as calendar
from app.planning.application import register_athlete_setup as setup
from app.planning.domain import athlete_setup
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.schemas.manual_workouts import ManualDraft, ManualSave
from app.schemas.planning_calendar import WorkoutGoalInput
from app.services.strength_catalog import catalog

SCHEMA = "manual-workout-v0.1"
MARKER = "paddletrainer_manual_workout"
KIND = AuditArtifactKind.MANUAL_WORKOUT_EDIT
ACTIVE = (WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED, WorkoutStatus.DRAFT)


def _now():
    return datetime.now(UTC)


def identity(owner, request_id):
    return "pt-manual-workout:" + calendar.digest({"athlete_id": owner}) + ":" + UUID(request_id).hex


def source_hash(row):
    return calendar.digest(calendar_moves.source(row))


def structured(row):
    """Optional recipe isolation: an old or damaged recipe cannot hide a workout."""
    value = (row.raw_data or {}).get(MARKER) if isinstance(row.raw_data, dict) else None
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA or row.source != "MANUAL":
        return None
    try:
        draft = ManualDraft.model_validate(value["draft"]).model_dump(mode="json")
        # A generic external edit must not leave a stale structured prescription.
        if (draft["sport"] != row.sport.value or draft["title"] != row.title
                or draft["duration_sec"] != row.duration_sec or draft["description"] != (row.description or "")):
            return None
        return draft
    except (ValueError, KeyError, TypeError):
        return None


def projection(row, executed=False, approved=False):
    if row.source != "MANUAL" or row.polar_target_id:
        return None
    flat = all(b.parent_block_id is None and b.block_type != BlockType.REPEAT for b in row.blocks)
    return {"schema_version": SCHEMA, "editable": row.status in ACTIVE and not executed and not approved and flat,
            "recipe": structured(row)}


async def target(session, owner, workout_id):
    return await calendar_moves.plan(session, owner, workout_id, lock=True)


async def edit_reason(session, owner, row):
    if row.source != "MANUAL" or row.polar_target_id:
        return "MANUAL_WORKOUT_PROTECTED"
    reason = await calendar_moves.blocked(session, owner, row)
    if reason:
        return reason
    if any(b.parent_block_id is not None or b.block_type == BlockType.REPEAT for b in row.blocks):
        return "MANUAL_WORKOUT_COMPLEX_BLOCKS"
    return None


async def context(*, owner, workout_id=None, repository, session):
    setup._require_session(repository, session)
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        periods = list((await session.execute(select(TrainingPeriod).where(
            TrainingPeriod.user_id == UUID(owner), TrainingPeriod.period_type == PeriodType.MESOCYCLE,
        ).order_by(TrainingPeriod.start_date.desc(), TrainingPeriod.id).limit(1001))).scalars())
        calendar.require(len(periods) <= 1000, "CALENDAR_RANGE_TOO_DENSE")
        result = {"schema_version": SCHEMA, "athlete_id": owner, "timezone_name": user.timezone,
            "local_today": _now().astimezone(ZoneInfo(user.timezone)).date().isoformat(),
            "mesocycles": [{"id": str(p.id), "title": p.title, "start_date": p.start_date.isoformat(),
                            "end_date": p.end_date.isoformat()} for p in periods],
            "exercises": [{"id": e["id"], "label": e["label"]} for e in catalog()["exercises"]],
            "workout": None, "provider_writeback": False}
        if workout_id is None:
            return result
        row = await calendar_moves.plan(session, owner, workout_id)
        goals = await calendar.latest_goals(repository, session, owner, {("planned", workout_id)})
        goal = goals.get(("planned", workout_id))
        saved = structured(row)
        instant = aware(row.planned_start_time).astimezone(ZoneInfo(user.timezone)) if row.planned_start_time else None
        flat = all(b.parent_block_id is None and b.block_type != BlockType.REPEAT for b in row.blocks)
        draft = {"date": row.date.isoformat(), "start_time": instant.strftime("%H:%M:%S") if instant else None,
            "start_fold": instant.fold if instant else None, "sport": row.sport.value, "title": row.title,
            "duration_sec": row.duration_sec, "distance_m": row.distance_m, "description": row.description or "",
            "intensity_type": row.intensity_type,
            "location": saved["location"] if saved else "", "primary_goal": goal["proposal"]["primary_goal"] if goal else None,
            "mesocycle_id": str(row.training_period_id) if row.training_period_id else None,
            "phases": saved["phases"] if saved else [{"block_type": b.block_type.value,
                "name": b.name or "Edzésszakasz", "duration_sec": b.duration_sec, "distance_m": b.distance_m,
                "repeat_count": b.repeat_count or 1, "notes": "", "intensity_type": b.intensity_type,
                "intensity_min": b.intensity_min, "intensity_max": b.intensity_max} for b in row.blocks] if flat else [],
            "exercises": saved["exercises"] if saved else []}
        reason = await edit_reason(session, owner, row)
        result["workout"] = {"id": str(row.id), "source_hash": source_hash(row), "source": row.source,
            "goal_reference": calendar.reference(goal) if goal else None, "draft": draft,
            "editable": reason is None, "blocked_reason": reason,
            "copyable": flat, "status": row.status.value}
        return result
    finally:
        await setup.rollback(session)


async def append_goal(repository, owner, workout_id, request_id, goal, parent):
    proposal = WorkoutGoalInput.model_validate({"request_id": str(uuid5(UUID(request_id), workout_id)),
        "entity_kind": "planned", "entity_id": workout_id,
        "previous_reference": calendar.reference(parent) if parent else None,
        "primary_goal": goal}).model_dump(mode="json")
    now = _now()
    if parent:
        now = max(now, datetime.fromisoformat(parent["created_at"]) + timedelta(microseconds=1))
    artifact = {"schema_version": calendar.GOAL_SCHEMA, "artifact_id": calendar.identity(owner, proposal),
        "athlete_id": owner, "proposal": proposal, "revision": parent["revision"] + 1 if parent else 1,
        "created_at": now.isoformat(), "planning_authorized": False, "workouts_changed": False}
    artifact["content_hash"] = calendar.artifact_hash(artifact)
    saved = await repository.save(AuditArtifactRecord(artifact_kind=calendar.KIND, artifact_id=artifact["artifact_id"],
        athlete_id=owner, schema_version=calendar.GOAL_SCHEMA, created_at=now,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM, content_hash=artifact["content_hash"],
        contract_json=canonical_json(artifact)))
    calendar.require(saved.status == AuditArtifactSaveStatus.CREATED, "CALENDAR_GOAL_STORAGE_INVALID")
    verified, _ = await calendar.load_goal(repository, owner, artifact["artifact_id"])
    calendar.require(verified == artifact, "CALENDAR_GOAL_STORAGE_INVALID")


async def period_for(session, owner, draft):
    day = date.fromisoformat(draft["date"])
    q = select(TrainingPeriod.id).where(TrainingPeriod.user_id == UUID(owner),
        TrainingPeriod.period_type == PeriodType.MESOCYCLE, TrainingPeriod.start_date <= day,
        TrainingPeriod.end_date >= day)
    if draft["mesocycle_id"]:
        q = q.where(TrainingPeriod.id == UUID(draft["mesocycle_id"]))
    values = list((await session.execute(q.limit(2))).scalars())
    if draft["mesocycle_id"]:
        calendar.require(len(values) == 1, "MANUAL_MESOCYCLE_DATE_MISMATCH")
    return values[0] if len(values) == 1 else None


async def apply_draft(session, owner, row, draft, timezone_name, revision_id):
    instant = athlete_setup.local_instant(draft["date"], draft["start_time"], timezone_name,
        draft["start_fold"]) if draft["start_time"] is not None else None
    period = await period_for(session, owner, draft)
    row.date = date.fromisoformat(draft["date"])
    row.planned_start_time = instant
    row.sport = draft["sport"]
    row.title = draft["title"]
    row.description = draft["description"] or None
    row.duration_sec = draft["duration_sec"]
    row.distance_m = draft["distance_m"]
    row.intensity_type = draft["intensity_type"]
    row.training_period_id = period
    row.raw_data = {**(row.raw_data or {}), MARKER: {"schema_version": SCHEMA, "revision_id": revision_id, "draft": draft}}
    row.updated_at = _now()
    # Editing is limited to flat blocks, so no foreign child can be orphaned.
    row.blocks.clear()
    expanded = []
    for phase in draft['phases']:
        recovery = phase.get('recovery_duration_sec')
        if recovery:
            for repetition in range(phase['repeat_count']):
                expanded.append({**phase, 'repeat_count': 1})
                if repetition < phase['repeat_count'] - 1:
                    expanded.append({'block_type': 'RECOVERY', 'name': 'Pihenő · ' + phase['name'][:105],
                        'duration_sec': recovery, 'distance_m': None, 'repeat_count': 1,
                        'intensity_type': None, 'intensity_min': None, 'intensity_max': None})
        else:
            expanded.append(phase)
    for i, phase in enumerate(expanded):
        row.blocks.append(WorkoutBlock(id=uuid5(NAMESPACE_URL, revision_id + ":" + str(row.id) + ":" + str(i)),
            position=i, block_type=BlockType(phase["block_type"]), name=phase["name"],
            duration_sec=phase["duration_sec"], distance_m=phase["distance_m"], repeat_count=phase["repeat_count"],
            intensity_type=phase['intensity_type'], intensity_min=phase['intensity_min'], intensity_max=phase['intensity_max']))
    await session.flush()


async def load_receipt(repository, owner, artifact_id):
    record = await repository.get(artifact_kind=KIND, artifact_id=artifact_id)
    if record is None:
        return None
    value = json.loads(record.contract_json)
    proposal = ManualSave.model_validate(value["proposal"]).model_dump(mode="json")
    # The optional paired-rest field did not exist in C21.10.20. Preserve those
    # immutable bytes while validating every original quantity as before.
    if proposal['draft']:
        for raw, checked in zip(value['proposal']['draft']['phases'], proposal['draft']['phases'], strict=True):
            if 'recovery_duration_sec' not in raw:
                checked.pop('recovery_duration_sec')
    calendar.require(record.athlete_id == value["athlete_id"] == owner
        and record.schema_version == value["schema_version"] == SCHEMA
        and record.artifact_id == value["artifact_id"] == identity(owner, proposal["request_id"])
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == value["content_hash"] == calendar.artifact_hash(value)
        and value["proposal"] == proposal and record.contract_json == canonical_json(value)
        and record.persisted_at is not None and record.created_at == datetime.fromisoformat(value["created_at"])
        and value["provider_writeback"] is False and value["actual_training_changed"] is False,
        "MANUAL_WORKOUT_STORAGE_INVALID")
    return value


def receipt(value, reused):
    return {"schema_version": SCHEMA, "athlete_id": value["athlete_id"], "committed": True,
        "reused": reused, "request_id": value["proposal"]["request_id"],
        "artifact_id": value["artifact_id"], "content_hash": value["content_hash"],
        "operation": value["proposal"]["operation"], "workout_ids": value["workout_ids"],
        "warnings": value["warnings"], "provider_writeback": False, "actual_training_changed": False}


async def save(*, owner, proposal, repository, session):
    setup._require_session(repository, session)
    try:
        await setup.lock_owner(session, owner)
        artifact_id = identity(owner, proposal["request_id"])
        old = await load_receipt(repository, owner, artifact_id)
        if old:
            calendar.require(ManualSave.model_validate(old["proposal"]).model_dump(mode='json') == proposal, "CALENDAR_REQUEST_IDENTITY_CONFLICT")
            await setup.rollback(session)
            return receipt(old, True)
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        calendar.require(user.timezone == proposal["timezone_name"], "CALENDAR_MOVE_TIMEZONE_CHANGED")
        current, parent, before = None, None, None
        if proposal["workout_id"]:
            current = await target(session, owner, proposal["workout_id"])
            reason = await edit_reason(session, owner, current)
            calendar.require(reason is None, reason or "MANUAL_WORKOUT_PROTECTED")
            calendar.require(source_hash(current) == proposal["expected_source_hash"], "MANUAL_WORKOUT_CHANGED")
            goals = await calendar.latest_goals(repository, session, owner, {("planned", str(current.id))})
            parent = goals.get(("planned", str(current.id)))
            calendar.require(proposal["expected_goal_reference"] == (calendar.reference(parent) if parent else None), "CALENDAR_REVISION_CONFLICT_RELOAD")
            before = calendar_moves.source(current)
        if proposal["copy_from"]:
            source = await target(session, owner, proposal["copy_from"])
            calendar.require(source_hash(source) == proposal["copy_source_hash"], "MANUAL_WORKOUT_CHANGED")
            calendar.require(all(b.parent_block_id is None and b.block_type != BlockType.REPEAT for b in source.blocks), "MANUAL_WORKOUT_COMPLEX_BLOCKS")
        rows, warnings = [], []
        if proposal["operation"] == "cancel":
            current.status = WorkoutStatus.CANCELLED
            current.updated_at = _now()
            rows.append(current)
        else:
            draft = proposal["draft"]
            known = {e["id"]: e["label"] for e in catalog()["exercises"]}
            for exercise in draft["exercises"]:
                calendar.require(exercise["exercise_id"] is None or known.get(exercise["exercise_id"]) == exercise["name"], "MANUAL_EXERCISE_UNKNOWN")
            for day in [draft["date"], *proposal["repeat_dates"]]:
                per_day = {**draft, "date": day}
                row = current
                if row is None:
                    row = PlannedWorkout(id=uuid5(NAMESPACE_URL, artifact_id + ":" + day), user_id=UUID(owner),
                        date=date.fromisoformat(day), sport=draft['sport'], title=draft['title'],
                        source="MANUAL", status=WorkoutStatus.PLANNED, raw_data={}, blocks=[])
                    session.add(row)
                await apply_draft(session, owner, row, per_day, user.timezone, artifact_id)
                if parent or draft["primary_goal"] is not None:
                    await append_goal(repository, owner, str(row.id), proposal["request_id"], draft["primary_goal"], parent)
                rows.append(row)
            # Inform rather than secretly cancelling another plan or changing a dose.
            occupied = list((await session.execute(select(PlannedWorkout.date).where(
                PlannedWorkout.user_id == UUID(owner), PlannedWorkout.date.in_([r.date for r in rows]),
                PlannedWorkout.id.not_in([r.id for r in rows]), PlannedWorkout.status.in_(ACTIVE),
            ).distinct())).scalars())
            warnings = [{"code": "OTHER_WORKOUT_ON_DAY", "date": d.isoformat()} for d in sorted(occupied)]
        await session.flush()
        value = {"schema_version": SCHEMA, "artifact_id": artifact_id, "athlete_id": owner,
            "created_at": _now().isoformat(), "proposal": proposal, "before": before,
            "workout_ids": [str(r.id) for r in rows], "after": [calendar_moves.source(r) for r in rows],
            "warnings": warnings, "provider_writeback": False, "actual_training_changed": False}
        value["content_hash"] = calendar.artifact_hash(value)
        saved = await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=artifact_id, athlete_id=owner,
            schema_version=SCHEMA, created_at=datetime.fromisoformat(value["created_at"]),
            content_hash_algorithm=CONTENT_HASH_ALGORITHM, content_hash=value["content_hash"], contract_json=canonical_json(value)))
        calendar.require(saved.status == AuditArtifactSaveStatus.CREATED, "MANUAL_WORKOUT_STORAGE_INVALID")
        verified = await load_receipt(repository, owner, artifact_id)
        calendar.require(verified == value, "MANUAL_WORKOUT_STORAGE_INVALID")
        await setup.commit(session)
        return receipt(value, False)
    except BaseException:
        await setup.rollback(session)
        raise
