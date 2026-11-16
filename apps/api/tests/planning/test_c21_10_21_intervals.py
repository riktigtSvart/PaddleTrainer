"""Paired intervals preserve n work / n-1 rest, exact seconds and old receipts."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import manual_workouts
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM
from tests.planning.test_p2_4c6_calendar_workspace import agenda
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_c21_10_20_manual_workouts import body, draft, post, source, edits


def paired(work=720, rest=120, repetitions=3, **changes):
    return draft(sport='RUNNING', title='3 × 12 / 2', exercises=[], primary_goal='PERIPHERAL_OXIDATIVE_CAPACITY',
        duration_sec=work * repetitions + rest * max(0, repetitions - 1),
        phases=[{'block_type': 'WORK', 'name': 'Résztáv', 'duration_sec': work,
                 'repeat_count': repetitions, 'recovery_duration_sec': rest}], **changes)


@pytest.mark.parametrize('work,rest,n', [(720,120,3),(75,45,4),(720,120,1),(720,0,3)])
def test_exact_timeline_has_rest_only_between_repetitions(agenda, work, rest, n):
    b = body(draft=paired(work,rest,n)); saved = post(agenda,b)
    assert post(agenda,b)['reused']
    s = source(agenda,saved['workout_ids'][0])['workout']
    assert s['editable'] and s['copyable']
    assert len(s['draft']['phases']) == 1
    assert s['draft']['phases'][0]['repeat_count'] == n and s['draft']['phases'][0]['recovery_duration_sec'] == rest
    with Session(agenda.engine) as db:
        row = db.get(PlannedWorkout,UUID(s['id'])); blocks = sorted(row.blocks,key=lambda x:x.position)
        assert sum((p.duration_sec or 0)*(p.repeat_count or 1) for p in blocks) == row.duration_sec == work*n+rest*(n-1)
        if rest:
            assert [p.duration_sec for p in blocks] == [v for i in range(n) for v in ([work,rest] if i<n-1 else [work])]
            assert [p.block_type.value for p in blocks] == [v for i in range(n) for v in (['WORK','RECOVERY'] if i<n-1 else ['WORK'])]
            assert all(p.repeat_count==1 and p.parent_block_id is None for p in blocks)
        else:
            assert len(blocks)==1 and blocks[0].repeat_count==n


def test_paired_interval_can_be_edited_and_copied_without_flattening_the_editor_recipe(agenda):
    created=post(agenda,body(draft=paired()))
    b=edits(agenda,created); b['draft']['phases'][0]['repeat_count']=4; b['draft']['duration_sec']=3240
    post(agenda,b)
    s=source(agenda,created['workout_ids'][0])['workout']
    copied=post(agenda,body(21121001,copy_from=s['id'],copy_source_hash=s['source_hash'],draft={**s['draft'],'date':'2026-11-27'}))
    clone=source(agenda,copied['workout_ids'][0])['workout']
    assert clone['draft']['phases']==s['draft']['phases'] and clone['draft']['duration_sec']==3240
    assert source(agenda,s['id'])['workout']==s


@pytest.mark.parametrize('value', [-1,True,1.5,86401,'00:02:00'])
def test_invalid_recovery_never_becomes_a_changed_or_partial_plan(agenda,value):
    b=body(draft=paired());b['draft']['phases'][0]['recovery_duration_sec']=value
    before=count(agenda,PlannedWorkout),count(agenda,PlanningAuditArtifactRow),count(agenda,WorkoutSession)
    post(agenda,b,422)
    assert before==(count(agenda,PlannedWorkout),count(agenda,PlanningAuditArtifactRow),count(agenda,WorkoutSession))


def test_work_only_total_does_not_hide_the_interleaved_rest(agenda):
    b=body(draft=paired());b['draft']['duration_sec']=2160
    post(agenda,b,422)


def test_expansion_is_bounded_before_any_database_write(agenda):
    b=body(draft=paired(1,1,100));b['draft']['phases']*=6;b['draft']['duration_sec']=1194
    before=count(agenda,PlannedWorkout),count(agenda,PlanningAuditArtifactRow)
    post(agenda,b,422)
    assert before==(count(agenda,PlannedWorkout),count(agenda,PlanningAuditArtifactRow))


def test_legacy_separate_recovery_is_not_reinterpreted_as_between_only(agenda):
    d=paired();d['phases'][0].pop('recovery_duration_sec');d['phases'].append({'block_type':'RECOVERY','name':'Régi külön pihenők','duration_sec':120,'repeat_count':3});d['duration_sec']=2520
    result=post(agenda,body(draft=d));s=source(agenda,result['workout_ids'][0])['workout']
    assert len(s['draft']['phases'])==2 and s['draft']['duration_sec']==2520
    assert s['draft']['phases'][1]['repeat_count']==3 and s['draft']['phases'][1]['recovery_duration_sec'] is None


def test_actual_frozen_c20_receipt_retains_exact_bytes_and_supports_idempotent_retry(agenda):
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/c21_10_21_legacy_manual_receipt.json').read_text(encoding='utf-8'))
    original=fixture['contract_json'];a=json.loads(original)
    assert all('recovery_duration_sec' not in p for p in a['proposal']['draft']['phases'])
    with Session(agenda.engine) as db:
        db.add(PlanningAuditArtifactRow(artifact_kind=manual_workouts.KIND.value,artifact_id=a['artifact_id'],athlete_id=UUID(a['athlete_id']),
            schema_version=a['schema_version'],created_at=datetime.fromisoformat(a['created_at']),persisted_at=agenda.clock.tick(),
            content_hash_algorithm=CONTENT_HASH_ALGORITHM,content_hash=a['content_hash'],contract_json=original))
        db.commit()
    before=count(agenda,PlanningAuditArtifactRow),count(agenda,PlannedWorkout)
    receipt=post(agenda,fixture['request']);assert receipt['reused'] and receipt['content_hash']==a['content_hash']
    assert before==(count(agenda,PlanningAuditArtifactRow),count(agenda,PlannedWorkout))
    changed=deepcopy(fixture['request']);changed['draft']['phases'][0]['recovery_duration_sec']=1
    post(agenda,changed,409)
    with Session(agenda.engine) as db:
        row=db.query(PlanningAuditArtifactRow).filter_by(artifact_id=a['artifact_id']).one()
        assert row.contract_json==original and row.content_hash==a['content_hash']
