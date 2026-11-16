"""A changed venue and an unreviewed intake can be explicitly saved before the first occasion."""
from copy import deepcopy
from uuid import UUID

import pytest

from app.models.entities import PlannedWorkout, WorkoutSession
from app.services.initial_assessment import reference
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c20_4_initial_assessment import context as initial_context
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
from tests.planning.test_p2_4c20_6_guided_strength import context, send, start_request
from tests.planning.test_p2_4c20_6r2_exercise_availability import venue as venue_fixture


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    wrapper = venue_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    try:
        current = initial_context(env)
        data = deepcopy(current['data'])
        data['reviewed'] = False
        env.unreviewed = save_initial(env, {
            'request_id': str(UUID(int=206801)), 'previous_reference': current['reference'],
            'source_hash': current['sources']['source_hash'], 'data': data,
        })
        options = deepcopy(env.options['artifact']['proposal'])
        options.update(request_id=str(UUID(int=206802)), previous_reference=reference(env.options['artifact']))
        options['data']['locations'][0]['notes'] = 'A helyszín adatai frissítve; a saját gyakorlatmegadások megmaradnak.'
        env.options = save_options(env, options)
        yield env
    finally:
        wrapper.close()


def reviewed_request(env, token=206803):
    current = initial_context(env)
    data = deepcopy(current['data'])
    data['reviewed'] = True
    return {'request_id': str(UUID(int=token)), 'previous_reference': current['reference'],
            'source_hash': current['sources']['source_hash'], 'data': data}


def test_explicit_source_adoption_and_review_unlock_first_occasion_without_prior_sets(recovery):
    before = context(recovery)
    assert set(before['preparation']['issues']) == {'GUIDED_SOURCES_CHANGED', 'GUIDED_INTAKE_REVIEW_REQUIRED'}
    assert before['intake']['summary']['recorded_reference_count'] == 0
    assert send(recovery, start_request(before), 409)['detail']['code'] == 'GUIDED_PREPARATION_CHANGED'
    counts = count(recovery, WorkoutSession), count(recovery, PlannedWorkout)
    proposal = reviewed_request(recovery)
    saved = save_initial(recovery, proposal)
    ready = context(recovery)
    assert not ready['preparation']['issues']
    assert ready['intake']['summary']['recorded_reference_count'] == 0
    assert saved['artifact']['proposal']['data']['exercises'] == before['intake']['data']['exercises']
    assert all(not e['sets'] for e in saved['artifact']['proposal']['data']['exercises'])
    assert (count(recovery, WorkoutSession), count(recovery, PlannedWorkout)) == counts
    assert save_initial(recovery, proposal, 200)['artifact'] == saved['artifact']
    assert send(recovery, start_request(ready, 206804))['artifact']['state'] == 'active'


def test_rebase_alone_does_not_claim_review_and_old_sources_cannot_be_saved(recovery):
    proposal = reviewed_request(recovery)
    old = deepcopy(proposal)
    old['source_hash'] = recovery.unreviewed['artifact']['proposal']['source_hash']
    assert save_initial(recovery, old, 409)['detail']['code'] == 'INITIAL_ASSESSMENT_SOURCES_CHANGED'
    proposal['data']['reviewed'] = False
    save_initial(recovery, proposal)
    after = context(recovery)
    assert after['preparation']['issues'] == ['GUIDED_INTAKE_REVIEW_REQUIRED']
    assert send(recovery, start_request(after), 409)['detail']['code'] == 'GUIDED_PREPARATION_CHANGED'


def test_saved_review_does_not_turn_unfamiliar_exercise_into_a_startable_one(recovery):
    proposal = reviewed_request(recovery)
    proposal['data']['exercises'][0]['familiarity'] = 'unfamiliar'
    save_initial(recovery, proposal)
    after = context(recovery)
    row = after['preparation']['locations'][0]['entries'][0]
    assert 'GUIDED_INSTRUCTION_REQUIRED' in row['issues'] and not row['ready']
    assert send(recovery, start_request(after), 409)['detail']['code'] == 'GUIDED_SELECTION_INVALID'
