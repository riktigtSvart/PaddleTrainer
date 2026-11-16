"""Owner-serialized, append-only reviews and explicit atomic plan application."""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.entities import (
    AthleteReadiness,
    PlannedWorkout,
    User,
    WorkoutBlock,
    WorkoutSession,
    WorkoutStatus,
)
from app.planning.application import calendar_duration
from app.planning.application import create_cycle_program as programs
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.domain.persistence.audit import AuditArtifactRecord
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningAuditArtifactRow,
    PlanningLogicalPlanRow,
)
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.workouts import WorkoutOut
from app.services import planning_inputs
from app.services import training_execution_reconciliation as execution
from app.services import training_plan_policy as policy
from app.services import training_alternative_availability as alternative_availability
from app.services.training_alternative_variants import variant as workout_variant
from app.services import training_prescriptions as prescriptions
from app.services import training_strength_assessment as strength_assessment
from app.services import training_running

SCHEMA = "training-plan-v0.1"
LIMIT = 2000
logger = logging.getLogger(__name__)


class TrainingPlanError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise TrainingPlanError(code)


def _now():
    return datetime.now(UTC)


def identity(owner, operation, token):
    return "pt-training-plan:" + digest({"owner": owner, "operation": operation, "token": token})


def decode(record, owner):
    value = json.loads(record.contract_json)
    require(
        record.athlete_id == owner
        and value["athlete_id"] == owner
        and value["artifact_id"] == record.artifact_id
        and value["schema_version"] == record.schema_version == SCHEMA
        and value["content_hash"]
        == record.content_hash
        == digest({k: v for k, v in value.items() if k != "content_hash"})
        and canonical_json(value) == record.contract_json
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.persisted_at is not None,
        "TRAINING_PLAN_STORAGE_INVALID",
    )
    return value


async def records(repo, session, owner, kind, program_id=None):
    rows = (
        (
            await session.execute(
                select(PlanningAuditArtifactRow)
                .where(
                    PlanningAuditArtifactRow.athlete_id == UUID(owner),
                    PlanningAuditArtifactRow.artifact_kind == kind.value,
                    *([PlanningAuditArtifactRow.contract_json.contains('"program_id":' + json.dumps(program_id))] if program_id else []),
                )
                .order_by(PlanningAuditArtifactRow.created_at, PlanningAuditArtifactRow.artifact_id)
                .limit(LIMIT + 1)
            )
        )
        .scalars()
        .all()
    )
    require(len(rows) <= LIMIT, "TRAINING_PLAN_HISTORY_LIMIT")
    values = []
    for row in rows:
        value = decode(repo._from_row(row), owner)
        if program_id is None or value["program_id"] == program_id:
            values.append(value)
    return values


async def latest_history(repo, session, owner, program_id, scope=None, choice_request=None):
    condition = (PlanningAuditArtifactRow.contract_json.contains('"alternatives_for":' + canonical_json(scope))
                 if scope else ~PlanningAuditArtifactRow.contract_json.contains('"alternatives_for":'))
    row = (await session.execute(select(PlanningAuditArtifactRow).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner),
        PlanningAuditArtifactRow.artifact_kind == Kind.TRAINING_PLAN_REVIEW.value,
        PlanningAuditArtifactRow.contract_json.contains('"program_id":' + json.dumps(program_id)), condition,
        *([PlanningAuditArtifactRow.contract_json.contains('"choice_request":' + canonical_json(choice_request))] if choice_request else []),
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id.desc()).limit(1))).scalar_one_or_none()
    if row is None:
        return None
    value = decode(repo._from_row(row), owner)
    require(value['program_id'] == program_id and value.get('alternatives_for') == scope
            and (choice_request is None or value.get('choice_request') == choice_request), 'TRAINING_PLAN_STORAGE_INVALID')
    return value


async def persist(repo, owner, kind, value):
    value = planning_inputs.wire(value)
    value.update(schema_version=SCHEMA, athlete_id=owner)
    value["content_hash"] = digest(value)
    require(len(canonical_json(value).encode()) < 8 * 1024 * 1024, "TRAINING_PLAN_SIZE_LIMIT")
    record = AuditArtifactRecord(
        artifact_kind=kind,
        artifact_id=value["artifact_id"],
        athlete_id=owner,
        schema_version=SCHEMA,
        created_at=policy.at(value["created_at"]),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=value["content_hash"],
        contract_json=canonical_json(value),
    )
    await repo.save(record)
    require(
        decode(await repo.get(artifact_kind=kind, artifact_id=value["artifact_id"]), owner)
        == value,
        "TRAINING_PLAN_STORAGE_INVALID",
    )
    from app.services.training_read_models import save as save_read_model
    await save_read_model(repo, owner, kind, value)
    return value


