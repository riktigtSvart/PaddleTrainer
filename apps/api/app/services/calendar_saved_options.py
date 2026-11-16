"""GET reads prepared choices. Only an explicit selection invokes the planner."""
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.entities import PlannedWorkout, WorkoutSession, User
from app.planning.application import calendar_workspace, register_athlete_setup as transactions
from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningLogicalPlanRow
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository as Repository
from app.services import training_plans as plans, training_read_models as views
from app.services import training_plan_policy as policy, training_alternative_availability as timing
from app.services.training_alternative_variants import variant
from app.services.calendar_training_projection import PlanningRead, latest_record, latest_scoped

SCHEMA = 'calendar-saved-options-v0.1'


async def target_row(session, owner, workout_id):
    row = (await session.execute(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
        PlannedWorkout.user_id == UUID(owner), PlannedWorkout.id == UUID(workout_id)))).scalar_one_or_none()
    plans.require(row is not None, 'CALENDAR_WORKOUT_NOT_FOUND')
    return row


async def available(session, owner, row, now, zone):
    if (row.source != policy.SOURCE or row.polar_target_id is not None or row.status.value not in {'PLANNED', 'DRAFT', 'SCHEDULED'}
            or row.date < now.astimezone(ZoneInfo(zone)).date()):
        return False
    linked = (await session.execute(select(WorkoutSession.id).where(WorkoutSession.user_id == UUID(owner),
        WorkoutSession.planned_workout_id == row.id).limit(1))).first()
    approved = (await session.execute(select(PlanningLogicalPlanRow.logical_plan_id).where(
        PlanningLogicalPlanRow.source_workout_id == row.id).limit(1))).first()
    low = datetime.combine(row.date, time.min, ZoneInfo(zone))
    high = datetime.combine(row.date + timedelta(days=1), time.min, ZoneInfo(zone))
    actual = (await session.execute(select(WorkoutSession.id).where(WorkoutSession.user_id == UUID(owner),
        WorkoutSession.started_at >= low, WorkoutSession.started_at < high, WorkoutSession.started_at <= now).limit(1))).first()
    return not (linked or approved or actual)


async def read(*, session, owner, workout_id):
    repository = Repository(session)
    transactions._require_session(repository, session)
    try:
        row = await target_row(session, owner, workout_id)
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        now = calendar_workspace._now()
        workout, hashed = plans.snapshot(row)
        marker = (row.raw_data or {}).get(policy.MARKER, {})
        base = {'schema_version': SCHEMA, 'athlete_id': owner, 'workout_id': workout_id,
            'workout_hash': hashed, 'date': row.date.isoformat(), 'timezone_name': user.timezone,
            'retrieved_at': now.isoformat(), 'planning_authorized': False, 'workouts_changed': False,
            'status': 'unavailable', 'source_review_reference': None, 'program_reference': None,
            'prepared_at': None, 'candidates': [], 'recommended_candidate_key': None}
        if not marker or not await available(session, owner, row, now, user.timezone):
            return {**base, 'content_hash': digest(base)}
        receipt = (await session.execute(select(PlanningAuditArtifactRow).where(
            PlanningAuditArtifactRow.athlete_id == UUID(owner),
            PlanningAuditArtifactRow.artifact_kind == Kind.TRAINING_PLAN_ACCEPTANCE.value,
            PlanningAuditArtifactRow.contract_json.contains('"' + workout_id + '":'),
        ).order_by(PlanningAuditArtifactRow.created_at.desc()).limit(1))).scalar_one_or_none()
        captured = plans.decode(repository._from_row(receipt), owner)['created_workouts'].get(workout_id) if receipt else None
        if not captured or captured['workout_hash'] != hashed or captured['marker'] != marker:
            return {**base, 'content_hash': digest(base)}
        source = (await views.load_many(repository, session, owner, Kind.TRAINING_PLAN_REVIEW, [marker.get('review_id')])).get(marker.get('review_id'))
        plans.require(source is not None and source['program_id'] == marker.get('program_id'), 'TRAINING_PLAN_STORAGE_INVALID')
        reader = PlanningRead(repository, owner)
        scope = {'schema_version': 'workout-alternatives-request-v0.1', 'workout_id': workout_id, 'expected_workout_hash': hashed}
        scoped = await latest_scoped(session, owner, {workout_id: (source['program_id'], scope)}, reader)
        regular = await latest_record(repository, session, owner, Kind.TRAINING_PLAN_REVIEW, source['program_id'], reader=reader)
        current = max((r for r in (source, regular, scoped.get(workout_id)) if r), key=reader.review_order)
        # The saved list is presentation evidence, never authority to skip the
        # fresh transactional check when an athlete actually chooses a card.
        group = next((g for g in current['result'].get('alternatives', []) if g['date'] == workout['date']), None)
        context = current['result'].get('prescription_context', {}).get('by_candidate', {})
        deadlines = current['result'].get('alternative_availability', {}).get('by_candidate', {})
        instructions = current['result'].get('instruction_context', {}).get('by_candidate', {})
        candidates = []
        for c in (group or {}).get('candidates', []):
            key = c['candidate_key']
            deadline = deadlines.get(key)
            if deadline is None or not timing.live(deadline, now):
                continue
            candidates.append({'candidate': c, 'timing': deadline, 'instructions': instructions.get(key),
                'workout_variant': variant(c, context.get(key)),
                'is_current': key == marker.get('candidate_key')})
        recommended = (group or {}).get('recommended_candidate_key')
        if not any(r['candidate']['candidate_key'] == recommended for r in candidates):
            ranked = sorted(candidates, key=lambda r: (r['timing']['goal_rank'], r['candidate']['capability_key'] !=
                next((c['capability_key'] for c in source['result']['create'] if c['candidate_key'] == marker.get('candidate_key')), None)))
            recommended = ranked[0]['candidate']['candidate_key'] if ranked else None
        base.update(status='ready', source_review_reference=reference(current), program_reference=source['program_reference'],
            prepared_at=current['created_at'], candidates=candidates, recommended_candidate_key=recommended)
        return {**base, 'content_hash': digest(base)}
    finally:
        await transactions.rollback(session)


