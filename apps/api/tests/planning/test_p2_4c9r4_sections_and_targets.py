"""Stored lap statistics, typed limits and old marker upgrades through real read/sync."""
from copy import deepcopy
import json,os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import BlockType,ProviderDataRecord,WorkoutBlock,WorkoutSession
from app.services import polar_session_details as details
from app.services import session_sections as sections
from app.services.session_chart_zones import zone_limits
from tests.planning.test_p2_4c6_calendar_workspace import agenda,ACTUAL,PLAN
from tests.planning.test_p2_4c9_session_analysis import raw,get
from tests.planning.test_p2_4c9r3_chart_guides import source_zones
from tests.planning.test_p2_4c9r2_session_details_sync import connections,enriched,fetch,identity,read
from tests.planning.test_p2_4c7_data_connections import proposal,post


def detailed_source():
    result=raw();e=result['exerciseSamples'][0]
    e['durationMillis']=600000;e['distanceMeters']=1800
    e['statistics']={'statistics':[{'type':'STATISTICS_TYPE_HEART_RATE','avg':124},{'type':'STATISTICS_TYPE_SPEED','avg':10.8}]}
    e['zones']=source_zones()+[
        {'type':'ZONE_TYPE_SPEED','zones':[{'lowerLimit':v,'higherLimit':v+2,'inZone':0} for v in (0,2,4,6,8)]},
        {'type':'ZONE_TYPE_POWER','zones':[{'lowerLimit':v,'higherLimit':v+100,'inZone':0} for v in (0,100,200,300,400)]}]
    e['laps']={'laps':[{'durationMillis':v,'distanceMeters':distance,'splitTimeMillis':total,'statistics':{'statistics':[
        {'type':'STATISTICS_TYPE_HEART_RATE','avg':hr},{'type':'STATISTICS_TYPE_SPEED','avg':speed}]}}
        for v,distance,total,hr,speed in [(120000,300,120000,110,9),(180000,600,300000,125,12),(300000,900,600000,135,10.8)]],
        'autoLaps':[{'durationMillis':200000,'distanceMeters':1000,'statistics':{'statistics':[{'type':'STATISTICS_TYPE_HEART_RATE','avg':140}]}}]}
    return result


def test_owned_read_retains_order_exact_per_section_metrics_limits_and_no_writes(agenda):
    source=detailed_source()
    with Session(agenda.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).raw_data=source
        db.add_all([WorkoutBlock(id=UUID(int=94001),workout_id=UUID(PLAN),position=0,block_type=BlockType.WORK,name='Sebesség <script>x</script>',intensity_type='SPEED_ZONES',intensity_min=2,intensity_max=3),
          WorkoutBlock(id=UUID(int=94002),workout_id=UUID(PLAN),position=1,block_type=BlockType.WORK,name='Wattos cél',intensity_type='POWER_W',intensity_min=180,intensity_max=220)])
        db.commit()
    result=get(agenda);groups=result['sections']['groups']
    assert result['sections']['row_count']==5 and len(groups)==3
    assert [r['avg_hr'] for r in groups[1]['rows']]==[110,125,135]
    assert [r['avg_speed'] for r in groups[1]['rows']]==[9,12,10.8]
    assert [r['duration_sec'] for r in groups[1]['rows']]==[120,180,300]
    assert groups[2]['rows'][0]['avg_speed'] is None
    exercise=result['samples']['exercises'][0]
    assert exercise['speed_zones']['zones'][0]['low']==0 and exercise['speed_zones']['unit']=='km/h'
    assert exercise['power_zones']['zones'][1]['high']==200 and exercise['power_zones']['unit']=='W'
    with Session(agenda.engine) as db:assert db.get(WorkoutSession,UUID(ACTUAL)).raw_data==source
    assert all(not r.in_transaction() for r in agenda.requests)
    if os.environ.get('P24C9R4_FIXTURE_OUTPUT'):Path(os.environ['P24C9R4_FIXTURE_OUTPUT']).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


@pytest.mark.parametrize('value',[None,True,-1,float('inf'),'120'])
def test_invalid_or_missing_section_duration_stays_unknown(value):
    source=detailed_source();source['exerciseSamples'][0]['laps']['laps'][0]['durationMillis']=value
    result=sections.section_groups(source,'POLAR')
    assert result['groups'][1]['rows'][0]['duration_sec'] is None


def test_zero_and_missing_averages_remain_distinct_without_whole_session_substitution():
    source=detailed_source();lap=source['exerciseSamples'][0]['laps']['laps'][0]
    lap['distanceMeters']=0;lap['durationMillis']=0;lap['statistics']={'statistics':[{'type':'STATISTICS_TYPE_SPEED','avg':0}]}
    row=sections.section_groups(source,'POLAR')['groups'][1]['rows'][0]
    assert row['avg_speed']==0 and row['avg_hr'] is None and row['distance_m']==0 and row['duration_sec']==0


def test_partial_invalid_sources_keep_slot_positions_and_report_issues():
    source=detailed_source();laps=source['exerciseSamples'][0]['laps']['laps'];laps[1]=False
    result=sections.section_groups(source,'POLAR')
    assert [r['position'] for r in result['groups'][1]['rows']]==[0,2]
    assert result['row_count']==4 and result['issues']==['SECTION_INVALID:exerciseSamples[0].laps.laps[1]']


