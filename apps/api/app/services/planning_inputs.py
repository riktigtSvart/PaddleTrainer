"""Current, owned planner-input bridge. No dose selection or plan mutation.

One read transaction, explicit version references and a hash of the captured
content. This is a current capture, not a claim about historical availability;
a future plan writer must revalidate sources rather than trusting this preview.
"""
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.entities import (
    AthleteReadiness,
    PlannedWorkout,
    TrainingPeriod,
    User,
    WorkoutSession,
)
from app.planning.application import calendar_constraints as calendar
from app.planning.application import create_cycle_program as programs
from app.planning.application import register_athlete_setup as setup
from app.planning.application import register_goal_protocol as goals
from app.planning.application import revise_cycle_boundary as boundaries
from app.planning.domain import athlete_setup
from app.planning.domain.common.serialization import (
    canonical_json,
    compute_content_hash,
    to_contract_primitive,
)
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.workouts import WorkoutOut
from app.services import feedback_learning

SCHEMA = 'planning-inputs-v0.1'
LIMIT = 2000

class PlanningInputError(ValueError):
    pass

def _now():
    return datetime.now(UTC)

def require(condition, code):
    if not condition:
        raise PlanningInputError(code)

def wire(value):
    """Decimal text avoids Python/JS float-canonicalization disagreements."""
    if isinstance(value, float):
        number = Decimal(str(value))
        require(number.is_finite(), 'PLANNING_INPUT_NONFINITE_SOURCE')
        return format(number, 'f')
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    if isinstance(value, list):
        return [wire(v) for v in value]
    return value

def ref(artifact, record):
    return {'artifact_id': artifact['artifact_id'], 'content_hash': artifact['content_hash'],
            'available_at': aware(record.persisted_at).isoformat()}

def known(record, cutoff):
    require(record.persisted_at is not None and aware(record.persisted_at) <= cutoff,
            'PLANNING_INPUT_SOURCE_CHANGED_RETRY')

async def goal_versions(repo, session, owner, periods, cutoff):
    ids = {p['id'] for p in periods}
    rows = (await session.execute(select(PlanningAuditArtifactRow).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner),
        PlanningAuditArtifactRow.artifact_kind.in_([goals.MACRO_KIND.value, goals.MESO_KIND.value]),
        PlanningAuditArtifactRow.persisted_at <= cutoff,
    ).order_by(PlanningAuditArtifactRow.artifact_id).limit(LIMIT+1))).scalars().all()
    require(len(rows) <= LIMIT, 'PLANNING_INPUT_GOAL_HISTORY_LIMIT')
    selected, cache = {}, {}
    for row in rows:
        # The validated artifact, rather than a JSON substring, decides its period.
        kind = goals.MACRO_KIND if row.artifact_kind == goals.MACRO_KIND.value else goals.MESO_KIND
        a, record = await goals._load(audit_repository=repo, athlete_id=owner, kind=kind,
            artifact_id=row.artifact_id, available_by=cutoff, cache=cache, visiting=set())
        period_id = a.proposal.macrocycle_period_id if kind == goals.MACRO_KIND else a.proposal.mesocycle_period_id
        if period_id not in ids:
            continue
        key = (kind.value, period_id)
        if key not in selected or a.proposal.revision > selected[key][0].proposal.revision:
            selected[key] = (a, record)
    return [dict(kind=kind, period_id=period_id, artifact=to_contract_primitive(a),
                 available_at=aware(record.persisted_at).isoformat())
            for (kind,period_id),(a,record) in sorted(selected.items())]

def daily_inputs(first, last, periods, schedule, versions):
    """Preserve source-window budgets; never sum overlapping opportunities."""
    declarations = {d['date']: d for d in (schedule['availability']['artifact']['proposal']['data']['days'] if schedule['availability'] else [])}
    result = []
    for i in range((last-first).days+1):
        day = (first+timedelta(days=i)).isoformat()
        windows = [w for w in schedule['opportunities'] if w['source_date'] == day or any(
            datetime.fromisoformat(v['start_at']).astimezone(ZoneInfo(schedule['timezone_name'])).date().isoformat() <= day <=
            (datetime.fromisoformat(v['end_at'])-timedelta(microseconds=1)).astimezone(ZoneInfo(schedule['timezone_name'])).date().isoformat()
            for v in w['intervals'])]
        declaration = declarations.get(day)
        if schedule['timezone_review_required']:
            state = 'unknown'
        elif declaration and declaration['status'] == 'unavailable' or day in schedule.get('training_options_override_days', []) and not windows:
            state = 'declared_unavailable'
        elif windows and all(w['known'] for w in windows):
            state = 'opportunities' if any(w['usable_minutes'] > 0 for w in windows) else 'blocked'
        else:
            state = 'unknown'
        mesos = [p for p in periods if p['period_type']=='MESOCYCLE' and p['start_date']<=day<=p['end_date']]
        meso = mesos[0] if len(mesos)==1 else None
        macro = next((v for v in versions if v['kind']==goals.MACRO_KIND.value and meso and v['period_id']==meso['parent_id']),None)
        directives = [d for d in macro['artifact']['proposal']['mesocycle_directives'] if d['mesocycle_period_id']==meso['id']] if macro and meso else []
        result.append({'date':day, 'availability_state':state, 'mesocycle_id':meso['id'] if meso else None,
            'capability_roles':directives, 'opportunities':windows,
            'daily_max_minutes':declaration['max_total_minutes'] if declaration else None})
    return result

