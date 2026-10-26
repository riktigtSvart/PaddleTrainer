"""Personal timetable duration, uncertainty, owned source data and midnight boundaries."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.models.entities import BlockType, PlannedWorkout, Sport, WorkoutBlock, WorkoutSession
from app.planning.application import calendar_constraints, calendar_duration, calendar_workspace
from app.planning.domain import calendar_constraints as constraints, calendar_duration as domain
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count
from tests.planning.test_p2_4c81_calendar_constraints import agenda as previous_agenda, body, details, rule
NOW = datetime(2026, 10, 26, 11, tzinfo=UTC)
TARGET, OBSERVATION = str(UUID(int=82001)), str(UUID(int=82002))
BASE = '/api/v1/planning/calendar'
def observation(token=82002, seconds=2000, distance=6000, sport='KAYAK', started='2026-10-26T05:00:00+00:00', **changes):
    start = datetime.fromisoformat(started)
    return {'id':str(UUID(int=token)), 'sport':sport, 'distance_m':distance, 'duration_sec':seconds,
        'started_at':started, 'ended_at':(start+timedelta(seconds=seconds)).isoformat(), **changes}
def estimate(rows, distance=6000, sport='KAYAK'):
    return domain.estimate(owner=ATHLETE, plan_id=TARGET, sport=sport, distance_m=distance, cutoff=NOW, observations=rows)
@pytest.fixture
def agenda(tmp_path, monkeypatch):
    wrapper = previous_agenda.__wrapped__(tmp_path, monkeypatch); env = next(wrapper)
    monkeypatch.setattr(calendar_workspace, '_now', lambda: NOW)
    monkeypatch.setattr(calendar_constraints, '_now', lambda: NOW)
    with Session(env.engine) as db:
        db.add_all([PlannedWorkout(id=UUID(TARGET), user_id=UUID(ATHLETE), date=date(2026,10,29),
            planned_start_time=datetime(2026,10,29,5,tzinfo=UTC), title='6km paddling', sport=Sport.KAYAK,
            distance_m=6000, duration_sec=None, source='POLAR', raw_data={'provider_duration':None}),
            WorkoutSession(id=UUID(OBSERVATION), user_id=UUID(ATHLETE), external_id='personal-6km', sport=Sport.KAYAK,
            started_at=datetime(2026,10,26,5,tzinfo=UTC), ended_at=datetime(2026,10,26,5,33,20,tzinfo=UTC),
            duration_sec=2000, distance_m=6000, raw_data={'measured':True})]); db.commit()
    r = env.client.post(BASE+'/constraints',json=body(rules=[rule(start_date='2026-10-26', weekdays=[1,3],details=details(start_time='08:00',end_time='17:00'))]))
    assert r.status_code==201,r.text
    try: yield env
    finally: wrapper.close()
def get(env, path='feed', first='2026-10-26', last='2026-11-01'):
    r=env.client.get(BASE+'/'+path,params={'start_date':first,'end_date':last}); assert r.status_code==200,r.text
    return r.json()
def test_personal_6km_is_33_minutes_with_a_visible_uncalibrated_range():
    e=estimate([observation()]); assert (e['duration_sec'],e['lower_sec'],e['upper_sec'])==(2000,1800,2220)
    assert e['sample_count']==1 and e['range_is_calibrated'] is False
@pytest.mark.parametrize('changes',[{'sport':'RUNNING'},{'distance_m':1000},{'distance_m':0},{'distance_m':float('nan')},
    {'started_at':'2026-06-01T05:00:00+00:00','ended_at':'2026-06-01T05:33:20+00:00'},
    {'ended_at':'2026-10-27T05:33:20+00:00'},{'duration_sec':None,'ended_at':None},
    {'duration_sec':0,'ended_at':None},{'ended_at':'2026-10-26T04:59:00+00:00'}])
def test_ineligible_history_stays_unknown(changes):
    assert estimate([observation(**changes)]) is None
@pytest.mark.parametrize('distance,sport',[(0,'KAYAK'),(None,'KAYAK'),(True,'KAYAK'),(6000,'OTHER'),(6000,'STRENGTH')])
def test_no_inference_from_titles_or_incomparable_sports(distance,sport):
    assert estimate([observation()],distance,sport) is None
def test_elapsed_includes_pauses_and_duration_fallback_is_labeled():
    assert estimate([observation(duration_sec=1500)])['duration_sec']==2000
    assert estimate([observation(ended_at=None)])['samples'][0]['basis']=='reported_duration'
def test_scaling_and_robust_center_keep_atypical_observation_without_using_it():
    e=estimate([observation(82003,2000),observation(82004,2100),observation(82005,18000)])
    assert e['duration_sec']==2050 and e['sample_count']==2 and len(e['samples'])==3
    assert not next(s for s in e['samples'] if s['session_id']==str(UUID(int=82005)))['used']
    assert estimate([observation(distance=6600,seconds=2200)])['duration_sec']==2000
def test_two_strongly_different_samples_are_insufficient():
    assert estimate([observation(82003,2000),observation(82004,9000)]) is None
def test_recent_candidate_cap_is_explicit_and_order_independent():
    rows=[observation(83000+i,started=(NOW-timedelta(days=i+1)).isoformat()) for i in range(20)]
    e=estimate(rows);assert len(e['samples'])==e['sample_count']==e['candidate_limit']==12
    assert e==estimate(list(reversed(rows)))
def test_feed_and_conflicts_share_estimate_without_writing_source(agenda):
    f,c=get(agenda),get(agenda,'constraints');p=next(p for p in f['planned'] if p['id']==TARGET)
    assert p['duration_sec'] is None and p['duration_estimate']['duration_sec']==2000
    assert p['duration_estimate']==c['duration_estimates'][TARGET]
    assert not any(x['plan_id']==TARGET for x in c['conflicts'])
    assert count(agenda,PlanningAuditArtifactRow)==1
    with Session(agenda.engine) as db:
        p=db.get(PlannedWorkout,UUID(TARGET));s=db.get(WorkoutSession,UUID(OBSERVATION))
        assert p.duration_sec is None and p.raw_data=={'provider_duration':None}
        assert s.duration_sec==2000 and s.raw_data=={'measured':True}
def test_other_owner_never_supplies_history(agenda):
    with Session(agenda.engine) as db:
        db.execute(update(WorkoutSession).where(WorkoutSession.id==UUID(OBSERVATION)).values(user_id=UUID(OTHER)));db.commit()
    assert TARGET not in get(agenda,'constraints')['duration_estimates']
@pytest.mark.parametrize('duration',[0,3600])
def test_explicit_duration_and_zero_are_preserved(agenda,duration):
    with Session(agenda.engine) as db:
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id==UUID(TARGET)).values(duration_sec=duration));db.commit()
    p=next(p for p in get(agenda)['planned'] if p['id']==TARGET)
    assert p['duration_sec']==duration and p['duration_estimate'] is None
def test_complex_intervals_do_not_borrow_whole_session_speed(agenda):
    with Session(agenda.engine) as db:
        db.add_all([WorkoutBlock(workout_id=UUID(TARGET),position=0,block_type=BlockType.WORK,distance_m=5000),
            WorkoutBlock(workout_id=UUID(TARGET),position=1,block_type=BlockType.RECOVERY,duration_sec=300)]);db.commit()
    assert TARGET not in get(agenda,'constraints')['duration_estimates']
def test_flat_distance_phase_supported_and_overflow_not_silently_truncated(agenda,monkeypatch):
    with Session(agenda.engine) as db:
        db.add(WorkoutBlock(workout_id=UUID(TARGET),position=0,block_type=BlockType.WORK,distance_m=6000,repeat_count=1));db.commit()
    assert TARGET in get(agenda,'constraints')['duration_estimates']
    monkeypatch.setattr(calendar_duration,'HISTORY_LIMIT',0)
    assert get(agenda,'constraints')['duration_estimates']=={}
@pytest.mark.parametrize('start,end,expected',[('08:00','17:00',None),('06:37','08:00',None),
    ('06:35','08:00','ESTIMATED_OVERLAP_POSSIBLE'),('06:20','08:00','ESTIMATED_WORKOUT_OVERLAP'),('05:45','08:00','START_IN_COMMITMENT')])
def test_range_is_used_for_conflicts(start,end,expected):
    r=rule(start_date='2026-10-29',end_date='2026-10-29',repeat='once',weekdays=[],details=details(start_time=start,end_time=end))
    rows=constraints.expand({'timezone_name':'Europe/Budapest','rules':[r],'exceptions':[]},'2026-10-29','2026-10-29','Europe/Budapest')
    p={'id':TARGET,'title':'6km','date':'2026-10-29','start_at':'2026-10-29T05:00:00+00:00','duration_sec':None,'duration_estimate':estimate([observation()])}
    impacts=constraints.conflicts([p],rows);assert [c['code'] for c in impacts]==([expected] if expected else [])
    if expected and expected.startswith('ESTIMATED_'):assert impacts[0]['severity']=='review'
def test_no_back_prediction_from_own_later_execution(agenda):
    with Session(agenda.engine) as db:
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id==UUID(TARGET)).values(date=date(2026,10,26),planned_start_time=datetime(2026,10,26,5,tzinfo=UTC)));db.commit()
    assert TARGET not in get(agenda,'constraints')['duration_estimates']
def test_opportunity_fit_uses_conservative_bound():
    p={'id':TARGET,'title':'6km','date':'2026-10-29','start_at':'2026-10-29T05:00:00+00:00','duration_sec':None,'duration_estimate':estimate([observation()])}
    g={'source_date':p['date'],'start_at':p['start_at'],'end_at':'2026-10-29T06:00:00+00:00','known':True,'max_minutes':60,'daily_max_minutes':None,'intervals':[{'start_at':p['start_at'],'end_at':'2026-10-29T06:00:00+00:00'}]}
    assert constraints.opportunity_conflicts([p],[g],None,set())==[]
    g=deepcopy(g);g['max_minutes']=35
    assert constraints.opportunity_conflicts([p],[g],None,set())[0]['code']=='ESTIMATED_OPPORTUNITY_FIT_REVIEW'
    g['max_minutes']=20
    assert constraints.opportunity_conflicts([p],[g],None,set())[0]['code']=='ESTIMATED_OUTSIDE_OPPORTUNITY'
@pytest.mark.parametrize('hour,minute,duration,visible',[(22,45,None,True),(21,0,None,False),(22,45,3600,True),(22,45,0,False)])
def test_midnight_carry_is_half_open(agenda,hour,minute,duration,visible):
    with Session(agenda.engine) as db:
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id==UUID(TARGET)).values(date=date(2026,10,28),planned_start_time=datetime(2026,10,28,hour,minute,tzinfo=UTC),duration_sec=duration));db.commit()
    f=get(agenda,first='2026-10-29',last='2026-10-29');assert any(p['id']==TARGET for p in f['planned']) is visible
    c=get(agenda,'constraints')
    r=agenda.client.post(BASE+'/constraints',json=body(token=84001,previous=c['reference'],rules=[rule(start_date='2026-10-26',weekdays=[3],details=details(start_time='00:00',end_time='01:00'))]));assert r.status_code==201,r.text
    impacts=[c for c in get(agenda,'constraints',first='2026-10-29',last='2026-10-29')['conflicts'] if c['plan_id']==TARGET]
    assert bool(impacts) is visible
