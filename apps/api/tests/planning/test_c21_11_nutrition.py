"""Real owned HTTP persistence and independent meal/shopping arithmetic."""
from copy import deepcopy
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
from uuid import UUID
import pytest
from sqlalchemy import update
from app.api.routes import nutrition as route
from app.planning.application import register_athlete_setup as intake
from app.planning.domain.athlete_setup import digest
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition import NutritionData
from app.services import nutrition_domain as domain
from tests.planning.test_p2_4c3_goal_workflow_api import environment, count, OTHER_EMAIL

BASE = '/api/v1/planning/nutrition'


@pytest.fixture
def env(environment, monkeypatch):
    from app.models.entities import PlannedWorkout
    PlannedWorkout.__table__.create(environment.engine, checkfirst=True)
    environment.app.include_router(route.router, prefix='/api/v1')
    monkeypatch.setattr(intake, '_now', environment.clock.tick)
    return environment


def data(**changes):
    result = NutritionData().model_dump()
    result['preferences']['allergens_reviewed'] = True
    result['plan'] = domain.make_plan(result['preferences'], '2026-11-16', 7, 2)
    return {**result, **changes}


def body(token=21110001, previous=None, value=None):
    return {'request_id': str(UUID(int=token)), 'previous_reference': previous,
        'catalog_hash': domain.catalog()['content_hash'], 'data': value or data()}


def get(env, expected=200):
    r = env.client.get(BASE)
    assert r.status_code == expected, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def post(env, value, expected=201):
    r = env.client.post(BASE, json=value)
    assert r.status_code == expected, r.text
    return r.json()


def test_actual_create_swap_pantry_check_reload_and_idempotent_recovery(env):
    initial = get(env)
    assert initial['saved'] is None and initial['reference'] is None
    before = count(env, PlanningAuditArtifactRow)
    first = body()
    saved = post(env, first)
    assert saved['committed'] and not saved['artifact']['workouts_changed'] and not saved['artifact']['actual_intake_changed']
    context = get(env)
    assert context['saved'] == saved['artifact']
    assert post(env, first, 200)['reused']
    changed = deepcopy(first['data'])
    meal = changed['plan']['meals'][0]
    meal['recipe_id'] = 'chickpea_toast'
    meal['portion_factor'] = '1.5'
    changed['pantry'] = {'chickpeas': '50.125', 'olive_oil': '10.25'}
    changed['checked'] = ['bread']
    second = body(21110002, context['reference'], changed)
    updated = post(env, second)
    current = get(env)
    assert current['saved']['result'] == domain.project(changed)
    assert current['saved']['proposal']['data'] == changed
    assert count(env, PlanningAuditArtifactRow) == before + 2
    assert post(env, first, 200)['artifact'] == saved['artifact']
    assert get(env)['saved'] == updated['artifact']  # retry never restores old state
    assert all(not request.in_transaction() for request in env.requests)
    if os.getenv('C21_11_EXPORT'):
        Path(os.environ['C21_11_EXPORT']).write_bytes(gzip.compress(json.dumps({'initial': initial,
            'first_body': first, 'first_receipt': saved, 'second_body': second, 'second_receipt': updated,
            'current': current}, ensure_ascii=False).encode(), mtime=0))


