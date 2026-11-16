"""Weighted event intent and shared dated measurements through real owned HTTP."""
from copy import deepcopy
from uuid import UUID
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.planning.domain import event_demands as demands
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services.planning_goal_suggestions import build
from tests.planning.test_p2_4c5r2_athlete_setup import intake, profile, manual, get, post
from tests.planning.test_p2_4c18_planning_inputs import inputs, get as capture
from tests.planning.test_p2_4c18_3_strategy import source
from tests.planning.test_p2_4c5_cycle_creation import proposal, mesocycles, post as cycle_post
from tests.planning.test_p2_4c5r1_cycle_intent_and_boundaries import profile as event_profile
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER_EMAIL


def mass(token=217001, value='116.900', day='2026-10-20'):
    return dict(request_id=str(UUID(int=token)), value_kg=value, recorded_on=day, note='Reggeli mérés')


def goal(token=217010, kind='weight_loss', target='110.00', previous=None):
    return dict(request_id=str(UUID(int=token)), previous_reference=previous, goal=kind, target_kg=target, note='Saját szándék')


def long_profile(unit='km'):
    p=event_profile('1000')
    p.update(discipline='Kajak, síkvízi maraton', event_type='endurance', distance_status='specified',
        distance_value='10' if unit=='km' else '10000', distance_unit=unit, capability_basis=demands.BASIS,
        capability_keys=list(demands.KEYS), capability_weights=dict(zip(demands.KEYS, demands.VALUES['paddling_long_distance'])))
    return p


def long_program(token=217100, legacy=False):
    p=proposal(token=token)
    p['sport']='Kajak';p['start_date']='2026-10-23'
    p['macrocycles'][0].update(start_date='2026-10-23',end_date='2027-01-14',mesocycles=mesocycles('2026-10-23','2027-01-14'))
    e=dict(key='marathon-ob',title='Marathon OB 10 km',start_date='2027-01-14',end_date='2027-01-14',precision='exact',priority='main',status='planned',profile=long_profile())
    if legacy:
        e['profile'].update(capability_basis='unassessed',capability_keys=[]);e['profile'].pop('capability_weights')
    p['competitions']=[e]
    return p


@pytest.mark.parametrize('unit',['m','km'])
def test_long_event_has_complete_relative_priorities_without_claiming_percentages(unit):
    s=demands.suggest(long_profile(unit))
    assert s['template_key']=='paddling_long_distance' and len(s['weights'])==13
    assert s['weights']['MUSCULAR_ENDURANCE']==5 and s['weights']['MAX_STRENGTH']==3
    assert not s['training_percentages'] and len(s['sources'])==3


@pytest.mark.parametrize('sport,discipline',[('Futás','országút'),('Kajak','szlalom'),('Kajak','surfski')])
def test_unrelated_disciplines_do_not_borrow_flatwater_weights(sport,discipline):
    p=long_profile();p['discipline']=discipline
    assert demands.suggest(p,sport) is None


@pytest.mark.parametrize('legacy',[False,True])
def test_real_owned_capture_uses_long_distance_priorities_without_rewriting_saved_intent(inputs,legacy):
    p=long_program(217101+legacy,legacy)
    saved=cycle_post(inputs,'/programs',p)['artifact']
    inputs.url='/api/v1/planning/cycles/programs/'+saved['artifact_id']+'/planning-inputs'
    before=count(inputs,PlanningAuditArtifactRow)
    data=capture(inputs);s=data['goal_suggestions'];m=s['macrocycles'][0]
    assert s['schema_version']=='planning-goal-suggestions-v0.3'
    assert len(m['rows'])==13 and not m['unprofiled_event_keys']
    assert next(r for r in m['rows'] if r['capability_key']=='MUSCULAR_ENDURANCE')['demand_priority']==5
    assert not s['strategy']['demand_priorities']['training_percentages']
    assert count(inputs,PlanningAuditArtifactRow)==before
    stored=inputs.client.get('/api/v1/planning/cycles/programs/'+saved['artifact_id']).json()['program']['artifact']
    assert stored==saved
    specific=next(v for v in m['strategy_periods'] if v['phase']=='specific')
    primary={r['capability_key'] for r in m['rows'] for d in r['mesocycle_directives'] if d['mesocycle_period_id']==specific['mesocycle_period_id'] and d['role']=='primary_development'}
    assert primary=={'MUSCULAR_ENDURANCE','PACING_COMPETENCE'}


