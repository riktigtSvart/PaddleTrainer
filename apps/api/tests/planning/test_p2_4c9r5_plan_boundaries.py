"""Owned plan clocks: source fallback, repeats, unknowns and read-only guards."""
from copy import deepcopy
import json,os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import pytest
from sqlalchemy.orm import Session
from app.models.entities import BlockType,PlannedWorkout,WorkoutBlock
from app.services import session_plan_timeline as timeline
from tests.planning.test_p2_4c6_calendar_workspace import agenda,PLAN
from tests.planning.test_p2_4c9_session_analysis import get


def source():
    return {'session':{'id':'four-by-twelve'},'exercise':[{'phaseOrRepeat':[
      {'name':'Bemelegítés','goal':{'type':'DURATION','duration':1200000}},
      {'name':'Ismétlések','repeatCount':4,'phaseOrRepeat':[
        {'name':'Munka <script>literal</script>','goal':{'type':'DURATION','duration':720000}},
        {'name':'Pihenő','goal':{'type':'DURATION','duration':120000}}]}]}]}


def plan(raw=None,blocks=None,**values):
    return SimpleNamespace(id=UUID(PLAN),blocks=blocks or [],source='POLAR',polar_target_id='four-by-twelve',raw_data=raw,**values)


def test_real_owned_read_restores_missing_block_clock_from_exact_stored_target_without_writing(agenda):
    raw=source()
    with Session(agenda.engine) as db:
        p=db.get(PlannedWorkout,UUID(PLAN));p.source='POLAR';p.polar_target_id='four-by-twelve';p.raw_data=raw;db.commit()
    result=get(agenda);clock=result['plan_timeline'];phases=clock['parts'][0]['phases']
    assert result['plan']['blocks']==[] and clock['source']=='stored_polar_target'
    assert len(phases)==9 and phases[1]['from_ms']==1200000 and phases[1]['to_ms']==1920000
    assert [p['from_ms'] for p in phases[1::2]]==[1200000,2040000,2880000,3720000]
    assert clock['parts'][0]['total_ms']==4560000  # This source explicitly includes the fourth recovery.
    again=get(agenda);assert again['plan_timeline']['content_hash']==clock['content_hash']
    with Session(agenda.engine) as db:
        p=db.get(PlannedWorkout,UUID(PLAN));assert p.blocks==[] and p.raw_data==raw
    assert all(not r.in_transaction() for r in agenda.requests)
    output=os.environ.get('P24C9R5_FIXTURE_OUTPUT')
    if output:Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def test_empty_plan_title_does_not_invent_warmup_or_recovery_even_for_four_by_twelve():
    result=timeline.plan_timeline(plan())
    assert result['source']=='unavailable' and result['parts']==[] and result['issues']==['PLAN_PHASES_NOT_STORED']


@pytest.mark.parametrize('change',[
    lambda p:setattr(p,'source','MANUAL'),
    lambda p:setattr(p,'polar_target_id','another-target'),
    lambda p:p.raw_data['session'].update(id=True),
])
def test_stale_manual_or_differently_identified_source_is_not_used(change):
    p=plan(source());change(p);assert timeline.plan_timeline(p)['parts']==[]


def test_stored_block_hierarchy_takes_precedence_and_expands_repeat_in_order():
    warm=SimpleNamespace(id=UUID(int=1),parent_block_id=None,position=0,block_type=BlockType.WARMUP,name='Warm',duration_sec=600,repeat_count=1)
    repeat=SimpleNamespace(id=UUID(int=2),parent_block_id=None,position=1,block_type=BlockType.REPEAT,name='Repeat',duration_sec=None,repeat_count=4)
    work=SimpleNamespace(id=UUID(int=3),parent_block_id=repeat.id,position=0,block_type=BlockType.WORK,name='Work',duration_sec=720,repeat_count=1)
    result=timeline.plan_timeline(plan(source(),[work,repeat,warm]));part=result['parts'][0]
    assert result['source']=='stored_blocks' and [p['from_ms'] for p in part['phases']]==[0,600000,1320000,2040000,2760000]
    assert all(p['source_block_id']==str(work.id) for p in part['phases'][1:])
    assert part['total_ms']==3480000


def test_unknown_distance_or_manual_goal_stops_later_positioning_without_losing_durations():
    raw=source();raw['exercise'][0]['phaseOrRepeat'][0]['goal']={'type':'DISTANCE','distance':1000,'duration':60000}
    part=timeline.plan_timeline(plan(raw))['parts'][0]
    assert part['phases'][0]['from_ms']==0 and part['phases'][0]['to_ms'] is None
    assert part['phases'][1]['from_ms'] is None and part['phases'][1]['duration_ms']==720000
    assert part['total_ms'] is None and part['issues']==['PLAN_DURATION_UNKNOWN']


@pytest.mark.parametrize('value',[None,False,0,1.5,100,'4'])
def test_unknown_or_invalid_repeat_counts_do_not_create_precise_timepoints(value):
    raw=source();raw['exercise'][0]['phaseOrRepeat'][1]['repeatCount']=value
    result=timeline.plan_timeline(plan(raw));assert result['parts']==[] and result['issues']==['PLAN_REPEAT_COUNT_UNKNOWN']


def test_multiple_target_exercises_keep_separate_clocks():
    raw=source();raw['exercise'].append(deepcopy(raw['exercise'][0]));part=timeline.plan_timeline(plan(raw))['parts']
    assert [p['index'] for p in part]==[0,1] and part[1]['phases'][0]['from_ms']==0
    assert part[1]['phases'][0]['id']!=part[0]['phases'][0]['id']


def test_changed_timing_changes_fingerprint_without_mutating_raw_source():
    raw=source();before=deepcopy(raw);first=timeline.plan_timeline(plan(raw));assert raw==before
    raw['exercise'][0]['phaseOrRepeat'][0]['goal']['duration']+=1000
    assert timeline.plan_timeline(plan(raw))['content_hash']!=first['content_hash']


def test_source_limits_are_explicit_not_silent_truncation(monkeypatch):
    monkeypatch.setattr(timeline,'PHASE_LIMIT',2)
    with pytest.raises(timeline.CalendarRuleError):timeline.plan_timeline(plan(source()))


def test_foreign_plan_read_does_not_leak_a_timeline(agenda):
    from tests.planning.test_p2_4c6_calendar_workspace import ACTUAL,OTHER_PLAN
    from app.models.entities import WorkoutSession
    with Session(agenda.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).planned_workout_id=UUID(OTHER_PLAN);p=db.get(PlannedWorkout,UUID(OTHER_PLAN));p.source='POLAR';p.polar_target_id='four-by-twelve';p.raw_data=source();db.commit()
    result=get(agenda);assert result['plan'] is None and result['plan_timeline']['plan_id'] is None
    assert result['plan_timeline']['parts']==[]


def test_fractional_ms_and_explicit_zero_duration_keep_their_source_values():
    raw=source();phases=raw['exercise'][0]['phaseOrRepeat'];phases[:]=[{'name':'Zero','goal':{'type':'DURATION','duration':0}},{'name':'Fraction','goal':{'type':'DURATION','duration':1250.5}}]
    result=timeline.plan_timeline(plan(raw))['parts'][0]
    assert result['phases'][0]['to_ms']==0 and result['phases'][1]['from_ms']==0 and result['total_ms']==1250.5
