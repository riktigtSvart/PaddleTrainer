"""Persistent round trips through real routers and an isolated SQLite DB."""
from copy import deepcopy
from datetime import datetime
from uuid import uuid4, UUID

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.main import app
from app.models.entities import PlannedWorkout
from app.models.phase_clarification import PhaseClarificationRevision as Revision
from app.services import phase_clarification_storage as store
from test_plan_contract_read_api import environment, AsyncBridge, OWNER, OTHER
from test_executed_workout_read_api import executions
from test_phase_reconciliation_api import make_session, get, body


class StorageBridge(AsyncBridge):
    @property
    def new(self): return self.session.new
    @property
    def dirty(self): return self.session.dirty
    @property
    def deleted(self): return self.session.deleted
    async def rollback(self): self.session.rollback()


@pytest.fixture
def storage(executions):
    from app.api.routes.phase_clarification_storage import get_db
    env = executions
    Revision.__table__.create(env.session.bind)
    app.dependency_overrides[get_db] = lambda: StorageBridge(env.session)
    original_add = env.add_execution
    def reloaded_add(**kwargs):
        row = original_add(**kwargs)
        # Unlike PostgreSQL TIMESTAMPTZ, SQLite reloads these fixture fields as
        # naive datetimes. Start both GET and locked POST from persisted values.
        env.session.expire_all()
        return row
    env.add_execution = reloaded_add
    env.sql.clear()
    yield env


def state(env, row, full=True):
    return env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation/state',
                          params={'include_source':str(full).lower()})


def save(env, row, request):
    return env.client.post(f'/api/v1/sessions/{row.id}/phase-reconciliation/clarifications',json=request)


def request_for(env, row, kind='DONT_KNOW', expected=None):
    value = get(env,row).json()
    candidate = value['result']['questions'][0]['options'][-1]['candidate_id'] if kind=='SELECT_CANDIDATE' else None
    return {**body(value,kind,candidate),'expected_revision_id':expected}


def archive(env, row, revision_id):
    return env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation/clarifications/{revision_id}?include_source=true')


def test_empty_storage_state_is_replayable_and_select_only(storage):
    env=storage;row=make_session(env);a=state(env,row)
    assert a.status_code==200,a.text
    value=a.json()
    assert value['saved_answers_status']=='NO_SAVED_ANSWERS' and store.verify_saved_state(value)
    assert value['latest_revision_id'] is None and set(env.sql)=={'SELECT'}


def test_first_save_repeat_and_later_read_round_trip(storage):
    env=storage;row=make_session(env);raw=deepcopy(row.raw_data)
    request=request_for(env,row)
    a=save(env,row,request);assert a.status_code==200,a.text
    result=a.json();rid=result['revision']['revision_id']
    assert result['status']=='PHASE_CLARIFICATION_REVISION_CREATED' and result['database_writes']==1
    assert set(env.sql)<= {'SELECT','INSERT'}
    env.sql.clear()
    b=save(env,row,request);assert b.status_code==200,b.text
    assert b.json()['status']=='PHASE_CLARIFICATION_ALREADY_PRESENT' and b.json()['revision']['revision_id']==rid
    assert set(env.sql)=={'SELECT'}
    current=state(env,row).json();saved=archive(env,row,rid).json()
    assert store.verify_saved_state(current,saved)
    assert current['saved_answers_status']=='APPLIED' and current['applied_revision_id']==rid
    effective=current['effective_reconciliation']
    assert effective['result']['pending_question_count']==0
    assert effective['result']['questions'][0]['state']=='ACKNOWLEDGED_UNRESOLVED'
    assert not current['actual_phase_alignment_verified'] and not effective['training_authorized']
    assert raw==row.raw_data
    # Original read and inspect endpoints deliberately retain their old contract.
    assert get(env,row).json()['result']['pending_question_count']==1


def test_correction_appends_and_old_retry_does_not_undo_it(storage):
    env=storage;row=make_session(env)
    original=request_for(env,row);first=save(env,row,original).json()['revision']
    correction=request_for(env,row,'SELECT_CANDIDATE',first['revision_id'])
    second_response=save(env,row,correction);assert second_response.status_code==200,second_response.text
    second=second_response.json()['revision']
    assert second['sequence']==2 and second['previous_revision_id']==first['revision_id']
    retry=save(env,row,original).json()
    assert not retry['returned_revision_is_latest'] and retry['latest_revision_id']==second['revision_id']
    current=state(env,row).json()
    assert current['applied_revision_id']==second['revision_id']
    assert store.verify_saved_state(current,archive(env,row,second['revision_id']).json())
    history=env.client.get(f'/api/v1/sessions/{row.id}/phase-reconciliation/clarifications/history?limit=1').json()
    assert len(history['revisions'])==1 and history['has_more']
    assert archive(env,row,first['revision_id']).json()['revision']==first


