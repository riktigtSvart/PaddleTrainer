"""Current planning-source bridge with real owned HTTP and isolated storage."""
from copy import deepcopy
from datetime import UTC,date,datetime,timedelta
from uuid import UUID
import pytest
from sqlalchemy import select,update
from sqlalchemy.orm import Session
from app.models.entities import AthleteReadiness,PlannedWorkout,TrainingPeriod,WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.domain.common.serialization import compute_content_hash
from app.planning.application import calendar_constraints
from app.services import planning_inputs as service
from tests.planning.test_p2_4c6_calendar_workspace import agenda as agenda_fixture,ACTUAL
from tests.planning.test_p2_4c5_cycle_creation import proposal,mesocycles,post as cycle_post
from tests.planning.test_p2_4c5r2_athlete_setup import profile,calendar,post as setup_post
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE,OTHER_EMAIL,count
BASE='/api/v1/planning/cycles'

@pytest.fixture
def inputs(tmp_path,monkeypatch):
    wrapper=agenda_fixture.__wrapped__(tmp_path,monkeypatch);env=next(wrapper)
    monkeypatch.setattr(service,'_now',env.clock.tick);monkeypatch.setattr(calendar_constraints,'_now',env.clock.tick)
    value=proposal();value['start_date']='2026-10-23';value['macrocycles'][0].update(start_date='2026-10-23',end_date='2027-01-14',mesocycles=mesocycles('2026-10-23','2027-01-14'))
    env.program=cycle_post(env,'/programs',value)['artifact'];env.url=BASE+'/programs/'+env.program['artifact_id']+'/planning-inputs'
    try:yield env
    finally:wrapper.close()

def get(env,query='?start_date=2026-10-23&end_date=2026-10-29',status=200):
    r=env.client.get(env.url+query);assert r.status_code==status,r.text;assert r.headers['Cache-Control']=='no-store';return r.json()

def macro_goals(env,role='maintenance',previous=None):
    macro=next(p for p in env.program['periods'] if p['period_type']=='MACROCYCLE');mesos=[p for p in env.program['periods'] if p['period_type']=='MESOCYCLE']
    proposal={'macrocycle_period_id':macro['id'],'revision':2 if previous else 1,'supersedes':{'artifact_id':previous['artifact_id'],'content_hash':previous['content_hash']} if previous else None,'goals':[{'capability_key':'VO2_CAPACITY','role':'primary_development','rationale':'explicit'}],'mesocycle_directives':[{'mesocycle_period_id':p['id'],'capability_key':'VO2_CAPACITY','role':role,'rationale':'explicit'} for p in mesos],'rationale':'test'}
    r=env.client.post('/api/v1/planning/goals/macrocycle-plans',json=proposal);assert r.status_code==201,r.text;return r.json()['artifact']

def test_complete_owned_current_capture_is_hashed_and_has_no_writes(inputs):
    profile_saved=setup_post(inputs,'profiles',profile())['artifact'];setup_post(inputs,'availability',calendar());goal=macro_goals(inputs)
    before=[count(inputs,t) for t in (PlanningAuditArtifactRow,PlannedWorkout,TrainingPeriod)]
    data=get(inputs);assert data['profile']['reference']['artifact_id']==profile_saved['artifact_id'];assert data['goal_versions'][0]['artifact']['artifact_id']==goal['artifact_id']
    assert data['days'][0]['capability_roles'][0]['role']=='maintenance';assert data['days'][0]['availability_state']=='opportunities'
    assert data['days'][0]['opportunities'][0]['constraints']['sports']==['Futás'];assert data['days'][0]['opportunities'][0]['constraints']['effort_cap']=='easy'
    assert data['profile']['data']['sport_history'][0]['sport']=='Kajak';assert data['planner_connection']['personal_model_applied'] is False
    assert all(data[k] is False for k in ('planning_authorized','workouts_created','workouts_changed','durable','has_more','historical_replay_supported'))
    body={k:v for k,v in data.items() if k!='content_hash'};assert compute_content_hash(body,exclude_fields=frozenset())==data['content_hash']
    assert [count(inputs,t) for t in (PlanningAuditArtifactRow,PlannedWorkout,TrainingPeriod)]==before
    assert all(not req.in_transaction() for req in inputs.requests)

