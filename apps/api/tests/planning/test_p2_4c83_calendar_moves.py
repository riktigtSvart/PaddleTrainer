"""Real HTTP + immutable audit + transactional start changes, isolated SQLite."""
from datetime import UTC,date,datetime
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import PlannedWorkout, WorkoutSession, WorkoutStatus, Sport
from app.planning.application import calendar_moves as service
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, count
from tests.planning.test_p2_4c81_calendar_constraints import agenda as fixture, UNLINKED, PLAN

BASE='/api/v1/planning/calendar'

@pytest.fixture
def agenda(tmp_path,monkeypatch):
    gen=fixture.__wrapped__(tmp_path,monkeypatch);env=next(gen)
    monkeypatch.setattr(service,'_now',env.clock.tick)
    try:yield env
    finally:gen.close()

def context(e,plan=UNLINKED,status=200):
    r=e.client.get(BASE+'/moves/'+plan);assert r.status_code==status,r.text
    return r.json()

def proposal(e,n=99001,**updates):
    c=context(e)
    return dict(request_id=str(UUID(int=n)),plan_id=UNLINKED,expected_source_hash=c['source_hash'],
        previous_reference=c['previous_reference'],timezone_name=c['timezone_name'],date='2026-10-24',start_time='06:00',start_fold=None,**updates)

def preview(e,b,status=200):
    r=e.client.post(BASE+'/moves/preview',json=b);assert r.status_code==status,r.text
    return r.json()

def save(e,b,v=None,status=201):
    if v is None:v=preview(e,b)
    r=e.client.post(BASE+'/moves',json={'proposal':b,'review_hash':v['review_hash']});assert r.status_code==status,r.text
    return r.json()

def test_preview_and_save_preserve_prescription_and_actuals(agenda):
    e=agenda;b=proposal(e);v=preview(e,b)
    assert v['after']['planned_start_time']=='2026-10-24T04:00:00+00:00'
    assert count(e,PlanningAuditArtifactRow)==0
    with Session(e.engine) as db:assert db.get(PlannedWorkout,UUID(UNLINKED)).date==date(2026,10,23)
    a=save(e,b,v)['artifact']
    with Session(e.engine) as db:
        p=db.get(PlannedWorkout,UUID(UNLINKED));assert p.date==date(2026,10,24) and p.duration_sec==1200 and p.planned_start_time.hour==4
        assert db.get(PlannedWorkout,UUID(PLAN)).planned_start_time.hour==15
    assert a['before']['date']=='2026-10-23' and a['training_dose_changed'] is False
    feed=e.client.get(BASE+'/feed?start_date=2026-10-24&end_date=2026-10-24').json()
    assert any(p['id']==UNLINKED for p in feed['planned'])
    assert context(e)['restore']==a['before']

def test_identical_retry_and_request_conflict(agenda):
    b=proposal(agenda);v=preview(agenda,b);first=save(agenda,b,v)
    again=save(agenda,b,v,status=200);assert again['reused'] and again['artifact']==first['artifact']
    changed={**b,'start_time':'07:00'};save(agenda,changed,v,status=409)
    assert count(agenda,PlanningAuditArtifactRow)==1

def test_source_changed_after_preview_rejected(agenda):
    b=proposal(agenda);v=preview(agenda,b)
    with Session(agenda.engine) as db:
        db.get(PlannedWorkout,UUID(UNLINKED)).title='Changed';db.commit()
    assert save(agenda,b,v,status=409)['detail']['code']=='CALENDAR_MOVE_SOURCE_CHANGED'
    assert count(agenda,PlanningAuditArtifactRow)==0

def test_linked_completed_cancelled_and_foreign_are_not_movable(agenda):
    assert context(agenda,PLAN)['blocked_reason']=='CALENDAR_MOVE_ALREADY_EXECUTED'
    b=proposal(agenda)
    for status in [WorkoutStatus.COMPLETED,WorkoutStatus.CANCELLED]:
        with Session(agenda.engine) as db:db.get(PlannedWorkout,UUID(UNLINKED)).status=status;db.commit()
        assert not context(agenda)['allowed']
        preview(agenda,b,409)
    context(agenda,str(UUID(int=701099)),404)

