"""Goal representation, explicit omissions, and unchanged prescription gates."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from app.services import training_plan_policy as policy, training_options
from tests.planning.test_c21_9_1_calendar_endurance import env as source_fixture
from tests.planning.test_c21_10_swimming_load import configure, SETTINGS
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c19_training_options import save as save_options
from tests.planning.test_p2_4c20_4_initial_assessment import save as save_assessment
from tests.planning.test_p2_4c20_5_assessed_strength import request


@pytest.fixture
def env(tmp_path, monkeypatch):
    yield from source_fixture.__wrapped__(tmp_path, monkeypatch)


def full(e):
    r = e.client.post(e.plan_url + '/review', json={'start_date': '2026-10-26', 'end_date': '2026-11-22', 'coordinate_mesocycles': True})
    assert r.status_code == 200, r.text
    return r.json()['review']


def export(name, value):
    if os.getenv('C21_10_5_EXPORT'):
        path = Path(os.environ['C21_10_5_EXPORT'])
        data = json.loads(path.read_text()) if path.exists() else {}
        data[name] = value
        path.write_text(json.dumps(data))


def test_technical_maintenance_is_not_starved_by_repeating_the_aerobic_primary_goal(env):
    configure(env)
    value = full(env)
    data = deepcopy(value['inputs'])
    for day in data['days']:
        sample = day['capability_roles'][0]
        day['capability_roles'] = [{**sample, 'capability_key': key, 'role': role} for key, role in [
            ('PERIPHERAL_OXIDATIVE_CAPACITY', 'primary_development'), ('MAX_STRENGTH', 'primary_development'), ('TECHNICAL_SKILL', 'maintenance')]]
    result = policy.build(data, [], policy.at(data['captured_at']), coordinate_mesocycles=True)
    assert {'PERIPHERAL_OXIDATIVE_CAPACITY', 'MAX_STRENGTH', 'TECHNICAL_SKILL'} <= {c['capability_key'] for c in result['proposals']}
    assert any(c['sport'] == 'KAYAK' and c['role'] == 'maintenance' and c['template_key'] == 'KAYAK_EASY_TECHNICAL' for c in result['proposals'])
    caps = result['prescription_context']['starting_budget']
    rows = result['proposals']
    for c in rows:
        group = [r for r in rows if 0 <= (datetime.fromisoformat(r['date']) - datetime.fromisoformat(c['date'])).days <= 6]
        assert len(group) <= caps['max_sessions_per_7_days']
        assert sum(r['duration_sec'] for r in group) <= caps['max_minutes_per_7_days'] * 60
        for other in rows:
            if c is not other:
                assert not policy.load_policy.conflicts([{'at': policy.at(other['start_at']), 'sport': other['sport'], 'known': True}], policy.at(c['start_at']), c['sport'])
    assert len({c['date'] for c in rows}) == len(rows)
    assert result['policy']['version'] == 'training-plan-policy-v0.15'


def test_material_equipment_change_reports_why_strength_is_withheld_and_review_reopens_it(env):
    saved = configure(env)
    changed = deepcopy(saved['artifact']['proposal'])
    changed.update(request_id=str(UUID(int=2110501)), previous_reference=training_options.reference(saved['artifact']))
    changed['data']['locations'][0]['resources'].append('Gumiszalag')
    save_options(env, changed)
    value = full(env)
    report = value['result']['preparation']['sport_availability']
    strength = next(r for r in report['sports'] if r['sport'] == 'STRENGTH')
    assert strength['planned_sessions'] == strength['candidate_days'] == 0
    assert 'STRENGTH_ASSESSMENT_SOURCES_CHANGED' in strength['reasons']
    goals = [r for r in report['goal_coverage'] if r['capability_key'] == 'MAX_STRENGTH']
    assert goals and all(r['status'] == 'unavailable' and 'STRENGTH_ASSESSMENT_SOURCES_CHANGED' in r['reasons'] for r in goals)
    export('changed_timetable', value)
    save_assessment(env, request(env, token=2110502))
    fresh = full(env)
    assert any(c['sport'] == 'STRENGTH' for c in fresh['result']['proposals'])
    export('reviewed_timetable', fresh)


def test_current_valid_sources_produce_a_mixed_plan_and_repeat_acceptance_is_stable(env):
    configure(env)
    value = full(env)
    rows = value['result']['proposals']
    assert {'STRENGTH', 'KAYAK', 'RUNNING', 'SWIMMING'} <= {c['sport'] for c in rows}
    report = value['result']['preparation']['sport_availability']
    assert report['schema_version'] == 'training-sport-availability-v0.3'
    for r in report['goal_coverage']:
        assert r['planned_sessions'] == sum(c['training_period_id'] == r['mesocycle_id'] and c['capability_key'] == r['capability_key'] and c['role'] == r['role'] for c in rows)
    accept(env, value, token=2110503)
    repeated = full(env)
    assert not repeated['result']['create'] and not repeated['result']['cancel']
    export('mixed', value)


def test_missing_swimming_ability_stays_a_real_gate_instead_of_becoming_a_quota(env):
    configure(env, settings={**deepcopy(SETTINGS), 'swimming': None})
    value = full(env)
    row = next(r for r in value['result']['preparation']['sport_availability']['sports'] if r['sport'] == 'SWIMMING')
    assert not row['planned_sessions'] and not row['candidate_days']
    assert 'SWIMMING_ABILITY_REQUIRED' in row['reasons']
    assert any(c['sport'] == 'RUNNING' for c in value['result']['proposals'])


def test_coverage_includes_unsupported_and_unselected_goals_without_claiming_adaptation():
    from app.services.training_sport_availability import goal_coverage
    roles = [{'capability_key': key, 'role': role} for key, role in [('TECHNICAL_SKILL', 'maintenance'), ('VO2_CAPACITY', 'primary_development')]]
    data = {'days': [{'date': '2026-11-13', 'mesocycle_id': 'm', 'capability_roles': roles}]}
    alternatives = [{'date': '2026-11-13', 'candidates': [{'training_period_id': 'm', 'template_key': 'KAYAK_EASY_TECHNICAL'}]}]
    rows = goal_coverage(data, policy.TEMPLATES, [], alternatives, [])
    by_key = {r['capability_key']: r for r in rows}
    assert by_key['TECHNICAL_SKILL']['status'] == 'available_unselected'
    assert by_key['TECHNICAL_SKILL']['reasons'] == ['GOAL_NOT_SELECTED']
    assert by_key['VO2_CAPACITY']['status'] == 'unsupported'
    assert all(r['planned_sessions'] == 0 for r in rows)