@pytest.mark.parametrize('query',[
 '?start_date=2026-10-21&end_date=2026-10-24','?start_date=2026-10-29&end_date=2026-10-23',
 '?start_date=2026-10-23&end_date=2026-11-20','?start_date=2026-02-30&end_date=2026-10-25',
])
def test_invalid_or_historical_ranges_do_not_claim_a_capture(inputs,query):get(inputs,query,status=409)

@pytest.mark.parametrize('query',['?as_of=2025-01-01','?start_date=2026-10-23&start_date=2026-10-24'])
def test_unknown_and_duplicate_query_fields_rejected(inputs,query):get(inputs,query,status=422)

def test_foreign_owner_cannot_read_program_or_profile(inputs):
    setup_post(inputs,'profiles',profile());inputs.email=OTHER_EMAIL;get(inputs,status=404)

def test_missing_profile_and_days_stay_unknown_not_unrestricted(inputs):
    data=get(inputs);assert data['profile'] is None;assert data['days'][0]['availability_state']=='unknown';assert data['days'][0]['daily_max_minutes'] is None
    assert 'PROFILE_NOT_RECORDED' in data['gaps'];assert 'CAPABILITY_ROLES_NOT_DECLARED' in data['gaps'];assert data['declared_goals'][0]['key']=='regular_activity';assert not data['days'][0]['capability_roles']

def test_declared_unavailable_day_is_not_missing_availability_or_an_error(inputs):
    c=calendar(first='2026-10-23',length=1);c['data']['days'][0].update(status='unavailable',windows=[],max_total_minutes=None);setup_post(inputs,'availability',c)
    data=get(inputs,'?start_date=2026-10-23&end_date=2026-10-23');assert data['days'][0]['availability_state']=='declared_unavailable';assert 'AVAILABILITY_PARTLY_UNKNOWN' not in data['gaps']

def test_latest_explicit_goal_revision_is_used_without_inventing_roles(inputs):
    first=macro_goals(inputs);second=macro_goals(inputs,'permitted_decline',first);data=get(inputs);assert data['goal_versions'][0]['artifact']['artifact_id']==second['artifact_id'];assert data['days'][0]['capability_roles'][0]['role']=='permitted_decline'

def test_period_drift_is_rejected_instead_of_mixing_old_program_and_live_dates(inputs):
    p=next(p for p in inputs.program['periods'] if p['period_type']=='MESOCYCLE')
    with Session(inputs.engine) as db:db.execute(update(TrainingPeriod).where(TrainingPeriod.id==UUID(p['id'])).values(title='foreign edit'));db.commit()
    get(inputs,status=503)

def test_profile_hash_drift_is_not_silently_ignored(inputs):
    a=setup_post(inputs,'profiles',profile())['artifact']
    with Session(inputs.engine) as db:db.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id==a['artifact_id']).values(content_hash='f'*64));db.commit()
    get(inputs,status=503)

def test_recent_history_keeps_zero_distinct_from_missing_and_excludes_future_start(inputs):
    with Session(inputs.engine) as db:
        row=db.get(WorkoutSession,UUID(ACTUAL));row.started_at=datetime(2026,10,21,7,tzinfo=UTC);row.ended_at=datetime(2026,10,21,8,tzinfo=UTC);row.created_at=datetime(2026,10,21,tzinfo=UTC);row.duration_sec=0;row.distance_m=None;db.commit()
    data=get(inputs);assert data['recent_sessions'][0]['id']==ACTUAL;assert data['recent_sessions'][0]['duration_sec']==0;assert data['recent_sessions'][0]['distance_m'] is None
    with Session(inputs.engine) as db:db.get(WorkoutSession,UUID(ACTUAL)).started_at=datetime(2030,1,1,tzinfo=UTC);db.commit()
    assert not get(inputs)['recent_sessions']