async def choose(*, session, owner, workout_id, proposal):
    """A saved card is re-evaluated once with its exact dose as a preference."""
    repository = Repository(session)
    try:
        row = await target_row(session, owner, workout_id)
        _, hashed = plans.snapshot(row)
        plans.require(hashed == proposal['expected_workout_hash'], 'TRAINING_PLAN_ALTERNATIVES_NOT_AVAILABLE')
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        plans.require(await available(session, owner, row, calendar_workspace._now(), user.timezone), 'TRAINING_PLAN_ALTERNATIVES_NOT_AVAILABLE')
        source_id = proposal['source_review_reference']['artifact_id']
        source = (await views.load_many(repository, session, owner, Kind.TRAINING_PLAN_REVIEW, [source_id])).get(source_id)
        plans.require(source is not None and reference(source) == proposal['source_review_reference'], 'TRAINING_PLAN_REVIEW_CHANGED')
        marker = (row.raw_data or {}).get(policy.MARKER, {})
        plans.require(source['program_id'] == marker.get('program_id'), 'TRAINING_PLAN_REVIEW_CHANGED')
        candidate = next((c for g in source['result'].get('alternatives', []) if g['date'] == row.date.isoformat()
                          for c in g['candidates'] if c['candidate_key'] == proposal['candidate_key']), None)
        plans.require(candidate is not None, 'TRAINING_PLAN_ALTERNATIVE_NOT_AVAILABLE')
        deadline = source['result'].get('alternative_availability', {}).get('by_candidate', {}).get(candidate['candidate_key'])
        plans.require(deadline is not None and timing.live(deadline, calendar_workspace._now()), 'TRAINING_PLAN_ALTERNATIVE_EXPIRED')
        meta = source['result']['prescription_context']['by_candidate'].get(candidate['candidate_key'])
        physical = variant(candidate, meta)
        preferences = {candidate['date']: {**{k: candidate[k] for k in ('template_key', 'opportunity_key', 'capability_key', 'role')},
            'duration_sec': candidate['duration_sec'], 'workout_variant_hash': digest(physical)}}
        scope = {'schema_version': 'workout-alternatives-request-v0.1', 'workout_id': workout_id, 'expected_workout_hash': hashed}
        program_id, day = source['program_id'], row.date.isoformat()
        coordinated = source['result'].get('mesocycle_coordination', {}).get('mode') == 'coordinated'
    finally:
        await transactions.rollback(session)
    result = await plans.review(session=session, owner=owner, program_id=program_id, first=day, last=day,
        coordinate_mesocycles=coordinated, alternatives_for=scope, selection_preferences=preferences)
    reviewed = result['review']
    chosen = reviewed['result']['create']
    plans.require(not reviewed['result']['blockers'] and reviewed['result']['cancel'] == [workout_id] and len(chosen) == 1,
                  'TRAINING_PLAN_SAVED_OPTION_CHANGED')
    fresh_meta = reviewed['result']['prescription_context']['by_candidate'].get(chosen[0]['candidate_key'])
    plans.require(chosen[0]['opportunity_key'] == candidate['opportunity_key'] and variant(chosen[0], fresh_meta) == physical,
                  'TRAINING_PLAN_SAVED_OPTION_CHANGED')
    return result