def test_auto_weights_cannot_be_relabelled_without_explicit_manual_basis(inputs):
    p=long_program();p['competitions'][0]['profile']['capability_weights']['MAX_STRENGTH']=5
    before=count(inputs,PlanningAuditArtifactRow)
    reply=inputs.client.post('/api/v1/planning/cycles/programs',json=p)
    assert reply.status_code==409,reply.text
    assert reply.json()['detail']['code']=='CYCLE_EVENT_DEMAND_PROFILE_DIFFERS'
    assert count(inputs,PlanningAuditArtifactRow)==before
    p['competitions'][0]['profile']['capability_basis']='coach_declared'
    assert inputs.client.post('/api/v1/planning/cycles/programs',json=p).status_code==201


def test_later_marathon_does_not_inherit_sprint_peak_scores():
    d=source();sprint=deepcopy(d['competitions'][0]);sprint.update(key='sprint',start_date='2026-12-25',end_date='2026-12-25')
    d['competitions'][0].update(start_date='2027-03-01',end_date='2027-03-01')
    sprint['profile']=event_profile('200');sprint['profile'].update(capability_basis=demands.BASIS,capability_keys=list(demands.KEYS),capability_weights=demands.suggest(sprint['profile'],'Kajak')['weights'])
    d['competitions'][0]['profile']=long_profile();d['competitions'].insert(0,sprint)
    m=build(d)['macrocycles'][0]
    last=next(v for v in m['strategy_periods'] if v['mesocycle_period_id']=='m3')
    assert last['phase']=='specific'
    primary={r['capability_key'] for r in m['rows'] for v in r['mesocycle_directives'] if v['mesocycle_period_id']=='m3' and v['role']=='primary_development'}
    assert primary=={'MUSCULAR_ENDURANCE','PACING_COMPETENCE'}


def test_dated_mass_history_exact_retry_and_latest_read_are_shared_with_profile(intake):
    a=post(intake,'body-mass',mass())
    first=get(intake,'body-mass');assert first['current']['value_kg']=='116.900' and first['total']==1
    assert post(intake,'body-mass',mass(),200)['artifact']==a['artifact']
    post(intake,'body-mass',mass(217002,'117.50','2026-10-01'))
    data=get(intake,'body-mass');assert data['total']==2 and data['current']==first['current']
    post(intake,'body-mass',mass(217003,'116.500','2026-10-20'))
    data=get(intake,'body-mass');assert data['total']==3 and data['current']['value_kg']=='116.500'
    context=get(intake,'context');assert context['body_mass']['current']==data['current']
    assert context['profile']['artifact']['proposal']['data']['body_mass_kg']=='116.500'
    assert get(intake,'body-mass?limit=1&offset=1')['items'][0]==data['items'][1]
    assert get(intake,'body-mass?limit=1&offset=1')['has_more']


def test_profile_and_manual_measurements_join_ledger_without_dropping_old_days(intake):
    p=profile(217020);p['data'].update(body_mass_kg='120',body_measurements_recorded_on='2026-10-01',height_cm='192')
    a=post(intake,'profiles',p)['artifact']
    p=profile(217021,a);p['data'].update(body_mass_kg='119.25',body_mass_recorded_on='2026-10-21',height_cm='192',body_measurements_recorded_on='2026-10-01')
    p['data']['manual_observations']=[manual('body_mass_kg','119.50',217022)]
    b=post(intake,'profiles',p)['artifact']
    state=get(intake,'body-mass');assert state['total']==3
    assert [r['value_kg'] for r in state['items']]==['119.25','119.50','120']
    # Explicitly recording an older personal measurement must not replace the current projection.
    p=profile(217023,b);p['data'].update(body_mass_kg='121',body_mass_recorded_on='2026-09-01')
    post(intake,'profiles',p)
    assert get(intake,'context')['body_mass']['current']['value_kg']=='119.25'
    assert get(intake,'profiles/'+a['artifact_id'])['artifact']==a


