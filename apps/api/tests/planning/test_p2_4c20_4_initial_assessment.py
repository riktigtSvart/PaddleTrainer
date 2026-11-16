"""Guided intake: real owned HTTP, immutable saves and explicit self reports."""
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest

from app.api.routes import initial_assessment as routes
from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.domain.athlete_setup import digest
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.initial_assessment import AssessmentInput
from app.services import initial_assessment as service
from app.services import initial_assessment_domain as domain
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL, count
from tests.planning.test_p2_4c19_training_options import HOME, WATER
from tests.planning.test_p2_4c19_training_options import body as options_body
from tests.planning.test_p2_4c19_training_options import opportunities as options_fixture
from tests.planning.test_p2_4c19_training_options import save as save_options

BASE = '/api/v1/planning/initial-assessment'


@pytest.fixture
def assessment(tmp_path, monkeypatch):
    wrapper = options_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    env.app.include_router(routes.router, prefix='/api/v1')
    monkeypatch.setattr(service, '_now', env.clock.tick)
    proposal = options_body()
    proposal['data']['locations'][0].update(sports=['KAYAK', 'STRENGTH'], resources=['Kajak', 'Kézisúlyzó', 'Szabad padlófelület'])
    proposal['data']['locations'][2].update(sports=['STRENGTH'], resources=[])
    env.options = save_options(env, proposal)
    try:
        yield env
    finally:
        wrapper.close()


def context(env):
    r = env.client.get(BASE)
    assert r.status_code == 200, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def body(c, token=204001, complete=False):
    data = {'timezone_name': c['timezone_name'], 'assessment_date': c['local_today']}
    if complete:
        data.update(state_change='unchanged', experience='returning', strength_frequency='weekly_2', supervision='self',
                    program_reference=c['sources']['programs'][0]['reference'], default_location_id=WATER,
                    sports=[{'sport_key': 'KAYAK', 'role': 'primary'}, {'sport_key': 'CYCLING', 'role': 'secondary'},
                            {'sport_key': 'FOOTBALL', 'role': 'recreation'}], references_reviewed=True, reviewed=True,
                    exercises=[])
        for i, (pattern, exercise) in enumerate([('pull', 'dumbbell_row'), ('push', 'pushup'), ('knee', 'goblet_squat'), ('hip', 'glute_bridge'), ('core', 'plank')]):
            weighted = pattern in {'pull', 'knee'}
            data['exercises'].append({'id': str(UUID(int=204100 + i)), 'pattern': pattern, 'exercise_id': exercise,
                'location_id': WATER, 'familiarity': 'independent', 'comfort': 'none', 'performed_on': c['local_today'],
                'sets': [{'id': str(UUID(int=204200 + i)), 'repetitions': None if pattern == 'core' else 8,
                          'hold_seconds': '30.000' if pattern == 'core' else None,
                          'load_kind': 'external_kg' if weighted else 'bodyweight',
                          'load_value': '12.500000' if weighted else None,
                          'load_basis': ('per_hand' if pattern == 'pull' else 'total') if weighted else 'not_applicable',
                          'rir': '3', 'technique': 'stable', 'symptoms': 'none'}]})
        data['sport_references'] = [{'id': str(UUID(int=204300)), 'sport_key': 'CYCLING', 'performed_on': c['local_today'],
            'protocol': 'Saját, ismert kör <nem új edzés>', 'distance_m': '20000.125', 'duration_minutes': '52.500000',
            'duration_basis': 'elapsed', 'power_w': '0', 'heart_rate_bpm': None, 'rpe': 0,
            'elevation_gain_m': '0', 'conditions': 'Szél / ismeretlen mérési pontosság', 'equipment': 'Saját kerékpár'}]
    return AssessmentInput.model_validate({'request_id': str(UUID(int=token)), 'previous_reference': c['reference'],
        'source_hash': c['sources']['source_hash'], 'data': data}).model_dump(mode='json')


