"""A fully populated strategic starter; no invented personal model, dose or date mutation."""
from copy import deepcopy
from datetime import date,timedelta
import pytest
from app.services.planning_goal_suggestions import build
from app.services.planning_strategy import phase_at,segments
from tests.planning.test_p2_4c18_planning_inputs import inputs,get,macro_goals
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL
KEYS=['TECHNICAL_SKILL','MAX_STRENGTH','PERIPHERAL_OXIDATIVE_CAPACITY','VO2_CAPACITY','POWER_RFD','SPRINT_SPEED_AND_START','MUSCULAR_ENDURANCE','HIGH_INTENSITY_AND_ANAEROBIC_PROFILE']
def source():
    first=date(2026,10,30);children=[]
    for i in range(4):
        start=first+timedelta(days=i*28);end=start+timedelta(days=27)
        children.append({'id':f'm{i}','parent_id':'macro','period_type':'MESOCYCLE','title':f'Blokk {i+1}','start_date':start.isoformat(),'end_date':end.isoformat()})
    macro={'id':'macro','parent_id':None,'period_type':'MACROCYCLE','title':'Szezon','start_date':first.isoformat(),'end_date':children[-1]['end_date']}
    event={'key':'race','title':'Főverseny','status':'planned','priority':'main','precision':'exact','start_date':macro['end_date'],'end_date':macro['end_date'],'profile':{'capability_basis':'coach_declared','capability_keys':KEYS,'distance_value':'1000','distance_unit':'m'}}
    return {'periods':[macro,*children],'competitions':[event],'declared_goals':[],'goal_versions':[],'profile':None,'feedback':[],'recovery_records':[],'program_sport':'Kajak','timezone_name':'Europe/Budapest','captured_at':'2026-10-30T12:00:00+00:00'}
def test_no_history_produces_complete_differentiated_theoretical_plan():
    d=source();before=deepcopy(d);s=build(d);m=s['macrocycles'][0]
    assert d==before and s['periodization_inferred'];assert s['rules_version']=='mesocycle-strategy-v0.1'
    assert all(r['role'] is not None and all(v['role'] is not None for v in r['mesocycle_directives']) for r in m['rows'])
    assert m['strategy_periods'][0]['phase']=='foundation';assert any(v['phase']=='specific' for v in m['strategy_periods'])
    for p in m['strategy_periods']:
        assert sum(next(v for v in r['mesocycle_directives'] if v['mesocycle_period_id']==p['mesocycle_period_id'])['role']=='primary_development' for r in m['rows'])<=2
    assert not s['strategy']['personal_response_model']['applied'];assert not s['dose_selected'];assert not s['committed']
    assert not s['strategy']['boundaries_changed'] and not s['strategy']['race_dates_changed']
def test_race_inside_mesocycle_does_not_make_whole_block_a_taper():
    d=source();m=build(d)['macrocycles'][0];last=m['strategy_periods'][-1]
    assert {p['phase'] for p in last['segments']}=={'specific','race_readiness'}
    assert last['segments'][0]['start_date']==d['periods'][-1]['start_date'];assert last['segments'][-1]['end_date']==d['periods'][-1]['end_date']
def test_window_event_is_not_falsely_anchored_as_exact_taper():
    d=source();e=d['competitions'][0];e.update(precision='window',end_date=(date.fromisoformat(e['end_date'])+timedelta(days=7)).isoformat())
    s=build(d);assert all(v['phase']!='race_readiness' for p in s['macrocycles'][0]['strategy_periods'] for v in p['segments'])
def test_supporting_race_does_not_create_main_race_taper():
    d=source();d['competitions'][0]['priority']='supporting';s=build(d)
    assert all(v['phase']=='general' for p in s['macrocycles'][0]['strategy_periods'] for v in p['segments'])
def test_close_main_races_do_not_restart_foundation():
    d=source();e=d['competitions'][0];second=deepcopy(e);second.update(key='second',title='Második',start_date='2027-02-25',end_date='2027-02-25')
    phase,anchor=phase_at(date(2027,2,19),[e,second],date(2026,10,30));assert phase=='race_readiness' and anchor['key']=='second'
def test_next_macro_race_can_anchor_previous_preparation():
    d=source();d['periods'][0]['end_date']='2027-01-01';s=build(d)
    assert s['macrocycles'][0]['rows'] and s['macrocycles'][0]['strategy_periods'][0]['segments'][0]['event_key']=='race'
def test_beginner_and_returning_do_not_get_anaerobic_development_by_default():
    d=source();d['profile']={'data':{'sport_history_status':'none','interruption':'none','participation':'unrestricted'}}
    for row in build(d)['macrocycles'][0]['rows']:
        if row['capability_key']=='HIGH_INTENSITY_AND_ANAEROBIC_PROFILE':assert all(v['role']=='maintenance' for v in row['mesocycle_directives'])
@pytest.mark.parametrize('participation',['paused','professional_review'])
def test_participation_hold_keeps_complete_nonprescriptive_roles(participation):
    d=source();d['profile']={'data':{'participation':participation}}
    s=build(d);assert s['strategy']['profile_context']['restricted'];assert all(v['role']=='maintenance' for r in s['macrocycles'][0]['rows'] for v in r['mesocycle_directives'])
