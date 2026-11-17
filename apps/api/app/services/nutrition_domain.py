"""Small, deterministic recipe projection with exact shopping arithmetic."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from functools import lru_cache
import json
from pathlib import Path
from app.planning.domain.athlete_setup import digest, require
from app.schemas.nutrition import NutritionData

SCHEMA = 'nutrition-workspace-v0.1'
SLOTS = ['breakfast', 'lunch', 'dinner', 'snack']


def quantity(value):
    text = format(Decimal(value), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


@lru_cache(maxsize=1)
def _catalog():
    value = json.loads((Path(__file__).parent / 'data/nutrition_catalog_v0_1.json').read_text(encoding='utf-8'))
    foods = {f['id']: f for f in value['foods']}
    require(value['schema_version'] == 'nutrition-catalog-v0.1' and len(foods) == len(value['foods'])
        and len({r['id'] for r in value['recipes']}) == len(value['recipes']), 'NUTRITION_CATALOG_INVALID')
    for f in foods.values():
        require(f['unit'] in {'g', 'ml', 'db'} and f['category'] in value['categories']
            and set(f['allergens']) <= value['allergens'].keys()
            and f['animal_source'] in {'none', 'milk_egg', 'fish', 'meat'}, 'NUTRITION_CATALOG_INVALID')
    for r in value['recipes']:
        require(r['ingredients'] and set(r['slots']) <= set(SLOTS)
            and len({i['food_id'] for i in r['ingredients']}) == len(r['ingredients'])
            and all(i['food_id'] in foods and Decimal(i['quantity']) > 0 for i in r['ingredients']), 'NUTRITION_CATALOG_INVALID')
    value['content_hash'] = digest(value)
    return value


def catalog():
    return deepcopy(_catalog())


def eligible(recipe, preferences, bank=None):
    bank = bank or _catalog()
    foods = {f['id']: f for f in bank['foods']}
    items = [foods[i['food_id']] for i in recipe['ingredients']]
    allowed = {'omnivore': {'none', 'milk_egg', 'fish', 'meat'}, 'pescatarian': {'none', 'milk_egg', 'fish'},
        'vegetarian': {'none', 'milk_egg'}, 'vegan': {'none'}}[preferences['diet']]
    return recipe['prep_minutes'] <= preferences['max_prep_minutes'] and all(f['animal_source'] in allowed
        and f['id'] not in preferences['excluded_foods']
        and not set(f['allergens']) & set(preferences['excluded_allergens']) for f in items)


def make_plan(preferences, start_date, day_count=7, people=1):
    """Used by tests and equivalent local UI generation; nothing is persisted."""
    require(preferences['allergens_reviewed'], 'NUTRITION_ALLERGEN_REVIEW_REQUIRED')
    bank = _catalog()
    pools = {slot: [r for r in bank['recipes'] if slot in r['slots'] and eligible(r, preferences, bank)] for slot in SLOTS[:preferences['meals_per_day']]}
    require(all(pools.values()), 'NUTRITION_NO_MATCHING_RECIPE')
    meals = []
    for index in range(day_count):
        day = (date.fromisoformat(start_date) + timedelta(days=index)).isoformat()
        for slot, pool in pools.items():
            rank = index * 2 + (1 if slot == 'dinner' else 0) if slot in {'lunch', 'dinner'} else index
            meals.append({'date': day, 'slot': slot, 'recipe_id': pool[rank % len(pool)]['id'], 'portion_factor': '1'})
    return {'start_date': start_date, 'day_count': day_count, 'people': people, 'meals': meals}


def project(raw, bank=None):
    data = NutritionData.model_validate(raw).model_dump()
    bank = bank or _catalog()
    foods = {f['id']: f for f in bank['foods']}
    recipes = {r['id']: r for r in bank['recipes']}
    p, plan = data['preferences'], data['plan']
    require(set(p['excluded_foods']) <= foods.keys() and set(data['pantry']) <= foods.keys()
        and set(data['checked']) <= foods.keys(), 'NUTRITION_UNKNOWN_FOOD')
    if plan is None:
        require(not data['checked'], 'NUTRITION_CHECKED_ITEM_INVALID')
        return {'days': [], 'shopping': [], 'meal_count': 0}
    require(p['allergens_reviewed'], 'NUTRITION_ALLERGEN_REVIEW_REQUIRED')
    dates = [(date.fromisoformat(plan['start_date']) + timedelta(days=i)).isoformat() for i in range(plan['day_count'])]
    slots = SLOTS[:p['meals_per_day']]
    expected = {(d, s) for d in dates for s in slots}
    require(len(plan['meals']) == len(expected) and {(m['date'], m['slot']) for m in plan['meals']} == expected,
        'NUTRITION_MEAL_COVERAGE_INVALID')
    lookup = {(m['date'], m['slot']): m for m in plan['meals']}
    totals, days = {}, []
    for day in dates:
        meals = []
        for slot in slots:
            choice = lookup[(day, slot)]
            r = recipes.get(choice['recipe_id'])
            require(r is not None and slot in r['slots'] and eligible(r, p, bank), 'NUTRITION_RECIPE_NOT_ALLOWED')
            factor = Decimal(choice['portion_factor']) * plan['people']
            ingredients = []
            for i in r['ingredients']:
                f = foods[i['food_id']]
                amount = Decimal(i['quantity']) * factor
                totals[f['id']] = totals.get(f['id'], Decimal(0)) + amount
                ingredients.append({'food_id': f['id'], 'quantity': quantity(amount)})
            meals.append({**choice, 'ingredients': ingredients})
        days.append({'date': day, 'meals': meals})
    shopping = []
    for f in bank['foods']:
        if f['id'] not in totals:
            continue
        required = totals[f['id']]
        stock = Decimal(data['pantry'].get(f['id'], '0'))
        buy = max(Decimal(0), required - stock)
        if f['unit'] == 'db':
            buy = buy.to_integral_value(rounding=ROUND_CEILING)
        shopping.append({'food_id': f['id'], 'required': quantity(required), 'in_stock': quantity(stock),
            'to_buy': quantity(buy), 'checked': f['id'] in data['checked']})
    require(set(data['checked']) <= {r['food_id'] for r in shopping if Decimal(r['to_buy']) > 0}, 'NUTRITION_CHECKED_ITEM_INVALID')
    return {'days': days, 'shopping': shopping, 'meal_count': len(plan['meals'])}
