"""Daily nutrition estimates join owned training and immutable meal portions."""
from datetime import UTC, date, datetime
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.api.routes import athlete_setup
from app.db.base import Base
from app.models.entities import PlannedWorkout, ProviderDataRecord, Sport, WorkoutSession, WorkoutStatus
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition_journal import JournalData
from app.services import nutrition_domain as menus
from app.services.nutrition_requirements import composition, recipe_values
from tests.planning.test_c21_12_nutrition_journal import body, entry, env, environment, get, menu, post  # noqa: F401
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, OTHER_EMAIL, count
from tests.planning.test_p2_4c5r2_athlete_setup import post as save_profile, profile


@pytest.fixture
def nutrition(env):
    Base.metadata.create_all(env.engine, tables=[
        PlannedWorkout.__table__, WorkoutSession.__table__, ProviderDataRecord.__table__,
    ])
    env.app.include_router(athlete_setup.router, prefix='/api/v1')
    return env


def read(env, start='2026-11-15', end='2026-11-19', status=200):
    return get(env, f'/requirements?start_date={start}&end_date={end}', status)


def test_training_correction_and_saved_menu_use_same_owned_day(nutrition):
    p = profile()
    p['data'].update(birth_date='1986-01-01', sex_reference='male', height_cm='180',
        body_mass_kg='80', body_measurements_recorded_on='2026-11-13')
    save_profile(nutrition, 'profiles', p)
    menu(nutrition)
    with Session(nutrition.engine) as db:
        row = PlannedWorkout(id=UUID(int=151), user_id=UUID(ATHLETE),
            date=date(2026, 11, 17), sport=Sport.STRENGTH, title='Erősítés',
            duration_sec=3600, status=WorkoutStatus.SCHEDULED)
        db.add(row)
        db.flush()
        db.add(WorkoutSession(user_id=UUID(ATHLETE), planned_workout_id=row.id,
            sport=Sport.STRENGTH, external_id='strength-actual',
            started_at=datetime(2026, 11, 17, 10, tzinfo=UTC), duration_sec=1800))
        for owner, day, sport, duration, status in [
            (ATHLETE, 15, Sport.RUNNING, 5400, WorkoutStatus.PLANNED),
            (ATHLETE, 18, Sport.RUNNING, 3600, WorkoutStatus.PLANNED),
            (ATHLETE, 18, Sport.CYCLING, 1800, WorkoutStatus.CANCELLED),
            (ATHLETE, 19, Sport.OTHER, 1800, WorkoutStatus.PLANNED),
            (OTHER, 18, Sport.RUNNING, 7200, WorkoutStatus.PLANNED),
        ]:
            db.add(PlannedWorkout(user_id=UUID(owner), date=date(2026, 11, day),
                sport=sport, title='Edzés', duration_sec=duration, status=status))
        db.commit()
    before = count(nutrition, PlanningAuditArtifactRow)
    data = read(nutrition)
    past, _, today, future, incomplete = data['days']
    assert data['athlete_id'] == ATHLETE and data['read_only']
    assert past['maintenance_kcal'] == ['2618', '2618']
    assert today['workouts']['recorded'] == 1 and today['workouts']['planned'] == 0
    assert today['workouts']['extra_kcal'] == ['105', '210']
    assert today['references']['protein']['minimum'] == '128'
    assert future['workouts']['planned'] == 1 and future['workouts']['recorded'] == 0
    assert future['maintenance_kcal'] == ['3080', '3290']
    assert future['references']['carbohydrate']['minimum'] == '400'
    assert incomplete['workouts']['unestimated'] == 1 and incomplete['maintenance_kcal'] is None
    assert today['planned']['entries'] == 4 and today['logged']['entries'] == 0
    assert today['logged']['amounts']['energy']['amount'] is None
    assert count(nutrition, PlanningAuditArtifactRow) == before
    assert count(nutrition, PlannedWorkout) == 6 and count(nutrition, WorkoutSession) == 1
    if os.getenv('C21_15_EXPORT'):
        Path(os.environ['C21_15_EXPORT']).write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode(), mtime=0))
    nutrition.email = OTHER_EMAIL
    other = read(nutrition)['days'][2]
    assert other['planned']['entries'] == 0 and other['logged']['entries'] == 0 and other['baseline_kcal'] is None


