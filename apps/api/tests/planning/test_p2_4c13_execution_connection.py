"""Real owned atomic adoption, execution identity and evidence connection."""
from datetime import UTC, datetime
from uuid import UUID
import pytest
from sqlalchemy import event, DateTime
from sqlalchemy.orm import Session, attributes
from app.db.base import Base
from app.models.entities import PlannedWorkout, WorkoutBlock, WorkoutSession, BlockType
from app.planning.infrastructure.persistence import sqlalchemy_models as models
from app.services import execution_connection as service
from tests.planning.test_p2_4c12_feedback_learning import env as c12_env
from tests.planning.test_p2_4c11_session_feedback import body
from tests.planning.test_p2_4c6_calendar_workspace import ACTUAL, PLAN, agenda
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

BASE=f'/api/v1/planning/calendar/sessions/{ACTUAL}/execution-connection'
NOW=datetime(2026,10,28,12,tzinfo=UTC)

@pytest.fixture
def env(c12_env,monkeypatch):
    Base.metadata.create_all(c12_env.engine,tables=[getattr(models,name).__table__ for name in (
        'PlanningLogicalPlanRow','PlanningPlanRevisionRow','PlanningPlanOccurrenceIdentityRow',
        'PlanningPlanRevisionOccurrenceRow','PlanningPlanRevisionReconciliationAuditRow',
        'PlanningPlanExecutionLinkRow','PlanningOccurrenceExecutionLinkRow')])
    async def scalar(self,statement):return (await self.execute(statement)).scalar_one_or_none()
    monkeypatch.setattr(AsyncSQLiteBridge,'scalar',scalar,raising=False)
    monkeypatch.setattr(AsyncSQLiteBridge,'no_autoflush',property(lambda self:self.session.no_autoflush),raising=False)
    monkeypatch.setattr(service,'_now',lambda:NOW)
    # SQLite drops timezone information. Restore mapped UTC at the test DB
    # boundary, matching PostgreSQL's timezone-aware production values.
    def restore_utc(row,context):
        for col in row.__table__.columns:
            value=getattr(row,col.name)
            if isinstance(col.type,DateTime) and isinstance(value,datetime) and value.tzinfo is None:
                attributes.set_committed_value(row,col.name,value.replace(tzinfo=UTC))
    def refresh_utc(row,context,attrs):restore_utc(row,context)
    for model in (PlannedWorkout,WorkoutSession,WorkoutBlock):
        event.listen(model,'load',restore_utc);event.listen(model,'refresh',refresh_utc)
    with Session(c12_env.engine) as db:
        p=db.get(PlannedWorkout,UUID(PLAN));p.source='MANUAL';p.duration_sec=2700;p.distance_m=None
        db.add(WorkoutBlock(id=UUID(int=130099),workout_id=p.id,position=0,block_type=BlockType.WORK,
            name='Synthetic 45 minutes',duration_sec=2700,repeat_count=1))
        w=db.get(WorkoutSession,UUID(ACTUAL));w.planned_workout_link_source='MANUAL_CONFIRMED'
        db.commit()
    try:yield c12_env
    finally:
        for model in (PlannedWorkout,WorkoutSession,WorkoutBlock):
            event.remove(model,'load',restore_utc);event.remove(model,'refresh',refresh_utc)

def preview(env):
    reply=env.client.get(BASE);assert reply.status_code==200,reply.text;return reply.json()

def proposal(value,token=130001):
    return {'request_id':str(UUID(int=token)),'review_hash':value['review_hash'],
        'acknowledge_current_state_baseline_only':True,'acknowledge_session_identity_only':True}

def post(env,payload,status=201):
    reply=env.client.post(BASE,json=payload);assert reply.status_code==status,reply.text;return reply.json()

def test_preview_is_read_only_and_describes_only_current_state_authority(env):
    value=preview(env)
    assert value['state']=='ready_for_review',value
    assert value['plan_adoption_required'] and value['link_basis']=='manual_confirmed'
    assert value['plan_content_at_execution_status']=='unverified'
    with Session(env.engine) as db:
        assert db.query(models.PlanningPlanRevisionRow).count()==0
        assert db.query(models.PlanningAuditArtifactRow).count()==0

def test_one_commit_connects_plan_identity_and_execution_evidence(env):
    value=preview(env);saved=post(env,proposal(value))
    assert saved['committed'] and saved['artifact']['plan_adopted']
    assert saved['artifact']['plan_content_at_execution_status']=='unverified'
    with Session(env.engine) as db:
        assert db.query(models.PlanningPlanRevisionRow).count()==1
        assert db.query(models.PlanningPlanExecutionLinkRow).count()==1
        assert db.query(models.PlanningEvidenceItemRow).count()==1
        assert db.get(WorkoutSession,UUID(ACTUAL)).raw_data=={'unchanged':True}
    assert preview(env)['state']=='already_frozen'

def test_repeat_request_reuses_the_committed_receipt(env):
    payload=proposal(preview(env));first=post(env,payload);again=post(env,payload,200)
    assert again['reused'] and again['artifact']==first['artifact']

