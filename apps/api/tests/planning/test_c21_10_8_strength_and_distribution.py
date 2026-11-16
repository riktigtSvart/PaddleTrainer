"""Actual source receipts, bounded redistribution, fixed load and explicit choices."""
from copy import deepcopy
from datetime import date, timedelta
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from app.services import assessment_source_compatibility as sources
from app.services import training_distribution as distribution, training_plan_policy as policy
from tests.planning.test_c21_9_1_calendar_endurance import env as source_fixture
from tests.planning.test_c21_10_swimming_load import configure, SETTINGS
from tests.planning.test_c21_10_5_goal_coverage import full
from tests.planning.test_c21_10_6_reusable_references import change_options
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c20_4_initial_assessment import context as assessment_context


@pytest.fixture
def env(tmp_path, monkeypatch):
    yield from source_fixture.__wrapped__(tmp_path, monkeypatch)


def export(name, value):
    if os.getenv('C21_10_8_EXPORT'):
        path = Path(os.environ['C21_10_8_EXPORT'])
        saved = json.loads(path.read_text()) if path.exists() else {}
        saved[name] = value
        path.write_text(json.dumps(saved), encoding='utf-8')


def new_pool(data):
    pool = deepcopy(data['locations'][0])
    pool.update(id=str(UUID(int=2110801)), name='Új uszoda', sports=['SWIMMING'], resources=['Úszómedence'])
    data['locations'].append(pool)


def test_unrelated_pool_addition_keeps_exact_assessment_and_restores_strength(env):
    saved = configure(env)
    before = assessment_context(env)['saved']['artifact']
    change_options(env, saved, 2110802, new_pool)
    reviewed = full(env)
    context = reviewed['inputs']['strength_assessment']
    assert context['receipt']['artifact'] == before
    assert context['receipt']['artifact']['proposal']['source_hash'] != context['source_hash']
    assert context['source_comparison']['reusable'] is True
    assert context['source_comparison']['changes'] == ['OPTIONS_OTHER_FIELDS']
    strength = [c for c in reviewed['result']['proposals'] if c['sport'] == 'STRENGTH']
    assert strength and all(c['capability_key'] == 'MAX_STRENGTH' for c in strength)
    assert all(c['strength_prescription']['assessment_reference']['artifact_id'] == before['artifact_id'] for c in strength)
    assert 'STRENGTH_ASSESSMENT_SOURCES_CHANGED' not in reviewed['result']['strength_assessment']['issues']
    export('added_pool', reviewed)
    accept(env, reviewed, token=2110803)
    repeated = full(env)
    assert not repeated['result']['create'] and not repeated['result']['cancel']
    export('repeated', repeated)


def test_cosmetic_location_changes_and_resource_order_do_not_invalidate_observations(env):
    saved = configure(env)
    def change(data):
        new_pool(data)
        venue = data['locations'][0]
        venue['name'] = 'Ugyanaz a terem új megjelenítési névvel'
        venue['resources'].reverse()
        venue['sports'].reverse()
        data['locations'].reverse()
    change_options(env, saved, 2110804, change)
    reviewed = full(env)
    assert reviewed['inputs']['strength_assessment']['source_comparison']['reusable'] is True
    assert any(c['sport'] == 'STRENGTH' for c in reviewed['result']['proposals'])
    export('cosmetic', reviewed)


