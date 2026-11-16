"""Real owned HTTP measurement, restart, publication and derived starter targets."""
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.strength_calibration import CalibrationCommand, Measurement, PROTOCOL
from app.services import strength_calibration_domain as calibration
from app.services import guided_strength as service
from app.services import initial_assessment_domain
from tests.planning.test_p2_4c20_6_guided_strength import guided, context, send, next_request, start_request
from tests.planning.test_p2_4c3_goal_workflow_api import count, OTHER_EMAIL
from tests.planning.test_p2_4c18_4_training_plan import review
from tests.planning.test_p2_4c20_5_assessed_strength import strength_candidates
from tests.planning.test_p2_4c20_5_assessed_strength import request as initial_request
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
from app.planning.domain.athlete_setup import digest


def start(env, token=207001, mode='manual', measurement_mode='calibration'):
    c = context(env)
    p = start_request(c, token, mode)
    p.update(protocol_version=PROTOCOL, protocol_hash=c['calibration_protocols']['content_hash'], measurement_mode=measurement_mode)
    p['progress']['protocol_version'] = PROTOCOL
    return send(env, CalibrationCommand.model_validate(p).model_dump(mode='json'))


def measurement(protocol, day, token, repetitions=8, trial=1, **updates):
    side = 'left' if protocol['side'] == 'each_side' else 'alternating' if protocol['side'] == 'alternating_sides' else 'both'
    v = {'id': str(UUID(int=token)), 'purpose': 'calibration', 'performed_on': day,
         'performed_confirmed': True, 'trial_number': trial, 'side': side,
         'repetitions': repetitions, 'load_kind': 'external_kg', 'load_value': '12.500000', 'load_basis': 'total',
         'rir': '2', 'technique': 'stable', 'symptoms': 'none', 'stop_reason': 'reserve_target',
         'actual_rest_seconds': None, 'setup_note': 'Saját ismert változat, azonos eszköz'}
    if protocol['load_kind'] in {'bodyweight_variant', 'supported_bodyweight_variant', 'leverage_variant'}:
        v.update(load_kind='bodyweight', load_value=None, load_basis='not_applicable')
    v.update(updates)
    return Measurement.model_validate(v).model_dump(mode='json')


def finish(env, started, token=207002, repetitions=8, **updates):
    p = next_request(started, 'finish', token)
    p['progress'].update(phase='review', warmup_completed=True)
    bank = {v['entry_id']: v['protocol'] for v in started['artifact']['measurement_protocols']['entries']}
    for i, row in enumerate(p['progress']['results']):
        s = measurement(bank[row['entry_id']], env.initial['artifact']['proposal']['data']['assessment_date'], 207100+i, repetitions, **updates)
        row.update(state='recorded', observations=[s])
    env.clock.current += timedelta(minutes=20)
    p.update(actual_start_at=started['artifact']['created_at'], actual_end_at=env.clock.current.isoformat(), no_other_recording_confirmed=True, reviewed=True)
    return p


def test_every_catalog_strength_exercise_has_a_selectable_protocol():
    bank = calibration.protocols()
    selected = {v for p in initial_assessment_domain.registry()['patterns'] for v in p['exercise_ids']}
    assert len(bank['entries']) == 120
    assert selected == {v['exercise_id'] for v in bank['entries'] if v['scope'] != 'sport_route'}
    assert len(selected) == 115 and all(len(v['steps']) == 7 for v in bank['entries'])


def test_new_start_freezes_the_exact_selected_protocols_without_workout(guided):
    before = count(guided, WorkoutSession), count(guided, PlannedWorkout)
    result = start(guided)
    assert result['artifact']['schema_version'] == 'guided-strength-session-v0.2'
    assert result['artifact']['measurement_protocols']['protocol_hash'] == calibration.protocols()['content_hash']
    assert before == (count(guided, WorkoutSession), count(guided, PlannedWorkout))


def test_two_calibration_trials_and_23_repetitions_survive_reload_without_health_change(guided):
    started = start(guided)
    p = finish(guided, started, repetitions=23)
    first = p['progress']['results'][0]
    second = {**first['observations'][0], 'id': str(UUID(int=207199)), 'trial_number': 2, 'repetitions': 6, 'rir': '1', 'actual_rest_seconds': 305}
    first['observations'].append(second)
    result = send(guided, p)
    assert result['artifact']['result']['stop_required'] is False
    assert result['assessment_receipt']['artifact']['proposal']['data']['state_change'] == 'unchanged'
    assert context(guided)['latest']['artifact'] == result['artifact']
    assert result['artifact']['proposal']['progress']['results'][0]['observations'] == [first['observations'][0], second]
    assert result['assessment_receipt']['artifact']['proposal']['data']['exercises'][0]['sets'][0]['repetitions'] == 23
    before = count(guided, WorkoutSession)
    assert send(guided, p, 200)['artifact'] == result['artifact']
    assert count(guided, WorkoutSession) == before