def test_duplicate_statistics_do_not_choose_an_arbitrary_average():
    source=detailed_source();lap=source['exerciseSamples'][0]['laps']['laps'][0]
    lap['statistics']['statistics'].append({'type':'STATISTICS_TYPE_HEART_RATE','avg':170})
    row=sections.section_groups(source,'POLAR')['groups'][1]['rows'][0]
    assert row['avg_hr'] is None and row['issues']==['AMBIGUOUS_STATISTIC:STATISTICS_TYPE_HEART_RATE']


def test_multisport_parts_and_alternate_lap_sources_are_not_combined():
    source=detailed_source();other=deepcopy(source['exerciseSamples'][0]);other['laps']['laps'][0]['distanceMeters']=400
    source['exerciseSamples'].append(other);result=sections.section_groups(source,'POLAR')
    assert len(result['groups'])==5 and result['row_count']==10
    assert result['groups'][3]['rows'][0]['distance_m']==400
    assert result['groups'][1]['rows'][0]['exercise_index']==0 and result['groups'][3]['rows'][0]['exercise_index']==1


def test_projection_caps_rows_and_statistics_without_silent_truncation(monkeypatch):
    monkeypatch.setattr(sections,'ROW_LIMIT',2)
    with pytest.raises(sections.CalendarRuleError):sections.section_groups(detailed_source(),'POLAR')
    monkeypatch.setattr(sections,'ROW_LIMIT',4000)
    source=detailed_source();source['exerciseSamples'][0]['statistics']={'statistics':[{}]*129}
    with pytest.raises(sections.CalendarRuleError):sections.section_groups(source,'POLAR')


def test_nonpolar_or_empty_sources_never_fabricate_laps():
    assert sections.section_groups(detailed_source(),'OTHER')['groups']==[]
    assert sections.section_groups({},'POLAR')['groups']==[]


def test_native_lap_view_is_preserved_while_optional_features_are_added():
    stored={'identifier':{'id':'s'},'exercises':[{'identifier':{'id':'e'},'laps':{'laps':[{'durationMillis':1000}]}}]}
    incoming={'identifier':{'id':'s'},'exercises':[{'identifier':{'id':'e'}}]}
    merged=details.merge_details(stored,incoming,'s')
    assert merged['exerciseSamples'][0]['laps']==stored['exercises'][0]['laps']
    assert 'exerciseSamples' not in stored
    incoming['exercises'][0]['laps']={'laps':[{'durationMillis':2000}]}
    with pytest.raises(details.PolarRawPreservationError):details.merge_details(stored,incoming,'s')


def test_laps_upgrade_accepts_old_zone_marker_without_rewriting_old_sync_receipt(connections):
    e=connections;post(e,proposal(token=880001,datasets=['sessions']));first=fetch(e)
    with Session(e.engine) as db:
        marker=db.scalar(select(ProviderDataRecord).where(ProviderDataRecord.data_type==details.RECEIPT_TYPE))
        marker.raw_data={**marker.raw_data,'features':details.ZONE_FEATURES};marker.provider_record_id='sync:'+details.digest(marker.raw_data);db.commit()
    response=enriched(e.session_payload['trainingSessions'][0]);response['exercises'][0]['laps']=detailed_source()['exerciseSamples'][0]['laps']
    e.detail_responses['2026-10-22']={'trainingSessions':[response]}
    assert fetch(e,status=200)['result']==first['result'] and len(e.detail_calls)==1
    result=fetch(e,880003);assert result['run']['state']=='succeeded' and len(e.detail_calls)==2
    assert len(read(e,identity(e))['sections']['groups'][1]['rows'])==3
    fetch(e,880004);assert len(e.detail_calls)==2


def test_real_protected_plan_plus_details_batch_produces_a_verifiable_resumable_receipt(connections,monkeypatch):
    from app.models.entities import PlannedWorkout
    from tests.planning.test_p2_4c7_data_connections import get as connection_status
    e=connections;post(e,proposal(token=880010,datasets=['targets']))
    with Session(e.engine) as db:
        plan=db.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id=='new-target'))
        plan.source='MANUAL';db.commit()
    one=e.session_payload['trainingSessions'][0]
    e.session_payload['trainingSessions']=[{**deepcopy(one),'identifier':{'id':f'day-{day}'},'startTime':f'2026-10-{day:02}T07:00:00Z','stopTime':f'2026-10-{day:02}T08:00:00Z'} for day in (21,22)]
    monkeypatch.setattr(details,'DAY_LIMIT',1)
    body=proposal(token=880011,datasets=['sessions','targets','session_details']);result=post(e,body)
    assert result['run']['state']=='partial' and result['run']['error_code']=='DATA_SYNC_PROTECTED_PLANS_SKIPPED'
    assert result['run']['datasets'][2]['error_code']=='DATA_SYNC_DETAILS_PENDING'
    assert result['run']['datasets'][2]['details']['pending_sessions']==1
    if os.environ.get('P24C9R4_SYNC_FIXTURE_OUTPUT'):
        Path(os.environ['P24C9R4_SYNC_FIXTURE_OUTPUT']).write_text(json.dumps({'body':body,'receipt':result,'status':connection_status(e)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
