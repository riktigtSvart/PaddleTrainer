"""Automatic meal clocks are owned, reproducible suggestions with manual priority."""
from copy import deepcopy
from datetime import date, datetime, UTC
import gzip
import json
import os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from tests.planning.test_c21_12_nutrition_journal import env, environment, menu, post, get, body, entry
from tests.planning.test_c21_13_nutrition_calendar import calendar, save_period
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER_EMAIL
from app.models.entities import PlannedWorkout, Sport, WorkoutStatus
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition_journal import JournalData
from app.services import nutrition_timing as timing

SLOTS=['breakfast','lunch','snack','dinner']


def context(**changes):
    return {'schema_version':'nutrition-timing-v0.1','rules_version':timing.RULES,
        'athlete_id':str(UUID(int=1)),'timezone':'Europe/Budapest',
        'start_date':'2026-11-17','end_date':'2026-11-30','now':'2026-11-17T12:00:00+00:00',
        'local_today':'2026-11-17','activities':[],'uncertain_dates':[],**changes}


def clocks(value):
    return {slot:v['time'] for slot,v in value.items()}


def workout(e, start='2026-11-18T18:00:00+00:00', duration=3420, ident=21140001,
    status=WorkoutStatus.PLANNED, owner=None):
    owner=owner or get(e,'')['athlete_id']
    with Session(e.engine) as db:
        db.add(PlannedWorkout(id=UUID(int=ident),user_id=UUID(owner),
            date=date(2026,11,18),planned_start_time=datetime.fromisoformat(start) if start else None,
            sport=Sport.RUNNING,title='Szintetikus esti futás',duration_sec=duration,status=status))
        db.commit()


def test_defaults_are_actual_meal_clocks_not_recipe_preparation_times():
    d=JournalData().model_dump();before=deepcopy(d)
    v=timing.day_schedule(d,'2026-11-18',SLOTS,context())
    assert clocks(v)=={'breakfast':'07:30:00','lunch':'12:30:00','snack':'16:00:00','dinner':'19:00:00'}
    assert all(m['origin']=='default' and not m['shifted'] for m in v.values())
    assert d==before and d['entries']==[]


def test_date_specific_clock_and_explicitly_unset_clock_always_win():
    d=JournalData().model_dump();d['timings']=[{'date':'2026-11-18','slot':'breakfast','time':'09:12:34'},
        {'date':'2026-11-18','slot':'lunch','time':None}]
    d['default_times']['breakfast']='07:00:00'
    v=timing.day_schedule(d,'2026-11-18',SLOTS,context())
    assert v['breakfast']['time']=='09:12:34' and v['breakfast']['origin']=='manual'
    assert v['lunch']['time'] is None and v['lunch']['origin']=='unset'


def test_evening_run_moves_auto_dinner_after_the_occupied_interval():
    c=context(activities=[{'workout_id':str(UUID(int=2)),'date':'2026-11-18','start_second':68400,'end_second':71820}])
    d=JournalData().model_dump();v=timing.day_schedule(d,'2026-11-18',SLOTS,c)
    assert v['dinner']['time']=='20:15:00' and v['dinner']['shifted'] and not v['dinner']['conflict']
    d['timings']=[{'date':'2026-11-18','slot':'dinner','time':'19:05:00'}]
    v=timing.day_schedule(d,'2026-11-18',SLOTS,c)
    assert v['dinner']['time']=='19:05:00' and v['dinner']['conflict'] and v['dinner']['origin']=='manual'


def test_no_free_time_stays_unknown_and_does_not_remove_the_meal():
    c=context(activities=[{'workout_id':str(UUID(int=2)),'date':'2026-11-18','start_second':0,'end_second':86400}])
    v=timing.day_schedule(JournalData().model_dump(),'2026-11-18',SLOTS,c)
    assert set(v)==set(SLOTS) and all(x['time'] is None and x['origin']=='no_window' for x in v.values())


def test_past_unknown_times_are_not_backfilled_as_historical_plans():
    v=timing.day_schedule(JournalData().model_dump(),'2026-11-16',SLOTS,context())
    assert all(x['time'] is None and x['origin']=='past_unknown' for x in v.values())


@pytest.mark.parametrize('day',['2026-03-29','2026-10-25'])
def test_automatic_routine_avoids_missing_and_ambiguous_dst_hours(day):
    d=JournalData().model_dump();d['default_times']['breakfast']='02:30:00'
    c=context(local_today=day,start_date=day,end_date=day,now=day+'T00:00:00+00:00')
    v=timing.day_schedule(d,day,['breakfast'],c)
    assert v['breakfast']['time']=='03:00:00' and v['breakfast']['shifted']