def save(env, proposal, expected=201):
    r = env.client.post(BASE, json=proposal)
    assert r.status_code == expected, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def test_owned_read_imports_exact_sources_without_writing(assessment):
    before = count(assessment, PlanningAuditArtifactRow)
    c = context(assessment)
    assert c['reference'] is None and c['summary'] is None and c['data'] is None
    assert c['sources']['options_reference'] == service.reference(assessment.options['artifact'])
    assert c['sources']['profile_receipt']['artifact']['athlete_id'] == c['athlete_id']
    assert c['sources']['programs'] and c['sources']['catalog']['equipment']
    assert {'KAYAK', 'RUNNING', 'SWIMMING', 'CYCLING', 'XC_SKIING', 'FOOTBALL'} <= {v['key'] for v in c['sources']['registry']['sports']}
    assert c['content_hash'] == digest({k: v for k, v in c.items() if k != 'content_hash'})
    assert count(assessment, PlanningAuditArtifactRow) == before
    assert all(not s.in_transaction() for s in assessment.requests)


def test_partial_and_complete_revisions_survive_reload_without_workouts(assessment):
    before = count(assessment, PlannedWorkout), count(assessment, WorkoutSession)
    partial = save(assessment, body(context(assessment)))
    assert not partial['artifact']['summary']['form_complete']
    request = body(context(assessment), 204002, True)
    complete = save(assessment, request)
    assert complete['artifact']['revision'] == 2
    assert complete['artifact']['summary']['form_complete']
    assert complete['artifact']['summary']['recorded_reference_count'] == 5
    assert context(assessment)['data'] == request['data']
    assert complete['artifact']['proposal']['data']['exercises'][0]['sets'][0]['load_value'] == '12.500000'
    assert context(assessment)['data']['sport_references'][0]['rpe'] == 0
    assert context(assessment)['data']['sport_references'][0]['heart_rate_bpm'] is None
    assert before == (count(assessment, PlannedWorkout), count(assessment, WorkoutSession))
    assert all(complete[k] is False for k in ['planning_authorized', 'workouts_changed', 'clinical_clearance'])


def test_exact_old_retry_wins_before_current_parent_and_source_checks(assessment):
    original = body(context(assessment), complete=True)
    first = save(assessment, original)
    second_request = body(context(assessment), 204002)
    second = save(assessment, second_request)
    updated = options_body(204501, service.reference(assessment.options['artifact']))
    updated['data']['locations'][0]['name'] = 'Átnevezett csónakház'
    save_options(assessment, updated)
    retried = save(assessment, original, 200)
    assert retried['reused'] and retried['artifact'] == first['artifact']
    latest = context(assessment)
    assert latest['sources_changed'] and latest['reference'] == service.reference(second['artifact'])
    assert latest['data'] == second_request['data']
    changed = deepcopy(original)
    changed['data']['state_notes'] = 'Más kérés azonos azonosítóval'
    assert save(assessment, changed, 409)['detail']['code'] == 'INITIAL_ASSESSMENT_REQUEST_CONFLICT'


def test_stale_parent_and_changed_sources_cannot_silently_rebase(assessment):
    old = context(assessment)
    save(assessment, body(old))
    assert save(assessment, body(old, 204002), 409)['detail']['code'] == 'INITIAL_ASSESSMENT_REVISION_CONFLICT'
    current = context(assessment)
    updated = options_body(204501, service.reference(assessment.options['artifact']))
    save_options(assessment, updated)
    assert save(assessment, body(current, 204003), 409)['detail']['code'] == 'INITIAL_ASSESSMENT_SOURCES_CHANGED'


def test_other_owner_never_loads_or_reuses_assessment(assessment):
    request = body(context(assessment), complete=True)
    saved = save(assessment, request)
    assessment.email = OTHER_EMAIL
    other = context(assessment)
    assert other['data'] is None and other['reference'] is None and other['sources']['locations'] == []
    assert save(assessment, request, 409)['detail']['code'] == 'INITIAL_ASSESSMENT_SOURCES_CHANGED'
    foreign = body(other, 204003)
    foreign['data']['program_reference'] = saved['artifact']['proposal']['data']['program_reference']
    assert save(assessment, foreign, 409)['detail']['code'] == 'INITIAL_ASSESSMENT_PROGRAM_UNKNOWN'


@pytest.mark.parametrize('field,value', [('sport', 'FUTURE_SPORT'), ('exercise', 'plank'), ('location', str(UUID(int=999999))), ('program', {'artifact_id': 'foreign', 'content_hash': 'a' * 64})])
def test_declared_selections_must_belong_to_owned_registry_and_sources(assessment, field, value):
    request = body(context(assessment), complete=True)
    if field == 'sport':
        request['data']['sports'][0]['sport_key'] = value
    elif field == 'exercise':
        request['data']['exercises'][0]['exercise_id'] = value
    elif field == 'location':
        request['data']['exercises'][0]['location_id'] = value
    else:
        request['data']['program_reference'] = value
    save(assessment, request, 409)