@pytest.mark.parametrize('change', ['equipment', 'archived', 'sport_removed', 'missing', 'exercise_confirmation'])
def test_real_changes_at_a_measured_venue_remain_review_boundaries(env, change):
    saved = configure(env)
    def mutate(data):
        if change == 'equipment':
            data['locations'][0]['resources'].append('Új erőgép')
        elif change == 'archived':
            data['locations'][0]['archived'] = True
        elif change == 'sport_removed':
            data['locations'][0]['sports'].remove('STRENGTH')
        elif change == 'exercise_confirmation':
            catalogue = assessment_context(env)['saved']['artifact']['snapshot']['catalog']
            data['locations'][0]['exercise_confirmations'] = [{'exercise_id': catalogue['exercises'][0]['id']}]
        else:
            new_pool(data)
            removed = data['locations'].pop(0)['id']
            for slot in data['weekly_slots']:
                slot['details']['location_ids'] = [data['locations'][0]['id'] if v == removed else v for v in slot['details']['location_ids']]
    change_options(env, saved, 2110805, mutate)
    reviewed = full(env)
    comparison = reviewed['inputs']['strength_assessment']['source_comparison']
    assert comparison['reusable'] is False and 'OPTIONS_REFERENCED_LOCATIONS' in comparison['changes']
    assert not any(c['sport'] == 'STRENGTH' for c in reviewed['result']['proposals'])
    assert 'STRENGTH_ASSESSMENT_SOURCES_CHANGED' in reviewed['result']['strength_assessment']['issues']
    export('material_' + change, reviewed)


def test_new_program_is_distinct_from_editing_previous_program_or_health_sources(env):
    configure(env)
    context = full(env)['inputs']['strength_assessment']
    added = deepcopy(context)
    added['source_body']['programs'].append({'new_program': 'unrelated'})
    assert sources.compare(added)['reusable'] is True
    assert sources.compare(added)['changes'] == ['PROGRAMS_ADDED']
    for key, code in [('programs', 'PROGRAMS'), ('profile_reference', 'PROFILE'), ('registry_hash', 'REGISTRY'), ('catalog_hash', 'CATALOG')]:
        changed = deepcopy(context)
        changed['source_body'][key] = [] if key == 'programs' else None
        result = sources.compare(changed)
        assert result['reusable'] is False and code in result['changes']


def candidate(n, sport='RUNNING', goal='PERIPHERAL_OXIDATIVE_CAPACITY', role='primary_development'):
    day = (date(2026, 11, 20) + timedelta(days=n)).isoformat()
    return {'candidate_key': f'{sport}-{goal}-{n}', 'template_key': sport, 'opportunity_key': day + sport,
            'date': day, 'start_at': day + 'T12:00:00+00:00', 'duration_sec': 1200,
            'sport': sport, 'capability_key': goal, 'role': role, 'training_period_id': 'meso'}


def situation(candidates):
    context = {'mode': 'coordinated', 'blocks': [{'key': 'meso:1', 'start_date': '2026-11-20', 'end_date': '2026-11-26',
        'max_sessions': 3, 'max_minutes': 60}]}
    state = {'coordination': context, 'loads': [], 'eligible': [], 'max_count': 3, 'max_seconds': 3600}
    data = {'start_date': '2026-11-20', 'end_date': '2026-11-26'}
    alternatives = [{'date': c['date'], 'candidates': [c]} for c in candidates]
    return alternatives, state, data