def test_stale_optimistic_revision_never_overwrites(storage):
    env=storage;row=make_session(env)
    first=save(env,row,request_for(env,row)).json()['revision']
    stale=request_for(env,row,'SELECT_CANDIDATE');env.sql.clear()
    result=save(env,row,stale)
    assert result.status_code==409 and 'REVISION_CONFLICT' in result.text
    assert set(env.sql)=={'SELECT'}
    assert state(env,row).json()['latest_revision_id']==first['revision_id']


@pytest.mark.parametrize('change',['SOURCE','PLAN'])
def test_changed_source_or_plan_preserves_history_but_does_not_apply(storage,change):
    env=storage;row=make_session(env);request=request_for(env,row)
    rid=save(env,row,request).json()['revision']['revision_id']
    if change=='SOURCE':
        raw=deepcopy(row.raw_data);raw['distanceMeters']+=1;row.raw_data=raw
    else:
        plan=env.session.scalar(select(PlannedWorkout))
        raw=deepcopy(plan.raw_data);raw['exercise'][0]['phaseOrRepeat'][0]['goal']['duration']+=1000;plan.raw_data=raw
    env.session.commit();env.sql.clear()
    current=state(env,row).json()
    assert current['saved_answers_status']=='RECHECK_REQUIRED' and current['applied_revision_id'] is None
    assert current['effective_reconciliation']['result']['pending_question_count']==1
    old=archive(env,row,rid).json()
    assert store.verify_saved_state(current,old)
    assert set(env.sql)=={'SELECT'}
    assert save(env,row,request).status_code==409


def test_source_conversion_failure_still_exposes_audit_without_applying(storage):
    env=storage;row=make_session(env)
    rid=save(env,row,request_for(env,row)).json()['revision']['revision_id']
    row.raw_data={};env.session.commit();env.sql.clear()
    value=state(env,row).json()
    assert value['effective_reconciliation'] is None and value['saved_revision']['revision_id']==rid
    assert value['saved_answers_status']=='RECHECK_REQUIRED' and not value['saved_answers_used']
    assert archive(env,row,rid).status_code==200 and set(env.sql)=={'SELECT'}


def test_retraction_is_a_new_empty_snapshot_and_reopens_questions(storage):
    env=storage;row=make_session(env)
    initial={**body(get(env,row).json()),'expected_revision_id':None}
    assert save(env,row,initial).status_code==409
    rid=save(env,row,request_for(env,row)).json()['revision']['revision_id']
    initial['expected_revision_id']=rid
    result=save(env,row,initial);assert result.status_code==200,result.text
    assert result.json()['revision']['sequence']==2
    assert state(env,row).json()['effective_reconciliation']['result']['pending_question_count']==1


@pytest.mark.parametrize('field',['request','evidence','record','owner'])
def test_stored_tampering_is_withheld(storage,field):
    env=storage;row=make_session(env);save(env,row,request_for(env,row))
    record=env.session.scalar(select(Revision))
    if field=='request': record.request_json={}
    elif field=='evidence': record.evidence_gzip=b'broken'
    elif field=='record': record.record_sha256='0'*64
    else:
        record.source_sha256='0'*64
        record.record_sha256=store.digest(store.record_fields(record))
    env.session.commit();env.sql.clear()
    response=state(env,row)
    assert response.status_code==409 and 'PHASE_STORAGE_' in response.text
    assert set(env.sql)=={'SELECT'}


def test_foreign_session_and_wrong_session_archive_are_not_exposed(storage):
    env=storage;row=make_session(env)
    rid=save(env,row,request_for(env,row)).json()['revision']['revision_id']
    other=env.add_execution(owner=OTHER)
    assert state(env,other).status_code==404
    assert archive(env,other,rid).status_code==404
    another=make_session(env)
    assert archive(env,another,rid).status_code==404


