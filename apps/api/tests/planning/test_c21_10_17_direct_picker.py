"""Automatically offered one-day alternatives and click-authorized selection."""
from datetime import date, timedelta
import json
import os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import PlannedWorkout, WorkoutSession, WorkoutStatus, Sport
from app.planning.domain.athlete_setup import reference
from app.services import training_alternative_availability as timing
from tests.planning.test_c21_10_15_today_and_variants import env, prepare, feed
from tests.planning.test_p2_4c19_plan_choices import choice
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER


def export(name, value):
    if os.getenv('C21_10_17_EXPORT'):
        p=Path(os.environ['C21_10_17_EXPORT']);data=json.loads(p.read_text()) if p.exists() else {};data[name]=value;p.write_text(json.dumps(data),encoding='utf-8')


def setup(e):
    target, _ = prepare(e)
    # Leave a genuine rest gap around this isolated one-day choice. Future
    # workouts outside that gap remain fixed commitments, not editable rows.
    with Session(e.engine) as db:
        for row in db.query(PlannedWorkout).all():
            if str(row.id)!=target['id'] and row.date<=date.fromisoformat(target['date'])+timedelta(days=3):
                row.status=WorkoutStatus.CANCELLED
        db.commit()
    target=next(p for p in feed(e)['planned'] if p['id']==target['id'])
    return target, {'schema_version':'workout-alternatives-request-v0.1','workout_id':target['id'],'expected_workout_hash':target['planning_context']['workout_hash']}


def get_options(e, target, scope, status=200, **extra):
    r=e.client.post(e.plan_url+'/review',json={'start_date':target['date'],'end_date':target['date'],'alternatives_for':scope,**extra})
    assert r.status_code==status,r.text
    return r.json()['review'] if status==200 else r.json()


def snapshots(e):
    with Session(e.engine) as db:
        return {str(r.id):(r.status.value,r.date,r.planned_start_time,r.duration_sec,r.title,json.dumps(r.raw_data,sort_keys=True)) for r in db.query(PlannedWorkout).all()}


def test_opening_offers_current_day_options_without_a_human_confirmation_or_calendar_write(env):
    target, scope=setup(env);before=snapshots(env);sessions=count(env,WorkoutSession)
    old=env.client.get(env.plan_url).json()
    value=get_options(env,target,scope)
    assert value['alternatives_for']==scope==value['inputs']['alternatives_for']
    assert 'same_day_replacement' not in value and value['calibration_review'] is None
    assert value['result']['alternatives'][0]['candidates'] and not value['result']['blockers']
    assert {p['workout']['id'] for p in value['plan_snapshots'] if p['replaceable']}=={target['id']}
    assert snapshots(env)==before and count(env,WorkoutSession)==sessions
    status=env.client.get(env.plan_url).json()
    assert status==old  # a day picker must not shrink the programme/calibration stream
    export('initial',value);export('target',target);export('initial_feed',feed(env));export('regular',old)


def test_card_choice_commits_exactly_one_day_and_never_changes_other_workouts(env):
    target,scope=setup(env);value=get_options(env,target,scope)
    rows=value['result']['alternatives'][0]['candidates'];c=next(c for c in rows if c['sport']=='STRENGTH')
    before=snapshots(env);sessions=count(env,WorkoutSession);regular=env.client.get(env.plan_url).json()
    chosen=choice(env,value,target['date'],c['candidate_key'])['review']
    assert snapshots(env)==before
    assert chosen['result']['cancel']==[target['id']] and len(chosen['result']['create'])==1
    receipt=accept(env,chosen,token=21117001);after=snapshots(env)
    assert {k:v for k,v in after.items() if k in before and k!=target['id']}=={k:v for k,v in before.items() if k!=target['id']}
    assert after[target['id']][0]=='CANCELLED' and len(after)==len(before)+1
    assert count(env,WorkoutSession)==sessions and env.client.get(env.plan_url).json()==regular
    again=accept(env,chosen,token=21117001,expected=200);assert again['reused'] and snapshots(env)==after
    export('choice',chosen);export('receipt',receipt);export('after',feed(env))


@pytest.mark.parametrize('change',['owner','hash','changed','completed','skipped','linked','approved','past_day'])
def test_automatic_offer_never_overrides_positive_evidence_ownership_or_changed_prescription(env,change):
    target,scope=setup(env)
    with Session(env.engine) as db:
        row=db.get(PlannedWorkout,UUID(target['id']))
        if change=='owner':row.user_id=UUID(OTHER)
        if change=='hash':scope['expected_workout_hash']='f'*64
        if change=='changed':row.duration_sec+=300
        if change=='completed':row.status=WorkoutStatus.COMPLETED
        if change=='skipped':row.status=WorkoutStatus.SKIPPED
        if change=='approved':row.polar_target_id='approved-provider-target'
        if change=='past_day':row.date-=timedelta(days=1)
        if change=='linked':db.add(WorkoutSession(id=UUID(int=21117100),user_id=row.user_id,external_provider='LOCAL',external_id='already-executed',sport=Sport(row.sport),started_at=env.clock.current,planned_workout_id=row.id,raw_data={}))
        db.commit()
    before=snapshots(env);get_options(env,target,scope,409);assert snapshots(env)==before


