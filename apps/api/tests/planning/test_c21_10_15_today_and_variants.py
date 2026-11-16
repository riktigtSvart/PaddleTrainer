"""Explicit same-day replacement, future-only allocation and content grouping."""
from copy import deepcopy
from datetime import UTC,datetime,timedelta
import json,os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import PlannedWorkout,WorkoutSession,Sport,WorkoutStatus
from app.services import training_options,training_alternative_variants as variants
from app.planning.domain.athlete_setup import reference
from tests.planning.test_c21_10_9_profile_sources import env,configure
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c19_plan_choices import choice
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE,OTHER,count


def export(name,value):
    if os.getenv('C21_10_15_EXPORT'):
        p=Path(os.environ['C21_10_15_EXPORT']);data=json.loads(p.read_text()) if p.exists() else {};data[name]=value;p.write_text(json.dumps(data),encoding='utf-8')


def review(e,scope=None,status=200):
    body={'start_date':'2026-10-26','end_date':'2026-11-01'}
    if scope is not None:body['same_day_replacement']=scope
    r=e.client.post(e.plan_url+'/review',json=body)
    assert r.status_code==status,r.text
    return r.json()['review'] if status==200 else r.json()


def feed(e):
    r=e.client.get('/api/v1/planning/calendar/feed?start_date=2026-10-26&end_date=2026-11-01')
    assert r.status_code==200,r.text
    return r.json()


def prepare(e):
    e.clock.current=datetime(2026,10,26,4,tzinfo=UTC)
    saved=configure(e)
    p=deepcopy(saved['artifact']['proposal']);p.update(request_id=str(UUID(int=21115001)),previous_reference=reference(saved['artifact']))
    slots=[]
    for i,slot in enumerate(p['data']['weekly_slots']):
        added=deepcopy(slot);added['id']=str(UUID(int=21115100+i));added['details'].update(start_time='14:00',end_time='18:00',max_minutes=120);slots.append(added)
    for slot in p['data']['weekly_slots']:
        slot['details'].update(start_time='08:00',end_time='10:00',max_minutes=120)
    p['data']['weekly_slots'].extend(slots);save_options(e,p)
    original=review(e)
    g=next(g for g in original['result']['alternatives'] if g['date']=='2026-10-26')
    c=next(c for c in g['candidates'] if datetime.fromisoformat(c['start_at']).hour<10)
    picked=choice(e,original,g['date'],c['candidate_key'])['review']
    accept(e,picked,token=21115002)
    target=next(w for w in feed(e)['planned'] if w['date']=='2026-10-26')
    e.clock.current=datetime(2026,10,26,10,tzinfo=UTC)
    scope={'schema_version':'same-day-training-replacement-v0.1','workout_id':target['id'],'confirmed_not_started':True}
    return target,scope


def test_elapsed_planned_start_can_be_explicitly_replaced_in_remaining_windows(env):
    target,scope=prepare(env)
    ordinary=review(env)
    assert target['id'] in ordinary['result']['protected_workout_ids'] and target['id'] not in ordinary['result']['cancel']
    current=next(w for w in feed(env)['planned'] if w['id']==target['id'])
    assert current['planning_context']['replaceable'] and current['planning_context']['same_day_confirmation_required']
    proposed=review(env,scope)
    g=next(g for g in proposed['result']['alternatives'] if g['date']==target['date'])
    assert g['candidates'] and all(datetime.fromisoformat(c['start_at'])>env.clock.current for c in g['candidates'])
    assert proposed['same_day_replacement']==scope==proposed['inputs']['same_day_replacement']
    other=next((c for c in g['candidates'] if c['sport']!=target['sport']),g['candidates'][0])
    before=(count(env,PlannedWorkout),count(env,WorkoutSession))
    chosen=choice(env,proposed,target['date'],other['candidate_key'])['review']
    assert chosen['same_day_replacement']==scope and target['id'] in chosen['result']['cancel']
    assert before==(count(env,PlannedWorkout),count(env,WorkoutSession))
    accepted=accept(env,chosen,token=21115003)
    after=feed(env);rows=[p for p in after['planned'] if p['date']==target['date']]
    assert len(rows)==1 and rows[0]['id']!=target['id'] and rows[0]['planning_context']['candidate_key']==other['candidate_key']
    assert count(env,WorkoutSession)==before[1]
    export('today',{'review':proposed,'choice':chosen,'target':current,'feed':feed(env),'after':after,'selected':other,'receipt':accepted})