def test_explicit_maintenance_goal_is_not_reinterpreted_as_development():
    d=source();d['competitions']=[];d['declared_goals']=[{'key':'strength','details':{'direction':'maintain'}}]
    r=build(d)['macrocycles'][0]['rows'][0];assert r['role']=='maintenance';assert all(v['role']=='maintenance' for v in r['mesocycle_directives'])
def test_immediate_fatigue_is_not_a_chronic_adaptation_claim():
    d=source();d['feedback']=[{'id':'f','recorded_at':'2026-10-30T11:00:00+00:00','response_timing':'IMMEDIATE','fatigue_score':10}]
    assert not build(d)['strategy']['recent_review_signals']
def test_recent_next_morning_signal_is_local_overlay_not_entire_meso_rewrite():
    d=source();before=build(d);d['feedback']=[{'id':'f','recorded_at':'2026-10-30T11:00:00+00:00','response_timing':'NEXT_MORNING','fatigue_score':8}]
    after=build(d);assert after['strategy']['recent_review_signals'][0]['source_id']=='f';assert after['macrocycles'][0]['strategy_periods'][0]['current_overlay']=='review_recovery'
    assert after['macrocycles'][0]['rows'][0]['role']==before['macrocycles'][0]['rows'][0]['role'];assert all(p['current_overlay'] is None for p in after['macrocycles'][0]['strategy_periods'][1:])
def test_stale_and_future_feedback_are_not_used():
    d=source();d['feedback']=[{'id':'old','recorded_at':'2026-10-20T11:00:00+00:00','response_timing':'NEXT_MORNING','fatigue_score':9},{'id':'future','recorded_at':'2026-11-20T11:00:00+00:00','response_timing':'NEXT_MORNING','fatigue_score':9}]
    assert not build(d)['strategy']['recent_review_signals']
def test_current_recorded_roles_win_even_if_theoretical_ranking_differs(inputs):
    a=macro_goals(inputs,'permitted_decline');s=get(inputs)['goal_suggestions'];r=s['macrocycles'][0]['rows'][0]
    assert r['origin']=='recorded' and r['rationale']=='explicit';assert all(v['role']=='permitted_decline' for v in r['mesocycle_directives'])
def test_owned_http_complete_strategy_saves_and_flows_back_to_daily_inputs(inputs):
    data=get(inputs);data['declared_goals']=[{'key':'strength','details':{'direction':'improve'}}]
    m=build(data)['macrocycles'][0];proposal={'macrocycle_period_id':m['macrocycle_period_id'],'revision':1,'supersedes':None,'goals':[{k:r[k] for k in ('capability_key','role','rationale')} for r in m['rows']],
    'mesocycle_directives':[dict(v,capability_key=r['capability_key']) for r in m['rows'] for v in r['mesocycle_directives']],'rationale':'Reviewed strategic starter'}
    for v in proposal['mesocycle_directives']:v.pop('origin')
    reply=inputs.client.post('/api/v1/planning/goals/macrocycle-plans',json=proposal);assert reply.status_code==201,reply.text
    assert get(inputs)['days'][0]['capability_roles'][0]['role'] in {'primary_development','secondary_development','maintenance'}
def test_foreign_owner_cannot_read_strategy(inputs):
    inputs.email=OTHER_EMAIL;get(inputs,status=404)


def test_youth_profile_does_not_silently_use_elite_intensive_emphasis():
    d=source();d['profile']={'data':{'birth_date':'2014-01-01','participation':'unrestricted','interruption':'none'}}
    s=build(d);assert s['strategy']['profile_context']['beginner_or_returning']
    anaerobic=next(r for r in s['macrocycles'][0]['rows'] if r['capability_key']=='HIGH_INTENSITY_AND_ANAEROBIC_PROFILE')
    assert all(v['role']=='maintenance' for v in anaerobic['mesocycle_directives'])

def test_no_automatic_decline_and_no_empty_roles_for_unknown_profile():
    s=build(source());assert not any(v['role'] in (None,'permitted_decline') for r in s['macrocycles'][0]['rows'] for v in r['mesocycle_directives'])


def test_registered_race_program_reaches_complete_http_strategy_without_manual_roles(inputs):
    from tests.planning.test_p2_4c5_cycle_creation import proposal,mesocycles,post
    from tests.planning.test_p2_4c5r1_cycle_intent_and_boundaries import profile
    p=proposal(token=983001);p['start_date']='2026-10-23';p['macrocycles'][0].update(start_date='2026-10-23',end_date='2027-01-14',mesocycles=mesocycles('2026-10-23','2027-01-14'))
    event={'key':'main-race','title':'1000 m főverseny','start_date':'2027-01-14','end_date':'2027-01-14','precision':'exact','priority':'main','status':'planned','profile':profile('1000')}
    event['profile'].update(capability_basis='coach_declared',capability_keys=KEYS);p['competitions']=[event]
    a=post(inputs,'/programs',p)['artifact'];inputs.url='/api/v1/planning/cycles/programs/'+a['artifact_id']+'/planning-inputs'
    data=get(inputs);m=data['goal_suggestions']['macrocycles'][0]
    assert len(m['rows'])==len(KEYS);assert all(v['role'] is not None for r in m['rows'] for v in r['mesocycle_directives'])
    assert data['goal_suggestions']['event_titles']['main-race']=='1000 m főverseny'
