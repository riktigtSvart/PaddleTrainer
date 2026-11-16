"""Exact read-only recovery of old acknowledgements and newer reference sets."""
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c20_4_initial_assessment import BASE, body, context, save
from tests.planning.test_p2_4c20_6_guided_strength import guided  # noqa: F401 -- fixture
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL, count


def recovery_case(env):
    before = context(env)
    request = body(before, 2182001, True)
    request['data']['assessment_date'] = '2026-10-23'
    request['data']['last_strength_date'] = '2026-08-15'
    for entry in request['data']['exercises']:
        entry['performed_on'] = '2026-08-15'
    old = save(env, request)
    old_context = context(env)
    env.clock.current = datetime(2026, 11, 11, 10, tzinfo=UTC)
    later = deepcopy(request)
    later.update(request_id=str(UUID(int=2182002)), previous_reference=old_context['reference'])
    later['data']['assessment_date'] = later['data']['last_strength_date'] = '2026-11-11'
    for i, entry in enumerate(later['data']['exercises']):
        if i == 3:
            entry.update(sets=[], performed_on=None, familiarity='unfamiliar', comfort='no_experience')
        else:
            entry['performed_on'] = '2026-11-11'
            entry['sets'][0].update(id=str(UUID(int=2182100+i)), rir='2')
    new = save(env, later)
    return {'before': before, 'old': old, 'old_context': old_context, 'request': request,
            'new': new, 'current': context(env)}


def test_exact_old_read_recovers_acknowledgement_without_replacing_four_new_results(guided):
    values = recovery_case(guided)
    before = tuple(count(guided, model) for model in (PlanningAuditArtifactRow, PlannedWorkout, WorkoutSession))
    response = guided.client.get(BASE + '/revisions/' + values['request']['request_id'])
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['artifact'] == values['old']['artifact']
    assert response.json()['committed'] is True
    assert context(guided)['data'] == values['current']['data']
    assert values['current']['summary']['recorded_reference_count'] == 4
    assert before == tuple(count(guided, model) for model in (PlanningAuditArtifactRow, PlannedWorkout, WorkoutSession))
    assert all(not session.in_transaction() for session in guided.requests)


def test_missing_request_is_not_reported_as_saved(guided):
    response = guided.client.get(BASE + '/revisions/' + str(UUID(int=2182999)))
    assert response.status_code == 404
    assert response.json()['detail']['code'] == 'INITIAL_ASSESSMENT_NOT_FOUND'


def test_revision_token_never_reads_another_athletes_result(guided):
    values = recovery_case(guided)
    guided.email = OTHER_EMAIL
    response = guided.client.get(BASE + '/revisions/' + values['request']['request_id'])
    assert response.status_code == 404
    assert 'artifact' not in response.json()


@pytest.mark.parametrize('suffix', ['?owner=foreign', '?url=http://evil.invalid', '?available_by=2027-01-01'])
def test_revision_read_refuses_query_fields(guided, suffix):
    token = guided.initial['artifact']['proposal']['request_id']
    assert guided.client.get(BASE + '/revisions/' + token + suffix).status_code == 422


@pytest.mark.parametrize('method', ['post', 'put', 'delete'])
def test_revision_is_read_only(guided, method):
    token = guided.initial['artifact']['proposal']['request_id']
    assert getattr(guided.client, method)(BASE + '/revisions/' + token).status_code == 405


def test_revision_read_rechecks_durable_content_hash(guided):
    with Session(guided.engine) as db:
        row = db.get(PlanningAuditArtifactRow, ('initial_assessment', guided.initial['artifact']['artifact_id']))
        row.content_hash = '0' * 64
        db.commit()
    token = guided.initial['artifact']['proposal']['request_id']
    response = guided.client.get(BASE + '/revisions/' + token)
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'INITIAL_ASSESSMENT_STORAGE_INVALID'
