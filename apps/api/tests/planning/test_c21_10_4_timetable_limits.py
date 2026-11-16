"""Actual options writes: many slots fit; an overlong budget never commits."""
from copy import deepcopy
from uuid import UUID

import pytest

from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import training_options
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c19_training_options import opportunities as fixture, body, context, save


@pytest.fixture
def env(tmp_path, monkeypatch):
    yield from fixture.__wrapped__(tmp_path, monkeypatch)


def slots_body(total, token=2110401, previous=None):
    value = body(token=token, previous=previous)
    template = value['data']['weekly_slots'][0]
    value['data']['weekly_slots'] = []
    for i in range(total):
        slot = deepcopy(template)
        slot.update(id=str(UUID(int=21104000 + i)), weekdays=[i % 7])
        value['data']['weekly_slots'].append(slot)
    return value


@pytest.mark.parametrize('total', [32, 128])
def test_weekly_slots_are_not_limited_to_the_first_few_weekdays(env, total):
    result = save(env, slots_body(total))
    current = context(env)
    assert len(current['data']['weekly_slots']) == total
    assert {d for s in current['data']['weekly_slots'] for d in s['weekdays']} == set(range(7))
    assert current['reference'] == training_options.reference(result['artifact'])


def test_129_slots_are_rejected_without_changing_the_saved_timetable(env):
    saved = save(env, slots_body(32))
    before = count(env, PlanningAuditArtifactRow)
    save(env, slots_body(129, token=2110402, previous=training_options.reference(saved['artifact'])), expected=422)
    current = context(env)
    assert count(env, PlanningAuditArtifactRow) == before
    assert len(current['data']['weekly_slots']) == 32
    assert current['reference'] == training_options.reference(saved['artifact'])


def test_thursday_90_minute_window_cannot_store_120_minutes_or_replace_prior_work(env):
    saved = save(env, slots_body(32))
    value = slots_body(33, token=2110403, previous=training_options.reference(saved['artifact']))
    slot = value['data']['weekly_slots'][-1]
    slot['weekdays'] = [3]
    slot['details'].update(start_time='18:30', end_time='20:00', max_minutes=120)
    before = count(env, PlanningAuditArtifactRow)
    save(env, value, expected=422)
    assert count(env, PlanningAuditArtifactRow) == before
    assert context(env)['reference'] == training_options.reference(saved['artifact'])
    slot['details']['max_minutes'] = 90
    valid = save(env, value)
    current = context(env)
    assert len(current['data']['weekly_slots']) == 33
    assert current['data']['weekly_slots'][-1]['details']['max_minutes'] == 90
    assert current['reference'] == training_options.reference(valid['artifact'])