@pytest.mark.parametrize('change',['missing_hash','two_scopes','two_days','wrong_date'])
def test_picker_scope_is_closed_and_only_covers_the_clicked_day(env,change):
    target,scope=setup(env);extra={};status=409
    if change=='missing_hash':scope.pop('expected_workout_hash');status=422
    if change=='two_scopes':extra['same_day_replacement']={'schema_version':'same-day-training-replacement-v0.1','workout_id':target['id'],'confirmed_not_started':True};status=422
    if change in {'two_days','wrong_date'}:
        extra['end_date']='2026-10-27'
        if change=='wrong_date':extra['start_date']='2026-10-27'
    before=snapshots(env);get_options(env,target,scope,status,**extra);assert snapshots(env)==before


@pytest.mark.parametrize('linked',[False,True])
def test_completion_arriving_after_display_blocks_the_click_commit(env,linked):
    target,scope=setup(env);value=get_options(env,target,scope);c=value['result']['alternatives'][0]['candidates'][0]
    chosen=choice(env,value,target['date'],c['candidate_key'])['review']
    with Session(env.engine) as db:
        db.add(WorkoutSession(id=UUID(int=21117200),user_id=UUID(value['athlete_id']),external_provider='LOCAL',external_id='arrived-after-display',sport=Sport(c['sport']),started_at=env.clock.current,planned_workout_id=UUID(target['id']) if linked else None,raw_data={}))
        db.commit()
    before=snapshots(env);accept(env,chosen,token=21117201,expected=409);assert snapshots(env)==before


def test_expired_options_are_removed_and_cannot_be_committed_from_an_old_card(env):
    target,scope=setup(env);value=get_options(env,target,scope)
    rows=value['result']['alternatives'][0]['candidates'];long=max(rows,key=lambda c:c['duration_sec']);context=value['result']['alternative_availability']['by_candidate']
    env.clock.current=timing.at(context[long['candidate_key']]['expires_at'])+timedelta(seconds=1)
    before=snapshots(env)
    r=env.client.post(env.plan_url+'/choose',json={'review_reference':reference(value),'date':target['date'],'candidate_key':long['candidate_key']})
    assert r.status_code==409 and 'ALTERNATIVE_EXPIRED' in r.text and snapshots(env)==before
    fresh=get_options(env,target,scope)
    assert all(timing.live(v,env.clock.current) for v in fresh['result']['alternative_availability']['by_candidate'].values())
    export('after_expiry',fresh)


def test_no_remaining_window_keeps_the_current_workout_without_any_extra_confirmation(env):
    target,scope=setup(env);env.clock.current+=timedelta(hours=11)
    before=snapshots(env);value=get_options(env,target,scope)
    assert value['result']['blockers'] and value['result']['create']==value['result']['cancel']==[]
    assert snapshots(env)==before


def test_a_future_day_uses_its_own_scope_and_never_defaults_to_today(env):
    target,scope=setup(env)
    future=next(p for p in feed(env)['planned'] if p['date']>target['date'])
    scope.update(workout_id=future['id'],expected_workout_hash=future['planning_context']['workout_hash'])
    value=get_options(env,future,scope)
    assert value['start_date']==value['end_date']==future['date']
    assert all(c['date']==future['date'] for c in value['result']['proposals'])
    export('future',value)


def test_a_clicked_future_workout_survives_replanning_and_can_be_explicitly_changed_again(env):
    target,scope=setup(env)
    future=next(p for p in feed(env)['planned'] if p['date']>target['date'])
    scope.update(workout_id=future['id'],expected_workout_hash=future['planning_context']['workout_hash'])
    value=get_options(env,future,scope)
    candidate=next(c for c in value['result']['alternatives'][0]['candidates'] if c['candidate_key']!=future['planning_context']['candidate_key'])
    chosen=choice(env,value,future['date'],candidate['candidate_key'])['review'];saved=accept(env,chosen,token=21117300)
    created=next(iter(saved['artifact']['created_workouts']))
    response=env.client.post(env.plan_url+'/review',json={'start_date':target['date'],'end_date':'2026-11-01'})
    assert response.status_code==200,response.text
    regular=response.json()['review']
    assert created in regular['result']['protected_workout_ids'] and created not in regular['result']['cancel']
    fresh=next(p for p in feed(env)['planned'] if p['id']==created)
    scope.update(workout_id=created,expected_workout_hash=fresh['planning_context']['workout_hash'])
    again=get_options(env,fresh,scope)
    assert next(p for p in again['plan_snapshots'] if p['workout']['id']==created)['replaceable']