def test_exact_stock_subtraction_and_scaling_are_hand_calculated_not_a_float_sum():
    d = data(); p = d['preferences']; p.update(diet='vegan', meals_per_day=3)
    d['plan'] = {'start_date': '2026-11-16', 'day_count': 1, 'people': 2, 'meals': [
        {'date': '2026-11-16', 'slot': 'breakfast', 'recipe_id': 'banana_oats', 'portion_factor': '1.5'},
        {'date': '2026-11-16', 'slot': 'lunch', 'recipe_id': 'chickpea_seed_salad', 'portion_factor': '0.5'},
        {'date': '2026-11-16', 'slot': 'dinner', 'recipe_id': 'chickpea_seed_salad', 'portion_factor': '1'}]}
    d['pantry'] = {'chickpeas': '50.5', 'olive_oil': '10.25', 'oats': '1000'}
    rows = {r['food_id']: r for r in domain.project(d)['shopping']}
    assert rows['chickpeas']['required'] == '750' and rows['chickpeas']['to_buy'] == '699.5'
    assert rows['olive_oil']['required'] == '30' and rows['olive_oil']['to_buy'] == '19.75'
    assert rows['oats']['required'] == '240' and rows['oats']['to_buy'] == '0'
    assert rows['pumpkin_seeds']['required'] == '150'
    assert rows['banana']['required'] == '450'


def test_whole_items_round_only_after_the_whole_period_and_stock_are_combined():
    d = data(); d['preferences']['meals_per_day'] = 3
    d['plan'] = {'start_date': '2026-11-16', 'day_count': 1, 'people': 1, 'meals': [
        {'date': '2026-11-16', 'slot': 'breakfast', 'recipe_id': 'eggs_toast', 'portion_factor': '0.5'},
        {'date': '2026-11-16', 'slot': 'lunch', 'recipe_id': 'chickpea_seed_salad', 'portion_factor': '1'},
        {'date': '2026-11-16', 'slot': 'dinner', 'recipe_id': 'egg_potato', 'portion_factor': '0.5'}]}
    d['pantry'] = {'eggs': '0.1'}
    row = next(r for r in domain.project(d)['shopping'] if r['food_id'] == 'eggs')
    assert row == {'food_id': 'eggs', 'required': '2.5', 'in_stock': '0.1', 'to_buy': '3', 'checked': False}


@pytest.mark.parametrize('diet', ['omnivore', 'pescatarian', 'vegetarian', 'vegan'])
@pytest.mark.parametrize('minutes', [15, 30, 45, 60])
def test_every_diet_and_preparation_budget_has_valid_options_even_with_all_major_allergens_excluded(diet, minutes):
    d = data()
    d['preferences'].update(diet=diet, max_prep_minutes=minutes, excluded_allergens=list(domain.catalog()['allergens']))
    d['plan'] = domain.make_plan(d['preferences'], '2026-10-23', 14, 8)
    result = domain.project(d)
    assert len(result['days']) == 14 and result['days'][2]['date'] == '2026-10-25'  # civil dates across DST
    foods = {f['id']: f for f in domain.catalog()['foods']}
    assert all(not foods[r['food_id']]['allergens'] for r in result['shopping'])
    if diet == 'vegan':
        assert all(foods[r['food_id']]['animal_source'] == 'none' for r in result['shopping'])


def test_impossible_exclusions_are_explained_without_relaxing_them():
    d = data(); d['preferences']['excluded_foods'] = [f['id'] for f in domain.catalog()['foods']]
    before = deepcopy(d)
    with pytest.raises(ValueError):
        domain.make_plan(d['preferences'], '2026-11-16')
    assert d == before


@pytest.mark.parametrize('mutation,code', [
    (lambda b: b['data']['preferences'].update(allergens_reviewed=False), 'NUTRITION_ALLERGEN_REVIEW_REQUIRED'),
    (lambda b: b['data']['preferences'].update(excluded_allergens=['gluten']), 'NUTRITION_RECIPE_NOT_ALLOWED'),
    (lambda b: b['data']['plan']['meals'].pop(), 'NUTRITION_MEAL_COVERAGE_INVALID'),
    (lambda b: b['data']['plan']['meals'].__setitem__(1, deepcopy(b['data']['plan']['meals'][0])), 'NUTRITION_MEAL_COVERAGE_INVALID'),
    (lambda b: b['data']['plan']['meals'][0].update(recipe_id='chicken_rice'), 'NUTRITION_RECIPE_NOT_ALLOWED'),
    (lambda b: b['data']['pantry'].update(unknown='1'), 'NUTRITION_UNKNOWN_FOOD'),
    (lambda b: b['data']['pantry'].update(oats='999999') or b['data'].update(checked=['oats']), 'NUTRITION_CHECKED_ITEM_INVALID'),
    (lambda b: b.update(catalog_hash='f'*64), 'NUTRITION_CATALOG_CHANGED'),
])
def test_semantic_errors_have_no_writes(env, mutation, code):
    before = count(env, PlanningAuditArtifactRow); b = body(); mutation(b)
    assert post(env, b, 409)['detail']['code'] == code
    assert count(env, PlanningAuditArtifactRow) == before