def test_dst_gap_fold_and_review_tamper(agenda):
    b=proposal(agenda)
    gap={**b,'date':'2027-03-28','start_time':'02:30'}
    assert preview(agenda,gap,409)['detail']['code']=='ATHLETE_TIME_DOES_NOT_EXIST'
    repeated={**b,'date':'2026-10-25','start_time':'02:30'}
    assert preview(agenda,repeated,409)['detail']['code']=='ATHLETE_TIME_IS_AMBIGUOUS'
    first=preview(agenda,{**repeated,'start_fold':0});second=preview(agenda,{**repeated,'start_fold':1})
    assert first['after']!=second['after']
    v=preview(agenda,b);v['review_hash']='0'*64;save(agenda,b,v,status=409)

def test_earlier_request_replay_never_rewinds_and_restore_is_new_revision(agenda):
    b=proposal(agenda);v=preview(agenda,b);one=save(agenda,b,v)
    two=proposal(agenda,n=99002);two['start_time']='08:00';second=save(agenda,two)
    save(agenda,b,v,status=200)
    assert context(agenda)['current']==second['artifact']['after']
    restore=proposal(agenda,n=99003);restore['date']='2026-10-23';restore['start_time']='17:40'
    third=save(agenda,restore)
    assert third['artifact']['revision']==3

def test_constraints_change_after_review_requires_new_preview(agenda):
    from tests.planning.test_p2_4c81_calendar_constraints import post as schedule_post,body,rule,details
    b=proposal(agenda);v=preview(agenda,b)
    schedule_post(agenda,body(rules=[rule(start_date='2026-10-24',end_date='2026-10-24',repeat='once',weekdays=[],details=details(start_time='05:00',end_time='09:00'))]))
    result=save(agenda,b,v,status=409)
    assert result['detail']['code']=='CALENDAR_MOVE_REVIEW_CHANGED'
    fresh=preview(agenda,b);assert fresh['conflicts']
    save(agenda,b,fresh)

def test_prescription_field_injection_and_boolean_fold_are_rejected(agenda):
    b=proposal(agenda)
    for patch in [{'duration_sec':1},{'distance_m':1},{'start_fold':True},{'entity_kind':'session'}]:
        preview(agenda,{**b,**patch},422)
    assert count(agenda,PlanningAuditArtifactRow)==0

def test_approved_plan_requires_its_own_revision_workflow(agenda):
    from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningLogicalPlanRow
    with Session(agenda.engine) as db:
        db.add(PlanningLogicalPlanRow(logical_plan_id='tracked-plan',athlete_id=UUID(ATHLETE),source_workout_id=UUID(UNLINKED),current_revision_number=0,created_at=datetime.now(UTC),updated_at=datetime.now(UTC)))
        db.commit()
    assert context(agenda)['blocked_reason']=='CALENDAR_MOVE_APPROVED_PLAN_REVIEW_REQUIRED'
    preview(agenda,proposal(agenda),409)

def test_failed_commit_rolls_back_timing_and_audit_together(agenda,monkeypatch):
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    b=proposal(agenda);v=preview(agenda,b)
    async def failure(self):raise RuntimeError('synthetic commit failure')
    monkeypatch.setattr(AsyncSQLiteBridge,'commit',failure)
    save(agenda,b,v,status=503)
    with Session(agenda.engine) as db:assert db.get(PlannedWorkout,UUID(UNLINKED)).date==date(2026,10,23)
    assert count(agenda,PlanningAuditArtifactRow)==0

def test_untimed_original_can_be_restored_without_inventing_zero(agenda):
    from tests.planning.test_p2_4c6_calendar_workspace import UNTIMED
    c=context(agenda,UNTIMED);b=proposal(agenda);b.update(plan_id=UNTIMED,expected_source_hash=c['source_hash'],previous_reference=c['previous_reference'])
    one=save(agenda,b)
    c=context(agenda,UNTIMED);b.update(request_id=str(UUID(int=99002)),expected_source_hash=c['source_hash'],previous_reference=c['previous_reference'],date='2026-10-23',start_time=None)
    two=save(agenda,b)
    assert two['artifact']['after']['planned_start_time'] is None
    with Session(agenda.engine) as db:assert db.get(PlannedWorkout,UUID(UNTIMED)).duration_sec is None