@pytest.mark.parametrize('field,value', [('repetitions', True), ('load_value', '-1'), ('load_value', '1e2'), ('load_value', '100001'), ('load_basis', 'assistance'), ('rir', 0), ('symptoms', 'fine')])
def test_set_inputs_are_strict_and_load_meanings_remain_distinct(assessment, field, value):
    request = body(context(assessment), complete=True)
    request['data']['exercises'][0]['sets'][0][field] = value
    save(assessment, request, 422)


def test_unknown_zero_and_pain_never_become_a_usable_reference(assessment):
    request = body(context(assessment), complete=True)
    entries = request['data']['exercises']
    entries[0]['sets'][0]['repetitions'] = 0
    entries[1]['sets'][0]['repetitions'] = None
    entries[2]['sets'].append({**entries[2]['sets'][0], 'id': str(UUID(int=204777)), 'symptoms': 'pain'})
    entries[3]['location_id'] = HOME  # No borrowing the dumbbells/floor of another venue.
    entries[4]['performed_on'] = '2026-01-01'
    result = save(assessment, request)['artifact']['summary']
    assert result['form_complete'] and result['recorded_reference_count'] == 0
    assert result['exercise_states'][2]['state'] == 'avoid'
    assert 'EQUIPMENT_MISSING' in result['exercise_states'][3]['reasons']
    assert 'RECENT_REFERENCE_MISSING' in result['exercise_states'][4]['reasons']


def test_references_age_without_rewriting_saved_receipt(assessment):
    saved = save(assessment, body(context(assessment), complete=True))
    assessment.clock.current += timedelta(days=57)
    c = context(assessment)
    assert c['summary']['recorded_reference_count'] == 0
    assert c['saved']['artifact'] == saved['artifact']
    assert c['saved']['artifact']['summary']['recorded_reference_count'] == 5


@pytest.mark.parametrize('method', ['get', 'post'])
def test_queries_cannot_select_foreign_owners_or_arbitrary_routes(assessment, method):
    kwargs = {'json': body(context(assessment))} if method == 'post' else {}
    response = getattr(assessment.client, method)(BASE + '?owner=foreign', **kwargs)
    assert response.status_code == 422


def test_registry_is_extensible_and_distinguishes_intake_from_planning():
    registry = domain.registry()
    assert len(registry['sports']) >= 14 and len(registry['patterns']) == 5
    cycling = next(s for s in registry['sports'] if s['key'] == 'CYCLING')
    assert cycling['assessment_support'] == 'declarations_and_references'
    assert cycling['planning_support'] == 'not_implemented'
    assert registry['planning_authorized'] is False


def test_a_beginner_can_finish_the_questions_without_inventing_a_measured_set(assessment):
    request = body(context(assessment), complete=True)
    request['data'].update(experience='none', strength_frequency='none', supervision='needed', sport_references=[])
    for exercise in request['data']['exercises']:
        exercise.update(familiarity='unfamiliar', comfort='no_experience', performed_on=None, sets=[])
    result = save(assessment, request)['artifact']['summary']
    assert result['form_complete'] and result['recorded_reference_count'] == 0
    assert all(e['state'] == 'needs_instruction' for e in result['exercise_states'])


def test_failed_commit_rolls_back_and_same_request_can_be_saved_once(assessment, monkeypatch):
    request = body(context(assessment))
    before = count(assessment, PlanningAuditArtifactRow)
    commit = service.transactions.commit

    async def fail(_session):
        raise RuntimeError('simulated storage failure')

    monkeypatch.setattr(service.transactions, 'commit', fail)
    save(assessment, request, 503)
    assert count(assessment, PlanningAuditArtifactRow) == before
    monkeypatch.setattr(service.transactions, 'commit', commit)
    result = save(assessment, request)
    assert result['artifact']['revision'] == 1
    assert count(assessment, PlanningAuditArtifactRow) == before + 1


@pytest.mark.parametrize('field,value', [('assessment_date', '2027-01-01'), ('timezone_name', 'UTC')])
def test_future_date_and_different_profile_timezone_are_rejected(assessment, field, value):
    request = body(context(assessment))
    request['data'][field] = value
    assert save(assessment, request, 409)['detail']['code'] == 'INITIAL_ASSESSMENT_DATE_OR_ZONE_INVALID'
