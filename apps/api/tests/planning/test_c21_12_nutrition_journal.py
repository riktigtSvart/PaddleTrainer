"""Owned HTTP journal: actual meals, personal portions, historical source and DST."""
from copy import deepcopy
from datetime import datetime, UTC
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
from app.schemas.nutrition_journal import JournalData
from app.services import nutrition_domain as menus
from tests.planning.test_p2_4c3_goal_workflow_api import environment, count, OTHER_EMAIL

BASE = '/api/v1/planning/nutrition'


@pytest.fixture
def env(environment, monkeypatch):
    from app.models.entities import PlannedWorkout
    PlannedWorkout.__table__.create(environment.engine, checkfirst=True)
    environment.app.include_router(route.router, prefix='/api/v1')
    environment.clock.current = datetime(2026, 11, 17, 12, tzinfo=UTC)
    monkeypatch.setattr(intake, '_now', environment.clock.tick)
    return environment


def post(env, body, path='/journal', status=201):
    r = env.client.post(BASE + path, json=body)
    assert r.status_code == status, r.text
    assert r.headers['Cache-Control'] == 'no-store'
    return r.json()


def get(env, path='/journal', status=200):
    r = env.client.get(BASE + path)
    assert r.status_code == status, r.text
    return r.json()


def menu(env):
    p = {'diet': 'omnivore', 'allergens_reviewed': True, 'excluded_allergens': [], 'excluded_foods': [], 'max_prep_minutes': 45, 'meals_per_day': 4}
    plan = menus.make_plan(p, '2026-11-15', 3, 8)
    plan['meals'][0]['portion_factor'] = '1.5'
    return post(env, {'request_id': str(UUID(int=21120001)), 'previous_reference': None, 'catalog_hash': menus.catalog()['content_hash'], 'data': {'preferences': p, 'plan': plan, 'pantry': {}, 'checked': []}}, '')['artifact']


def entry(saved, index=0, ident=21120100):
    m = saved['proposal']['data']['plan']['meals'][index]
    r = next(r for r in menus.catalog()['recipes'] if r['id'] == m['recipe_id'])
    return {'id': str(UUID(int=ident)), 'date': m['date'], 'time': '07:45:30', 'timezone': 'Europe/Budapest', 'fold': None, 'status': 'eaten', 'title': r['title'], 'amount': '0.5', 'unit': 'portion', 'recipe_id': r['id'], 'source': {'reference': {'artifact_id': saved['artifact_id'], 'content_hash': saved['content_hash']}, 'date': m['date'], 'slot': m['slot']}, 'note': '', 'satisfaction': 4}


def body(data=None, previous=None, token=21120200):
    return {'request_id': str(UUID(int=token)), 'previous_reference': previous, 'data': data or JournalData().model_dump()}


def test_real_owned_log_independent_personal_dose_and_exact_recovery(env):
    initial = get(env); source = menu(env)
    data = JournalData().model_dump(); data['entries'] = [entry(source)]
    data['default_times']['breakfast'] = '07:30:15'
    b = body(data); saved = post(env, b)
    assert saved['artifact']['result']['entries'][0]['recipe_portions'] == '0.75'  # never x 8 people
    assert saved['artifact']['result']['entries'][0]['instant'] == '2026-11-15T06:45:30+00:00'
    assert saved['artifact']['result']['nutrient_totals'] is None
    assert saved['artifact']['result']['nutrient_adequacy'] == 'not_evaluated'
    assert get(env, '')['saved'] == source
    current = get(env)
    assert current['saved'] == saved['artifact'] and current['sources'] == [source]
    before = count(env, PlanningAuditArtifactRow)
    assert post(env, b, status=200)['reused']
    assert count(env, PlanningAuditArtifactRow) == before
    d = deepcopy(data); d['entries'][0]['amount'] = '0.75'
    second_body = body(d, current['reference'], 21120201)
    second = post(env, second_body)
    assert post(env, b, status=200)['artifact'] == saved['artifact']
    assert get(env)['saved'] == second['artifact']
    if os.getenv('C21_12_EXPORT'):
        Path(os.environ['C21_12_EXPORT']).write_bytes(gzip.compress(json.dumps({'initial': initial, 'catalog': menus.catalog(), 'menu': source, 'body': b, 'receipt': saved, 'current': current, 'second_body': second_body, 'second_receipt': second}, ensure_ascii=False).encode(), mtime=0))


