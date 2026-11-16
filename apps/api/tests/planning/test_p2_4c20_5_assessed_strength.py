"""Actual owned assessment -> reviewed strength plan -> atomic acceptance."""
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, Sport, WorkoutSession
from app.planning.domain.athlete_setup import digest
from app.services import initial_assessment as intake
from app.services import strength_catalog
from app.services import training_strength_assessment as strength
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL, count
from tests.planning.test_p2_4c18_4_training_plan import accept, owned_plans, review
from tests.planning.test_p2_4c19_training_options import HOME, WATER
from tests.planning.test_p2_4c19_training_options import body as options_body
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c20_1_prescriptions import completed
from tests.planning.test_p2_4c20_4_initial_assessment import assessment as intake_fixture
from tests.planning.test_p2_4c20_4_initial_assessment import body, context, save


@pytest.fixture
def planner(tmp_path, monkeypatch):
    wrapper = intake_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    proposal = options_body(205501, intake.reference(env.options['artifact']))
    proposal['data']['locations'][0].update(sports=['STRENGTH'], resources=['Kézisúlyzó', 'Szabad padlófelület'])
    env.options = save_options(env, proposal)
    try:
        yield env
    finally:
        wrapper.close()


def request(env, token=205001):
    value = body(context(env), token, True)
    value['data']['sports'].append({'sport_key': 'STRENGTH', 'role': 'secondary', 'discipline': '', 'goal': '', 'notes': ''})
    for entry in value['data']['exercises']:
        entry['side'] = 'both'
    return value


def strength_candidates(value):
    # These tests concern prescriptions copied from actual assessed sets.
    # A labelled, unloaded introductory default is tested separately in C21.10.6.
    return [c for group in value['result']['alternatives'] for c in group['candidates'] if c.get('strength_prescription')]


def test_assessment_without_a_recorded_strength_workout_yields_source_bound_candidates(planner):
    before = count(planner, PlannedWorkout), count(planner, WorkoutSession)
    proposal = request(planner)
    saved = save(planner, proposal)
    result = review(planner)
    candidates = strength_candidates(result)
    assert candidates and all(c['template_version'] == 'v0.5' for c in candidates)
    assert result['inputs']['strength_assessment']['receipt']['artifact'] == saved['artifact']
    assert result['result']['strength_assessment']['reference'] == intake.reference(saved['artifact'])
    originals = {e['id']: e for e in proposal['data']['exercises']}
    for candidate in candidates:
        assert candidate['duration_sec'] >= 1200
        assert candidate['duration_reference_session_id'] is None
        recipe = candidate['strength_prescription']
        assert len(recipe['movements']) == 2
        assert recipe['assessment_reference'] == intake.reference(saved['artifact'])
        for movement in recipe['movements']:
            entry = originals[movement['entry_id']]
            assert movement['reference_set'] == entry['sets'][0]
            assert movement['target']['load_value'] == entry['sets'][0]['load_value']
            assert movement['work_sets'] >= 2
            assert movement['location_id'] == candidate['location_id'] == WATER
        meta = result['result']['prescription_context']['by_candidate'][candidate['candidate_key']]
        assert meta['strength'] == recipe and meta['product_default_used']
        assert not recipe['load_increased'] and not recipe['one_rm_estimated']
    assert before == (count(planner, PlannedWorkout), count(planner, WorkoutSession))


def test_explicit_acceptance_preserves_exact_recipe_and_is_idempotent(planner):
    save(planner, request(planner))
    result = review(planner)
    acceptance = accept(planner, result)
    retried = accept(planner, result, expected=200)
    assert retried['artifact'] == acceptance['artifact']
    rows = owned_plans(planner)
    assert rows and all(row.sport == Sport.STRENGTH for row in rows)
    recipes = {c['candidate_key']: c['strength_prescription'] for c in result['result']['create']}
    for row in rows:
        marker = row.raw_data['paddletrainer_training_plan']
        assert row.raw_data['paddletrainer_strength_prescription'] == recipes[marker['candidate_key']]
    repeated = review(planner)
    assert not repeated['result']['create'] and not repeated['result']['cancel']


def test_latest_assessment_change_invalidates_unaccepted_preview(planner):
    save(planner, request(planner))
    result = review(planner)
    changed = request(planner, 205002)
    changed['data']['exercises'][0]['sets'][0]['load_value'] = '10.250000'
    save(planner, changed)
    rejected = accept(planner, result, expected=409)
    assert rejected['detail']['code'] == 'TRAINING_PLAN_REVIEW_CHANGED'
    assert not owned_plans(planner)
    newer = review(planner)
    assert newer['artifact_id'] != result['artifact_id']
    assert newer['result']['strength_assessment']['reference'] != result['result']['strength_assessment']['reference']


def test_missing_assessment_does_not_guess_exercise_familiarity_from_session_minutes(planner):
    completed(planner, 205100, sport=Sport.STRENGTH, minutes=30)
    result = review(planner)
    assert not strength_candidates(result)
    assert result['result']['strength_assessment']['issues'] == ['STRENGTH_ASSESSMENT_MISSING']