def test_source_change_requires_a_new_review(env):
    payload=proposal(preview(env))
    with Session(env.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).duration_sec=2500;db.commit()
    post(env,payload,409)
    with Session(env.engine) as db:assert db.query(models.PlanningPlanRevisionRow).count()==0


def test_connection_finishes_the_c12_feedback_learning_chain(env):
    reply=env.client.post(f'/api/v1/planning/calendar/sessions/{ACTUAL}/feedback',json=body(130010))
    assert reply.status_code==201,reply.text
    assert reply.json()['learning']['items'][0]['state']=='waiting_for_execution'
    saved=post(env,proposal(preview(env)))
    assert saved['learning']['items'][0]['state']=='ready'
    data=env.client.get('/api/v1/planning/calendar/learning-inputs').json()
    assert len(data['assembly']['response_observations'])==5
    assert data['assembly']['planning_authorized'] is False


def test_real_polar_id_and_reconciliation_are_accepted_without_clock_matching(env):
    from tests.planning.test_p1_4_polar_source_reconciliation import polar_raw
    raw=polar_raw(duration_ms=2700000)
    raw['session']['startTime'].update(month=10,day=23,hour=17,min=30)
    with Session(env.engine) as db:
        p=db.get(PlannedWorkout,UUID(PLAN));p.source='POLAR';p.polar_target_id=raw['session']['id'];p.raw_data=raw
        p.title=raw['session']['name'];p.description='';p.intensity_type='HEART_RATE_ZONES'
        b=db.get(WorkoutBlock,UUID(int=130099));b.name='source phase';b.intensity_type='HEART_RATE_ZONES';b.intensity_min=1;b.intensity_max=4
        w=db.get(WorkoutSession,UUID(ACTUAL));w.planned_workout_link_source='PROVIDER_EXACT'
        w.raw_data={'trainingTarget':{'id':raw['session']['id']}}
        db.commit()
    value=preview(env)
    assert value['state']=='ready_for_review',value
    assert value['link_basis']=='exact_provider_id'
    saved=post(env,proposal(value))
    assert saved['committed']
    with Session(env.engine) as db:assert db.query(models.PlanningPlanRevisionReconciliationAuditRow).count()==1


def test_a_naked_calendar_fk_is_not_manual_confirmation(env):
    with Session(env.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).planned_workout_link_source='AUTO_MATCHED';db.commit()
    value=preview(env)
    assert value['state']=='blocked' and 'EXECUTION_EXACT_IDENTITY_REQUIRED' in value['blockers']
    post(env,proposal(value),409)


def test_missing_or_foreign_plan_is_not_adopted(env):
    with Session(env.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).planned_workout_id=None;db.commit()
    assert preview(env)['blockers']==['EXECUTION_OWNED_PLAN_REQUIRED']
    other=f'/api/v1/planning/calendar/sessions/{UUID(int=702099)}/execution-connection'
    assert env.client.get(other).status_code==404
    assert env.client.post(other,json=proposal(preview(env))).status_code==404


@pytest.mark.parametrize('field,value',[
    ('acknowledge_current_state_baseline_only',False),('acknowledge_current_state_baseline_only',1),
    ('acknowledge_session_identity_only','true'),('extra','not allowed')])
def test_acknowledgements_and_closed_payload_are_required(env,field,value):
    data=proposal(preview(env));data[field]=value;post(env,data,422)


def test_failed_commit_rolls_back_adoption_link_evidence_and_receipt(env,monkeypatch):
    async def fail(session):raise RuntimeError('Synthetic commit failure')
    monkeypatch.setattr(service.setup,'commit',fail)
    post(env,proposal(preview(env)),503)
    with Session(env.engine) as db:
        assert db.query(models.PlanningLogicalPlanRow).count()==0
        assert db.query(models.PlanningPlanExecutionLinkRow).count()==0
        assert db.query(models.PlanningEvidenceItemRow).count()==0
        assert db.query(models.PlanningAuditArtifactRow).count()==0


def test_lost_commit_acknowledgement_can_retry_the_original_review(env,monkeypatch):
    commit=service.setup.commit
    async def commit_then_fail(session):await commit(session);raise RuntimeError('Synthetic lost ack')
    data=proposal(preview(env))
    with monkeypatch.context() as scoped:
        scoped.setattr(service.setup,'commit',commit_then_fail);post(env,data,503)
    saved=post(env,data,200);assert saved['reused']
    with Session(env.engine) as db:assert db.query(models.PlanningPlanRevisionRow).count()==1


def test_old_review_cannot_create_a_second_connection_under_a_new_request_id(env):
    value=preview(env);post(env,proposal(value))
    post(env,proposal(value,130002),409)


def test_provider_refresh_after_freeze_does_not_rewrite_the_frozen_source(env):
    data=proposal(preview(env));first=post(env,data)
    with Session(env.engine) as db:
        w=db.get(WorkoutSession,UUID(ACTUAL));w.duration_sec=2000;w.raw_data={'refreshed':True};db.commit()
    again=post(env,data,200)
    assert again['artifact']==first['artifact']
    assert preview(env)['execution_reference']==first['artifact']['execution_reference']


