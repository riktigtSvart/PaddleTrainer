"""Real ASGI/SQLite reads, repeat capture identity and stateless answer checks."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json

import pytest

from test_plan_contract_read_api import environment,OWNER,OTHER,NOW,polar_target
from test_executed_workout_read_api import executions
from test_execution_phase_fix import phase,routed_source
from app.api.routes import phase_reconciliations as routes
from app.main import app
from app.models.entities import User
from app.planning_contracts.phase_reconciliation import reconcile
from app.planning_contracts.phase_reconciliation_input import load_api,prepare_api
from app.planning_contracts.execution_adapter import build_execution_read
from app.services.plan_contract_read import build_plan_read
from app.services.plan_execution_comparison_read import build_comparison_read
from app.services import phase_reconciliation_read as service

FIXTURES=Path(__file__).resolve().parent/'fixtures/phase_reconciliation'
PRIVATE_REPLAY_AVAILABLE = all((FIXTURES/name).is_file() for name in ('api_00.json.gz','api_01.json.gz','api_02.json.gz'))
PRIVATE_REPLAY_REASON = 'private real-derived Polar replay fixtures are not installed; synthetic/public regression coverage still runs'


def make_session(env):
    raw=polar_target()
    raw['exercise'][0]['phaseOrRepeat']=[phase(value=20000,change='MANUAL'),phase(value=10000),phase(value=20000)]
    env.add(source='POLAR',raw=raw)
    src=routed_source()['raw_data']
    speed=next(v for v in src['exerciseSamples'][0]['samples']['samples'] if v['type']=='SPEED')['values']
    speed[25:35]=[0.0]*10
    return env.add_execution(raw=src)


def get(env,row,full=True):
    return env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation',params={'include_source':str(full).lower()})


def body(value,kind=None,candidate=None):
    answers=[]
    if kind:
        answers=[{'question_id':value['result']['questions'][0]['question_id'],
                  'answer_type':kind,'candidate_id':candidate,'submitted_at':'2026-10-17T10:00:00+02:00'}]
    return {'schema_version':'0.1','artifact_id':value['stable_artifact_id'],'answers':answers}


def post(env,row,value,full=True):
    return env.client.post(f'/api/v1/sessions/{row.id}/phase-reconciliation/clarifications/inspect',
                          params={'include_source':str(full).lower()},json=value)


def recapture(api,at):
    old=api['source_execution_read']
    pc=build_plan_read(old['plan_capture']['source_snapshot'],captured_at=at)
    er=build_execution_read(old['source_snapshot'],captured_at=at,plan_read=pc,
                            plan_selection=old['plan_selection'],source_mode=old['source_mode'])
    return build_comparison_read(er,include_source=True,include_bundle=True)


@pytest.mark.skipif(not PRIVATE_REPLAY_AVAILABLE, reason=PRIVATE_REPLAY_REASON)
@pytest.mark.parametrize('index',[0,1,2])
def test_fresh_plan_and_session_captures_keep_source_question_ids(index):
    original=load_api(FIXTURES/f'api_{index:02}.json.gz')
    first=recapture(original,'2026-10-17T08:00:00+00:00')
    second=recapture(original,'2026-10-17T08:01:00+00:00')
    a,b=service.build_phase_reconciliation_read(first,include_source=True),service.build_phase_reconciliation_read(second,include_source=True)
    assert first['capture_id']!=second['capture_id']
    assert a['source_capture_occurrence_mapping']!=b['source_capture_occurrence_mapping']
    assert a['stable_artifact_id']==b['stable_artifact_id']
    assert a['stable_normalized_motion_input_sha256']==b['stable_normalized_motion_input_sha256']
    assert a['result']['questions']==b['result']['questions']
    assert service.verify_phase_reconciliation_read(a) and service.verify_phase_reconciliation_read(b)


@pytest.mark.skipif(not PRIVATE_REPLAY_AVAILABLE, reason=PRIVATE_REPLAY_REASON)
def test_saved_answer_applies_to_later_read_of_unchanged_source():
    original=load_api(FIXTURES/'api_01.json.gz')
    a=service.build_phase_reconciliation_read(recapture(original,'2026-10-17T08:00:00+00:00'))
    request=body(a,'DONT_KNOW')
    b=service.build_phase_reconciliation_read(recapture(original,'2026-10-17T08:01:00+00:00'),clarifications=request,include_source=True)
    assert b['result']['pending_question_count']==0
    assert not b['clarifications_persisted'] and not b['actual_phase_alignment_verified']
    assert service.verify_phase_reconciliation_read(b)


def test_real_read_replays_and_queries_select_only(executions):
    env=executions;row=make_session(env);original=deepcopy(row.raw_data)
    response=get(env,row)
    assert response.status_code==200,response.text
    value=response.json()
    assert service.verify_phase_reconciliation_read(value)
    assert value['result']['question_count']==1
    assert value['result']['source_preservation']['discarded_sample_count']==0
    assert row.raw_data==original and set(env.sql)=={'SELECT'}
    assert response.headers['cache-control']=='no-store'


def test_real_repeated_get_keeps_question_identity(executions):
    env=executions;row=make_session(env)
    a,b=get(env,row).json(),get(env,row).json()
    assert a['captured_at']!=b['captured_at']
    assert a['stable_artifact_id']==b['stable_artifact_id']
    assert a['result']['questions']==b['result']['questions']


def test_compact_get_omits_replay_material(executions):
    env=executions;row=make_session(env);value=get(env,row,False).json()
    assert value['source_comparison_read'] is None and not value['source_replay_material_included']
    with pytest.raises(service.PhaseReconciliationReadError,match='FULL_SOURCE_REQUIRED'):
        service.verify_phase_reconciliation_read(value)


def test_empty_answer_inspection_is_replayable_select_only(executions):
    env=executions;row=make_session(env);first=get(env,row).json()
    response=post(env,row,body(first))
    assert response.status_code==200,response.text
    value=response.json()
    assert service.verify_phase_reconciliation_read(value)
    assert value['stable_artifact_id']==first['stable_artifact_id']
    assert value['result']['pending_question_count']==1
    assert not value['clarifications_persisted'] and value['user_answer_storage_writes']==0
    assert set(env.sql)=={'SELECT'}


def test_unknown_answer_does_not_persist_or_promote_authority(executions):
    env=executions;row=make_session(env);first=get(env,row).json()
    inspected=post(env,row,body(first,'DONT_KNOW'))
    assert inspected.status_code==200,inspected.text
    value=inspected.json()
    assert value['result']['pending_question_count']==0
    assert value['result']['questions'][0]['state']=='ACKNOWLEDGED_UNRESOLVED'
    assert not value['actual_phase_alignment_verified'] and not value['numeric_prediction_authorized']
    assert not value['clarifications_persisted'] and set(env.sql)=={'SELECT'}
    assert get(env,row).json()['result']['pending_question_count']==1


def test_selected_candidate_is_user_evidence_not_provider_event(executions):
    env=executions;row=make_session(env);first=get(env,row).json()
    candidate=first['result']['questions'][0]['options'][-1]['candidate_id']
    response=post(env,row,body(first,'SELECT_CANDIDATE',candidate))
    assert response.status_code==200,response.text
    value=response.json()
    assert value['result']['pending_question_count']==0
    assert not value['actual_phase_alignment_verified'] and not value['training_authorized']
    assert service.verify_phase_reconciliation_read(value)


def test_changed_source_refuses_previous_answer(executions):
    env=executions;row=make_session(env);first=get(env,row).json();request=body(first,'DONT_KNOW')
    raw=deepcopy(row.raw_data);raw['distanceMeters']+=1;row.raw_data=raw
    env.session.commit();env.sql.clear()
    response=post(env,row,request)
    assert response.status_code==409
    assert 'SOURCE_BINDING_MISMATCH' in response.json()['detail']['blocking_reason']
    assert set(env.sql)=={'SELECT'}


def test_changed_plan_refuses_previous_answer(executions):
    env=executions;row=make_session(env);first=get(env,row).json();request=body(first,'DONT_KNOW')
    from sqlalchemy import select
    from app.models.entities import PlannedWorkout
    plan=env.session.scalar(select(PlannedWorkout))
    raw=deepcopy(plan.raw_data);raw['exercise'][0]['phaseOrRepeat'][0]['goal']['duration']+=1000
    plan.raw_data=raw;env.session.commit();env.sql.clear()
    assert post(env,row,request).status_code==409
    assert set(env.sql)=={'SELECT'}


def test_foreign_and_missing_sessions_have_identical_404(executions):
    env=executions;row=env.add_execution(owner=OTHER)
    a=get(env,row);b=env.client.get(f'/api/v1/sessions/{uuid4()}/phase-reconciliation')
    assert a.status_code==b.status_code==404 and a.json()==b.json()
    assert set(env.sql)=={'SELECT'}


def test_protected_guard_precedes_numerical_reconciliation(executions,monkeypatch):
    env=executions
    from app.planning_contracts.comparison_evidence import PROTECTED_EXTERNAL_IDS
    import app.services.plan_execution_comparison_read as original
    row=env.add_execution(sid=sorted(PROTECTED_EXTERNAL_IDS)[0])
    async def forbidden(*args,**kwargs):pytest.fail('protected execution adapter reached')
    monkeypatch.setattr(original,'read_owned_execution',forbidden)
    response=get(env,row)
    assert response.status_code==409
    assert response.json()['detail']['upstream_reason']=='COMPARISON_PROTECTED_SESSION_METADATA_ONLY'
    assert 'metrics' not in response.text


def test_no_plan_withholds_instead_of_guessing(executions):
    env=executions;row=env.add_execution()
    response=get(env,row)
    assert response.status_code==409
    assert response.json()['detail']['result'] is None
    assert set(env.sql)=={'SELECT'}


@pytest.mark.parametrize('query',['athlete_id=other','captured_at=2026-01-01','plan_id=wrong',
    'include_source=true&include_source=false','include_source=invalid'])
def test_rejects_owner_clock_or_duplicate_query_overrides(executions,query):
    env=executions;row=make_session(env)
    assert env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation?'+query).status_code==422
    assert not env.sql


@pytest.mark.parametrize('field,value',[('user_id','wrong'),('training_authorized',True),('persist',True),('captured_at','2020-01-01')])
def test_inspection_rejects_extra_authority_or_storage_fields(executions,field,value):
    env=executions;row=make_session(env);request=body(get(env,row).json());env.sql.clear()
    request[field]=value
    assert post(env,row,request).status_code==422
    assert not env.sql


def test_duplicate_json_body_fields_are_rejected_before_queries(executions):
    env=executions;row=make_session(env);request=body(get(env,row).json());env.sql.clear()
    raw=json.dumps(request)[:-1]+',"schema_version":"0.1"}'
    response=env.client.post(f'/api/v1/sessions/{row.id}/phase-reconciliation/clarifications/inspect',
                            content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and not env.sql


def test_request_and_response_budgets_are_enforced(executions,monkeypatch):
    env=executions;row=make_session(env);request=body(get(env,row).json());env.sql.clear()
    monkeypatch.setattr(routes,'MAX_INSPECTION_BODY_BYTES',1)
    assert post(env,row,request).status_code==413 and not env.sql
    monkeypatch.setattr(service,'MAX_RESPONSE_BYTES',1)
    assert get(env,row).status_code==413
    assert set(env.sql)=={'SELECT'}


@pytest.mark.parametrize('method',['post','put','patch','delete'])
def test_read_route_rejects_mutation_methods(executions,method):
    env=executions;row=make_session(env)
    assert getattr(env.client,method)(f'/api/v1/sessions/{row.id}/phase-reconciliation').status_code==405
    assert not env.sql


def test_pending_objects_are_not_flushed(executions):
    env=executions;row=make_session(env)
    pending=User(id=uuid4(),email='pending-phase@example.test',created_at=NOW)
    env.session.add(pending)
    assert get(env,row).status_code==200
    assert pending in env.session.new and set(env.sql)=={'SELECT'}
    env.session.expunge(pending)


def test_missing_configured_owner_does_not_create_user(executions):
    env=executions;env.session.get(User,OWNER).email='renamed@example.test';env.session.commit();env.sql.clear()
    response=env.client.get(f'/api/v1/sessions/{uuid4()}/phase-reconciliation')
    assert response.status_code==404 and set(env.sql)=={'SELECT'}


def test_capabilities_and_old_routes_remain_available(executions):
    env=executions
    env.sql.clear()
    response=env.client.get('/api/v1/planning/phase-reconciliation/capabilities')
    assert response.status_code==200 and not env.sql
    value=response.json()
    assert value['read_and_inspect_only'] and not value['clarifications_persisted']
    assert value['rules_version']=='phase-reconciliation-0.1-draft2'
    paths=app.openapi()['paths']
    assert '/api/v1/sessions/{session_id}/plan-execution-comparison' in paths
    assert '/api/v1/sessions/{session_id}/phase-reconciliation' in paths
    assert '/api/v1/pft/measurements/tcx' in paths
