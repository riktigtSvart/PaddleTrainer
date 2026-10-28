"""C12 source selection, real owned HTTP and the existing durable learning chain."""
from datetime import UTC, datetime, timedelta
from uuid import UUID
import json
import pytest
from sqlalchemy.orm import Session
from app.db.base import Base
from app.models.entities import AthleteResponse, User
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningEvidenceItemRow, PlanningAuditArtifactRow
from app.services import feedback_learning as learning, session_feedback
from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind, AuditArtifactRecord
from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.executed_training.models import build_authoritative_executed_training_evidence
from app.planning.domain.execution_link import ExecutionLinkBasis, finalize_authoritative_plan_execution_link
from tests.planning.test_p2_4c6_calendar_workspace import agenda, ACTUAL, PLAN
from tests.planning.test_p2_4c11_session_feedback import body
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE

BASE=f'/api/v1/planning/calendar/sessions/{ACTUAL}'
NOW=datetime(2026,10,28,12,tzinfo=UTC)

@pytest.fixture
def env(agenda,monkeypatch):
    Base.metadata.create_all(agenda.engine,tables=[PlanningEvidenceItemRow.__table__,AthleteResponse.__table__])
    monkeypatch.setattr(learning,'_now',lambda:NOW)
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,24,7,tzinfo=UTC))
    return agenda

def save(env,token=120001,**changes):
    reply=env.client.post(BASE+'/feedback',json=body(token,**changes))
    assert reply.status_code==201,reply.text
    return reply.json()

def get(env,suffix='/learning',status=200):
    r=env.client.get(BASE+suffix);assert r.status_code==status,r.text;return r.json()

def seed_execution(env):
    at=datetime(2026,10,23,16,30,tzinfo=UTC)
    link=finalize_authoritative_plan_execution_link(link_id='pt-exec-link:c12-synthetic',athlete_id=ATHLETE,
        logical_plan_id=f'planned-workout:{PLAN}',observed_revision_id='pt-plan-rev:c12-synthetic',
        workout_session_id=ACTUAL,source_workout_id=PLAN,link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
        provider_target_id='c12-synthetic',source_workout_content_hash='a'*64,session_source_content_hash='b'*64,
        observed_revision_content_hash='c'*64,created_at=at)
    artifact=build_authoritative_executed_training_evidence(artifact_id='pt-executed-training-evidence:session:'+ACTUAL,
        plan_execution_link=link,occurrence_execution_links=(),observed_at=at-timedelta(hours=1),modality_key='KAYAK',
        duration_status=KnowledgeStatus.KNOWN,duration_s=2700,created_at=at)
    with Session(env.engine) as db:
        db.add(PlanningAuditArtifactRow(artifact_kind=AuditArtifactKind.AUTHORITATIVE_EXECUTED_TRAINING.value,
            artifact_id=artifact.artifact_id,athlete_id=UUID(ATHLETE),schema_version=artifact.schema_version,
            created_at=artifact.created_at,persisted_at=at,content_hash_algorithm=artifact.content_hash_algorithm,
            content_hash=artifact.content_hash,contract_json=canonical_json(artifact)))
        import asyncio
        from app.planning.application.project_authoritative_executed_training import project_authoritative_executed_training_evidence
        from app.planning.infrastructure.repositories.postgres_evidence import SqlAlchemyEvidenceRepository
        from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
        asyncio.run(SqlAlchemyEvidenceRepository(AsyncSQLiteBridge(db)).save(
            project_authoritative_executed_training_evidence(artifact,created_at=at)))
        db.commit()
    return artifact

def test_no_feedback_and_owned_boundary(env):
    assert get(env)['items']==[]
    other=f'/api/v1/planning/calendar/sessions/{UUID(int=702099)}/learning'
    assert env.client.get(other).status_code==404
    assert env.client.post(other,json={}).status_code==404

def test_missing_execution_is_explicit_and_does_not_fabricate_authority(env):
    saved=save(env)
    assert saved['committed'] and saved['learning']['items'][0]['state']=='waiting_for_execution'
    item=get(env)['items'][0]
    assert item['revision']==1 and item['response_reference'] is None
    metrics={x['metric_key']:x for x in item['measurements']}
    assert metrics['self_reported_fatigue_score']['value']==0
    assert metrics['self_reported_soreness_score']['knowledge_status']=='unknown'
    assert item['reporting_delay_seconds']>0
    reply=env.client.post(BASE+'/learning',json={});assert reply.status_code==200
    assert not reply.json()['model_updated']