def test_polar_refresh_preserves_explicit_app_timing_and_updates_source(connections):
    from sqlalchemy import select
    from tests.planning.test_p2_4c7_data_connections import post as sync,proposal as sync_body
    e=connections;sync(e,sync_body(datasets=['targets']))
    with Session(e.engine) as db:pid=str(db.scalar(select(PlannedWorkout.id).where(PlannedWorkout.polar_target_id=='new-target')))
    c=context(e,pid);b=dict(request_id=str(UUID(int=99101)),plan_id=pid,expected_source_hash=c['source_hash'],previous_reference=c['previous_reference'],timezone_name=c['timezone_name'],date='2026-10-29',start_time='06:30',start_fold=None)
    save(e,b)
    e.target_payload[0]['session']['name']='Provider updated title'
    sync(e,sync_body(token=770002,datasets=['targets']))
    with Session(e.engine) as db:
        p=db.get(PlannedWorkout,UUID(pid));assert p.date==date(2026,10,29) and p.planned_start_time.hour==5 and p.planned_start_time.minute==30
        assert p.title=='Provider updated title' and p.raw_data['session']['name']=='Provider updated title'
    assert context(e,pid)['current']['date']=='2026-10-29'

from tests.planning.test_p2_4c7_data_connections import connections

def test_overlap_with_actual_is_reviewed_without_changing_measured_time(agenda):
    from tests.planning.test_p2_4c6_calendar_workspace import ACTUAL
    b=proposal(agenda);b.update(date='2026-10-23',start_time='17:45')
    v=preview(agenda,b);assert any(c['code']=='TRAINING_OVERLAP' for c in v['conflicts'])
    save(agenda,b,v)
    with Session(agenda.engine) as db:
        actual=db.get(WorkoutSession,UUID(ACTUAL));assert actual.started_at.hour==15 and actual.started_at.minute==35
        assert actual.duration_sec==2700 and actual.raw_data=={'unchanged':True}

def test_another_plan_with_unknown_end_remains_a_review_reason(agenda):
    with Session(agenda.engine) as db:
        db.add(PlannedWorkout(user_id=UUID(ATHLETE),date=date(2026,10,24),planned_start_time=datetime(2026,10,24,3,tzinfo=UTC),sport=Sport.KAYAK,title='Unknown end',duration_sec=None));db.commit()
    v=preview(agenda,proposal(agenda))
    assert any(c['code']=='OTHER_TRAINING_TIME_UNKNOWN' for c in v['conflicts'])

def test_missing_own_duration_never_yields_a_clear_overlap_claim(agenda):
    from tests.planning.test_p2_4c6_calendar_workspace import UNTIMED
    c=context(agenda,UNTIMED);b=proposal(agenda);b.update(plan_id=UNTIMED,expected_source_hash=c['source_hash'],previous_reference=None)
    v=preview(agenda,b)
    assert any(c['code']=='PLAN_END_UNKNOWN' for c in v['conflicts'])

def test_changed_period_boundary_requires_re_review(agenda):
    from app.models.entities import TrainingPeriod,PeriodType
    with Session(agenda.engine) as db:
        period=TrainingPeriod(user_id=UUID(ATHLETE),title='One-day cycle',period_type=PeriodType.MESOCYCLE,start_date=date(2026,10,23),end_date=date(2026,10,23));db.add(period);db.flush();db.get(PlannedWorkout,UUID(UNLINKED)).training_period_id=period.id;db.commit();pid=period.id
    b=proposal(agenda);v=preview(agenda,b);assert v['period_warning']
    with Session(agenda.engine) as db:db.get(TrainingPeriod,pid).end_date=date(2026,10,25);db.commit()
    assert save(agenda,b,v,status=409)['detail']['code']=='CALENDAR_MOVE_REVIEW_CHANGED'


def test_actual_with_missing_end_stays_unknown_without_a_fabricated_estimate(agenda):
    with Session(agenda.engine) as db:
        db.add(WorkoutSession(user_id=UUID(ATHLETE),external_provider='POLAR',external_id='unknown-end',sport=Sport.KAYAK,
            started_at=datetime(2026,10,24,3,tzinfo=UTC),ended_at=None,duration_sec=None,raw_data={}));db.commit()
    v=preview(agenda,proposal(agenda))
    assert any(c['code']=='OTHER_TRAINING_TIME_UNKNOWN' and c['severity']=='review' and c['occurrence_key'].startswith('session:') for c in v['conflicts'])