def test_missing_migration_returns_actionable_503_and_old_read_still_works(executions):
    env=executions;row=make_session(env)
    response=state(env,row)
    assert response.status_code==503 and 'MIGRATION_REQUIRED' in response.text
    env.session.rollback()
    assert get(env,row).status_code==200


def test_pending_unrelated_change_is_not_committed(storage):
    env=storage;row=make_session(env);request=request_for(env,row)
    plan=env.session.scalar(select(PlannedWorkout));plan.title='Unrelated pending edit';env.sql.clear()
    response=save(env,row,request)
    assert response.status_code==409 and 'UNRELATED_PENDING_CHANGES' in response.text
    assert set(env.sql)<= {'SELECT'}
    env.session.rollback()


@pytest.mark.parametrize('extra',['user_id','persist','training_authorized','source_sha256'])
def test_save_rejects_authority_overrides_before_queries(storage,extra):
    env=storage;row=make_session(env);request=request_for(env,row);request[extra]='bad';env.sql.clear()
    assert save(env,row,request).status_code==422 and not env.sql


def test_duplicate_json_fields_and_duplicate_answers_are_rejected(storage):
    import json
    env=storage;row=make_session(env);request=request_for(env,row)
    raw=json.dumps(request)[:-1]+',"schema_version":"0.1"}'
    env.sql.clear()
    response=env.client.post(f'/api/v1/sessions/{row.id}/phase-reconciliation/clarifications',
        content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and not env.sql
    # Identical repeats collapse in the core, but conflicting answers cannot be saved.
    bad=deepcopy(request['answers'][0]);bad['submitted_at']='2026-10-17T10:01:00+02:00'
    request['answers'].append(bad)
    assert save(env,row,request).status_code==409


def test_readonly_views_do_not_flush_pending_changes(storage):
    env=storage;row=make_session(env);sid=row.id;plan=env.session.scalar(select(PlannedWorkout))
    plan.title='pending';env.sql.clear()
    assert env.client.get(f'/api/v1/sessions/{sid}/phase-reconciliation/state').status_code==200
    assert set(env.sql)=={'SELECT'}
    env.session.rollback()


def test_optimistic_lock_sql_has_owner_and_row_lock():
    sql=str(store.locked_session_statement(uuid4(),OWNER).compile(dialect=postgresql.dialect()))
    assert 'FOR UPDATE' in sql and 'workout_sessions.user_id =' in sql


def test_rules_change_marks_saved_answers_stale(storage,monkeypatch):
    env=storage;row=make_session(env)
    saved=save(env,row,request_for(env,row)).json()['revision']
    current=get(env,row).json();current['rules_version']='future-rules'
    latest=env.session.scalar(select(Revision))
    value=store.build_saved_state(current,latest,include_source=True)
    assert value['saved_answers_status']=='RECHECK_REQUIRED' and 'RULES_CHANGED' in value['recheck_reasons']
    assert value['applied_revision_id'] is None


def test_full_replay_detects_state_and_archive_tampering(storage):
    env=storage;row=make_session(env)
    rid=save(env,row,request_for(env,row)).json()['revision']['revision_id']
    current=state(env,row).json();old=archive(env,row,rid).json()
    changed=deepcopy(current);changed['applied_revision_id']=str(uuid4())
    with pytest.raises(store.PhaseStorageError): store.verify_saved_state(changed,old)
    changed=deepcopy(old);changed['revision']['available_at_utc']='2020-01-01T00:00:00+00:00'
    with pytest.raises(store.PhaseStorageError): store.verify_saved_state(current,changed)


def test_failed_commit_rolls_back_the_insert(storage,monkeypatch):
    from sqlalchemy.exc import IntegrityError
    env=storage;row=make_session(env);request=request_for(env,row)
    async def fail_commit(self): raise IntegrityError('injected',{},Exception('test'))
    monkeypatch.setattr(StorageBridge,'commit',fail_commit)
    result=save(env,row,request)
    assert result.status_code==409
    assert env.session.scalar(select(Revision)) is None


def test_new_connection_reads_committed_evidence(storage):
    from sqlalchemy.orm import Session
    env=storage;row=make_session(env)
    rid=save(env,row,request_for(env,row)).json()['revision']['revision_id']
    with Session(env.session.bind) as fresh:
        record=fresh.scalar(select(Revision).where(Revision.id==UUID(rid)))
        assert store.verify_revision(record)
        assert record.sequence==1 and record.user_id==OWNER
