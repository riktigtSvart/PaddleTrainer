"""Calendar uses saved dates, whole-day replacements and separate actual history."""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
from uuid import UUID
import pytest
from tests.planning.test_c21_12_nutrition_journal import env, environment, menu, post, get, entry, body
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER_EMAIL
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition_journal import JournalData
from app.services import nutrition_domain as domain


def calendar(e,start='2026-11-15',end='2026-11-23',status=200):
    return get(e,f'/calendar?start_date={start}&end_date={end}',status)


def save_period(e,source,start,days=3,meals=4,token=21130001):
    proposal=deepcopy(source['proposal']);proposal['request_id']=str(UUID(int=token))
    proposal['previous_reference']=get(e,'')['reference']
    d=proposal['data'];d['preferences']['meals_per_day']=meals
    d['plan']=domain.make_plan(d['preferences'],start,days,2)
    return post(e,proposal,'')['artifact']


def test_empty_calendar_is_read_only_and_does_not_claim_consumption(env):
    before=count(env,PlanningAuditArtifactRow)
    v=calendar(env)
    assert v['result']['days']==[] and v['result']['actual_entries']==[]
    assert v['read_only'] and not v['result']['personal_energy_prescribed']
    assert count(env,PlanningAuditArtifactRow)==before


def test_saved_periods_survive_new_menu_and_reading_never_changes_training(env):
    first=menu(env);second=save_period(env,first,'2026-11-18')
    before=count(env,PlanningAuditArtifactRow)
    v=calendar(env)
    assert len(v['result']['days'])==6 and v['result']['meal_count']==24
    assert v['result']['days'][0]['meals'][0]['source']['artifact_id']==first['artifact_id']
    assert v['result']['days'][3]['meals'][0]['source']['artifact_id']==second['artifact_id']
    assert v['result']['days'][0]['meals'][0]['people']==8
    assert v['result']['days'][3]['meals'][0]['people']==2
    assert count(env,PlanningAuditArtifactRow)==before
    if os.getenv('C21_13_EXPORT'):
        Path(os.environ['C21_13_EXPORT']).write_bytes(gzip.compress(json.dumps(v,ensure_ascii=False).encode(),mtime=0))


def test_overlap_replaces_whole_day_but_keeps_other_dates(env):
    first=menu(env);second=save_period(env,first,'2026-11-16',2,3)
    days=calendar(env)['result']['days']
    assert [len(d['meals']) for d in days]==[4,3,3]
    assert all(m['source']['artifact_id']==second['artifact_id'] for m in days[1]['meals'])
    assert all(m['slot']!='snack' for m in days[1]['meals'])


def test_actual_history_survives_replan_and_cannot_mark_replacement_as_eaten(env):
    first=menu(env);d=JournalData().model_dump();d['entries']=[entry(first)]
    d['default_times']['breakfast']='07:30:15';post(env,body(d));log=get(env)
    initial=calendar(env)['result']['days'][0]['meals'][0]
    assert initial['status']=='eaten' and initial['planned_time']=='07:30:15'
    save_period(env,first,'2026-11-15')
    v=calendar(env);m=v['result']['days'][0]['meals'][0]
    assert m['status']=='planned' and m['different_report']
    assert v['result']['actual_entries']==d['entries']
    assert get(env)['saved']==log['saved'] and get(env)['sources']==log['sources']


def test_unknown_meal_time_is_not_preparation_duration_or_evidence_of_eating(env):
    menu(env);v=calendar(env)
    defaults={'breakfast':'07:30:00','lunch':'12:30:00','snack':'16:00:00','dinner':'19:00:00'}
    for d in v['result']['days']:
        for m in d['meals']:
            assert m['status']=='planned'
            assert m['planned_time']==(None if d['date']<v['journal']['local_today'] else defaults[m['slot']])


def test_shopping_state_save_does_not_undo_a_report_of_the_same_physical_meal(env):
    first=menu(env);d=JournalData().model_dump();d['entries']=[entry(first)];post(env,body(d))
    p=deepcopy(first['proposal']);p['request_id']=str(UUID(int=21130009));p['previous_reference']=get(env,'')['reference']
    p['data']['pantry'][domain.catalog()['foods'][0]['id']]='100';post(env,p,'')
    m=calendar(env)['result']['days'][0]['meals'][0]
    assert m['status']=='eaten' and not m['different_report']
    assert get(env)['saved']['proposal']['data']['entries']==d['entries']


def test_configured_owner_and_closed_query_boundary(env):
    menu(env);env.email=OTHER_EMAIL
    assert calendar(env)['result']['days']==[]
    base='/api/v1/planning/nutrition/calendar'
    for query in ['','?owner=x','?start_date=2026-11-15&start_date=2026-11-16&end_date=2026-11-20']:
        assert env.client.get(base+query).status_code==422
    assert env.client.post(base,json={}).status_code==405


@pytest.mark.parametrize('start,end',[('2026-02-30','2026-03-01'),('2026-11-20','2026-11-15'),('2025-01-01','2026-11-20')])
def test_invalid_calendar_range_is_rejected(env,start,end):
    calendar(env,start,end,422)


def test_civil_dates_across_dst_keep_all_three_days(env):
    first=menu(env);save_period(env,first,'2026-10-24')
    assert [d['date'] for d in calendar(env,'2026-10-24','2026-10-26')['result']['days']]==['2026-10-24','2026-10-25','2026-10-26']