def test_learning_uses_three_real_reports_and_routine_setting_has_priority():
    d=JournalData().model_dump()
    d['entries']=[{'status':'eaten','source':{'slot':'breakfast'},'timezone':'Europe/Budapest','date':'2026-11-16','time':t} for t in ['07:00:00','08:00:00','07:45:00']]
    v=timing.day_schedule(d,'2026-11-18',['breakfast'],context())
    assert v['breakfast']['time']=='07:45:00' and v['breakfast']['origin']=='learned'
    d['default_times']['breakfast']='09:15:20'
    assert timing.day_schedule(d,'2026-11-18',['breakfast'],context())['breakfast']['time']=='09:15:20'
    d['default_times']['breakfast']=None;d['entries'][2]['date']='2026-11-18'
    assert timing.day_schedule(d,'2026-11-18',['breakfast'],context())['breakfast']['origin']=='default'


def test_real_api_assigns_saved_menus_immediately_and_retains_immutable_sources(env):
    first=menu(env);source=save_period(env,first,'2026-11-18');workout(env)
    before=count(env,PlanningAuditArtifactRow)
    v=calendar(env,'2026-11-18','2026-11-20');current=get(env,'')
    assert v['schema_version']=='nutrition-calendar-v0.2'
    assert current['saved']==source and v['sources'][0]==source
    dinner=next(m for m in v['result']['days'][0]['meals'] if m['slot']=='dinner')
    assert dinner['planned_time']=='20:15:00' and dinner['timing']['shifted']
    assert current['timing_context']['activities']==v['timing_context']['activities']
    assert get(env)['saved'] is None  # Read-time suggestions never fabricate a diary write.
    assert count(env,PlanningAuditArtifactRow)==before
    if os.getenv('C21_14_EXPORT'):
        Path(os.environ['C21_14_EXPORT']).write_bytes(gzip.compress(json.dumps({'calendar':v,'menu_context':current},ensure_ascii=False).encode(),mtime=0))


def test_manual_change_survives_a_later_workout_change_and_does_not_change_intake(env):
    first=menu(env);save_period(env,first,'2026-11-18');workout(env)
    d=JournalData().model_dump();d['timings']=[{'date':'2026-11-18','slot':'dinner','time':'18:12:34'}]
    post(env,body(d));before=get(env)['saved']
    with Session(env.engine) as db:
        r=db.get(PlannedWorkout,UUID(int=21140001));r.planned_start_time=datetime(2026,11,18,16,tzinfo=UTC);db.commit()
    m=next(m for m in calendar(env,'2026-11-18','2026-11-18')['result']['days'][0]['meals'] if m['slot']=='dinner')
    assert m['planned_time']=='18:12:34' and m['timing']['origin']=='manual'
    assert get(env)['saved']==before and before['proposal']['data']['entries']==[]


def test_unknown_and_cancelled_workouts_are_distinct_and_other_owners_are_excluded(env):
    first=menu(env);save_period(env,first,'2026-11-18')
    workout(env,ident=21140003,status=WorkoutStatus.CANCELLED)
    workout(env,ident=21140004,start=None)
    c=calendar(env,'2026-11-18','2026-11-18')
    assert c['timing_context']['activities']==[] and c['timing_context']['uncertain_dates']==['2026-11-18']
    assert all(m['timing']['incomplete'] for m in c['result']['days'][0]['meals'])
    env.email=OTHER_EMAIL
    other=calendar(env,'2026-11-18','2026-11-18')
    assert other['timing_context']['activities']==[] and other['timing_context']['uncertain_dates']==[]


def test_overnight_workout_covers_the_following_civil_day(env):
    first=menu(env);save_period(env,first,'2026-11-18');workout(env,start='2026-11-18T22:30:00+00:00',duration=7200)
    c=calendar(env,'2026-11-18','2026-11-19')['timing_context']
    assert [(a['date'],a['start_second'],a['end_second']) for a in c['activities']]==[
        ('2026-11-18',84600,86400),('2026-11-19',0,5400)]


def test_known_zero_duration_does_not_become_unknown_or_reserve_time(env):
    first=menu(env);save_period(env,first,'2026-11-18');workout(env,duration=0)
    c=calendar(env,'2026-11-18','2026-11-18')
    assert c['timing_context']['activities']==[] and c['timing_context']['uncertain_dates']==[]
    assert next(m for m in c['result']['days'][0]['meals'] if m['slot']=='dinner')['planned_time']=='19:00:00'