def test_menu_swap_does_not_rewrite_previous_actual_intake(env):
    source = menu(env); d = JournalData().model_dump(); d['entries'] = [entry(source)]
    post(env, body(d)); before = get(env)
    p = deepcopy(source['proposal']); p['request_id'] = str(UUID(int=21120202)); p['previous_reference'] = get(env, '')['reference']; p['data']['plan']['meals'][0]['portion_factor'] = '2'
    post(env, p, '')
    after = get(env)
    assert after['saved'] == before['saved'] and after['sources'] == before['sources']


def test_free_food_and_lab_have_exact_units_and_do_not_invent_an_intake_target(env):
    d = JournalData().model_dump()
    d['entries'] = [{'id': str(UUID(int=21120300)), 'date': '2026-11-16', 'time': '18:12:03', 'timezone': 'Europe/Budapest', 'fold': None, 'status': 'eaten', 'title': 'Saját étel és ital', 'amount': '250.125', 'unit': 'ml', 'recipe_id': None, 'source': None, 'note': 'Nem tervezett', 'satisfaction': None}]
    d['observations'] = [{'id': str(UUID(int=21120301)), 'analyte': 'Szintetikus laborérték', 'value': '12.350', 'qualifier': 'less_than', 'unit': 'µg/l', 'sampled_on': '2026-11-15', 'source_name': 'Tesztlabor', 'reference_low': '10', 'reference_high': '100', 'interpretation': 'Külön szakmai értékelés szükséges', 'note': ''}]
    d['muscle_goal'] = 'gain'; d['performance_goal'] = 'strength'
    a = post(env, body(d))['artifact']
    assert a['proposal']['data'] == d
    assert a['result']['assessment_mode'] == 'general_guidance'
    assert a['lab_based_dose_generated'] is False and a['personal_energy_prescribed'] is False
    assert a['result']['nutrient_totals'] is None


def test_professional_target_is_separate_from_a_lab_result_and_retains_its_basis(env):
    d = JournalData().model_dump()
    d['targets'] = [{'id': str(UUID(int=21120310)), 'nutrient': 'protein', 'minimum': '100.125', 'maximum': '120', 'unit': 'g', 'scope': 'total_intake', 'source_name': 'Szintetikus dietetikusi javaslat', 'assessed_on': '2026-11-01', 'valid_until': '2026-11-10', 'observation_ids': [], 'note': 'A lejárt cél is megőrzött előzmény.'}]
    a = post(env, body(d))['artifact']
    assert a['proposal']['data']['targets'] == d['targets']
    assert a['result']['assessment_mode'] == 'general_guidance'  # expired, retained for history
    assert a['result']['nutrient_adequacy'] == 'not_evaluated'


@pytest.mark.parametrize('change', [
    lambda d: d['default_times'].update(breakfast='7:30'),
    lambda d: d['default_times'].update(breakfast='24:00:00'),
    lambda d: d.update(personal_energy_kcal=2000),
    lambda d: d.update(performance_goal='invented'),
    lambda d: d['entries'][0].update(amount=True),
    lambda d: d['entries'][0].update(satisfaction=True),
    lambda d: d['entries'][0].update(fold=True),
    lambda d: d['entries'].append(deepcopy(d['entries'][0])),
    lambda d: d['entries'][0].update(status='skipped'),
    lambda d: d['entries'][0].update(unit='mg'),
])
def test_strict_shapes_reject_before_any_journal_write(env, change):
    source = menu(env); d = JournalData().model_dump(); d['entries'] = [entry(source)]; change(d)
    before = count(env, PlanningAuditArtifactRow)
    post(env, body(d), status=422)
    assert count(env, PlanningAuditArtifactRow) == before