def test_nutrition_goal_is_cas_bound_and_never_writes_measured_mass(intake):
    post(intake,'body-mass',mass())
    before=get(intake,'context');history=get(intake,'body-mass')
    saved=post(intake,'nutrition-goal',goal())['artifact']
    assert get(intake,'context')==before
    assert get(intake,'body-mass')['items']==history['items']
    assert post(intake,'nutrition-goal',goal(),200)['artifact']==saved
    assert post(intake,'nutrition-goal',goal(217011),409)['detail']['code']=='NUTRITION_GOAL_CHANGED'
    ref={k:saved[k] for k in ('artifact_id','content_hash')}
    post(intake,'nutrition-goal',goal(217012,'weight_maintenance',None,ref))
    assert get(intake,'body-mass')['nutrition_goal']['proposal']['target_kg'] is None


@pytest.mark.parametrize('patch,status',[(dict(value_kg='0'),422),(dict(value_kg=True),422),(dict(recorded_on='2099-01-01'),409),(dict(recorded_on='2026-02-30'),422)])
def test_invalid_measurement_leaves_no_partial_profile_or_ledger(intake,patch,status):
    before=count(intake,PlanningAuditArtifactRow)
    post(intake,'body-mass',{**mass(),**patch},status)
    assert count(intake,PlanningAuditArtifactRow)==before


def test_request_reuse_owner_isolation_and_closed_queries(intake):
    post(intake,'body-mass',mass())
    assert post(intake,'body-mass',mass(value='115'),409)['detail']['code']=='BODY_REQUEST_CONFLICT'
    get(intake,'body-mass?owner=other',422);get(intake,'body-mass?limit=1&limit=2',422)
    intake.email=OTHER_EMAIL
    assert get(intake,'body-mass')['current'] is None
    post(intake,'body-mass',mass(value='90'))
    assert get(intake,'body-mass')['current']['value_kg']=='90'


def test_profile_failure_rolls_back_mass_and_profile_together(intake,monkeypatch):
    from app.planning.application import register_athlete_setup as service
    original=service.commit
    async def fail(session):raise RuntimeError('injected commit failure')
    monkeypatch.setattr(service,'commit',fail)
    post(intake,'body-mass',mass(),503)
    assert count(intake,PlanningAuditArtifactRow)==0
    monkeypatch.setattr(service,'commit',original)
    assert post(intake,'body-mass',mass())['committed']


def test_legacy_weight_intent_remains_available_after_training_goal_replacement(intake):
    from tests.planning.test_c21_6_sport_goals import replacement
    athlete=post(intake,'profiles',profile(217299))['artifact']
    p=long_program(217300)
    p['athlete_context']=dict(profile_reference={k:athlete[k] for k in ('artifact_id','content_hash')},availability_reference=None)
    p['goals']=[dict(key='weight_loss',body_mass=dict(current_kg='120',target_kg='110'),target_description='Korábbi saját cél')]
    a=cycle_post(intake,'/programs',p)
    before=get(intake,'body-mass')
    assert before['legacy_goals'][0]['body_mass']['current_kg']=='120'
    assert before['current'] is None  # Undated intent is not a dated measurement.
    changed=replacement(a,217301);changed['goals']=[dict(key='regular_activity',target_description='Rendszeres mozgás')]
    cycle_post(intake,'/programs',changed)
    after=get(intake,'body-mass')
    assert after['legacy_goals']==before['legacy_goals']
    assert after['current'] is None


def test_failure_during_profile_save_rolls_back_staged_mass(intake,monkeypatch):
    from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
    original=SqlAlchemyPlanningAuditRepository.save
    async def fail_profile(self,record):
        if record.artifact_kind.value=='athlete_profile':raise RuntimeError('injected profile save failure')
        return await original(self,record)
    monkeypatch.setattr(SqlAlchemyPlanningAuditRepository,'save',fail_profile)
    p=profile(217310);p['data'].update(body_mass_kg='118',body_mass_recorded_on='2026-10-20')
    post(intake,'profiles',p,503)
    assert count(intake,PlanningAuditArtifactRow)==0


def test_planning_capture_does_not_accept_a_measurement_committed_after_its_cutoff(inputs):
    from datetime import UTC, datetime
    from sqlalchemy import update
    post(inputs,'body-mass',mass(217320,'118','2026-10-20'))
    old=post(inputs,'body-mass',mass(217321,'120','2026-10-01'))['artifact']
    # This older-day entry does not change the current profile; its own durable time is still checked.
    with Session(inputs.engine) as session:
        session.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id==old['artifact_id']).values(persisted_at=datetime(2099,1,1,tzinfo=UTC)))
        session.commit()
    capture(inputs,status=503)