def test_projection_write_failure_leaves_no_partial_adoption_or_link(env,monkeypatch):
    async def fail(*args,**kwargs):raise RuntimeError('Synthetic evidence write failure')
    monkeypatch.setattr(service.SqlAlchemyEvidenceRepository,'save',fail)
    post(env,proposal(preview(env)),503)
    with Session(env.engine) as db:
        assert db.query(models.PlanningPlanRevisionRow).count()==0
        assert db.query(models.PlanningPlanExecutionLinkRow).count()==0
        assert db.query(models.PlanningAuditArtifactRow).count()==0


def test_learning_refresh_failure_preserves_the_committed_execution_proof(env,monkeypatch):
    from app.services import feedback_learning
    async def fail(**kwargs):raise RuntimeError('Synthetic learning refresh error')
    monkeypatch.setattr(feedback_learning,'refresh',fail)
    result=post(env,proposal(preview(env)))
    assert result['committed'] and result['learning']=={'state':'retry_required'}
    assert preview(env)['state']=='already_frozen'


def test_profile_timezone_changes_require_rechecking_the_review(env):
    from app.models.entities import User
    from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE
    value=preview(env)
    with Session(env.engine) as db:db.get(User,UUID(ATHLETE)).timezone='UTC';db.commit()
    post(env,proposal(value),409)


def test_locked_capture_refreshes_preloaded_orm_rows_before_hashing(env):
    import asyncio
    from sqlalchemy import update
    from app.planning.infrastructure.adapters.locked_execution_source import CurrentAppLockedExecutionSource
    from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE
    with Session(env.engine) as db:
        workout=db.get(WorkoutSession,UUID(ACTUAL));plan=db.get(PlannedWorkout,UUID(PLAN))
        db.execute(update(WorkoutSession).where(WorkoutSession.id==workout.id).values(duration_sec=2000).execution_options(synchronize_session=False))
        db.execute(update(PlannedWorkout).where(PlannedWorkout.id==plan.id).values(title='Refreshed source').execution_options(synchronize_session=False))
        assert workout.duration_sec==2700
        capture=asyncio.run(service.CurrentAppLockedExecutionSource().lock_and_capture(AsyncSQLiteBridge(db),
            athlete_id=ATHLETE,source_workout_id=PLAN,workout_session_id=ACTUAL))
        assert capture.session_snapshot['duration_sec']==2000
        assert plan.title=='Refreshed source'


def test_request_identity_is_not_reusable_for_another_owned_session(env):
    from app.models.entities import Sport
    from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE
    value=preview(env);data=proposal(value);post(env,data)
    other=UUID(int=130002)
    with Session(env.engine) as db:
        db.add(WorkoutSession(id=other,user_id=UUID(ATHLETE),sport=Sport.KAYAK,started_at=NOW,
            external_provider='SYNTHETIC',external_id='c13-other'));db.commit()
    reply=env.client.post(f'/api/v1/planning/calendar/sessions/{other}/execution-connection',json=data)
    assert reply.status_code==409


def test_receipt_and_preview_fixture_is_synthetic_and_cross_language_ready(env):
    import os,json
    from pathlib import Path
    value=preview(env);data=proposal(value);saved=post(env,data)
    destination=os.environ.get('P24C13_FIXTURE')
    if destination:Path(destination).write_text(json.dumps({'preview':value,'proposal':data,'receipt':saved},ensure_ascii=False,indent=2)+'\n')
    assert saved['artifact']['phase_alignment_verified'] is False


def test_conflicting_provider_target_ids_cannot_be_overridden_by_the_review(env):
    with Session(env.engine) as db:
        p=db.get(PlannedWorkout,UUID(PLAN));p.source='POLAR';p.polar_target_id='expected'
        w=db.get(WorkoutSession,UUID(ACTUAL));w.raw_data={'trainingTarget':{'id':'different'}}
        w.planned_workout_link_source='MANUAL_CONFIRMED';db.commit()
    value=preview(env);assert value['state']=='blocked'
    post(env,proposal(value),409)


def test_an_existing_plan_baseline_is_reused_for_another_explicit_session(env):
    from app.models.entities import Sport
    from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE
    first=post(env,proposal(preview(env)))
    other=UUID(int=130003)
    with Session(env.engine) as db:
        db.add(WorkoutSession(id=other,user_id=UUID(ATHLETE),sport=Sport.KAYAK,started_at=NOW,
            duration_sec=2700,planned_workout_id=UUID(PLAN),planned_workout_link_source='MANUAL_CONFIRMED',
            external_provider='SYNTHETIC',external_id='second-owned',raw_data={}));db.commit()
    url=f'/api/v1/planning/calendar/sessions/{other}/execution-connection'
    value=env.client.get(url).json()
    assert value['state']=='ready_for_review' and value['plan_adoption_required'] is False
    saved=env.client.post(url,json=proposal(value,130004))
    assert saved.status_code==201,saved.text
    assert saved.json()['artifact']['plan_reference']==first['artifact']['plan_reference']
    with Session(env.engine) as db:assert db.query(models.PlanningPlanRevisionRow).count()==1