@pytest.mark.parametrize('change', [
    lambda e: e.update(date='2026-11-18'),
    lambda e: e.update(time='23:59:59', date='2026-11-17'),
    lambda e: e.update(timezone='America/New_York'),
    lambda e: e['source']['reference'].update(content_hash='f'*64),
    lambda e: e.update(recipe_id='chicken_rice'),
    lambda e: e.update(title='Másik recept'),
])
def test_semantic_rejections_never_log_an_invented_past_meal(env, change):
    source = menu(env); d = JournalData().model_dump(); d['entries'] = [entry(source)]; change(d['entries'][0])
    before = count(env, PlanningAuditArtifactRow)
    post(env, body(d), status=409)
    assert count(env, PlanningAuditArtifactRow) == before


def test_dst_gap_rejected_and_two_autumn_occurrences_remain_distinct(env):
    source = menu(env); d = JournalData().model_dump(); e = entry(source)
    e.update(date='2026-03-29', time='02:30:00'); d['entries'] = [e]
    assert post(env, body(d), status=409)['detail']['code'] == 'NUTRITION_JOURNAL_DST_GAP'
    e.update(date='2026-10-25')
    assert post(env, body(d), status=409)['detail']['code'] == 'NUTRITION_JOURNAL_DST_FOLD_REQUIRED'
    e['fold'] = 0
    first = post(env, body(d)); ref = get(env)['reference']
    e['fold'] = 1
    second = post(env, body(d, ref, 21120400))
    a = datetime.fromisoformat(first['artifact']['result']['entries'][0]['instant'])
    b = datetime.fromisoformat(second['artifact']['result']['entries'][0]['instant'])
    assert (b-a).total_seconds() == 3600


def test_skips_are_explicit_and_do_not_count_as_observed_food_or_learning(env):
    source = menu(env); d = JournalData().model_dump(); e = entry(source); e.update(status='skipped', time=None, amount='0', satisfaction=None); d['entries'] = [e]
    r = post(env, body(d))['artifact']['result']
    assert r['skipped_count'] == 1 and r['eaten_count'] == 0 and r['favourites'] == [] and r['suggested_times'] == {}


def test_time_learning_requires_three_actual_observations_and_never_changes_defaults(env):
    source = menu(env); d = JournalData().model_dump(); d['entries'] = [entry(source, index=i*4, ident=21120500+i) for i in range(3)]
    d['entries'][2]['date'] = '2026-11-16'  # report a past actual occurrence explicitly
    for e, time in zip(d['entries'], ['07:15:00', '08:15:00', '07:45:00']): e['time'] = time
    a = post(env, body(d))['artifact']
    assert a['result']['suggested_times'] == {'breakfast': '07:45:00'}
    assert a['proposal']['data']['default_times']['breakfast'] is None


def test_owner_and_stale_revision_are_enforced_without_global_history(env):
    source = menu(env); d = JournalData().model_dump(); d['entries'] = [entry(source)]
    b = body(d); a = post(env, b)
    assert post(env, body(d, token=21120600), status=409)['detail']['code'] == 'NUTRITION_JOURNAL_REVISION_CHANGED'
    changed = deepcopy(b); changed['data']['entries'][0]['amount'] = '1'
    assert post(env, changed, status=409)['detail']['code'] == 'NUTRITION_JOURNAL_REQUEST_CONFLICT'
    env.email = OTHER_EMAIL
    assert get(env)['saved'] is None
    post(env, body(d), status=409)  # cannot use another owner's menu source
    assert get(env)['saved'] is None
    assert a['artifact']['athlete_id'] != get(env)['athlete_id']


def test_rehashed_stored_result_cannot_claim_more_consumption(env):
    source = menu(env); d = JournalData().model_dump(); d['entries'] = [entry(source)]
    a = post(env, body(d))['artifact']; a['result']['entries'][0]['recipe_portions'] = '8'
    a['content_hash'] = digest({k: v for k, v in a.items() if k != 'content_hash'})
    with env.engine.begin() as db:
        db.execute(update(PlanningAuditArtifactRow).where(PlanningAuditArtifactRow.artifact_id == a['artifact_id']).values(contract_json=json.dumps(a, ensure_ascii=False), content_hash=a['content_hash']))
    get(env, status=409)


def test_closed_queries_and_methods(env):
    assert env.client.get(BASE + '/journal?owner=someone').status_code == 422
    assert env.client.post(BASE + '/journal?x=y', json=body()).status_code == 422
    assert env.client.delete(BASE + '/journal').status_code == 405
