"""Scarce daylight, endurance, cancellations and persisted automatic refresh."""
from copy import deepcopy
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from uuid import UUID
import json
import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import automatic_planning, planning_calendar
from app.models.entities import PlannedWorkout, Sport, WorkoutStatus
from app.planning.domain import daylight
from app.services import training_options
from tests.planning.test_p2_4c20_5_assessed_strength import planner as fixture, request
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial, context as intake_context
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c20_1_prescriptions import completed
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c21_automatic_workspace import setting


@pytest.fixture
def env(tmp_path, monkeypatch):
    gen=fixture.__wrapped__(tmp_path,monkeypatch);e=next(gen)
    for route in [automatic_planning,planning_calendar]:e.app.include_router(route.router,prefix='/api/v1')
    try: yield e
    finally: gen.close()


def prepare(e, *, light=True, running=True, swimming=False):
    p=deepcopy(e.options['artifact']['proposal'])
    p.update(request_id=str(UUID(int=219101)),previous_reference=training_options.reference(e.options['artifact']))
    p['data']['locations'][0].update(sports=['KAYAK','STRENGTH','RUNNING']+(['SWIMMING'] if swimming else []),
        resources=['Kajak','Futócipő','Kézisúlyzó','Szabad padlófelület']+(['Úszómedence'] if swimming else []),
        coordinates={'latitude':'47.5','longitude':'19.04','timezone_name':'Europe/Budapest'})
    slot=p['data']['weekly_slots'][0];slot['weekdays']=[0,1,2,3,4]
    slot['details'].update(location_ids=[p['data']['locations'][0]['id']],start_time='18:00',end_time='20:00',max_minutes=90)
    weekend=deepcopy(slot);weekend['id']=str(UUID(int=219102));weekend['weekdays']=[5,6]
    weekend['details'].update(start_time='08:00',end_time='11:00');p['data']['weekly_slots']=[slot,weekend]
    if light:p['data']['daylight_rules']=[{'sport':'KAYAK','mode':'daylight','start_buffer_minutes':0,'end_buffer_minutes':0}]
    saved=save_options(e,p);save_initial(e,request(e))
    completed(e,219103,sport=Sport.KAYAK,minutes=65,day='2026-10-17')
    if running:completed(e,219104,sport=Sport.RUNNING,minutes=35,day='2026-10-19')
    return saved


def review(e):
    r=e.client.post(e.plan_url+'/review',json={'start_date':'2026-10-26','end_date':'2026-11-08','coordinate_mesocycles':True})
    assert r.status_code==200,r.text
    return r.json()['review']


def export(name, value):
    if os.getenv('C21_9_1_EXPORT'):
        path=Path(os.environ['C21_9_1_EXPORT']);saved=json.loads(path.read_text()) if path.exists() else {}
        saved[name]=value;path.write_text(json.dumps(saved),encoding='utf-8')


def test_daylight_scarcity_keeps_weekends_for_kayak_and_allows_proven_running(env):
    prepare(env);v=review(env);rows=v['result']['proposals']
    assert {'KAYAK','RUNNING','STRENGTH'} <= {c['sport'] for c in rows}
    for c in rows:
        if c['sport']=='KAYAK':
            assert datetime.fromisoformat(c['date']).weekday() in [5,6]
            assert daylight.permits(v['inputs']['daylight_context']['options_receipt']['artifact']['proposal']['data'],c['location_id'],c['sport'],datetime.fromisoformat(c['start_at']),datetime.fromisoformat(c['end_at']))
    assert all((datetime.fromisoformat(b['start_at'])-datetime.fromisoformat(a['start_at'])).total_seconds()>= (48 if a['sport']==b['sport']=='STRENGTH' else 24 if 'STRENGTH' in [a['sport'],b['sport']] or a['sport']==b['sport'] or {a['sport'],b['sport']}<={'KAYAK','SWIMMING'} else 12)*3600 for a,b in pairwise(rows))
    for c in rows:
        week=[x for x in rows if 0<=(datetime.fromisoformat(x['date'])-datetime.fromisoformat(c['date'])).days<=6]
        assert len(week)<=3 and sum(x['duration_sec'] for x in week)<=180*60
    accept(env,v);repeated=review(env)
    assert not repeated['result']['create'] and not repeated['result']['cancel']


def test_existing_strength_only_allocation_can_rebalance_when_light_window_opens(env):
    first=prepare(env,running=False)
    p=deepcopy(first['artifact']['proposal']);p.update(request_id=str(UUID(int=219105)),previous_reference=training_options.reference(first['artifact']))
    p['data']['locations'][0]['coordinates']={'latitude':'90','longitude':'0','timezone_name':'UTC'}
    polar=save_options(env,p);before=review(env)
    assert before['result']['proposals'] and 'KAYAK' not in {c['sport'] for c in before['result']['proposals']}
    assert 'STRENGTH' in {c['sport'] for c in before['result']['proposals']}
    accept(env,before)
    p=deepcopy(first['artifact']['proposal']);p.update(request_id=str(UUID(int=219106)),previous_reference=training_options.reference(polar['artifact']))
    save_options(env,p);after=review(env)
    assert {'KAYAK','STRENGTH'} <= {c['sport'] for c in after['result']['proposals']}
    for key in ['max_sessions_per_7_days','max_minutes_per_7_days']:
        assert after['result']['preparation'][key]==before['result']['preparation'][key]
    accept(env,after,token=219107)
    again=review(env);assert not again['result']['create'] and not again['result']['cancel']


