"""Exercise the real probe and submission tool through the real ASGI app."""
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest
from sqlalchemy import select

from app.models.phase_clarification import PhaseClarificationRevision as Revision
from test_plan_contract_read_api import environment
from test_executed_workout_read_api import executions
from test_phase_clarification_storage import storage,request_for,save,state
from test_phase_reconciliation_api import make_session


def module(name):
    tools=Path(__file__).resolve().parents[3]/'tools'
    sys.path.insert(0,str(tools))
    path=tools/(name+'.py')
    spec=importlib.util.spec_from_file_location(name+'_test',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def planning_fixture(connection,tool):
    from sqlalchemy import Table,Column,MetaData,Text,JSON
    for name,keys in tool.PLANNING_KEYS.items():
        table=Table(name,MetaData(),*[Column(key,Text,primary_key=True) for key in keys],Column('payload',JSON))
        table.create(connection)
        connection.execute(table.insert(),[{**{key:f'{key}-{i}' for key in keys},
            'payload':{'revision':i,'notes':'preserve existing planning data'}} for i in range(2)])


def fetch(env,calls):
    def call(base,path,*,body=None):
        calls.append((path,body))
        response=env.client.get(path) if body is None else env.client.post(path,json=body)
        assert response.status_code==200,response.text
        return response.json()
    return call


@pytest.mark.parametrize('saved',[False,True])
def test_readonly_probe_replays_real_states_and_never_posts(storage,tmp_path,monkeypatch,saved):
    env=storage;row=make_session(env)
    if saved:save(env,row,request_for(env,row))
    env.sql.clear();tool=module('probe_phase_clarification_storage');calls=[]
    monkeypatch.setattr(tool,'TARGETS',( ('synthetic',str(row.id)), ))
    monkeypatch.setattr(tool,'request_json',fetch(env,calls))
    output=tmp_path/'read probe with spaces'
    result=tool.run_probe(output)
    assert result['status']=='PHASE_STORAGE_READ_AND_SOURCE_REPLAY_PROBE_PASSED'
    assert all(body is None for path,body in calls) and result['database_writes']==0
    assert set(env.sql)=={'SELECT'} and output.with_suffix('.zip').is_file()
    with zipfile.ZipFile(output.with_suffix('.zip')) as z:
        draft=json.loads(z.read('review/00_answers_DRAFT.json'))
        if not saved:assert draft['request']['answers'][0]['answer_type'] is None
        else:assert draft['request']['answers'][0]['answer_type']=='DONT_KNOW'


def test_submit_completed_user_file_and_exact_retry(storage,tmp_path,monkeypatch):
    env=storage;row=make_session(env);request=request_for(env,row)
    tool=module('submit_phase_clarifications');calls=[]
    monkeypatch.setattr(tool,'request_json',fetch(env,calls))
    file=tmp_path/'my answers.json'
    file.write_text(json.dumps({'session_id':str(row.id),'request':request}))
    result=tool.run_submit(file,tmp_path/'first')
    assert result['status']=='PHASE_STORAGE_USER_ANSWERS_SAVED_AND_READBACK_VERIFIED'
    assert result['database_writes_reported']==1
    second=tool.run_submit(file,tmp_path/'repeat')
    assert second['status']=='PHASE_STORAGE_USER_ANSWERS_SAVED_AND_READBACK_VERIFIED'
    assert second['database_writes_reported']==0 and second['revision_id']==result['revision_id']
    assert len([x for x in calls if x[1] is not None])==2


def test_draft_with_unknown_values_is_never_sent(storage,tmp_path,monkeypatch):
    env=storage;row=make_session(env);request=request_for(env,row)
    request['answers'][0]['answer_type']=None
    file=tmp_path/'draft.json';file.write_text(json.dumps({'session_id':str(row.id),'request':request}))
    tool=module('submit_phase_clarifications')
    monkeypatch.setattr(tool,'request_json',lambda *a,**k:pytest.fail('draft reached network'))
    with pytest.raises(ValueError):tool.run_submit(file,tmp_path/'not created')
    assert not (tmp_path/'not created').exists()


def test_stale_answer_file_is_not_submitted(storage,tmp_path,monkeypatch):
    env=storage;row=make_session(env);request=request_for(env,row)
    stale=dict(request);stale['artifact_id']='phase_reconciliation_'+'0'*64
    file=tmp_path/'stale.json';file.write_text(json.dumps({'session_id':str(row.id),'request':stale}))
    tool=module('submit_phase_clarifications');calls=[]
    monkeypatch.setattr(tool,'request_json',fetch(env,calls))
    result=tool.run_submit(file,tmp_path/'stale')
    assert not result['submission_attempted'] and result['commit_outcome']=='NOT_ATTEMPTED'
    assert all(body is None for path,body in calls)


def test_probe_failure_exports_partial_result(tmp_path,monkeypatch):
    tool=module('probe_phase_clarification_storage')
    def fail(*a,**k):raise RuntimeError('do not leak private detail')
    monkeypatch.setattr(tool,'request_json',fail)
    result=tool.run_probe(tmp_path/'stopped')
    assert result['status']=='PHASE_STORAGE_READ_PROBE_STOPPED_WITH_SAVED_PROGRESS'
    assert (tmp_path/'stopped.zip').is_file() and 'private detail' not in json.dumps(result)


def test_migration_validator_rejects_other_revisions_and_partial_schema():
    tool=module('migrate_phase_clarification_storage')
    with pytest.raises(ValueError): tool.validate_database_state({'revision':'unknown'})
    with pytest.raises(ValueError): tool.validate_database_state({'revision':tool.OLD,'table_exists':True})
    with pytest.raises(ValueError): tool.validate_database_state({'revision':tool.NEW,'table_exists':False})
    assert tool.validate_database_state({'revision':tool.OLD,'table_exists':False})['revision']==tool.OLD


def test_transaction_runner_adds_only_its_table_and_advances_version():
    from sqlalchemy import create_engine,text,inspect
    tool=module('migrate_phase_clarification_storage')
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('c91f7a3e2d40')"))
        connection.execute(text('CREATE TABLE users (id VARCHAR PRIMARY KEY, marker TEXT)'))
        connection.execute(text('CREATE TABLE workout_sessions (id VARCHAR PRIMARY KEY, marker TEXT)'))
        connection.execute(text("INSERT INTO workout_sessions VALUES ('session', 'unchanged')"))
        planning_fixture(connection,tool)
        preserved=tool.apply_on_connection(connection)
        assert preserved['planning_rows_unchanged_within_migration_transaction']
        assert all(x['row_count']==2 for x in preserved['planning_table_fingerprints'].values())
        assert connection.scalar(text('SELECT version_num FROM alembic_version'))==tool.NEW
        assert connection.scalar(text('SELECT marker FROM workout_sessions'))=='unchanged'
        assert set(inspect(connection).get_table_names())=={'alembic_version','users','workout_sessions','phase_clarification_revisions'}|set(tool.PLANNING_KEYS)
        with pytest.raises(ValueError,match='REVISION_CHANGED'):tool.apply_on_connection(connection)


def test_planning_row_mutation_aborts_and_rolls_back_version_change(monkeypatch):
    from sqlalchemy import create_engine,text
    from alembic.operations import Operations
    tool=module('migrate_phase_clarification_storage');engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('c91f7a3e2d40')"))
        connection.execute(text('CREATE TABLE users (id VARCHAR PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE workout_sessions (id VARCHAR PRIMARY KEY)'))
        planning_fixture(connection,tool)
    create=Operations.create_table
    def injected(self,*args,**kwargs):
        result=create(self,*args,**kwargs)
        self.get_bind().execute(text("UPDATE planning_logical_plans SET payload='{}'"))
        return result
    monkeypatch.setattr(Operations,'create_table',injected)
    with pytest.raises(ValueError,match='PLANNING_ROWS_CHANGED'):
        with engine.begin() as connection:tool.apply_on_connection(connection)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='c91f7a3e2d40'
        assert 'preserve existing planning data' in connection.scalar(text('SELECT payload FROM planning_logical_plans LIMIT 1'))