def test_new_measurements_make_a_separate_reduced_starter_dose_with_owned_proof(guided):
    result = send(guided, finish(guided, start(guided), repetitions=8))
    value = review(guided)
    evidence = value['inputs']['strength_assessment']['calibration_evidence']
    assert evidence[0]['artifact'] == result['artifact']
    candidates = strength_candidates(value)
    assert candidates
    for candidate in candidates:
        dose = candidate['strength_prescription']
        assert all(m['rest_seconds'] == 180 for m in dose['movements']) and dose['minimum_rir'] == 3
        assert not dose['one_rm_estimated'] and not dose['load_increased']
        assert len(dose['movements']) == 2 and all(m['calibration_derivation'] for m in dose['movements'])
        assert all(e['reference_set']['repetitions'] == e['target']['repetitions'] == 6 and e['reference_set']['rir'] == 'unknown' for e in dose['movements'])
        assert all(e['source_repetitions'] == 8 and e['source_rir'] == '2' and not e['personal_capacity_estimated'] for e in (m['calibration_derivation'] for m in dose['movements']))


@pytest.mark.parametrize('rir', ['0', '1', 'unknown'])
def test_effort_or_unknown_reserve_is_stored_without_inventing_a_training_reference(guided, rir):
    result = send(guided, finish(guided, start(guided), rir=rir))
    assert not result['artifact']['result']['stop_required']
    assert result['assessment_receipt']['artifact']['proposal']['data']['state_change'] == 'unchanged'
    assert not calibration.starter_targets(result)
    assert not strength_candidates(review(guided))


def test_symptom_stops_are_distinct_from_effort_and_retained(guided):
    result = send(guided, finish(guided, start(guided), symptoms='pain', stop_reason='symptom'))
    assert result['artifact']['result']['stop_required']
    assert result['assessment_receipt']['artifact']['proposal']['data']['state_change'] == 'changed'
    assert not calibration.starter_targets(result)


def test_new_checkpoint_can_resume_and_owned_history_is_read_only(guided):
    started = start(guided)
    p = next_request(started, token=207003)
    p['progress'].update(phase='movements', warmup_completed=True)
    p['progress']['results'][0]['observations'] = [measurement(started['artifact']['measurement_protocols']['entries'][0]['protocol'], context(guided)['local_today'], 207199, repetitions=4)]
    p['progress']['results'][0]['state'] = 'recorded'
    saved = send(guided, p)
    assert context(guided)['latest']['artifact'] == saved['artifact']
    response = guided.client.get('/api/v1/planning/guided-strength/revisions/' + p['request_id'])
    assert response.status_code == 200 and response.json()['artifact'] == saved['artifact']
    guided.email = OTHER_EMAIL
    assert guided.client.get('/api/v1/planning/guided-strength/revisions/' + p['request_id']).status_code == 409


@pytest.mark.parametrize('mutation', ['protocol', 'mode', 'metric', 'date', 'duplicate', 'boolean'])
def test_invalid_measurements_or_changed_protocol_never_commit(guided, mutation):
    started = start(guided)
    p = finish(guided, started)
    obs = p['progress']['results'][0]['observations'][0]
    expected = 409
    if mutation == 'protocol': p['protocol_hash'] = 'f'*64
    if mutation == 'mode': p['measurement_mode'] = 'repeatability'
    if mutation == 'metric': obs['distance_m'] = '20'
    if mutation == 'date': obs['performed_on'] = '2027-01-01'
    if mutation == 'duplicate': p['progress']['results'][1]['observations'][0]['id'] = obs['id']
    if mutation == 'boolean': obs['actual_rest_seconds'] = True; expected = 422
    before = count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow)
    send(guided, p, expected)
    assert before == (count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow))


def test_atomic_failure_retries_the_same_measurements_once(guided, monkeypatch):
    started = start(guided)
    p = finish(guided, started)
    before = count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow)
    original = service.transactions.commit
    async def fail(_session):
        raise RuntimeError('simulated disk failure')
    monkeypatch.setattr(service.transactions, 'commit', fail)
    send(guided, p, 503)
    assert before == (count(guided, WorkoutSession), count(guided, PlanningAuditArtifactRow))
    monkeypatch.setattr(service.transactions, 'commit', original)
    assert send(guided, p)['artifact']['state'] == 'finished'