def test_three_sessions_are_spread_across_seven_civil_days_without_more_load():
    pool = [candidate(n) for n in range(7)]
    alternatives, state, data = situation(pool)
    result, proof = distribution.improve(pool[:3], alternatives, state, data, {})
    assert len(result) == 3 and sum(c['duration_sec'] for c in result) == 3600
    assert all((date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days == 2 for a, b in zip(result, result[1:]))
    assert proof['before']['adjacent_training_day_pairs'] == 2
    assert proof['after']['adjacent_training_day_pairs'] == 0
    assert proof['after']['longest_training_free_span_days'] == 1


def test_scarce_strength_and_technical_maintenance_are_kept_around_flexible_aerobic_work():
    pool = [candidate(n) for n in range(7)] + [candidate(0, 'STRENGTH', 'MAX_STRENGTH'), candidate(6, 'KAYAK', 'TECHNICAL_SKILL', 'maintenance')]
    alternatives, state, data = situation(pool)
    selected, _ = distribution.improve(pool[:3], alternatives, state, data, {})
    assert {'MAX_STRENGTH', 'PERIPHERAL_OXIDATIVE_CAPACITY', 'TECHNICAL_SKILL'} == {c['capability_key'] for c in selected}
    assert all((date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days >= 2 for a, b in zip(selected, selected[1:]))


def test_explicit_choice_and_fixed_load_limit_redistribution():
    pool = [candidate(n) for n in range(7)]
    alternatives, state, data = situation(pool)
    preference = {pool[0]['date']: {k: pool[0][k] for k in ('template_key', 'opportunity_key', 'capability_key', 'role')}}
    result, _ = distribution.improve(pool[:3], alternatives, state, data, preference)
    assert pool[0] in result
    # With only three consecutive usable days no rest day can be invented.
    result, proof = distribution.improve(pool[:3], alternatives[:3], state, data, {})
    assert result == pool[:3] and proof['optimization_passes'] == 0
    # An actual high/unknown-effort session imposes the existing 36h boundary.
    state['loads'] = [{'date': date(2026, 11, 24), 'at': policy.at('2026-11-24T12:00:00+00:00'), 'sport': 'RUNNING', 'seconds': 1200}]
    state['max_count'], state['max_seconds'] = 4, 4800
    state['coordination']['blocks'][0].update(max_sessions=4, max_minutes=80)
    result, _ = distribution.improve([pool[0], pool[1]], alternatives, state, data, preference)
    assert all(not policy.load_policy.conflicts(state['loads'], policy.at(c['start_at']), c['sport']) for c in result)


def test_early_strength_tiebreak_does_not_reward_extra_strength_frequency():
    pool = [candidate(n) for n in range(7)] + [candidate(n, 'STRENGTH', 'MAX_STRENGTH') for n in range(7)]
    alternatives, state, data = situation(pool)
    baseline = [candidate(0, 'STRENGTH', 'MAX_STRENGTH'), candidate(2), candidate(5)]
    selected, _ = distribution.improve(baseline, alternatives, state, data, {})
    assert sum(c['sport'] == 'STRENGTH' for c in selected) == 1
    assert sum(c['duration_sec'] for c in selected) == 3600


def test_whole_api_review_preserves_microcycle_count_and_never_increases_minutes(env):
    configure(env)
    value = full(env)
    result = value['result']
    index = {c['candidate_key']: c for g in result['alternatives'] for c in g['candidates']}
    baseline = [index[k] for k in result['distribution']['baseline_candidate_keys']]
    before, after = distribution.totals(result['mesocycle_coordination'], baseline), distribution.totals(result['mesocycle_coordination'], result['proposals'])
    assert set(before) == set(after)
    assert all(after[k][0] == before[k][0] and after[k][1] <= before[k][1] for k in before)
    assert result['distribution']['after']['adjacent_training_day_pairs'] <= result['distribution']['before']['adjacent_training_day_pairs']
    export('balanced', value)


def test_friday_started_mesocycle_with_three_sessions_per_week_has_rest_days_and_strength(env):
    settings = deepcopy(SETTINGS)
    settings['current_baseline'].update(weekly_sessions=3, weekly_minutes=155)
    configure(env, settings=settings)
    response = env.client.post(env.plan_url + '/review', json={'start_date': '2026-11-20', 'end_date': '2026-12-17', 'coordinate_mesocycles': True})
    assert response.status_code == 200, response.text
    value = response.json()['review']
    rows = value['result']['proposals']
    assert any(c['sport'] == 'STRENGTH' for c in rows)
    assert value['result']['distribution']['after']['adjacent_training_day_pairs'] == 0
    assert all((date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days >= 2 for a, b in zip(rows, rows[1:]))
    assert value['result']['distribution']['after']['longest_training_free_span_days'] <= 2
    export('three_per_week', value)
    from tests.planning.test_p2_4c19_plan_choices import choice
    group = next(g for g in value['result']['alternatives'] if g['selected_candidate_key'] and any(c['sport'] == 'SWIMMING' for c in g['candidates']))
    alternative = next(c for c in group['candidates'] if c['sport'] == 'SWIMMING')
    chosen = choice(env, value, group['date'], alternative['candidate_key'])['review']
    actual = next(c for c in chosen['result']['proposals'] if c['date'] == group['date'])
    assert actual['sport'] == 'SWIMMING' and actual['capability_key'] == alternative['capability_key'] and actual['role'] == alternative['role']
    export('explicit_choice', chosen)