@pytest.mark.parametrize('field,value,code', [
    ('reviewed', False, 'STRENGTH_ASSESSMENT_REVIEW_REQUIRED'),
    ('references_reviewed', False, 'STRENGTH_ASSESSMENT_REVIEW_REQUIRED'),
    ('state_change', 'changed', 'STRENGTH_ASSESSMENT_STATE_REVIEW'),
    ('supervision', 'needed', 'STRENGTH_ASSESSMENT_HISTORY_REVIEW'),
    ('experience', 'none', 'STRENGTH_ASSESSMENT_HISTORY_REVIEW'),
])
def test_incomplete_or_restricted_intake_explains_the_exact_gate(planner, field, value, code):
    proposal = request(planner)
    proposal['data'][field] = value
    save(planner, proposal)
    result = review(planner)
    assert not strength_candidates(result)
    assert code in result['result']['strength_assessment']['issues']


def test_strength_must_be_selected_as_a_primary_or_complementary_sport(planner):
    proposal = request(planner)
    proposal['data']['sports'][-1]['role'] = 'recreation'
    save(planner, proposal)
    result = review(planner)
    assert not strength_candidates(result)
    assert 'STRENGTH_ASSESSMENT_SPORT_ROLE_REQUIRED' in result['result']['strength_assessment']['issues']


@pytest.mark.parametrize('field,value', [('familiarity', 'assisted'), ('comfort', 'symptoms'), ('side', 'unknown'), ('performed_on', '2026-01-01')])
def test_unready_entries_do_not_become_assumed_training_movements(planner, field, value):
    proposal = request(planner)
    for entry in proposal['data']['exercises']:
        entry[field] = value
    save(planner, proposal)
    result = review(planner)
    assert not strength_candidates(result)
    assert all(not e['eligible'] for e in result['result']['strength_assessment']['exercise_readiness'])


@pytest.mark.parametrize('field,value', [('rir', 'unknown'), ('rir', '1'), ('symptoms', 'pain'), ('technique', 'uncertain'), ('load_value', '0')])
def test_unusable_sets_are_withheld_with_entry_diagnostics(planner, field, value):
    proposal = request(planner)
    for entry in proposal['data']['exercises']:
        if field == 'load_value':
            entry['sets'][0].update(load_kind='external_kg', load_basis='total', load_value=value)
        else:
            entry['sets'][0][field] = value
    save(planner, proposal)
    assert not strength_candidates(review(planner))


def test_a_painful_set_is_not_hidden_by_another_valid_set(planner):
    proposal = request(planner)
    for i, entry in enumerate(proposal['data']['exercises']):
        entry['sets'].append({**entry['sets'][0], 'id': str(UUID(int=205200 + i)), 'symptoms': 'pain'})
    save(planner, proposal)
    result = review(planner)
    assert not strength_candidates(result)
    assert all('STRENGTH_MOVEMENT_SYMPTOMS' in e['reasons'] for e in result['result']['strength_assessment']['exercise_readiness'])


def test_equipment_cannot_be_borrowed_from_another_venue(planner):
    proposal = request(planner)
    for entry in proposal['data']['exercises']:
        entry['location_id'] = HOME
    save(planner, proposal)
    result = review(planner)
    assert not strength_candidates(result)


def test_new_options_require_explicit_assessment_source_review(planner):
    save(planner, request(planner))
    options = options_body(205502, intake.reference(planner.options['artifact']))
    options['data']['locations'][0]['resources'] = []
    save_options(planner, options)
    result = review(planner)
    assert 'STRENGTH_ASSESSMENT_SOURCES_CHANGED' in result['result']['strength_assessment']['issues']
    assert not strength_candidates(result)


def test_source_is_owner_bound_even_with_identical_assessment_request_ids(planner):
    save(planner, request(planner))
    planner.email = OTHER_EMAIL
    c = context(planner)
    assert c['saved'] is None
    # The planner's programme is also owned; another account cannot request it.
    result = planner.client.post(planner.plan_url + '/review', json={'start_date': '2026-10-24', 'end_date': '2026-10-29'})
    assert result.status_code in {404, 409}


def test_forward_days_age_each_reference_instead_of_extending_its_validity(planner):
    save(planner, request(planner))
    result = review(planner)
    evaluated = strength.evaluate(result['inputs']['strength_assessment'], result['inputs'], 'KAYAK', '2026-12-19')
    assert all(not e['eligible'] and 'RECENT_REFERENCE_MISSING' in e['reasons'] for e in evaluated['entries'])



def test_usual_duration_does_not_define_work_volume_and_measurements_are_not_duplicated(planner):
    proposal = request(planner)
    proposal['data']['usual_strength_minutes'] = 25
    for i, entry in enumerate(proposal['data']['exercises']):
        entry['sets'].extend([{**entry['sets'][0], 'id': str(UUID(int=205300 + i * 2 + j))} for j in range(2)])
    save(planner, proposal)
    candidates = strength_candidates(review(planner))
    assert candidates and all(c['duration_sec'] == c['strength_prescription']['duration_sec'] for c in candidates)
    assert all(m['work_sets'] == 2 for c in candidates for m in c['strength_prescription']['movements'])
    assert all(e['reference_set']['id'] in {s['id'] for entry in proposal['data']['exercises'] for s in entry['sets']} and 'sets' not in e for c in candidates for e in c['strength_prescription']['movements'])


