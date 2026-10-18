"""Real FastAPI/SQLite read-only integration plus the shipped probe."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4
import zipfile

import pytest

from test_plan_contract_read_api import environment, OWNER, OTHER
from test_executed_workout_read_api import executions
from test_phase_clarification_storage import storage, state, save, request_for
from test_phase_reconciliation_api import make_session
from app.services import flow_phase_time_evidence_read as service
from app.planning_contracts.flow_phase_time_evidence import reference_id
from app.planning_contracts.phase_reconciliation_input import strict_loads


def synthetic_reference(value):
    current = value['effective_reconciliation']; b = current['result']['binding']
    result = {'schema_version':'0.1', 'athlete_id':b['athlete_id'], 'session_id':b['session_id'],
        'source_sha256':b['source_sha256'], 'plan_sha256':b['plan_sha256'],
        'source_kind':'USER_SUPPLIED_FLOW_PHASE_TABLE_TRANSCRIPTION',
        'association_basis':'CONVERSATION_CONTEXT_AND_MATCHING_PHASE_STRUCTURE',
        'source_available_at_utc':None, 'display_resolution_s':1, 'exact_rounding_policy_known':False,
        'images':[{'filename':'synthetic_test_only.png','sha256':'0'*64,'session_id_or_date_visible':False}],
        'phases':[{'phase_number':i+1,'displayed_name':'synthetic','duration_s':duration,'cumulative_end_s':end}
                  for i,(duration,end) in enumerate(((20,20),(10,45),(20,65)))],
        'user_reports':[], 'reported_events':[]}
    result['evidence_id'] = reference_id(result)
    return result


@pytest.fixture
def flow_env(storage, monkeypatch):
    env = storage; row = make_session(env)
    reference = synthetic_reference(state(env,row).json())
    monkeypatch.setattr(service, 'select_reference', lambda owner, sid:
        deepcopy(reference) if str(owner)==reference['athlete_id'] and str(sid)==reference['session_id'] else None)
    env.sql.clear()
    return env, row, reference


def get(env,row,full=True,query=None):
    return env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation/execution-time-evidence',
                          params=query if query is not None else {'include_source':str(full).lower()})


def test_real_router_is_select_only_and_preserves_source_and_old_state(flow_env):
    env,row,_ = flow_env; before=deepcopy(row.raw_data)
    response=get(env,row); assert response.status_code==200,response.text
    value=response.json(); assert service.verify_evidence_read(value)
    assert value['result']['pending_questions_without_reference_support']==0
    assert state(env,row).json()['effective_reconciliation']['result']['pending_question_count']==1
    assert set(env.sql)=={'SELECT'} and row.raw_data==before
    assert response.headers['cache-control']=='no-store'


def test_repeated_http_reads_have_stable_evidence_results(flow_env):
    env,row,_=flow_env; a,b=get(env,row).json(),get(env,row).json()
    assert a['source_state_sha256'] != b['source_state_sha256']
    assert a['result']==b['result'] and set(env.sql)=={'SELECT'}


def test_saved_user_selection_conflict_is_not_overwritten(flow_env):
    env,row,_=flow_env; request=request_for(env,row,'SELECT_CANDIDATE')
    # Explicitly select the no-additional-wait option, unlike the synthetic display.
    original=state(env,row).json()['effective_reconciliation']
    request['answers'][0]['candidate_id']=original['result']['questions'][0]['options'][0]['candidate_id']
    response=save(env,row,request); assert response.status_code==200,response.text
    revision=response.json()['revision']['revision_id'];env.sql.clear()
    value=get(env,row).json()
    assert value['status']=='FLOW_TIME_EVIDENCE_CONFLICT_REQUIRES_REVIEW'
    assert value['result']['manual_question_evidence'][0]['status']=='SOURCE_USER_SELECTION_CONFLICT'
    assert value['source_state']['latest_revision_id']==revision
    assert value['source_state']['saved_revision']['answers']==request['answers']
    assert service.verify_evidence_read(value) and set(env.sql)=={'SELECT'}


def test_new_source_stales_reference_instead_of_reusing_it(flow_env):
    env,row,_=flow_env; raw=deepcopy(row.raw_data);raw['name']='changed';row.raw_data=raw
    env.session.commit();env.sql.clear()
    response=get(env,row);assert response.status_code==200,response.text
    assert response.json()['status']=='FLOW_REFERENCE_RECHECK_REQUIRED'
    assert response.json()['result']['phase_times']==[] and set(env.sql)=={'SELECT'}


def test_owned_session_without_reference_does_not_get_another_reference(flow_env):
    env,original,_=flow_env; row=env.add_execution(raw=original.raw_data); response=get(env,row)
    assert response.status_code==200,response.text
    assert response.json()['status']=='NO_REGISTERED_FLOW_REFERENCE'
    assert response.json()['reference_record'] is None


def test_foreign_and_missing_sessions_have_same_404(flow_env):
    env,_,_=flow_env; row=env.add_execution(owner=OTHER)
    a=get(env,row);b=env.client.get(f'/api/v1/sessions/{uuid4()}/phase-reconciliation/execution-time-evidence')
    assert a.status_code==b.status_code==404 and a.json()==b.json()
    assert set(env.sql)=={'SELECT'}


@pytest.mark.parametrize('query',['athlete_id=other','persist=true','offset_s=5','include_source=true&include_source=false','include_source=invalid'])
def test_authority_or_clock_query_overrides_rejected_before_db(flow_env,query):
    env,row,_=flow_env
    response=env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation/execution-time-evidence?'+query)
    assert response.status_code==422 and not env.sql


@pytest.mark.parametrize('method',['post','put','patch','delete'])
def test_reference_view_has_no_write_method(flow_env,method):
    env,row,_=flow_env
    assert getattr(env.client,method)(f'/api/v1/sessions/{row.id}/phase-reconciliation/execution-time-evidence').status_code==405
    assert not env.sql


def test_capability_has_no_private_catalog_entries_or_database_access(flow_env):
    env,_,reference=flow_env
    response=env.client.get('/api/v1/planning/phase-reconciliation/execution-time-evidence-capabilities')
    assert response.status_code==200 and response.json()['read_only']
    assert reference['session_id'] not in response.text and not env.sql


def test_missing_storage_migration_is_actionable_503(executions):
    env=executions;row=make_session(env);response=get(env,row)
    assert response.status_code==503 and 'MIGRATION_REQUIRED' in response.text


def test_shipped_read_probe_against_real_asgi_router(flow_env,tmp_path,monkeypatch):
    env,row,_=flow_env
    path=Path(__file__).resolve().parents[3]/'tools/probe_flow_phase_time_evidence.py'
    monkeypatch.syspath_prepend(str(path.parent))
    spec=importlib.util.spec_from_file_location('flow_probe_for_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'TARGETS',[('synthetic-test',str(row.id))])
    def request(base,path,**kwargs):
        assert not kwargs
        response=env.client.get(path)
        assert response.status_code==200,response.text
        return response.json()
    monkeypatch.setattr(module,'request_json',request)
    output=tmp_path/'flow-probe';result=module.run_probe(output)
    assert result['status']=='FLOW_TIME_EVIDENCE_READ_AND_FULL_SOURCE_REPLAY_PROBE_PASSED'
    assert result['local_api_requests']==3 and result['user_answers_submitted']==0
    assert result['pending_questions_without_reference_support']==0 and set(env.sql)=={'SELECT'}
    with zipfile.ZipFile(output.with_suffix('.zip')) as z:
        manifest=strict_loads(z.read('OUTPUT_MANIFEST.json'))['files']
        assert set(manifest)==set(z.namelist())-{'OUTPUT_MANIFEST.json'}
