"""Rescheduling preserves observations; declared sport skill and default starts."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from app.services import training_options
from tests.planning.test_c21_9_1_calendar_endurance import env as source_fixture
from tests.planning.test_c21_10_swimming_load import configure, SETTINGS
from tests.planning.test_c21_10_5_goal_coverage import full
from tests.planning.test_p2_4c5r2_athlete_setup import post as post_profile
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c20_4_initial_assessment import context as initial_context, save as save_initial
from tests.planning.test_p2_4c20_5_assessed_strength import request
from tests.planning.test_p2_4c20_1_prescriptions import completed
from app.models.entities import Sport


@pytest.fixture
def env(tmp_path, monkeypatch):
    yield from source_fixture.__wrapped__(tmp_path, monkeypatch)


def export(name, value):
    if os.getenv('C21_10_6_EXPORT'):
        path = Path(os.environ['C21_10_6_EXPORT'])
        data = json.loads(path.read_text()) if path.exists() else {}
        data[name] = value
        path.write_text(json.dumps(data))


def change_options(e, saved, token, change):
    p = deepcopy(saved['artifact']['proposal'])
    p.update(request_id=str(UUID(int=token)), previous_reference=training_options.reference(saved['artifact']))
    change(p['data'])
    return save_options(e, p)


def add_swimmer(e, *, proficiency='experienced', role='secondary', current=True, discipline='Vegyes'):
    before = full(e)['inputs']['profile']
    data = deepcopy(before['data'])
    data['sport_history'].append({'sport': 'Úszás', 'discipline': discipline, 'start_year': 1984, 'current': current,
        'last_active_date': None, 'level': 'recreational', 'usual_sessions_per_week': None, 'notes': '',
        'role': role, 'current_level': 'recreational', 'planning': {'version': 'sport-planning-context-v0.1',
            'supported_sports': ['Kajak-Kenu / Kajak'], 'purposes': ['aerobic_substitution'], 'proficiency': proficiency}})
    return post_profile(e, 'profiles', {'request_id': str(UUID(int=2110601)),
        'previous_reference': {k: before['reference'][k] for k in ('artifact_id', 'content_hash')}, 'data': data})


def swims(value):
    return [c for g in value['result']['alternatives'] for c in g['candidates'] if c['sport'] == 'SWIMMING']


def test_rescheduling_keeps_exact_saved_reference_and_uses_the_new_time(env):
    saved = configure(env)
    before = initial_context(env)
    def change(data):
        data['weekly_slots'][0]['details'].update(start_time='19:00', end_time='20:00', max_minutes=60)
    change_options(env, saved, 2110602, change)
    after = initial_context(env)
    assert after['reference'] == before['reference'] and after['sources']['source_hash'] == before['sources']['source_hash']
    assert after['sources_changed'] is False and after['saved']['artifact'] == before['saved']['artifact']
    v = full(env)
    strength = [c for c in v['result']['proposals'] if c.get('strength_prescription')]
    assert strength and all(c['strength_prescription']['assessment_reference'] == before['reference'] for c in strength)
    assert any(c['start_at'][11:16] == '18:00' for c in strength)  # 19:00 Budapest in winter.
    export('rescheduled', v)


def test_old_assessment_keeps_its_actual_anchor_not_an_older_equivalent_parent(env, monkeypatch):
    saved = configure(env)
    modern = training_options.assessment_content
    legacy = lambda data: {k: ([{a: b for a, b in row.items() if a not in {'coordinates', 'area', 'kind', 'pool_length_m', 'daylight_overrides'}} for row in v] if k == 'locations' else v) for k, v in data.items() if k not in {'prescription_settings', 'daylight_rules'}}
    with monkeypatch.context() as old:
        old.setattr(training_options, 'assessment_content', legacy)
        saved = change_options(env, saved, 2110603, lambda data: data['weekly_slots'][0]['details'].update(max_minutes=80))
        save_initial(env, request(env, token=2110604))
        before = initial_context(env)
    assert training_options.assessment_content is modern
    change_options(env, saved, 2110605, lambda data: data['weekly_slots'][0]['details'].update(max_minutes=70))
    after = initial_context(env)
    assert after['sources']['options_reference'] == before['saved']['artifact']['snapshot']['options_reference']
    assert after['sources']['source_hash'] == before['sources']['source_hash'] and not after['sources_changed']
    export('historical_anchor', full(env))


def test_sport_biography_updates_reuse_strength_and_enable_self_paced_swimming(env):
    configure(env, settings={**deepcopy(SETTINGS), 'swimming': None})
    before = initial_context(env)
    add_swimmer(env)
    after = initial_context(env)
    assert not after['sources_changed'] and after['reference'] == before['reference']
    assert after['sources']['source_hash'] == before['sources']['source_hash']
    v = full(env)
    assert swims(v) and any(c.get('strength_prescription') for c in v['result']['proposals'])
    proof = v['inputs']['strength_assessment']['current_profile_receipt']['artifact']
    assert proof['content_hash'] == v['inputs']['profile']['reference']['content_hash']
    for c in swims(v):
        m = v['result']['prescription_context']['by_candidate'][c['candidate_key']]['swimming']
        assert m['mode'] == 'self_paced' and m['stroke'] == 'self_selected'
        assert m['continuous_distance_limit_m'] is None and m['declared_cap_seconds'] is None
        assert m['pace_estimated'] is m['current_capacity_measured'] is False
        assert m['ability_basis']['profile_reference']['content_hash'] == proof['content_hash']
    export('profile_swimming', v)
    accept(env, v, token=2110606)
    again = full(env)
    assert not again['result']['create'] and not again['result']['cancel']


@pytest.mark.parametrize('change', [{'proficiency': 'learning'}, {'proficiency': 'unknown'}, {'role': 'recreation'}, {'role': 'paused'}, {'current': False}])
def test_learning_or_inactive_sport_history_does_not_claim_independent_swimming(env, change):
    configure(env, settings={**deepcopy(SETTINGS), 'swimming': None})
    add_swimmer(env, **change)
    assert not swims(full(env))


def test_explicit_negative_swimming_answer_wins_over_general_experience(env):
    settings = deepcopy(SETTINGS)
    settings['swimming']['independent'] = False
    configure(env, settings=settings)
    add_swimmer(env)
    assert not swims(full(env))


def test_time_based_profile_swim_needs_a_pool_but_not_its_exact_length(env):
    saved = configure(env, settings={**deepcopy(SETTINGS), 'swimming': None})
    add_swimmer(env, discipline='Mell')
    saved = change_options(env, saved, 2110607, lambda data: data['locations'][0].pop('pool_length_m'))
    v = full(env)
    assert swims(v)
    for c in swims(v):
        dose = v['result']['prescription_context']['by_candidate'][c['candidate_key']]['swimming']
        assert dose['pool_length_m'] is None and dose['stroke'] == 'breaststroke'
    export('swimming_without_length', v)
    change_options(env, saved, 2110608, lambda data: data['locations'][0]['resources'].remove('Úszómedence'))
    blocked = full(env)
    assert not swims(blocked)
    assert 'SWIMMING_POOL_REQUIRED' in next(r for r in blocked['result']['preparation']['sport_availability']['sports'] if r['sport'] == 'SWIMMING')['reasons']


def test_strength_without_an_assessment_has_a_labelled_introductory_session(env):
    v = full(env)
    rows = [c for c in v['result']['proposals'] if c['sport'] == 'STRENGTH']
    assert rows and all(c['template_version'] == 'v0.4' and 'strength_prescription' not in c for c in rows)
    for c in rows:
        m = v['result']['prescription_context']['by_candidate'][c['candidate_key']]
        assert m['product_default_used'] and m['reference_session_ids'] == [] and m['reference_cap_seconds'] is None
        assert m['introductory_strength']['preparatory_only'] and m['introductory_strength']['external_load_prescribed'] is False
        assert m['introductory_strength']['max_repetitions'] == 5
        assert sum(b['duration_sec'] for b in c['blocks']) == c['duration_sec'] == 1200
    export('introductory_strength', v)
    accept(env, v, token=2110609)
    repeated = full(env)
    assert not repeated['result']['create'] and not repeated['result']['cancel']


@pytest.mark.parametrize('field,value', [('comfort', 'symptoms'), ('comfort', 'avoid'), ('comfort', 'uncertain')])
def test_introductory_fallback_does_not_override_recorded_movement_problems(env, field, value):
    configure(env)
    p = request(env, token=2110610)
    for e in p['data']['exercises']:
        e[field] = value
        e['sets'] = []
    save_initial(env, p)
    assert not any(c['sport'] == 'STRENGTH' for g in full(env)['result']['alternatives'] for c in g['candidates'])


def test_no_series_reference_uses_intro_instead_of_inventing_a_load(env):
    configure(env)
    p = request(env, token=2110611)
    for e in p['data']['exercises']:
        e['sets'] = []
    save_initial(env, p)
    v = full(env)
    assert any(c['template_version'] == 'v0.4' for c in v['result']['proposals'])
    assert not any(c.get('strength_prescription') for g in v['result']['alternatives'] for c in g['candidates'])
    export('no_series_reference', v)


def test_health_profile_change_still_requires_review(env):
    configure(env)
    before = full(env)['inputs']['profile']
    data = deepcopy(before['data'])
    data['participation'] = 'professional_review'
    post_profile(env, 'profiles', {'request_id': str(UUID(int=2110612)), 'previous_reference': {k: before['reference'][k] for k in ('artifact_id', 'content_hash')}, 'data': data})
    assert initial_context(env)['sources_changed'] is True
    assert full(env)['result']['proposals'] == []


@pytest.mark.parametrize('field,value', [('supervision', 'needed'), ('state_change', 'changed'), ('references_reviewed', False)])
def test_intro_does_not_bypass_actual_assessment_review_gates(env, field, value):
    configure(env)
    p = request(env, token=2110613)
    p['data'][field] = value
    for entry in p['data']['exercises']:
        entry['sets'] = []
    save_initial(env, p)
    assert not any(c['sport'] == 'STRENGTH' for g in full(env)['result']['alternatives'] for c in g['candidates'])


def test_closure_uses_the_current_options_without_invalidating_observations(env):
    saved = configure(env)
    before = initial_context(env)
    def close(data):
        data['weekly_slots'] = []
    change_options(env, saved, 2110614, close)
    after = initial_context(env)
    assert not after['sources_changed'] and after['reference'] == before['reference']
    assert not full(env)['result']['proposals']


def test_intro_does_not_enlarge_a_known_short_strength_duration(env):
    completed(env, 2110615, sport=Sport.STRENGTH, minutes=15)
    assert not any(c['sport'] == 'STRENGTH' for g in full(env)['result']['alternatives'] for c in g['candidates'])
