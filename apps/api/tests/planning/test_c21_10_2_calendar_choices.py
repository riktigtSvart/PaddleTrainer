"""Accepted purpose and date-scoped replacements through the actual HTTP API."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutStatus
from app.planning.application import calendar_workspace
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import training_options
from tests.planning.test_c21_9_1_calendar_endurance import env as source_fixture, prepare, review
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c19_plan_choices import choice
from tests.planning.test_p2_4c19_training_options import save as save_options


@pytest.fixture
def env(tmp_path, monkeypatch):
    wrapper = source_fixture.__wrapped__(tmp_path, monkeypatch)
    e = next(wrapper)
    monkeypatch.setattr(calendar_workspace, '_now', e.clock.tick)
    e.current_options = prepare(e, light=False)
    try:
        yield e
    finally:
        wrapper.close()


def feed(e):
    r = e.client.get('/api/v1/planning/calendar/feed?start_date=2026-10-26&end_date=2026-11-08')
    assert r.status_code == 200, r.text
    return r.json()


def export(name, value):
    if os.getenv('C21_10_2_EXPORT'):
        path = Path(os.environ['C21_10_2_EXPORT'])
        data = json.loads(path.read_text()) if path.exists() else {}
        data[name] = value
        path.write_text(json.dumps(data), encoding='utf-8')


def test_existing_accepted_rows_expose_exact_purpose_without_rewriting_them(env):
    initial = review(env)
    accepted = accept(env, initial)
    with Session(env.engine) as db:
        before = [(w.id, deepcopy(w.raw_data)) for w in db.scalars(select(PlannedWorkout))]
        count = len(list(db.scalars(select(PlanningAuditArtifactRow))))
    value = feed(env)
    assert value['planned']
    for row in value['planned']:
        p = row['planning_context']
        key = accepted['artifact']['created_workouts'][row['id']]['candidate_key']
        candidate = next(c for c in initial['result']['create'] if c['candidate_key'] == key)
        assert p['primary_goal'] == candidate['capability_key']
        assert p['mesocycle_id'] == row['training_period_id'] == candidate['training_period_id']
        assert p['role'] == candidate['role'] and p['date'] == row['date']
        assert p['replaceable'] is True and row['goal_tag'] is None
        assert p['accepted_review_reference'] == accepted['artifact']['review_reference']
    feed(env)
    with Session(env.engine) as db:
        assert [(w.id, w.raw_data) for w in db.scalars(select(PlannedWorkout))] == before
        assert len(list(db.scalars(select(PlanningAuditArtifactRow)))) == count
    export('accepted_feed', value)


def test_alternatives_replace_a_later_clicked_day_without_adding_an_extra_session(env):
    first = review(env)
    accept(env, first)
    fresh = review(env)
    value = feed(env)
    target = next(row for row in reversed(value['planned']) if any(
        g['date'] == row['date'] and len(g['candidates']) > 1 for g in fresh['result']['alternatives']))
    context = target['planning_context']
    assert target['date'] > value['local_today']
    group = next(g for g in fresh['result']['alternatives'] if g['date'] == target['date'])
    assert context['alternatives_count'] == len(group['candidates']) - 1
    candidate = next(c for c in group['candidates'] if c['candidate_key'] != context['candidate_key'])
    changed = choice(env, fresh, target['date'], candidate['candidate_key'])['review']
    assert target['id'] in changed['result']['cancel']
    assert [c['candidate_key'] for c in changed['result']['proposals'] if c['date'] == target['date']] == [candidate['candidate_key']]
    assert len(feed(env)['planned']) == len(value['planned'])  # Preview only.
    receipt = accept(env, changed, token=2110201)
    after = feed(env)
    selected = [w for w in after['planned'] if w['date'] == target['date']]
    assert len(selected) == 1 and selected[0]['planning_context']['candidate_key'] == candidate['candidate_key']
    assert selected[0]['planning_context']['primary_goal'] == candidate['capability_key']
    assert target['id'] not in {w['id'] for w in after['planned']}
    export('review', fresh); export('feed', value); export('target_id', target['id'])
    export('choice', changed); export('receipt', receipt); export('after', after)
    export('candidate_key', candidate['candidate_key'])


def test_no_usable_window_reports_zero_and_old_candidates_cannot_be_chosen(env):
    initial = review(env); accept(env, initial)
    proposal = deepcopy(env.current_options['artifact']['proposal'])
    proposal.update(request_id=str(UUID(int=2110202)), previous_reference=training_options.reference(env.current_options['artifact']))
    proposal['data']['weekly_slots'] = []
    save_options(env, proposal)
    current = review(env)
    assert not current['result']['alternatives']
    value = feed(env)
    assert value['planned']
    assert all(w['planning_context']['alternatives_count'] == 0 for w in value['planned'])
    candidate = initial['result']['proposals'][-1]
    response = choice(env, current, candidate['date'], candidate['candidate_key'], expected=409)
    assert response['detail']['code'] == 'TRAINING_PLAN_ALTERNATIVE_NOT_AVAILABLE'


@pytest.mark.parametrize('change', ['edited', 'imported', 'completed'])
def test_edited_and_imported_rows_do_not_inherit_a_false_goal_or_choices(env, change):
    value = review(env); accept(env, value)
    key = feed(env)['planned'][0]['id']
    with Session(env.engine) as db:
        row = db.get(PlannedWorkout, UUID(key))
        if change == 'edited': row.title = 'Saját módosított előírás'
        elif change == 'imported': row.source = 'POLAR'
        else: row.status = WorkoutStatus.COMPLETED
        db.commit()
    row = next(w for w in feed(env)['planned'] if w['id'] == key)
    if change == 'completed':
        assert row['planning_context']['replaceable'] is False
        assert row['planning_context']['alternatives_count'] is None
    else:
        assert 'planning_context' not in row