def test_registry_extension_does_not_require_retyping_unchanged_answers(guided, monkeypatch):
    current = initial_assessment_domain._registry
    previous = deepcopy(current())
    previous.pop('content_hash')
    previous['version'] = 'before-additive-update'
    for group, count_ in zip(previous['patterns'], [12, 9, 7, 6, 8]):
        group['exercise_ids'] = group['exercise_ids'][:count_]
    previous['content_hash'] = digest(previous)
    monkeypatch.setattr(initial_assessment_domain, '_registry', lambda: previous)
    p = initial_request(guided, 207700)
    for e in p['data']['exercises']:
        e.update(sets=[], performed_on=None)
    saved = save_initial(guided, p)
    monkeypatch.setattr(initial_assessment_domain, '_registry', current)
    c = context(guided)
    assert c['intake']['sources_changed']
    assert 'GUIDED_SOURCES_CHANGED' not in c['preparation']['issues']
    assert c['intake']['reference']['artifact_id'] == saved['artifact']['artifact_id']
    result = send(guided, finish(guided, start(guided)))
    assert not result['artifact']['result']['application_pending']
    assert result['assessment_receipt']['artifact']['proposal']['source_hash'] == c['intake']['sources']['source_hash']


def test_unconfirmed_form_values_cannot_be_silently_published_as_actual(guided):
    p = finish(guided, start(guided))
    p['progress']['results'][0]['observations'][0]['performed_confirmed'] = False
    p['progress']['results'][0]['state'] = 'pending'
    before = count(guided, WorkoutSession)
    assert send(guided, p, 409)['detail']['code'] == 'CALIBRATION_UNCONFIRMED_RESULT'
    assert count(guided, WorkoutSession) == before


@pytest.mark.parametrize('exercise,values', [
    ('plank', {'repetitions': None, 'hold_seconds': '35.125', 'load_kind': 'bodyweight', 'load_value': None, 'load_basis': 'not_applicable'}),
    ('farmers_carry', {'repetitions': None, 'distance_m': '20.250', 'duration_seconds': '31.125'}),
    ('jump_squat', {'purpose': 'quality', 'repetitions': 1, 'measured_height_m': '0.45', 'load_kind': 'bodyweight', 'load_value': None, 'load_basis': 'not_applicable'}),
    ('slam', {'purpose': 'quality', 'repetitions': 1, 'metric_name': 'Mért sebesség', 'metric_unit': 'm/s', 'metric_value': '4.250'}),
    ('assisted_pullup', {'load_kind': 'assistance_kg', 'load_basis': 'assistance', 'load_value': '0'}),
])
def test_native_measurement_units_and_actual_values_above_planned_caps_are_preserved(exercise, values):
    protocol = next(v for v in calibration.protocols()['entries'] if v['exercise_id'] == exercise)
    observation = measurement(protocol, '2026-11-06', 207900, **values)
    proposal = {'action': 'checkpoint', 'protocol_hash': 'a'*64, 'measurement_mode': 'calibration', 'progress': {
        'phase': 'movements', 'warmup_completed': True, 'results': [{'entry_id': 'row', 'state': 'recorded', 'observations': [observation]}]}}
    snapshot = {'protocol_hash': 'a'*64, 'entries': [{'entry_id': 'row', 'protocol': protocol}]}
    calibration.validate(proposal, '2026-11-06', '2026-11-06', snapshot)
    assert observation['actual_rest_seconds'] is None


def test_repeatability_keeps_two_observed_sets_without_claiming_set_capacity(guided):
    started = start(guided, measurement_mode='repeatability')
    frozen = started['artifact']['measurement_protocols']
    assert frozen['measurement_mode'] == 'repeatability'
    assert all(v['protocol']['planned_measurement']['target_rir'] == 3
               and v['protocol']['planned_measurement']['repetition_cap'] == 8
               and v['protocol']['planned_measurement']['between_trials_rest_target_seconds'] == 180 for v in frozen['entries'])
    p = finish(guided, started, purpose='repeatability', rir='3')
    for index, row in enumerate(p['progress']['results']):
        row['observations'].append({**row['observations'][0], 'id':str(UUID(int=207950+index)), 'trial_number':2, 'actual_rest_seconds':180})
    result = send(guided, p)
    assert all(len(r['observations']) == 2 for r in result['artifact']['proposal']['progress']['results'])
    assert all(len(v['sets']) == 1 and not v['derivation']['personal_capacity_estimated'] for v in calibration.starter_targets(result))


def test_unilateral_result_retains_its_actual_side_without_inventing_the_other(guided):
    p = finish(guided, start(guided))
    p['progress']['results'][0]['observations'][0]['side'] = 'both'
    result = send(guided, p)
    assert result['artifact']['proposal']['progress']['results'][0]['observations'][0]['side'] == 'both'
    assert len(calibration.starter_targets(result)) == 1