def test_day_outside_selected_program_is_unassigned_not_guessed(inputs):
    data=get(inputs,'?start_date=2026-10-22&end_date=2026-10-22');assert data['days'][0]['mesocycle_id'] is None;assert 'MESOCYCLE_NOT_ASSIGNED_FOR_EVERY_DAY' in data['gaps']

def test_wire_float_decimal_text_and_unknown_preserved():
    assert service.wire({'zero':0.0,'missing':None,'bool':False,'precise':1e-10})=={'zero':'0.0','missing':None,'bool':False,'precise':'0.0000000001'}
    with pytest.raises(service.PlanningInputError):service.wire(float('inf'))

def test_manual_profile_and_calendar_limits_are_not_dose_authorization(inputs):
    p=profile();p['data']['participation']='paused';p['data']['typical_days_per_week']=0;setup_post(inputs,'profiles',p)
    data=get(inputs);assert data['profile']['data']['participation']=='paused';assert data['profile']['data']['typical_days_per_week']==0;assert data['planner_connection']['dose_policy_connected'] is False


def test_revisioned_feedback_correction_is_the_actual_input_not_provider_rpe(inputs,monkeypatch):
    from app.services import session_feedback
    from tests.planning.test_p2_4c11_session_feedback import body as feedback_body,post as feedback_post
    inputs.clock.current=datetime(2026,10,24,12,tzinfo=UTC);monkeypatch.setattr(session_feedback,'_now',inputs.clock.tick)
    feedback_post(inputs,feedback_body())
    data=get(inputs,'?start_date=2026-10-24&end_date=2026-10-30');assert data['feedback'][0]['fatigue_score']==0
    feedback_post(inputs,feedback_body(110002,expected_revision=1,rpe=None,fatigue=None,energy=None,comment='Correction: no score'))
    data=get(inputs,'?start_date=2026-10-24&end_date=2026-10-30');assert len(data['feedback'])==1;assert data['feedback'][0]['rpe_score'] is None and data['feedback'][0]['fatigue_score'] is None
    assert data['feedback'][0]['extra_data']['feedback_revision']==2


def test_calendar_rule_restrictions_and_single_budget_survive_busy_splitting(inputs):
    from tests.planning.test_p2_4c81_calendar_constraints import body,rule,details,post
    payload=body(rules=[rule(details=details('available',start_time='16:00',end_time='19:00',max_minutes=90,sport_scope='specified',sports=['Kajak'],effort_cap='easy',resources=['Hajó'])),rule(id=str(UUID(int=81004)),details=details(start_time='17:00',end_time='18:00'))])
    post(inputs,payload)
    data=get(inputs);group=data['days'][0]['opportunities'][0]
    assert group['constraints']['sports']==['Kajak'] and group['constraints']['resources']==['Hajó'];assert group['constraints']['effort_cap']=='easy'
    assert group['max_minutes']==90 and len(group['intervals'])==2;assert group['usable_minutes']==90;assert data['windows_share_budgets_across_days']


def test_recovery_fields_are_source_values_without_derived_readiness(inputs):
    with Session(inputs.engine) as db:
        db.add(AthleteReadiness(user_id=UUID(ATHLETE),recorded_date=date(2026,10,21),sleep_duration_sec=0,hrv_rmssd_ms=None,illness=True,travel=False,source='MANUAL'));db.commit()
    data=get(inputs);r=data['recovery_records'][0];assert r['sleep_duration_sec']==0 and r['hrv_rmssd_ms'] is None;assert r['illness'] is True;assert data['planner_connection']['personal_model_applied'] is False