def test_actual_fraction_unknown_food_and_expired_assessment(nutrition):
    source = menu(nutrition)
    report = entry(source)
    data = JournalData().model_dump()
    data['entries'] = [report, {
        **report, 'id': str(UUID(int=152)), 'recipe_id': None, 'source': None,
        'title': 'Saját étel', 'unit': 'g', 'amount': '120',
    }]
    target = {
        'id': str(UUID(int=153)), 'nutrient': 'protein', 'minimum': '100.125', 'maximum': '120',
        'unit': 'g', 'scope': 'total_intake', 'source_name': 'Szintetikus szakmai lelet',
        'assessed_on': '2026-11-13', 'valid_until': '2026-11-15', 'observation_ids': [], 'note': '',
    }
    data['targets'] = [target]
    journal_before = post(nutrition, body(data))['artifact']
    first, second = read(nutrition)['days'][:2]
    assert first['baseline_kcal'] is None
    assert first['references']['calcium']['minimum'] == '950'
    assert first['references']['protein']['minimum'] == '100.125'
    assert first['references']['protein']['scope'] == 'total_intake'
    assert 'protein' not in second['references']
    assert first['logged']['entries'] == 2 and first['logged']['unquantified'] == 1
    nutrient = first['logged']['amounts']['energy']
    base_recipe = next(r for r in menus.catalog()['recipes'] if r['id'] == report['recipe_id'])
    foods = composition()['foods']
    base_kcal = sum(Decimal(i['quantity']) * Decimal(foods[i['food_id']]['grams_per_unit'])
        * Decimal(foods[i['food_id']]['per_100g']['energy']) / 100 for i in base_recipe['ingredients'])
    assert abs(Decimal(nutrient['amount']) - Decimal('0.75') * base_kcal) <= Decimal('0.5')
    assert nutrient['partial']
    assert get(nutrition)['saved'] == journal_before


def test_overnight_load_keeps_elapsed_minutes_over_dst(nutrition):
    with Session(nutrition.engine) as db:
        db.add(WorkoutSession(user_id=UUID(ATHLETE), sport=Sport.KAYAK, external_id='midnight',
            started_at=datetime(2026, 10, 24, 21, 30, tzinfo=UTC), duration_sec=18000))
        db.commit()
    first, second = read(nutrition, '2026-10-24', '2026-10-25')['days']
    assert first['workouts']['seconds'] == 1800
    assert second['workouts']['seconds'] == 16200


def test_composition_covers_catalog_and_preserves_real_zeros():
    bank = menus.catalog()
    assert set(composition()['foods']) == {f['id'] for f in bank['foods']}
    assert all('energy' in present and totals['energy'] > 0 for totals, present, _ in recipe_values(bank['recipes']).values())
    assert composition()['foods']['milk']['grams_per_unit'] == '1.03'
    assert composition()['foods']['eggs']['grams_per_unit'] == '50'
    assert composition()['foods']['fish']['code'] == '16-356'
    assert 'iodine' not in composition()['foods']['millet']['per_100g']


def test_owner_range_and_method_are_closed(nutrition):
    assert read(nutrition, '2026-11-01', '2026-11-18', 409)['detail']['code'] == 'NUTRITION_REQUIREMENTS_RANGE_INVALID'
    base = '/api/v1/planning/nutrition/requirements'
    assert nutrition.client.get(base).status_code == 422
    assert nutrition.client.get(base + '?start_date=2026-11-15&end_date=2026-11-16&owner=other').status_code == 422
    assert nutrition.client.post(base, json={}).status_code == 405