def test_a_short_recorded_occasion_is_not_a_permanent_session_duration_ceiling(planner):
    completed(planner, 205110, sport=Sport.STRENGTH, minutes=15)
    save(planner, request(planner))
    values = strength_candidates(review(planner))
    assert values and all(c['duration_sec'] >= 1200 for c in values)


def test_recipe_hash_changes_when_exact_decimal_source_bytes_change(planner):
    original = request(planner)
    saved = save(planner, original)
    result = review(planner)
    assert saved['artifact']['content_hash'] == digest({k: v for k, v in saved['artifact'].items() if k != 'content_hash'})
    assert all(c['candidate_key'] == digest({k: v for k, v in c.items() if k != 'candidate_key'}) for c in strength_candidates(result))
    edited = request(planner, 205002)
    edited['data']['exercises'][0]['sets'][0]['load_value'] = '12.5000'
    newer = save(planner, edited)
    refreshed = review(planner)
    assert saved['artifact']['content_hash'] != newer['artifact']['content_hash']
    used = [m for c in strength_candidates(refreshed) for m in c['strength_prescription']['movements'] if m['entry_id'] == edited['data']['exercises'][0]['id']]
    assert used and all(m['reference_set']['load_value'] == '12.5000' for m in used)


@pytest.mark.parametrize('kind,value', [('machine_level', '4.000000'), ('external_kg', '35.500000')])
def test_machines_preserve_their_identity_and_original_units_without_dumbbells(planner, kind, value):
    cat = strength_catalog.catalog()
    equipment = {e['id']: e['resource'] for e in cat['equipment']}
    options = options_body(205502, intake.reference(planner.options['artifact']))
    options['data']['locations'][0].update(sports=['STRENGTH'], resources=[equipment['row_machine'], equipment['leg_press']])
    planner.options = save_options(planner, options)
    proposal = request(planner)
    proposal['data']['exercises'] = [proposal['data']['exercises'][0], proposal['data']['exercises'][2]]
    for entry, exercise in zip(proposal['data']['exercises'], ['seated_row', 'leg_press'], strict=True):
        entry['exercise_id'] = exercise
        entry['machine_note'] = 'Saját gép · ülés 4 / fogantyú 2'
        entry['sets'][0].update(load_kind=kind, load_basis='machine_display', load_value=value)
    save(planner, proposal)
    candidates = strength_candidates(review(planner))
    assert candidates
    for candidate in candidates:
        for movement in candidate['strength_prescription']['movements']:
            assert movement['reference_set']['load_kind'] == kind and movement['reference_set']['load_value'] == value
            assert movement['machine_note'] == 'Saját gép · ülés 4 / fogantyú 2'


def test_repeated_pull_entries_do_not_replace_two_distinct_patterns(planner):
    proposal = request(planner)
    first = proposal['data']['exercises'][0]
    proposal['data']['exercises'] = [first, {**first, 'id': str(UUID(int=205700))}]
    save(planner, proposal)
    result = review(planner)
    assert not strength_candidates(result)
    defaults = [c for group in result['result']['alternatives'] for c in group['candidates'] if c['sport'] == 'STRENGTH']
    assert defaults and all(c['template_version'] == 'v0.4' for c in defaults)
    assert all(result['result']['prescription_context']['by_candidate'][c['candidate_key']]['introductory_strength']['full_development_claim'] is False for c in defaults)


def test_the_programme_sport_keeps_its_primary_role(planner):
    proposal = request(planner)
    proposal['data']['sports'][0]['role'] = 'secondary'
    save(planner, proposal)
    assert not strength_candidates(review(planner))


def test_manually_edited_accepted_recipe_is_protected(planner):
    save(planner, request(planner))
    result = review(planner)
    accept(planner, result)
    row_id = owned_plans(planner)[0].id
    with Session(planner.engine) as db:
        row = db.get(PlannedWorkout, row_id)
        raw = {**row.raw_data, 'manual_strength_note': 'Saját, utólagos módosítás'}
        row.raw_data = raw
        db.commit()
    refreshed = review(planner)
    assert str(row_id) in refreshed['result']['protected_workout_ids']
    assert str(row_id) not in refreshed['result']['cancel']


def test_a_source_created_after_the_capture_cannot_be_used(planner):
    prior = planner.clock.current
    planner.clock.current += timedelta(days=1)
    save(planner, request(planner))
    planner.clock.current = prior
    response = planner.client.post(planner.plan_url + '/review', json={'start_date': '2026-10-24', 'end_date': '2026-10-29'})
    assert response.status_code == 503
    assert not owned_plans(planner)