def test_cancelled_night_plans_stay_archived_but_leave_the_calendar(env):
    first=prepare(env,light=False);old=review(env);accept(env,old)
    old_night={c['candidate_key'] for c in old['result']['proposals'] if c['sport']=='KAYAK' and datetime.fromisoformat(c['date']).weekday()<5}
    assert old_night
    with Session(env.engine) as db:
        old_ids={str(p.id) for p in db.scalars(select(PlannedWorkout).where(PlannedWorkout.user_id==UUID(old['athlete_id']))) if (p.raw_data or {}).get('paddletrainer_training_plan',{}).get('candidate_key') in old_night}
    p=deepcopy(first['artifact']['proposal']);p.update(request_id=str(UUID(int=219110)),previous_reference=training_options.reference(first['artifact']))
    p['data']['daylight_rules']=[{'sport':'KAYAK','mode':'daylight','start_buffer_minutes':0,'end_buffer_minutes':0}]
    source_before=intake_context(env)['sources']['source_hash'];save_options(env,p)
    assert intake_context(env)['sources']['source_hash']==source_before
    fresh=review(env);assert old_ids <= set(fresh['result']['cancel'])
    assert any(c['sport']=='KAYAK' for c in fresh['result']['proposals'])
    accept(env,fresh,token=219111)
    r=env.client.get('/api/v1/planning/calendar/feed?start_date=2026-10-26&end_date=2026-11-08')
    assert r.status_code==200,r.text
    feed=r.json();assert not old_ids & {p['id'] for p in feed['planned']}
    assert all(p['status']!='CANCELLED' for p in feed['planned'])
    assert len({p['date'] for p in feed['planned']})==len(feed['planned'])
    with Session(env.engine) as db:
        assert all(db.get(PlannedWorkout,UUID(i)).status==WorkoutStatus.CANCELLED for i in old_ids)
    repeated=review(env);assert not repeated['result']['create'] and not repeated['result']['cancel']
    export('review',fresh);export('feed',feed);export('cancelled_ids',sorted(old_ids))


def test_missing_running_reference_allows_a_starter_and_swimming_stays_explicit(env):
    prepare(env,running=False,swimming=True);v=review(env)
    report=v['result']['preparation']['sport_availability'];by={r['sport']:r for r in report['sports']}
    assert by['RUNNING']['opportunity_days']>0 and by['RUNNING']['planned_sessions']>0
    assert 'PERSONAL_DURATION_REFERENCE_MISSING' not in by['RUNNING']['reasons']
    assert by['SWIMMING']['supported'] is True and 'SWIMMING_ABILITY_REQUIRED' in by['SWIMMING']['reasons']
    assert by['KAYAK']['planned_sessions']>0
    export('missing_report',report)


def test_real_automatic_refresh_explains_selection_and_does_not_duplicate(env):
    prepare(env)
    r=env.client.post('/api/v1/planning/automation',json=setting(env,token=219120))
    assert r.status_code==201,r.text
    r=env.client.post('/api/v1/planning/automation/run',json={});assert r.status_code==200,r.text
    value=r.json();assert value['run']['state']=='applied'
    summary=value['run']['sport_availability'];assert summary['schema_version']=='training-sport-availability-v0.3'
    assert any(row['sport']=='KAYAK' and row['planned_sessions']>0 for row in summary['sports'])
    next_run=env.client.post('/api/v1/planning/automation/run',json={});assert next_run.status_code==200,next_run.text
    assert next_run.json()['run']['created_count']==next_run.json()['run']['cancelled_count']==0
    export('automatic',value)


def test_user_edited_plan_and_missed_budget_remain_protected(env):
    prepare(env);v=review(env);accept(env,v)
    with Session(env.engine) as db:
        rows=list(db.scalars(select(PlannedWorkout).where(PlannedWorkout.user_id==UUID(v['athlete_id'])).order_by(PlannedWorkout.date)))
        rows[0].status=WorkoutStatus.SKIPPED;rows[1].title='Saját szerkesztett edzés'
        preserved={str(rows[0].id),str(rows[1].id)};missed_date=rows[0].date
        db.commit()
    after=review(env)
    assert preserved <= set(after['result']['protected_workout_ids'])
    assert not preserved & set(after['result']['cancel'])
    week=[c for c in after['result']['proposals'] if 0<=(datetime.fromisoformat(c['date']).date()-missed_date).days<=6]
    assert len(week)+2<=after['result']['preparation']['max_sessions_per_7_days']


def test_coordinates_without_active_light_rule_keep_browser_verifiable_assessment(env):
    first=prepare(env,light=False)
    p=deepcopy(first['artifact']['proposal']);p.update(request_id=str(UUID(int=219130)),previous_reference=training_options.reference(first['artifact']))
    p['data']['locations'][0]['coordinates']['latitude']='47.6'
    save_options(env,p);value=review(env);inputs=value['inputs'];proof=inputs['strength_assessment']
    assert 'daylight_context' not in inputs
    assert proof['source_body']['options_reference']!=inputs['training_options_reference']
    assert training_options.reference(proof['current_options_receipt']['artifact'])==inputs['training_options_reference']
    assert any(c['sport']=='STRENGTH' for c in value['result']['proposals'])
    export('geo_only_review',value)
