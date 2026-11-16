"""Concrete routines preserve verified work sets and the accepted time envelope."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import training_instructions as instructions, training_plan_policy as policy
from tests.planning.test_c21_10_9_profile_sources import env, configure, full, initial_context
from tests.planning.test_c21_10_7_calendar_cycles import get
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c3_goal_workflow_api import count


def export(name, value):
    if os.getenv('C21_10_10_EXPORT'):
        path = Path(os.environ['C21_10_10_EXPORT'])
        values = json.loads(path.read_text()) if path.exists() else {}
        values[name] = value
        path.write_text(json.dumps(values), encoding='utf-8')


def stats(e):
    return tuple(count(e, table) for table in (PlanningAuditArtifactRow, PlannedWorkout, WorkoutSession))


def test_real_mixed_review_has_concrete_routines_and_unchanged_assessment(env):
    configure(env)
    before = initial_context(env)
    review = full(env)
    result = review['result']
    context = result['instruction_context']
    assert context['schema_version'] == 'training-instructions-v0.1'
    assert set(context['by_candidate']) == {c['candidate_key'] for c in result['proposals']}
    assert {c['sport'] for c in result['proposals']} == {'STRENGTH', 'KAYAK', 'RUNNING', 'SWIMMING'}
    for candidate in result['proposals']:
        routine = context['by_candidate'][candidate['candidate_key']]
        assert routine == instructions.derive(candidate, result['prescription_context']['by_candidate'][candidate['candidate_key']])
        assert sum(s['duration_sec'] for s in routine['warmup']['steps']) == routine['warmup']['duration_sec']
        assert sum(routine[k]['duration_sec'] for k in ('warmup', 'main', 'finish')) == candidate['duration_sec']
        finish = routine['finish']
        assert finish['stretching_optional'] and finish['stretching_replaces_easy_finish']
        assert finish['easy_duration_sec'] + sum(s['duration_sec'] for s in finish['stretches']) == finish['duration_sec']
        assert not any(routine[k] for k in ('external_load_increased', 'sets_added', 'recovery_effect_claimed', 'personal_response_model_applied'))
        if candidate['sport'] == 'STRENGTH':
            dose = candidate['strength_prescription']
            assert routine['main']['strength'] == dose
            assert dose['minimum_rir'] == 3 and not dose['load_increased']
            entries = {e['id']: e for e in before['data']['exercises']}
            assert all(m['reference_set'] in entries[m['entry_id']]['sets'] for m in dose['movements'])
        else:
            assert routine['main']['strength'] is None
    assert initial_context(env)['saved']['artifact'] == before['saved']['artifact']
    export('mixed_review', review)


def test_owned_calendar_reads_exact_accepted_instructions_without_writes(env):
    configure(env)
    review = full(env)
    accept(env, review, token=21110101)
    before = stats(env)
    feed = get(env, path='feed')
    assert {w['sport'] for w in feed['planned']} == {'STRENGTH', 'KAYAK', 'RUNNING', 'SWIMMING'}
    for row in feed['planned']:
        context = row['planning_context']
        assert context['instructions'] == review['result']['instruction_context']['by_candidate'][context['candidate_key']]
        assert context['instructions']['duration_sec'] == row['duration_sec']
        assert context['instructions']['main']['instruction'] == row['description']
    assert get(env, path='feed')['planned'] == feed['planned']
    assert stats(env) == before
    export('accepted_feed', feed)


def test_existing_v13_accepted_workouts_gain_instructions_without_reassessment(env, monkeypatch):
    configure(env)
    before = initial_context(env)
    with monkeypatch.context() as patch:
        patch.setattr(instructions, 'attach', lambda result: result)
        patch.setitem(policy.POLICY, 'version', 'training-plan-policy-v0.13')
        legacy = full(env)
        assert 'instruction_context' not in legacy['result']
        accept(env, legacy, token=21110102)
    count_before = stats(env)
    with Session(env.engine) as db:
        snapshots = {str(w.id): deepcopy(w.raw_data) for w in db.scalars(select(PlannedWorkout))}
    feed = get(env, path='feed')
    assert feed['planned'] and all(w['planning_context']['instructions'] for w in feed['planned'])
    assert stats(env) == count_before
    assert initial_context(env)['saved']['artifact'] == before['saved']['artifact']
    with Session(env.engine) as db:
        assert {str(w.id): w.raw_data for w in db.scalars(select(PlannedWorkout))} == snapshots
    export('legacy_feed', feed)


@pytest.mark.parametrize('change', ['load_text', 'duration', 'imported'])
def test_changed_or_external_prescription_cannot_inherit_verified_instructions(env, change):
    configure(env)
    accept(env, full(env), token=21110103)
    feed = get(env, path='feed')
    row = next(w for w in feed['planned'] if w['sport'] == 'STRENGTH')
    with Session(env.engine) as db:
        saved = db.get(PlannedWorkout, UUID(row['id']))
        if change == 'load_text':
            saved.description += ' Más, kézzel átírt munkasúly.'
        elif change == 'duration':
            saved.duration_sec += 60
        else:
            saved.source = 'POLAR'
        db.commit()
    changed = next(w for w in get(env, path='feed')['planned'] if w['id'] == row['id'])
    assert 'planning_context' not in changed


@pytest.mark.parametrize('sport', ['STRENGTH', 'RUNNING', 'SWIMMING', 'KAYAK'])
def test_optional_stretching_never_adds_time_or_work_sets(sport):
    candidate = {'sport': sport, 'duration_sec': 1200, 'description': 'Változatlan sportági előírás',
        'blocks': [{'duration_sec': 300}, {'duration_sec': 600}, {'duration_sec': 300}]}
    original = deepcopy(candidate)
    routine = instructions.derive(candidate, {})
    assert candidate == original
    assert routine['finish']['easy_duration_sec'] == 180
    assert [s['duration_sec'] for s in routine['finish']['stretches']] == [60, 60]
    assert not routine['external_load_increased'] and not routine['sets_added']
    assert routine['main']['strength'] is None
    assert len(routine['warmup']['steps']) == 3