def snapshot(row):
    value = WorkoutOut.model_validate(row).model_dump(mode="json")
    if row.planned_start_time:
        value["planned_start_time"] = aware(row.planned_start_time).isoformat()
    value["blocks"] = sorted(
        [{k: v for k, v in b.items() if k != "id"} for b in value["blocks"]],
        key=lambda b: b["position"],
    )
    raw = {k: v for k, v in (row.raw_data or {}).items() if k != policy.MARKER}
    value = planning_inputs.wire(value)
    return value, digest({"workout": value, "raw_data": planning_inputs.wire(raw)})


def resolved_preferences(preferences, result):
    resolved = {k: dict(v) for k, v in (preferences or {}).items()}
    for candidate in result['proposals']:
        row = resolved.get(candidate['date'])
        if row and row.get('workout_variant_hash') and row.get('template_key') == candidate['template_key'] and row.get('opportunity_key') == candidate['opportunity_key']:
            row['start_at'] = candidate['start_at']
    return resolved


def decision_key(data, plans, result, preferences, today):
    stable = {k: data[k] for k in (
        'athlete_id', 'program_reference', 'timezone_name', 'start_date', 'end_date',
        'periods', 'competitions', 'declared_goals', 'program_sport', 'goal_versions',
        'profile', 'calendar_reference', 'availability_reference', 'boundary_reference',
        'competition_reference', 'days', 'recent_sessions', 'running_background',
        'recovery_records', 'feedback', 'gaps', 'strength_assessment', 'strength_workout_context')}
    if data.get('same_day_replacement') is not None:
        stable['same_day_replacement'] = data['same_day_replacement']
    if data.get('alternatives_for') is not None:
        stable['alternatives_for'] = data['alternatives_for']
    return digest({'sources': {**stable, **({'training_options_reference': data['training_options_reference']} if data.get('training_options_reference') else {})},
        'plans': [{**p, 'duration_estimate': {k: v for k, v in p['duration_estimate'].items() if k != 'as_of'}
                   if p['duration_estimate'] else None} for p in plans],
        'result': execution.stable_result(result), 'local_today': today.isoformat(),
        **({'selection_preferences': resolved_preferences(preferences, result)} if preferences else {})})


def same_reviewed_mutation(viewed, fresh):
    """Unselected options may expire without changing an approved calendar edit.

    Every actual prescription, change and selected source must still be exact.
    The caller separately verifies every source and plan snapshot through the
    original decision key, and has already recalculated current eligibility.
    """
    old = viewed['result']
    if any(old.get(k) != fresh.get(k) for k in ('proposals', 'create', 'keep', 'cancel', 'protected_workout_ids', 'blockers', 'policy')):
        return False
    keys = {c['candidate_key'] for c in fresh['proposals']}
    return all({k: old.get(context, {}).get('by_candidate', {}).get(k) for k in keys} ==
               {k: fresh.get(context, {}).get('by_candidate', {}).get(k) for k in keys}
               for context in ('prescription_context', 'instruction_context'))


def scoped_history(history, alternatives_for):
    return [v for v in history if (v.get('alternatives_for') == alternatives_for if alternatives_for else not v.get('alternatives_for'))]


