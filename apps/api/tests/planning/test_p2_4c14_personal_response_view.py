"""The read-only personal-response view uses the existing cutoff-safe C12 assembly."""
from datetime import UTC,datetime
import json,os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import User
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow,PlanningEvidenceItemRow
from app.services import session_feedback
from tests.planning.test_p2_4c6_calendar_workspace import agenda
from tests.planning.test_p2_4c12_feedback_learning import env,save,seed_execution,ATHLETE

URL='/api/v1/planning/calendar/learning-inputs'

def read(env,suffix=''):
    response=env.client.get(URL+suffix)
    assert response.status_code==200,response.text
    return response.json()

def census(env):
    with Session(env.engine) as db:
        return (db.query(PlanningAuditArtifactRow).count(),db.query(PlanningEvidenceItemRow).count())

def test_empty_view_is_owned_and_uses_profile_timezone(env):
    with Session(env.engine) as db:
        user=db.get(User,UUID(ATHLETE));user.timezone='America/New_York';db.commit()
    before=census(env);value=read(env)
    assert value['athlete_id']==str(ATHLETE) and value['timezone_name']=='America/New_York'
    assert value['assembly']['response_observations']==[]
    assert census(env)==before

def test_connected_observations_are_available_without_read_side_writes(env):
    seed_execution(env);save(env);before=census(env)
    value=read(env)
    assert len(value['assembly']['response_observations'])==5
    assert value['model_updated'] is False and value['planning_authorized'] is False
    assert value['assembly']['evidence_level_ceiling']=='descriptive'
    assert census(env)==before


def test_local_date_window_uses_profile_timezone(env):
    with Session(env.engine) as db:
        user=db.get(User,UUID(ATHLETE));user.timezone='America/New_York';db.commit()
    value=read(env,'?start_date=2026-10-23&end_date=2026-10-24')
    assert value['window_start_at']=='2026-10-23T04:00:00+00:00'
    assert value['response_window_end_at']=='2026-10-25T04:00:00+00:00'
    assert value['as_of']==value['information_cutoff_at']


def test_latest_revision_still_replaces_previous_numeric_answers(env,monkeypatch):
    seed_execution(env);save(env)
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,25,7,tzinfo=UTC))
    save(env,140002,expected_revision=1,rpe=7,fatigue=9)
    observations=read(env)['assembly']['response_observations']
    assert len(observations)==5
    assert next(x for x in observations if x['metric_key']=='self_reported_fatigue_score')['value']==9

@pytest.mark.parametrize('suffix',['?start_date=2026-10-23','?start_date=2026-10-25&end_date=2026-10-23'])
def test_invalid_windows_remain_errors(env,suffix):
    assert env.client.get(URL+suffix).status_code==422


def test_real_python_http_response_is_the_frontend_contract_fixture(env):
    empty=read(env);seed_execution(env);save(env);connected=read(env)
    assert connected['timezone_name']=='Europe/Budapest'
    if target:=os.environ.get('C14_FIXTURE_OUTPUT'):
        Path(target).write_text(json.dumps({'empty':empty,'connected':connected},ensure_ascii=False,indent=2)+'\n')


def test_old_response_window_uses_current_knowledge_without_backdating_availability(env):
    seed_execution(env);save(env)
    value=read(env,'?start_date=2026-10-23&end_date=2026-10-23')
    observations=value['assembly']['response_observations']
    assert len(observations)==5
    assert all(datetime.fromisoformat(o['response_available_at']) > datetime.fromisoformat(value['response_window_end_at']) for o in observations)
    assert value['as_of']==value['information_cutoff_at']
    assert read(env,'?start_date=2026-10-24&end_date=2026-10-24')['assembly']['response_observations']==[]

def test_end_date_does_not_resurrect_replaced_feedback_revision(env,monkeypatch):
    seed_execution(env);save(env)
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,25,7,tzinfo=UTC))
    save(env,140003,expected_revision=1,observed_at='2026-10-24T17:00:00Z',fatigue=9)
    assert read(env,'?start_date=2026-10-23&end_date=2026-10-23')['assembly']['response_observations']==[]

def test_future_response_window_is_rejected_without_writes(env):
    before=census(env)
    assert env.client.get(URL+'?start_date=2026-10-29&end_date=2026-10-29').status_code==422
    assert census(env)==before