def test_source_is_frozen_through_existing_ingestion_and_retries_are_idempotent(env):
    seed_execution(env)
    saved=save(env)
    assert saved['learning']['items'][0]['state']=='ready'
    before=get(env)
    assert env.client.post(BASE+'/learning',json={}).json()['items']==before['items']
    with Session(env.engine) as db:
        assert db.query(PlanningEvidenceItemRow).count()==2
        assert db.query(AthleteResponse).count()==0
    assert all(not db.in_transaction() for db in env.requests)

def test_revisions_select_latest_known_without_resurrecting_removed_scores(env,monkeypatch):
    save(env)
    old=get(env)['items'][0]
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,25,7,tzinfo=UTC))
    save(env,120002,expected_revision=1,rpe=None,fatigue=None,energy=None,comment='Only text remains')
    now=get(env)['items'][0]
    assert now['revision']==2 and now['state']=='no_numeric_answers'
    past=get(env,'/learning?information_cutoff_at=2026-10-24T08:00:00Z')['items'][0]
    assert past['revision']==1 and past['feedback_reference']==old['feedback_reference']
    assert get(env,'/learning?information_cutoff_at=2026-10-24T06:59:59Z')['items']==[]

def test_next_morning_is_a_different_response_group(env):
    save(env)
    save(env,120002,timing='NEXT_MORNING',observed_at='2026-10-24T05:00:00Z')
    items=get(env)['items']
    assert {x['timing'] for x in items}=={'IMMEDIATE','NEXT_MORNING'}
    assert len({x['response_source_id'] for x in items})==2

@pytest.mark.parametrize('cutoff',['2026-10-29T00:00:00Z','2026-10-24T08:00:00'])
def test_future_or_naive_cutoff_is_rejected(env,cutoff):
    get(env,'/learning?information_cutoff_at='+cutoff,status=409)

def test_personal_inputs_endpoint_runs_the_existing_p2_2_chain_without_upgrading_authority(env):
    save(env)
    reply=env.client.get('/api/v1/planning/calendar/learning-inputs')
    assert reply.status_code==200,reply.text
    data=reply.json()
    assert data['assembly']['planning_authorized'] is False
    assert data['assembly']['evidence_level_ceiling']=='descriptive'
    assert data['assembly']['response_observations']==[]


def test_correction_freezes_a_new_source_but_personal_inputs_count_only_the_selected_revision(env,monkeypatch):
    seed_execution(env)
    first=save(env)
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,25,7,tzinfo=UTC))
    second=save(env,120002,expected_revision=1,rpe=7,fatigue=9)
    assert first['learning']['items'][0]['response_source_id']!=second['learning']['items'][0]['response_source_id']
    reply=env.client.get('/api/v1/planning/calendar/learning-inputs')
    assert reply.status_code==200,reply.text
    observations=reply.json()['assembly']['response_observations']
    assert len(observations)==5
    scores={x['metric_key']:x for x in observations}
    assert scores['self_reported_fatigue_score']['value']==9
    assert scores['self_reported_soreness_score']['value'] is None
    assert all(x['response_timing']=='immediate' for x in observations)
    pairs=[p for d in reply.json()['assembly']['datasets'] for p in d['pairs']]
    assert pairs and all(p['predictor_value']==2700 for p in pairs)
    with Session(env.engine) as db:
        assert db.query(PlanningEvidenceItemRow).count()==3


def test_comment_only_revision_suppresses_old_learning_scores(env,monkeypatch):
    seed_execution(env);save(env)
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,25,7,tzinfo=UTC))
    save(env,120002,expected_revision=1,rpe=None,fatigue=None,energy=None,comment='No numeric answer')
    reply=env.client.get('/api/v1/planning/calendar/learning-inputs')
    assert reply.status_code==200,reply.text
    assert reply.json()['assembly']['response_observations']==[]


def test_learning_failure_does_not_turn_a_committed_feedback_into_a_failed_user_save(env,monkeypatch):
    async def fail(**kwargs):raise RuntimeError('Synthetic learning error')
    monkeypatch.setattr(learning,'refresh',fail)
    data=save(env)
    assert data['committed'] and data['learning']=={'state':'retry_required'}
    assert get(env,'/feedback')['current']['IMMEDIATE']['revision']==1