@pytest.mark.parametrize('change',['false','number','foreign','future_day','past_day','completed','skipped','linked'])
def test_same_day_scope_cannot_override_owner_completion_or_dates(env,change):
    target,scope=prepare(env)
    status=409
    if change=='false':scope['confirmed_not_started']=False;status=422
    if change=='number':scope['confirmed_not_started']=1;status=422
    if change=='future_day':scope['workout_id']=next(p['id'] for p in feed(env)['planned'] if p['date']>target['date'])
    if change in {'foreign','past_day','completed','skipped','linked'}:
        with Session(env.engine) as db:
            row=db.get(PlannedWorkout,UUID(target['id']))
            if change=='foreign':row.user_id=UUID(OTHER)
            if change=='past_day':row.date-=timedelta(days=1)
            if change=='completed':row.status=WorkoutStatus.COMPLETED
            if change=='skipped':row.status=WorkoutStatus.SKIPPED
            if change=='linked':db.add(WorkoutSession(id=UUID(int=21115200),user_id=UUID(ATHLETE),external_provider='LOCAL',external_id='already-started',sport=Sport(row.sport),started_at=env.clock.current,planned_workout_id=row.id,raw_data={}))
            db.commit()
    before=(count(env,PlannedWorkout),count(env,WorkoutSession))
    review(env,scope,status)
    assert before==(count(env,PlannedWorkout),count(env,WorkoutSession))


def test_no_remaining_time_keeps_the_original_calendar_plan(env):
    target,scope=prepare(env);env.clock.current=datetime(2026,10,26,22,50,tzinfo=UTC)
    proposed=review(env,scope)
    assert 'SAME_DAY_NO_REMAINING_OPTION' in proposed['result']['blockers']
    assert proposed['result']['create']==proposed['result']['cancel']==[]
    assert any(p['id']==target['id'] for p in feed(env)['planned'])
    export('no_time',proposed)


def test_content_grouping_ignores_venue_time_and_provenance_but_retains_dose(env):
    prepare(env);r=review(env)
    c=next(c for g in r['result']['alternatives'] for c in g['candidates'] if c['sport']=='STRENGTH')
    meta=r['result']['prescription_context']['by_candidate'][c['candidate_key']]
    moved=deepcopy(c);moved.update(start_at='2026-10-26T14:00:00+00:00',end_at='2026-10-26T14:20:00+00:00',location='Other same equipment',location_id=str(UUID(int=21115300)),candidate_key='other')
    for m in moved['strength_prescription']['movements']:m['entry_id']='different-reference';m['performed_on']='2026-10-24';m['location_id']=moved['location_id']
    assert variants.variant(moved,meta)==variants.variant(c,meta)
    changed=deepcopy(moved);changed['strength_prescription']['movements'][0]['work_sets']+=1
    assert variants.variant(changed,meta)!=variants.variant(c,meta)
    changed=deepcopy(moved);changed['capability_key']='MUSCULOSKELETAL_ROBUSTNESS' if c['capability_key']!='MUSCULOSKELETAL_ROBUSTNESS' else 'MAX_STRENGTH'
    assert variants.variant(changed,meta)!=variants.variant(c,meta)
    summary=variants.summary(c,meta,[moved,moved,changed],{'other':meta},True)
    assert summary['different_workouts_count']==1 and summary['same_workout_schedule_count']==1
    export('grouping',{'candidate':c,'metadata':meta,'moved':moved,'changed':changed,'summary':summary})
    export('future',r)


def test_recorded_start_after_preview_blocks_the_same_day_acceptance(env):
    target,scope=prepare(env);proposed=review(env,scope)
    g=next(g for g in proposed['result']['alternatives'] if g['date']==target['date'])
    chosen=choice(env,proposed,target['date'],g['candidates'][0]['candidate_key'])['review']
    with Session(env.engine) as db:
        db.add(WorkoutSession(id=UUID(int=21115400),user_id=UUID(ATHLETE),external_provider='LOCAL',external_id='started-after-preview',sport=Sport(target['sport']),started_at=env.clock.current,planned_workout_id=UUID(target['id']),raw_data={}));db.commit()
    before=(count(env,PlannedWorkout),count(env,WorkoutSession))
    accept(env,chosen,token=21115004,expected=409)
    assert before==(count(env,PlannedWorkout),count(env,WorkoutSession))
    assert any(p['id']==target['id'] for p in feed(env)['planned'])


def test_a_same_day_confirmation_cannot_be_carried_past_local_midnight(env):
    target,scope=prepare(env);proposed=review(env,scope)
    env.clock.current=datetime(2026,10,26,23,30,tzinfo=UTC)
    accept(env,proposed,token=21115005,expected=409)
    with Session(env.engine) as db:assert db.get(PlannedWorkout,UUID(target['id'])).status!=WorkoutStatus.CANCELLED
