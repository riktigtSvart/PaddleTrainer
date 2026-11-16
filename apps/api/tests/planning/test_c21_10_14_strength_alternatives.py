"""Owned alternatives retain the cycle's frozen history and current strength evidence."""
import json
import os
from pathlib import Path
from app.models.entities import Sport, PlannedWorkout, WorkoutSession
from tests.planning.test_c21_10_9_profile_sources import env, configure, full
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c20_1_prescriptions import completed
from tests.planning.test_c21_10_7_calendar_cycles import get
from tests.planning.test_p2_4c19_plan_choices import choice
from tests.planning.test_p2_4c3_goal_workflow_api import count


def export(name,value):
    if os.getenv('C21_10_14_EXPORT'):
        path=Path(os.environ['C21_10_14_EXPORT']);data=json.loads(path.read_text()) if path.exists() else {};data[name]=value;path.write_text(json.dumps(data),encoding='utf-8')


def test_imported_strength_history_does_not_rewrite_the_cycle_reference_or_block_a_day_choice(env):
    configure(env)
    original=full(env)
    accept(env,original,token=21114001)
    # A later import provides another completed activity, without editing a
    # single observation, accepted plan or frozen calibration source.
    completed(env,21114002,Sport.STRENGTH,minutes=45,day='2026-10-22')
    response=env.client.post(env.plan_url+'/review',json={'start_date':original['start_date'],'end_date':original['end_date']})
    assert response.status_code==200,response.text
    fresh=response.json()['review']
    assert fresh['calibration_review']['artifact_id']==original['artifact_id']
    reference_ids={s['id'] for s in original['inputs']['recent_sessions']}
    assert any(s['id'] not in reference_ids for s in fresh['inputs']['recent_sessions'] if s['sport']=='STRENGTH')
    strength=[c for g in fresh['result']['alternatives'] for c in g['candidates'] if c['sport']=='STRENGTH']
    assert strength
    for c in strength:
        meta=fresh['result']['prescription_context']['by_candidate'][c['candidate_key']]
        assert set(meta['reference_session_ids']) <= reference_ids
    feed=get(env,'2026-10-26','2026-11-22','feed')
    target=next(p for p in feed['planned'] if any(g['date']==p['date'] and len(g['candidates'])>1 for g in fresh['result']['alternatives']))
    group=next(g for g in fresh['result']['alternatives'] if g['date']==target['date'])
    other=next(c for c in group['candidates'] if c['candidate_key']!=target['planning_context']['candidate_key'])
    before=tuple(count(env,t) for t in [PlannedWorkout,WorkoutSession])
    changed=choice(env,fresh,target['date'],other['candidate_key'])['review']
    assert target['id'] in changed['result']['cancel']
    assert [c['candidate_key'] for c in changed['result']['proposals'] if c['date']==target['date']]==[other['candidate_key']]
    assert tuple(count(env,t) for t in [PlannedWorkout,WorkoutSession])==before
    accepted=accept(env,changed,token=21114003)
    after=get(env,'2026-10-26','2026-11-22','feed')
    assert len([p for p in after['planned'] if p['date']==target['date']])==1
    assert next(p for p in after['planned'] if p['date']==target['date'])['planning_context']['candidate_key']==other['candidate_key']
    export('imported_history',{'original':original,'review':fresh,'feed':feed,'target':target,'candidate':other,'choice':changed,'receipt':accepted,'after':after})


def test_frozen_history_does_not_freeze_newly_recorded_work_sets(env,monkeypatch):
    from tests.planning.test_c21_10_13_strength_workouts import prepare,post
    body=prepare(env,monkeypatch)
    original=full(env)
    accept(env,original,token=21114010)
    saved=post(env,body)
    response=env.client.post(env.plan_url+'/review',json={'start_date':original['start_date'],'end_date':original['end_date']})
    assert response.status_code==200,response.text
    fresh=response.json()['review']
    assert fresh['calibration_review']['inputs']['strength_workout_context']['logs']==[]
    assert fresh['inputs']['strength_workout_context']['logs'][0]['log']['artifact']==saved['artifact']
    movements=[m for g in fresh['result']['alternatives'] for c in g['candidates'] if c['sport']=='STRENGTH' for m in c['strength_prescription']['movements']]
    logged=[m for m in movements if m['reference']['kind']=='workout_log']
    assert logged and all(m['observed_work_sets']==4 for m in logged)
    assert any(m['work_sets']==4 for m in logged)
    export('current_log',{'original':original,'review':fresh})