async def capture(*, owner, identity, session, first=None, last=None, close_transaction=True, max_days=28):
    repo = SqlAlchemyPlanningAuditRepository(session)
    if close_transaction:
        setup._require_session(repo, session)
    try:
        cutoff = _now()
        require(cutoff.tzinfo is not None, 'PLANNING_INPUT_CLOCK_INVALID')
        user = (await session.execute(select(User).where(User.id==UUID(owner)))).scalar_one()
        today = cutoff.astimezone(ZoneInfo(user.timezone)).date()
        try:
            first = date.fromisoformat(first) if first else today
            last = date.fromisoformat(last) if last else first+timedelta(days=6)
        except ValueError:
            raise PlanningInputError('PLANNING_INPUT_RANGE_INVALID') from None
        require(1 <= max_days <= 366 and today <= first <= last and (last-first).days < max_days, 'PLANNING_INPUT_RANGE_INVALID')
        program, stored = await programs._load(repo, owner, programs.PROGRAM, identity)
        known(stored, cutoff)
        changes = await boundaries.head(repo,owner,program)
        events = await boundaries.head(repo,owner,program,kind=programs.EVENTS)
        for receipt in changes+events:
            require(datetime.fromisoformat(receipt['durable_available_at']) <= cutoff, 'PLANNING_INPUT_SOURCE_CHANGED_RETRY')
        periods = changes[-1]['artifact']['periods'] if changes else program['periods']
        rows = (await session.execute(select(TrainingPeriod).where(TrainingPeriod.user_id==UUID(owner),
            TrainingPeriod.id.in_([UUID(p['id']) for p in periods])))).scalars().all()
        boundaries.verify_rows({str(row.id):row for row in rows},periods,owner,identity)
        profile = await setup.latest(repo,session,owner,'profile')
        if profile:
            known(profile[1],cutoff)
        schedule = await calendar.projected(owner=owner,repository=repo,session=session,first=first.isoformat(),
            last=last.isoformat(),close_transaction=False,include_timings=True)
        for saved in [schedule['saved'],schedule['availability']]:
            if saved:
                require(datetime.fromisoformat(saved['durable_available_at']) <= cutoff, 'PLANNING_INPUT_SOURCE_CHANGED_RETRY')
        if schedule.get('training_options_available_at'):
            require(datetime.fromisoformat(schedule['training_options_available_at']) <= cutoff, 'PLANNING_INPUT_SOURCE_CHANGED_RETRY')
        plan_ids = [UUID(p['id']) for p in schedule['_plan_timings']]
        plan_rows = (await session.execute(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
            PlannedWorkout.user_id==UUID(owner), PlannedWorkout.id.in_(plan_ids)))).scalars().all() if plan_ids else []
        plans = {str(p.id):p for p in plan_rows}
        require(set(plans)=={str(p) for p in plan_ids},'PLANNING_INPUT_SOURCE_CHANGED_RETRY')
        existing_plans = [{'timing':p,'workout':WorkoutOut.model_validate(plans[p['id']]).model_dump(mode='json'),
            'authority_status':'current_application_projection_not_authoritative_revision'} for p in schedule['_plan_timings']]
        versions = await goal_versions(repo,session,owner,periods,cutoff)
        low = datetime.combine(today-timedelta(days=14),time.min,ZoneInfo(user.timezone)).astimezone(UTC)
        sessions = (await session.execute(select(WorkoutSession).where(WorkoutSession.user_id==UUID(owner),
            WorkoutSession.started_at>=low,WorkoutSession.started_at<=cutoff, WorkoutSession.created_at<=cutoff)
            .order_by(WorkoutSession.started_at,WorkoutSession.id).limit(LIMIT+1))).scalars().all()
        require(len(sessions)<=LIMIT,'PLANNING_INPUT_HISTORY_LIMIT')
        readiness = (await session.execute(select(AthleteReadiness).where(AthleteReadiness.user_id==UUID(owner),
            AthleteReadiness.recorded_date>=today-timedelta(days=14),AthleteReadiness.recorded_date<=today)
            .order_by(AthleteReadiness.recorded_date,AthleteReadiness.id).limit(16))).scalars().all()
        reports = await feedback_learning.daily_observations(session,owner,low,cutoff,cutoff)
        days = daily_inputs(first,last,periods,schedule,versions)
        gaps = []
        if not profile: gaps.append('PROFILE_NOT_RECORDED')
        if any(d['availability_state']=='unknown' for d in days):gaps.append('AVAILABILITY_PARTLY_UNKNOWN')
        if any(d['mesocycle_id'] is None for d in days):gaps.append('MESOCYCLE_NOT_ASSIGNED_FOR_EVERY_DAY')
        if any(d['mesocycle_id'] and not d['capability_roles'] for d in days):gaps.append('CAPABILITY_ROLES_NOT_DECLARED')
        if not reports:gaps.append('NO_RECENT_SELF_REPORT')
        if not readiness:gaps.append('NO_RECENT_RECOVERY_RECORD')
        if schedule['conflicts']:gaps.append('EXISTING_PLAN_CONFLICTS')
        if program['timezone_name']!=user.timezone:gaps.append('PROGRAM_TIMEZONE_REVIEW')
        current_periods = {p['id']:p for p in periods}
        for version in versions:
            frozen = version['artifact']['sources']
            if any(p['period_id'] in current_periods and any(p[k] != current_periods[p['period_id']][k] for k in ('start_date','end_date','title')) for p in frozen['hierarchy'] + frozen['mesocycles']):
                if 'GOAL_SOURCE_SNAPSHOT_CHANGED' not in gaps:gaps.append('GOAL_SOURCE_SNAPSHOT_CHANGED')
        for version in versions:
            if version['kind'] == goals.MESO_KIND.value:
                parent = next((v['artifact'] for v in versions if v['kind']==goals.MACRO_KIND.value and v['period_id']==current_periods[version['period_id']]['parent_id']),None)
                frozen = version['artifact']['macrocycle_source']
                if parent and (frozen['artifact_id'] != parent['artifact_id'] or frozen['content_hash'] != parent['content_hash']):
                    if 'MEASUREMENT_PROTOCOL_PARENT_OUTDATED' not in gaps:gaps.append('MEASUREMENT_PROTOCOL_PARENT_OUTDATED')
        intent = events[-1]['artifact']['proposal'] if events else program['proposal']
        data = {'schema_version' :SCHEMA,'athlete_id':owner,'program_reference':programs.domain.reference(program),
            'captured_at':cutoff.isoformat(),'timezone_name':user.timezone,'start_date':first.isoformat(),'end_date':last.isoformat(),
            'periods':periods,'competitions':intent['competitions'],
            'declared_goals':intent.get('goals',program['proposal']['goals']), 'program_sport':program['proposal']['sport'], 'goal_versions':versions,
            'profile':{'reference':ref(*profile),'data':profile[0]['proposal']['data']} if profile else None,
            'calendar_reference':schedule['reference'],'availability_reference':athlete_setup.reference(schedule['availability']['artifact']) if schedule['availability'] else None,
            **({'training_options_reference':schedule['training_options_reference']} if schedule.get('training_options_reference') else {}),
            'boundary_reference':programs.domain.reference(changes[-1]['artifact']) if changes else None,
            'competition_reference':programs.domain.reference(events[-1]['artifact']) if events else None,
            'days':days,'existing_plans':existing_plans,'existing_conflicts':schedule['conflicts'],
            'recent_sessions':[{'id':str(s.id),'name':s.name,'sport':s.sport.value,'started_at':aware(s.started_at).isoformat(),
                'ended_at':aware(s.ended_at).isoformat() if s.ended_at else None,'duration_sec':s.duration_sec,'distance_m':s.distance_m,
                'planned_workout_id':str(s.planned_workout_id) if s.planned_workout_id else None,
                **{key:getattr(s,key) for key in ('calories','avg_hr','max_hr','avg_speed','max_speed','avg_power','max_power','cardio_load','perceived_load','rpe')}} for s in sessions],
            'recovery_records':[{'id':str(s.id),'date':s.recorded_date.isoformat(),'source':s.source,
                **{k:getattr(s,k) for k in ('sleep_duration_sec','sleep_score','hrv_rmssd_ms','resting_hr_bpm','energy_score','fatigue_score','soreness_score','stress_score','readiness_score','illness','travel')}} for s in readiness],
            'recent_window':{'start_at':low.isoformat(),'end_at':cutoff.isoformat(),'coverage':'stored_records_only_not_exhaustive'},
            'feedback':to_contract_primitive(reports), 'gaps':gaps,
            'planner_connection':{'inputs_assembled':True,'workout_generator_connected':False,'dose_policy_connected':False,'personal_model_applied':False},
            'capture_finished_at':_now().isoformat(),'mutable_source_semantics':'current_read_span','historical_replay_supported':False,'windows_share_budgets_across_days':True,'revalidate_before_planning':True,'durable':False,'has_more':False,
            'planning_authorized':False,'workouts_created':False,'workouts_changed':False}
        from app.services.planning_goal_suggestions import build as suggest_goals
        data['goal_suggestions'] = suggest_goals(data)
        data = wire(data)
        require(len(canonical_json(data).encode('utf-8')) <= 4*1024*1024,'PLANNING_INPUT_SIZE_LIMIT')
        data['content_hash']=compute_content_hash(data,exclude_fields=frozenset())
        return data
    finally:
        if close_transaction:
            await setup.rollback(session)