async def assess(session, repo, owner, program_id, first, last, active_window_end=None, selection_preferences=None, coordinate_mesocycles=None, calibration_review=None, same_day_replacement=None, alternatives_for=None):
    user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
    today_for_locks = _now().astimezone(ZoneInfo(user.timezone)).date()
    # These mutable records can also be corrected through older API paths.
    # Lock them before capture so the preview and the atomic writer see the
    # same values even when such an update does not take the owner lock.
    for model, column in (
        (WorkoutSession, WorkoutSession.started_at),
        (AthleteReadiness, AthleteReadiness.recorded_date),
        (PlannedWorkout, PlannedWorkout.date),
    ):
        boundary = (
            datetime.combine(today_for_locks - timedelta(days=prescriptions.HISTORY_DAYS + 1), datetime.min.time(), UTC)
            if model is WorkoutSession else today_for_locks - timedelta(days=15)
        )
        locked = (
            (
                await session.execute(
                    select(model.id)
                    .where(model.user_id == UUID(owner), column >= boundary)
                    .limit(LIMIT + 1)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        require(len(locked) <= LIMIT, "TRAINING_PLAN_WORKOUT_LIMIT")
        if model is PlannedWorkout and locked:
            await session.execute(
                select(WorkoutBlock.id).where(WorkoutBlock.workout_id.in_(locked)).with_for_update()
            )
    data = await planning_inputs.capture(
        owner=owner,
        identity=program_id,
        session=session,
        first=first,
        last=last,
        close_transaction=False,
        max_days=366,
        history_days=prescriptions.HISTORY_DAYS,
    )
    data['running_background'] = await training_running.capture_background(session, owner, data)
    data['strength_assessment'] = await strength_assessment.capture(
        session=session, repo=repo, owner=owner, user=user, data=data,
    )
    from app.services import strength_workout_log
    data['strength_workout_context'] = await strength_workout_log.capture(repo, session, owner, data)
    if same_day_replacement is not None:
        from app.schemas.training_plans import SameDayReplacement
        same_day_replacement = SameDayReplacement.model_validate(same_day_replacement).model_dump(mode='json')
        data['same_day_replacement'] = same_day_replacement
    if alternatives_for is not None:
        from app.schemas.training_plans import AlternativesFor
        alternatives_for = AlternativesFor.model_validate(alternatives_for).model_dump(mode='json')
        require(same_day_replacement is None and calibration_review is None, 'TRAINING_PLAN_ALTERNATIVES_SCOPE_INVALID')
        data['alternatives_for'] = alternatives_for
    assessment_ids = {v['artifact']['workout_session_id'] for v in data['strength_assessment']['guided_activities'] if v['artifact']['state'] == 'finished'}
    for row in data['recent_sessions']:
        if row['id'] in assessment_ids:
            row['reference_occasion'] = True
    data['content_hash'] = digest({k: v for k, v in data.items() if k != 'content_hash'})
    if calibration_review:
        stored_base = await repo.get(artifact_kind=Kind.TRAINING_PLAN_REVIEW, artifact_id=calibration_review["artifact_id"])
        require(stored_base is not None and decode(stored_base, owner) == calibration_review
                and calibration_review["program_id"] == program_id and not calibration_review.get("calibration_review"), "TRAINING_PLAN_CALIBRATION_CHANGED")
        original = calibration_review["inputs"]["recent_sessions"]
        source_rows = (await session.execute(select(WorkoutSession).where(
            WorkoutSession.user_id == UUID(owner), WorkoutSession.id.in_([UUID(s["id"]) for s in original])
        ).with_for_update())).scalars().all() if original else []
        sources = {str(row.id): row for row in source_rows}
        for source in original:
            row = sources.get(source["id"])
            require(row is not None and row.sport.value == source["sport"] and row.duration_sec == source["duration_sec"]
                    and aware(row.started_at) == policy.at(source["started_at"])
                    and (aware(row.ended_at) if row.ended_at else None) == (policy.at(source["ended_at"]) if source["ended_at"] else None), "TRAINING_PLAN_CALIBRATION_CHANGED")
    now = _now()
    today = now.astimezone(ZoneInfo(data["timezone_name"])).date()
    acceptances = await records(repo, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE, program_id)
    known = {key: value for a in acceptances for key, value in a["created_workouts"].items()}
    rows = (
        (
            await session.execute(
                select(PlannedWorkout)
                .options(selectinload(PlannedWorkout.blocks))
                .where(
                    PlannedWorkout.user_id == UUID(owner),
                    PlannedWorkout.date.between(
                        today - timedelta(days=14),
                        datetime.fromisoformat(data["end_date"]).date() + timedelta(days=6),
                    ),
                )
                .order_by(PlannedWorkout.date, PlannedWorkout.id)
                .limit(LIMIT + 1)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    require(len(rows) <= LIMIT, "TRAINING_PLAN_WORKOUT_LIMIT")
    ids = [row.id for row in rows]
    reconciliation = await execution.capture(
        session=session, repository=repo, owner=owner, plans=rows,
        sessions=data["recent_sessions"], cutoff=policy.at(data["captured_at"]),
        zone=data["timezone_name"],
        history_span=(policy.at(data["recent_window"]["start_at"]),
                      datetime.combine(today, datetime.min.time(), ZoneInfo(data["timezone_name"]))),
    )
    # Lock block edits and late execution-link inserts as part of the same
    # transaction. The owner lock serializes the application revision writers.
    if ids:
        await session.execute(
            select(WorkoutBlock.id).where(WorkoutBlock.workout_id.in_(ids)).with_for_update()
        )
    links = (
        set(
            (
                await session.execute(
                    select(WorkoutSession.planned_workout_id)
                    .where(
                        WorkoutSession.user_id == UUID(owner),
                        WorkoutSession.planned_workout_id.in_(ids),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if ids
        else set()
    )
    adopted = (
        set(
            (
                await session.execute(
                    select(PlanningLogicalPlanRow.source_workout_id).where(
                        PlanningLogicalPlanRow.athlete_id == UUID(owner),
                        PlanningLogicalPlanRow.source_workout_id.in_(ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if ids
        else set()
    )
    estimates = await calendar_duration.project(
        owner=owner, plans=rows, session=session, now=now, zone=data["timezone_name"]
    )
    links.update(UUID(item["workout_id"]) for item in reconciliation["resolved_links"])
    plans = []
    for row in rows:
        w, hashed = snapshot(row)
        receipt = known.get(str(row.id))
        marker = (row.raw_data or {}).get(policy.MARKER)
        owned = bool(
            receipt
            and marker == receipt["marker"]
            and row.source == policy.SOURCE
            and row.polar_target_id is None
        )
        replaceable = bool(
            owned
            and hashed == receipt["workout_hash"]
            and row.status in {WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED, WorkoutStatus.DRAFT}
            and row.planned_start_time
            and (aware(row.planned_start_time) > now or (same_day_replacement or alternatives_for) is not None
                 and (same_day_replacement or alternatives_for)["workout_id"] == str(row.id) and row.date == today)
            and (alternatives_for is None or alternatives_for['workout_id'] == str(row.id))
            and (not (marker or {}).get('selected_by_athlete') or
                 (alternatives_for or same_day_replacement or {}).get('workout_id') == str(row.id))
            and row.id not in links
            and row.id not in adopted
        )
        plans.append(
            {
                "workout": w,
                "workout_hash": hashed,
                "owned_sample": owned,
                "linked": row.id in links,
                "replaceable": replaceable,
                "template_key": receipt["template_key"] if receipt else None,
                "candidate_key": receipt["candidate_key"] if receipt else None,
                "duration_estimate": estimates.get(str(row.id)),
            }
        )
    if same_day_replacement is not None:
        target = next((p for p in plans if p['workout']['id'] == same_day_replacement['workout_id']),None)
        require(target is not None and target['replaceable'] and target['workout']['date'] == today.isoformat()
                and data['start_date'] <= today.isoformat() <= data['end_date'], 'TRAINING_PLAN_SAME_DAY_NOT_AVAILABLE')
    if alternatives_for is not None:
        target = next((p for p in plans if p['workout']['id'] == alternatives_for['workout_id']), None)
        require(target is not None and target['replaceable'] and target['workout_hash'] == alternatives_for['expected_workout_hash']
                and target['workout']['date'] >= today.isoformat()
                and data['start_date'] == data['end_date'] == target['workout']['date'], 'TRAINING_PLAN_ALTERNATIVES_NOT_AVAILABLE')
        target_day = datetime.fromisoformat(target['workout']['date']).date()
        day_start = datetime.combine(target_day, datetime.min.time(), ZoneInfo(data['timezone_name'])).astimezone(UTC)
        day_end = datetime.combine(target_day + timedelta(days=1), datetime.min.time(), ZoneInfo(data['timezone_name'])).astimezone(UTC)
        # A committed actual session is current evidence even if its provider
        # timestamp/created_at falls outside the historical replay snapshot.
        actual = (await session.execute(select(WorkoutSession.id).where(
            WorkoutSession.user_id == UUID(owner), WorkoutSession.started_at >= day_start,
            WorkoutSession.started_at < day_end, WorkoutSession.started_at <= now).limit(1))).scalar_one_or_none()
        require(actual is None, 'TRAINING_PLAN_ALTERNATIVES_NOT_AVAILABLE')
    result = policy.build(data, plans, now, active_window_end=active_window_end, selection_preferences=selection_preferences, reconciliation=reconciliation, coordinate_mesocycles=coordinate_mesocycles, calibration_review=calibration_review)
    if (same_day_replacement is not None or alternatives_for is not None) and not any(c['date'] == target['workout']['date'] for c in result['proposals']):
        result['blockers'].append('SAME_DAY_NO_REMAINING_OPTION' if same_day_replacement else 'WORKOUT_NO_REMAINING_ALTERNATIVE')
        result['create'], result['cancel'] = [], []
        result['keep'] = [p['workout']['id'] for p in plans if p['replaceable'] and data['start_date'] <= p['workout']['date'] <= data['end_date']]
    if any(day["reason"] == "SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE" for day in result["days_without_proposal"]):
        result["blockers"].append("SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE")
        result["create"], result["cancel"] = [], []
        result["keep"] = [plan["workout"]["id"] for plan in plans if plan["replaceable"] and data["start_date"] <= plan["workout"]["date"] <= data["end_date"]]
    alternative_availability.attach(data, result)
    key = decision_key(data, plans, result, selection_preferences, today)
    return data, plans, result, key, now, {str(row.id): row for row in rows}


async def review(*, session, owner, program_id, first=None, last=None, active_window_end=None, selection_preferences=None, choice_request=None, coordinate_mesocycles=None, reset_calibration=False, same_day_replacement=None, alternatives_for=None):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await transactions.lock_owner(session, owner)
        latest = await latest_history(repo, session, owner, program_id, alternatives_for)
        history = [latest] if latest else []
        if choice_request:
            replay = await latest_history(repo, session, owner, program_id, alternatives_for, choice_request)
            if replay:
                return {"review": replay, "reused": True}
            require(history and reference(history[-1]) == choice_request["review_reference"], "TRAINING_PLAN_REVIEW_CHANGED")
        if selection_preferences is None:
            selection_preferences = history[-1].get("selection_preferences", {}) if history and alternatives_for is None else {}
            if same_day_replacement and history:
                # A fresh manual search may recommend a different surviving
                # option; an expired earlier choice must not freeze today.
                today = _now().astimezone(ZoneInfo(history[-1]['timezone_name'])).date().isoformat()
                selection_preferences = {k: v for k, v in selection_preferences.items() if k != today}
        calibration_review = None
        if history and not reset_calibration and alternatives_for is None:
            source = history[-1].get("calibration_review") or history[-1]
            if source.get("coordinate_mesocycles") is True and first and last and source["start_date"] <= first <= last <= source["end_date"] and coordinate_mesocycles is not False:
                calibration_review = source
                coordinate_mesocycles = True
        if alternatives_for is not None:
            # The picker checks one day using current evidence, not the full
            # historical review tree. All other stored workouts stay fixed.
            if coordinate_mesocycles is None:
                coordinate_mesocycles = True
        data, plans, result, key, now, _ = await assess(
            session, repo, owner, program_id, first, last, active_window_end=active_window_end, selection_preferences=selection_preferences, coordinate_mesocycles=coordinate_mesocycles, calibration_review=calibration_review, same_day_replacement=same_day_replacement, alternatives_for=alternatives_for
        )
        if history and history[-1]["decision_key"] == key:
            return {"review": history[-1], "reused": True}
        previous = reference(history[-1]) if history else None
        # Time is evidence only. It cannot cause a new revision on every poll.
        value = {
            "artifact_id": identity(
                owner, "review", {"program": program_id, "previous": previous, "key": key}
            ),
            "program_id": program_id,
            "created_at": now.isoformat(),
            "previous_reference": previous,
            "decision_key": key,
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "timezone_name": data["timezone_name"],
            "active_window_end": active_window_end,
            "coordinate_mesocycles": result["mesocycle_coordination"]["mode"] == "coordinated",
            "calibration_review": calibration_review,
            **({"same_day_replacement": same_day_replacement} if same_day_replacement is not None else {}),
            **({'alternatives_for': alternatives_for} if alternatives_for is not None else {}),
            "program_reference": data["program_reference"],
            "inputs": data,
            "plan_snapshots": plans,
            "result": result,
            "committed_plan": False,
            "requires_explicit_acceptance": True,
            "selection_preferences": resolved_preferences(selection_preferences, result),
            **({"choice_request": choice_request} if choice_request else {}),
        }
        value = await persist(repo, owner, Kind.TRAINING_PLAN_REVIEW, value)
        await transactions.commit(session)
        return {"review": value, "reused": False}
    finally:
        await transactions.rollback(session)


async def choose(*, session, owner, program_id, proposal):
    """A choice recalculates a review; applying workouts remains a separate write."""
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        saved = await repo.get(artifact_kind=Kind.TRAINING_PLAN_REVIEW, artifact_id=proposal["review_reference"]["artifact_id"])
        require(saved is not None and saved.athlete_id == owner, "TRAINING_PLAN_REVIEW_CHANGED")
        viewed = decode(saved, owner)
        require(viewed["program_id"] == program_id and reference(viewed) == proposal["review_reference"], "TRAINING_PLAN_REVIEW_CHANGED")
        group = next((item for item in viewed["result"].get("alternatives", []) if item["date"] == proposal["date"]), None)
        candidate = next((item for item in group["candidates"] if item["candidate_key"] == proposal["candidate_key"]), None) if group else None
        require(candidate is not None, "TRAINING_PLAN_ALTERNATIVE_NOT_AVAILABLE")
        timing = viewed['result'].get('alternative_availability', {}).get('by_candidate', {}).get(candidate['candidate_key'])
        if timing is None:
            timing = alternative_availability.derive(viewed['inputs'], candidate)
        require(alternative_availability.live(timing, _now()), 'TRAINING_PLAN_ALTERNATIVE_EXPIRED')
        preference = {key: candidate[key] for key in ('template_key', 'opportunity_key', 'capability_key', 'role')}
        if timing is not None:
            metadata = viewed['result'].get('prescription_context', {}).get('by_candidate', {}).get(candidate['candidate_key'])
            preference.update(duration_sec=candidate['duration_sec'], start_at=candidate['start_at'],
                              workout_variant_hash=digest(workout_variant(candidate, metadata)))
        preferences = {**viewed.get("selection_preferences", {}), proposal["date"]: preference}
    finally:
        await transactions.rollback(session)
    return await review(session=session, owner=owner, program_id=program_id, first=viewed["start_date"], last=viewed["end_date"], active_window_end=viewed.get("active_window_end"), selection_preferences=preferences, choice_request=proposal, coordinate_mesocycles=viewed.get("coordinate_mesocycles"), same_day_replacement=viewed.get("same_day_replacement"), alternatives_for=viewed.get('alternatives_for'))


async def status(*, session, owner, program_id):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await programs._load(repo, owner, programs.PROGRAM, program_id)
        from app.services.calendar_training_projection import latest_record
        reviewed = await latest_record(repo, session, owner, Kind.TRAINING_PLAN_REVIEW, program_id)
        acceptance = await latest_record(repo, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE, program_id)
        return {
            "review": reviewed,
            "acceptance": acceptance,
            "automatic_review_interval_seconds": 60,
        }
    finally:
        await transactions.rollback(session)


async def retry(repo, owner, operation, proposal, kind):
    key = identity(owner, operation, proposal["request_id"])
    saved = await repo.get(artifact_kind=kind, artifact_id=key)
    if saved:
        value = decode(saved, owner)
        require(value["proposal"] == proposal, "TRAINING_PLAN_REQUEST_CONFLICT")
        return {"artifact": value, "reused": True, "committed": True}
    return None


async def accept(*, session, owner, program_id, proposal, automation_reference=None):
    proposal = {**proposal, "program_id": program_id,
                **({'automatic_policy_reference': automation_reference} if automation_reference else {})}
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await transactions.lock_owner(session, owner)
        if automation_reference:
            from app.services.automatic_planning import require_current
            await require_current(repo, session, owner, program_id, automation_reference)
        previous = await retry(repo, owner, "accept", proposal, Kind.TRAINING_PLAN_ACCEPTANCE)
        if previous:
            return previous
        saved = await repo.get(
            artifact_kind=Kind.TRAINING_PLAN_REVIEW,
            artifact_id=proposal["review_reference"]["artifact_id"],
        )
        require(saved is not None and saved.athlete_id == owner, "TRAINING_PLAN_REVIEW_CHANGED")
        viewed = decode(saved, owner)
        require(
            viewed["program_id"] == program_id
            and reference(viewed) == proposal["review_reference"],
            "TRAINING_PLAN_REVIEW_CHANGED",
        )
        latest = await latest_history(repo, session, owner, program_id, viewed.get('alternatives_for'))
        history = [latest] if latest else []
        require(bool(history), 'TRAINING_PLAN_REVIEW_CHANGED')
        require(reference(history[-1]) == reference(viewed), "TRAINING_PLAN_REVIEW_CHANGED")
        for candidate in viewed['result']['create']:
            timing = viewed['result'].get('alternative_availability', {}).get('by_candidate', {}).get(candidate['candidate_key'])
            require(timing is None or alternative_availability.live(timing, _now()), 'TRAINING_PLAN_ALTERNATIVE_EXPIRED')
        require(
            viewed["start_date"]
            >= _now().astimezone(ZoneInfo(viewed["timezone_name"])).date().isoformat(),
            "TRAINING_PLAN_REVIEW_CHANGED",
        )
        data, _plans, result, key, now, rows = await assess(
            session,
            repo,
            owner,
            program_id,
            viewed["start_date"],
            viewed["end_date"],
            active_window_end=viewed.get("active_window_end"),
            selection_preferences=viewed.get("selection_preferences", {}),
            coordinate_mesocycles=viewed.get("coordinate_mesocycles"),
            calibration_review=viewed.get("calibration_review"),
            same_day_replacement=viewed.get("same_day_replacement"),
            alternatives_for=viewed.get('alternatives_for'),
        )
        require(not automation_reference or not (viewed.get('same_day_replacement') or viewed.get('alternatives_for')),
                'TRAINING_PLAN_SAME_DAY_NOT_AVAILABLE')
        unchanged_manual_edit = bool((viewed.get('same_day_replacement') or viewed.get('alternatives_for')) and not automation_reference
            and same_reviewed_mutation(viewed, result)
            and decision_key(data, _plans, viewed['result'], viewed.get('selection_preferences'),
                             now.astimezone(ZoneInfo(viewed['timezone_name'])).date()) == viewed['decision_key'])
        require(key == viewed["decision_key"] or unchanged_manual_edit, "TRAINING_PLAN_REVIEW_CHANGED")
        require(
            not result["blockers"] and (result["create"] or result["cancel"]),
            "TRAINING_PLAN_NO_CHANGES",
        )
        if viewed.get('alternatives_for'):
            require(result['cancel'] == [viewed['alternatives_for']['workout_id']]
                    and len(result['create']) == len(result['proposals']) == 1
                    and result['create'][0]['date'] == viewed['start_date'] == viewed['end_date'], 'TRAINING_PLAN_ALTERNATIVES_SCOPE_INVALID')
        created = {}
        for candidate in result["create"]:
            require(policy.at(candidate["start_at"]) >= now if (viewed.get('same_day_replacement') or viewed.get('alternatives_for')) else policy.at(candidate["start_at"]) > now, "TRAINING_PLAN_REVIEW_CHANGED")
            plan_id = uuid5(
                NAMESPACE_URL,
                f"paddletrainer:{owner}:{viewed['artifact_id']}:{candidate['candidate_key']}",
            )
            marker = {
                "program_id": program_id,
                "review_id": viewed["artifact_id"],
                "candidate_key": candidate["candidate_key"],
                **({'selected_by_athlete': True} if viewed.get('alternatives_for') else {}),
            }
            row = PlannedWorkout(
                id=plan_id,
                user_id=UUID(owner),
                date=datetime.fromisoformat(candidate["date"]).date(),
                training_period_id=UUID(candidate["training_period_id"]),
                planned_start_time=policy.at(candidate["start_at"]),
                sport=candidate["sport"],
                title=candidate["title"],
                description=candidate["description"],
                duration_sec=candidate["duration_sec"],
                status=WorkoutStatus.PLANNED,
                source=policy.SOURCE,
                raw_data={policy.MARKER: marker, **({'paddletrainer_strength_prescription': candidate['strength_prescription']}
                                                  if 'strength_prescription' in candidate else {})},
                blocks=[WorkoutBlock(**b) for b in candidate["blocks"]],
            )
            session.add(row)
            await session.flush()
            _, hashed = snapshot(row)
            created[str(plan_id)] = {
                "workout_hash": hashed,
                "marker": marker,
                "candidate_key": candidate["candidate_key"],
                "template_key": candidate["template_key"],
            }
        for key in result["cancel"]:
            rows[key].status = WorkoutStatus.CANCELLED
            rows[key].updated_at = now
        await session.flush()
        artifact = await persist(
            repo,
            owner,
            Kind.TRAINING_PLAN_ACCEPTANCE,
            {
                "artifact_id": identity(owner, "accept", proposal["request_id"]),
                "program_id": program_id,
                "created_at": now.isoformat(),
                "proposal": proposal,
                "review_reference": reference(viewed),
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "coordinate_mesocycles": viewed.get("coordinate_mesocycles"),
                **({'alternatives_for': viewed['alternatives_for']} if viewed.get('alternatives_for') else {}),
                "created_workouts": created,
                "cancelled_workout_ids": result["cancel"],
                "kept_workout_ids": result["keep"],
                "authority_scope": "user_enabled_automatic_application_sample_plan" if automation_reference else "explicitly_reviewed_current_application_sample_plan",
                **({'automatic_policy_reference': automation_reference} if automation_reference else {}),
                "personal_model_applied": False,
                "provider_writeback": False,
            },
        )
        await transactions.commit(session)
        return {"artifact": artifact, "reused": False, "committed": True}
    finally:
        await transactions.rollback(session)


async def confirm_missed(*, session, owner, program_id, proposal):
    proposal = {**proposal, "program_id": program_id}
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await transactions.lock_owner(session, owner)
        saved = await retry(repo, owner, "missed", proposal, Kind.TRAINING_PLAN_OUTCOME)
        if saved:
            return saved
        user = await programs.timezone_for(session, owner)
        today = _now().astimezone(ZoneInfo(user)).date().isoformat()
        _, plans, _, _, now, rows = await assess(session, repo, owner, program_id, today, today)
        plan = next((p for p in plans if p["workout"]["id"] == proposal["workout_id"]), None)
        require(
            plan is not None
            and plan["owned_sample"]
            and not plan["linked"]
            and plan["workout_hash"] == proposal["expected_workout_hash"],
            "TRAINING_PLAN_OUTCOME_CHANGED",
        )
        w = plan["workout"]
        require(
            w["status"] in {"PLANNED", "DRAFT", "SCHEDULED"}
            and w["planned_start_time"]
            and w["duration_sec"] is not None
            and policy.at(w["planned_start_time"]) + timedelta(seconds=w["duration_sec"]) <= now,
            "TRAINING_PLAN_OUTCOME_NOT_ELAPSED",
        )
        rows[w["id"]].status = WorkoutStatus.SKIPPED
        rows[w["id"]].updated_at = now
        await session.flush()
        value = await persist(
            repo,
            owner,
            Kind.TRAINING_PLAN_OUTCOME,
            {
                "artifact_id": identity(owner, "missed", proposal["request_id"]),
                "program_id": program_id,
                "proposal": proposal,
                "created_at": now.isoformat(),
                "previous_workout": plan,
                "outcome": "athlete_confirmed_missed",
                "automatic_compensation": False,
            },
        )
        await transactions.commit(session)
        return {"artifact": value, "reused": False, "committed": True}
    finally:
        await transactions.rollback(session)


async def refresh_active(session, owner):
    """Catch up persisted events and elapsed windows, including after restart."""
    repo = SqlAlchemyPlanningAuditRepository(session)
    try:
        acceptances = [v for v in await records(repo, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE) if not v.get('alternatives_for')]
        reviews = [v for v in await records(repo, session, owner, Kind.TRAINING_PLAN_REVIEW) if not v.get('alternatives_for')]
        timezone_name = await programs.timezone_for(session, owner)
        today = _now().astimezone(ZoneInfo(timezone_name)).date().isoformat()
        # A first review may be blocked before the user can accept any plan.
        # New stored sync evidence must refresh that reviewed programme too.
        programs_to_review = {a["program_id"]: a for a in acceptances}
        for viewed in reviews:
            previous = programs_to_review.get(viewed["program_id"])
            if viewed["end_date"] >= today and (not previous or policy.at(viewed["created_at"]) >= policy.at(previous["created_at"])):
                programs_to_review[viewed["program_id"]] = viewed
    finally:
        await transactions.rollback(session)
    results = []
    for program_id, accepted in programs_to_review.items():
        if (
            today
            > (datetime.fromisoformat(accepted["end_date"]).date() + timedelta(days=14)).isoformat()
        ):
            continue
        first = max(today, accepted["start_date"])
        last = max(first, accepted["end_date"])
        try:
            results.append(
                await review(
                    session=session,
                    owner=owner,
                    program_id=program_id,
                    first=first,
                    last=last,
                    active_window_end=accepted["end_date"],
                    coordinate_mesocycles=accepted.get("coordinate_mesocycles"),
                )
            )
        except Exception:
            logger.exception("Programme review failed; later programmes will still be checked")
            results.append({"program_id": program_id, "error": "retry_required"})
    return results