@pytest.mark.parametrize('mutation', [
    lambda b: b.update(unexpected=True), lambda b: b['data'].update(personal_energy_kcal=2000),
    lambda b: b['data']['plan'].update(day_count=True), lambda b: b['data']['plan'].update(people=0),
    lambda b: b['data']['plan'].update(day_count=15), lambda b: b['data']['plan'].update(start_date='2100-12-31'),
    lambda b: b['data']['plan']['meals'][0].update(portion_factor='0'),
    lambda b: b['data']['preferences'].update(excluded_allergens=['invented']),
    lambda b: b['data']['pantry'].update(oats='-1'), lambda b: b['data']['pantry'].update(oats=1),
    lambda b: b['data']['pantry'].update(oats='1.0001'), lambda b: b['data']['pantry'].update(oats='NaN'),
])
def test_strict_input_rejects_invalid_quantities_ranges_and_unspecified_authority(env, mutation):
    before = count(env, PlanningAuditArtifactRow); b = body(); mutation(b)
    post(env, b, 422); assert count(env, PlanningAuditArtifactRow) == before


def test_preferences_can_be_saved_before_any_plan_and_unknown_allergens_never_mean_none(env):
    d = NutritionData().model_dump(); saved = post(env, body(value=d))
    assert saved['artifact']['result'] == {'days': [], 'shopping': [], 'meal_count': 0}
    assert not get(env)['saved']['proposal']['data']['preferences']['allergens_reviewed']


def test_stale_revision_foreign_owner_and_reused_request_never_overwrite_current(env):
    first = body(); a = post(env, first); current = get(env)
    stale = body(21110020)
    assert post(env, stale, 409)['detail']['code'] == 'NUTRITION_REVISION_CHANGED'
    changed = deepcopy(first); changed['data']['plan']['people'] = 3
    assert post(env, changed, 409)['detail']['code'] == 'NUTRITION_REQUEST_CONFLICT'
    env.email = OTHER_EMAIL
    assert get(env)['saved'] is None
    assert post(env, body(21110021, current['reference']), 409)['detail']['code'] == 'NUTRITION_REVISION_CHANGED'
    other = post(env, first)
    assert other['artifact']['athlete_id'] != a['artifact']['athlete_id']
    assert other['artifact']['artifact_id'] != a['artifact']['artifact_id']


def test_rehashed_stored_shopping_forgery_is_detected(env):
    saved = post(env, body())['artifact']
    saved['result']['shopping'][0]['to_buy'] = '999'
    saved['content_hash'] = digest({k: v for k, v in saved.items() if k != 'content_hash'})
    with env.engine.begin() as db:
        db.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id == saved['artifact_id'])
            .values(contract_json=json.dumps(saved, ensure_ascii=False), content_hash=saved['content_hash']))
    assert get(env, 409)['detail']['code'] == 'NUTRITION_STORAGE_INVALID'


def test_query_fields_are_closed_and_production_router_includes_nutrition(env):
    assert env.client.get(BASE + '?owner=another').status_code == 422
    assert env.client.post(BASE + '?x=y', json=body()).status_code == 422
    from app.main import app
    assert set(app.openapi()['paths'][BASE]) == {'get', 'post'}