def test_refresh_rejects_injected_measurements_and_unknown_fields(env):
    reply=env.client.post(BASE+'/learning',json={'rpe':10,'athlete_id':'other'})
    assert reply.status_code==422


def test_daily_state_consumes_current_feedback_without_creating_legacy_rows(env):
    import asyncio
    from app.services.response_observations import get_daily_response_observations
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    with Session(env.engine) as db:
        user=db.get(User,UUID(ATHLETE))
        # An older response to the same session/timing must not double support.
        from app.models.entities import ResponseTiming
        db.add(AthleteResponse(id=UUID(int=120099),user_id=user.id,workout_session_id=UUID(ACTUAL),
            response_timing=ResponseTiming.IMMEDIATE,recorded_at=datetime(2026,10,23,17,tzinfo=UTC),fatigue_score=2,created_at=datetime(2026,10,23,18,tzinfo=UTC)))
        db.commit()
    save(env)
    with Session(env.engine) as db:
        bridge=AsyncSQLiteBridge(db);user=db.get(User,UUID(ATHLETE))
        # The report was submitted Oct 24; an Oct 23 historical daily state
        # must retain the then-known legacy observation, not leak this report.
        rows=asyncio.run(get_daily_response_observations(bridge,user,datetime(2026,10,23).date(),'UTC'))
        assert len(rows)==1 and rows[0]['fatigue_score']==2


def test_known_next_morning_reaches_daily_response_state(env):
    import asyncio
    from app.services.response_observations import get_daily_response_observations
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    save(env,120001,timing='NEXT_MORNING',observed_at='2026-10-24T05:00:00Z',rpe=0)
    with Session(env.engine) as db:
        rows=asyncio.run(get_daily_response_observations(AsyncSQLiteBridge(db),db.get(User,UUID(ATHLETE)),datetime(2026,10,24).date(),'Europe/Budapest'))
    assert len(rows)==1
    assert rows[0]['rpe_score']==0 and rows[0]['soreness_score'] is None
    assert rows[0]['extra_data']['feedback_revision']==1
    assert rows[0]['response_timing']=='NEXT_MORNING'


def test_database_availability_is_not_backdated_to_observation_or_submission(env):
    from dataclasses import replace
    from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
    saved=save(env)['artifact']
    with Session(env.engine) as db:
        row=db.get(PlanningAuditArtifactRow,(AuditArtifactKind.SESSION_FEEDBACK.value,saved['artifact_id']))
        record=SqlAlchemyPlanningAuditRepository._from_row(row)
    record=replace(record,persisted_at=datetime(2026,10,26,7,tzinfo=UTC))
    assert learning.select_revisions((record,),ATHLETE,datetime(2026,10,25,8,tzinfo=UTC))==()
    selected=learning.select_revisions((record,),ATHLETE,NOW)
    assert learning.available(*selected[0])==record.persisted_at


def test_a_bad_feedback_hash_stops_learning_read_instead_of_using_old_scores(env):
    saved=save(env)['artifact']
    with Session(env.engine) as db:
        row=db.get(PlanningAuditArtifactRow,(AuditArtifactKind.SESSION_FEEDBACK.value,saved['artifact_id']))
        raw=json.loads(row.contract_json);raw['proposal']['fatigue']=10
        row.contract_json=canonical_json(raw);db.commit()
    get(env,status=503)


def test_learning_projection_failure_rolls_back_only_learning_and_can_retry(env,monkeypatch):
    from app.planning.infrastructure.repositories.postgres_evidence import SqlAlchemyEvidenceRepository
    seed_execution(env)
    async def fail(*args,**kwargs):raise RuntimeError('Synthetic projection write failure')
    with monkeypatch.context() as scoped:
        scoped.setattr(SqlAlchemyEvidenceRepository,'save',fail)
        saved=save(env)
    assert saved['committed'] and saved['learning']=={'state':'retry_required'}
    assert get(env)['items'][0]['state']=='ready_to_freeze'
    with Session(env.engine) as db:
        assert db.query(PlanningEvidenceItemRow).count()==1  # execution only
    assert env.client.post(BASE+'/learning',json={}).json()['items'][0]['state']=='ready'


def test_scientific_evidence_cannot_be_replayed_before_its_freeze(env):
    import asyncio
    from app.planning.application.feedback_personal_inputs import RevisionAwareFeedbackEvidenceRepository
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    seed_execution(env);save(env)
    with Session(env.engine) as db:
        items=asyncio.run(RevisionAwareFeedbackEvidenceRepository(AsyncSQLiteBridge(db)).list_available(
            athlete_id=ATHLETE,information_cutoff_at=datetime(2026,10,24,8,tzinfo=UTC)))
    from app.planning.domain.training_state.evidence import EXECUTED_TRAINING_SESSION
    assert len(items)==1 and items[0].evidence_type==EXECUTED_TRAINING_SESSION


def test_locked_source_has_stable_distinct_identity_and_preserves_five_answer_statuses(env):
    import asyncio
    from app.planning.infrastructure.adapters.session_feedback_source import LockedSessionFeedbackSource
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    saved=save(env)['artifact']
    with Session(env.engine) as db:
        capture=asyncio.run(LockedSessionFeedbackSource(saved['artifact_id'],saved['content_hash']).lock_and_capture(
            AsyncSQLiteBridge(db),athlete_id=ATHLETE,response_source_id=learning.source_id(saved)))
    assert capture.response_source_id!=saved['proposal']['request_id']
    assert capture.source_record_version==saved['artifact_id'] and capture.source_content_hash==saved['content_hash']
    assert len(capture.measurements)==5
    assert {x.metric_key:x.value for x in capture.measurements}['self_reported_fatigue_score']==0


def test_synthetic_frontend_learning_fixture(env):
    import os
    from pathlib import Path
    save(env)
    data=get(env)
    out=os.environ.get('P24C12_FIXTURE')
    if out:Path(out).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    assert data['items'][0]['state']=='waiting_for_execution'


def test_changed_observation_date_does_not_resurrect_an_old_revision(env,monkeypatch):
    import asyncio
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    save(env)
    monkeypatch.setattr(session_feedback,'_now',lambda:datetime(2026,10,25,7,tzinfo=UTC))
    save(env,120002,expected_revision=1,observed_at='2026-10-24T06:00:00Z')
    with Session(env.engine) as db:
        rows=asyncio.run(learning.daily_observations(AsyncSQLiteBridge(db),ATHLETE,
            datetime(2026,10,23,tzinfo=UTC),datetime(2026,10,24,tzinfo=UTC),NOW))
    assert rows==[]


def test_missing_response_projection_is_repaired_from_the_same_immutable_freeze(env):
    from app.planning.domain.training_state.evidence import SESSION_FEEDBACK
    seed_execution(env);save(env)
    with Session(env.engine) as db:
        row=db.query(PlanningEvidenceItemRow).filter_by(evidence_type=SESSION_FEEDBACK).one()
        db.delete(row);db.commit()
    assert get(env)['items'][0]['state']=='ready_to_freeze'
    assert env.client.post(BASE+'/learning',json={}).json()['items'][0]['state']=='ready'
    with Session(env.engine) as db:assert db.query(PlanningEvidenceItemRow).count()==2


def test_an_orphaned_frozen_revision_cannot_reenter_as_unrelated_legacy_evidence(env):
    seed_execution(env);saved=save(env)['artifact']
    with Session(env.engine) as db:
        db.delete(db.get(PlanningAuditArtifactRow,(AuditArtifactKind.SESSION_FEEDBACK.value,saved['artifact_id'])))
        db.commit()
    reply=env.client.get('/api/v1/planning/calendar/learning-inputs')
    assert reply.status_code==503


@pytest.mark.parametrize('wrong', ['hash','identity'])
def test_locked_adapter_refuses_a_changed_reference(env,wrong):
    import asyncio
    from app.planning.infrastructure.adapters.session_feedback_source import LockedSessionFeedbackSource
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    saved=save(env)['artifact']
    with Session(env.engine) as db,pytest.raises(ValueError):
        asyncio.run(LockedSessionFeedbackSource(saved['artifact_id'],'f'*64 if wrong=='hash' else saved['content_hash']).lock_and_capture(
            AsyncSQLiteBridge(db),athlete_id=ATHLETE,response_source_id=str(UUID(int=999)) if wrong=='identity' else learning.source_id(saved)))
