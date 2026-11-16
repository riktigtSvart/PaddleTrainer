"""Owned automatic planning applies the existing bounded policy, never forged human review."""
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.api.routes import automatic_planning as api
from app.models.entities import PlannedWorkout
from app.schemas.athlete_setup import ProfileInput
from app.services import automatic_planning as service
from app.services import training_plans
from tests.planning.test_p2_4c18_4_training_plan import planner, count
from tests.planning.test_p2_4c5r2_athlete_setup import profile
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER_EMAIL

URL = '/api/v1/planning/automation'


@pytest.fixture
def automatic(planner):
    planner.app.include_router(api.router, prefix='/api/v1')
    return planner


def read(env):
    response = env.client.get(URL)
    assert response.status_code == 200, response.text
    return response.json()


def setting(env, token=21001, enabled=True, previous=None):
    return {'request_id': str(UUID(int=token)), 'previous_reference': previous,
            'program_reference': {'artifact_id': env.program['artifact_id'], 'content_hash': env.program['content_hash']},
            'enabled': enabled, 'onboarding_completed': True}


def save(env, value, expected=201):
    response = env.client.post(URL, json=value)
    assert response.status_code == expected, response.text
    return response.json()


def run(env):
    response = env.client.post(URL+'/run', json={})
    assert response.status_code == 200, response.text
    return response.json()


def ref(value):
    return {key: value[key] for key in ['artifact_id', 'content_hash']}


def test_reads_and_disabled_mode_do_not_create_workouts(automatic):
    before = count(automatic, PlannedWorkout)
    assert read(automatic)['policy'] is None
    assert run(automatic)['run'] is None
    assert count(automatic, PlannedWorkout) == before


def test_exact_setting_retry_and_cas_keep_the_original_receipt(automatic):
    p = setting(automatic)
    saved = save(automatic, p)
    assert save(automatic, p, 200)['artifact'] == saved['artifact']
    assert read(automatic)['policy'] == saved['artifact']
    changed = deepcopy(p); changed['enabled'] = False
    assert save(automatic, changed, 409)['detail']['code'] == 'AUTOMATIC_PLANNING_REQUEST_CONFLICT'
    assert save(automatic, setting(automatic, 21002), 409)['detail']['code'] == 'AUTOMATIC_PLANNING_REVISION_CONFLICT'


def test_enabled_mode_applies_supported_workouts_without_a_false_human_review_claim(automatic):
    saved = save(automatic, setting(automatic))['artifact']
    result = run(automatic)
    actual = result['run']
    assert actual['state'] == 'applied' and actual['created_count'] > 0
    assert actual['policy_reference'] == ref(saved)
    assert result['context']['last_run'] == actual
    status = automatic.client.get(automatic.plan_url).json()
    accepted = status['acceptance']
    assert accepted['authority_scope'] == 'user_enabled_automatic_application_sample_plan'
    assert accepted['automatic_policy_reference'] == ref(saved)
    assert 'acknowledge_reviewed_plan' not in accepted['proposal']
    assert not accepted['personal_model_applied'] and not accepted['provider_writeback']
    with Session(automatic.engine) as db:
        for key in accepted['created_workouts']:
            row = db.get(PlannedWorkout, UUID(key))
            assert row.date.isoformat() <= actual['end_date'] and row.duration_sec > 0
    before = count(automatic, PlannedWorkout)
    run(automatic); run(automatic)
    assert count(automatic, PlannedWorkout) == before


def test_disabling_prevents_later_application_and_preserves_existing_plans(automatic):
    saved = save(automatic, setting(automatic))['artifact']
    run(automatic)
    before = count(automatic, PlannedWorkout)
    disabled = save(automatic, setting(automatic, 21002, False, ref(saved)))['artifact']
    assert run(automatic)['run'] is None
    assert not read(automatic)['policy']['proposal']['enabled']
    assert disabled['authority_scope'] == 'disabled'
    assert count(automatic, PlannedWorkout) == before


def test_revocation_between_review_and_commit_is_checked_under_the_owner_lock(automatic, monkeypatch):
    saved = save(automatic, setting(automatic))['artifact']
    original = training_plans.accept
    async def revoke(**kwargs):
        await service.save(session=kwargs['session'], owner=kwargs['owner'], proposal=setting(automatic, 21002, False, ref(saved)))
        return await original(**kwargs)
    monkeypatch.setattr(training_plans, 'accept', revoke)
    before = count(automatic, PlannedWorkout)
    result = run(automatic)['run']
    assert result['state'] == 'blocked' and result['blockers'] == ['AUTOMATIC_PLANNING_AUTHORITY_CHANGED']
    assert count(automatic, PlannedWorkout) == before


def test_unknown_profile_data_remains_a_blocker(automatic):
    from tests.planning.test_p2_4c5r2_athlete_setup import post
    p = profile(token=21009)
    p['previous_reference'] = ref(automatic.profile)
    p['data']['birth_date'] = None
    post(automatic, 'profiles', p)
    before = count(automatic, PlannedWorkout)
    save(automatic, setting(automatic))
    result = run(automatic)['run']
    assert result['state'] == 'blocked' and result['blockers']
    assert result['created_count'] == 0 and count(automatic, PlannedWorkout) == before


@pytest.mark.parametrize('field,value', [('enabled', 1), ('onboarding_completed', 1), ('athlete_id', 'foreign'), ('provider_writeback', True)])
def test_closed_setting_rejects_coercion_owner_injection_and_provider_authority(automatic, field, value):
    p = setting(automatic); p[field] = value
    assert automatic.client.post(URL, json=p).status_code == 422


def test_queries_and_foreign_programs_are_rejected(automatic):
    assert automatic.client.get(URL+'?athlete_id=foreign').status_code == 422
    assert automatic.client.post(URL+'/run', json={'enabled': True}).status_code == 422
    p = setting(automatic); p['program_reference']['artifact_id'] = 'pt-cycle:'+'a'*64
    assert automatic.client.post(URL, json=p).status_code == 404
    save(automatic, setting(automatic))
    automatic.email = OTHER_EMAIL
    assert read(automatic)['policy'] is None


def test_sparse_profile_extensions_preserve_older_bytes_and_record_explicit_levels():
    old = ProfileInput.model_validate(profile()).model_dump(mode='json')
    assert 'body_mass_kg' not in old['data'] and all('role' not in row for row in old['data']['sport_history'])
    proposal = deepcopy(old)
    proposal['data'].update(body_mass_kg='72.500', height_cm='178.0', body_measurements_recorded_on='2026-10-23')
    proposal['data']['sport_history'][0].update(role='primary', current_level='recreational')
    restored = ProfileInput.model_validate(proposal).model_dump(mode='json')
    assert restored == proposal


def test_goal_end_stops_automatic_planning_without_creating_later_workouts(automatic):
    from datetime import UTC, datetime
    from tests.planning.test_p2_4c5_cycle_creation import proposal, post as create
    automatic.program = create(automatic, '/programs', proposal('race', token=211950))['artifact']
    save(automatic, setting(automatic))
    automatic.clock.current = datetime(2031, 1, 1, tzinfo=UTC)
    before = count(automatic, PlannedWorkout)
    result = run(automatic)['run']
    assert result['state'] == 'completed' and result['start_date'] is None and result['end_date'] is None
    assert count(automatic, PlannedWorkout) == before


def test_monitor_can_resume_saved_automatic_authority_after_a_fresh_session(automatic, monkeypatch):
    import asyncio
    import builtins
    from contextlib import asynccontextmanager
    from app.services import training_plan_monitor
    from types import SimpleNamespace
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

    monkeypatch.setattr(training_plan_monitor, "get_settings", lambda: SimpleNamespace(demo_user_email=automatic.email))
    saved = save(automatic, setting(automatic))['artifact']
    opened = []

    @asynccontextmanager
    async def session_factory():
        # A fresh real DB session per tick, using the project's existing test
        # adapter instead of an optional, undeclared SQLite async driver.
        with Session(automatic.engine, expire_on_commit=False) as db:
            bridge = AsyncSQLiteBridge(db)
            opened.append(bridge)
            yield bridge

    original_import = builtins.__import__

    def without_optional_driver(name, *args, **kwargs):
        if name.split('.')[0] == 'aiosqlite':
            raise ModuleNotFoundError("aiosqlite is intentionally unavailable in this test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', without_optional_driver)
    asyncio.run(training_plan_monitor.run_once(session_factory))
    first = read(automatic)['last_run']
    assert first['state'] == 'applied' and first['created_count'] > 0
    assert first['policy_reference'] == ref(saved)
    before = count(automatic, PlannedWorkout)

    asyncio.run(training_plan_monitor.run_once(session_factory))
    assert read(automatic)['last_run']['state'] in ['applied', 'current']
    assert len(opened) == 2 and opened[0].session is not opened[1].session
    assert all(not bridge.in_transaction() for bridge in opened)
    assert count(automatic, PlannedWorkout) == before


@pytest.mark.parametrize('changes', [dict(body_mass_kg='0'), dict(height_cm='-2'), dict(body_mass_kg='72', body_measurements_recorded_on=None)])
def test_invalid_direct_body_measurements_are_rejected(changes):
    from pydantic import ValidationError
    value = profile(); value['data'].update(changes)
    with pytest.raises(ValidationError):
        ProfileInput.model_validate(value)


def test_extended_profile_is_saved_with_exact_levels_and_future_date_is_rejected(automatic):
    from tests.planning.test_p2_4c5r2_athlete_setup import post
    value = profile(token=211900); value['previous_reference'] = ref(automatic.profile)
    value['data'].update(body_mass_kg='72.500', height_cm='178.0', body_measurements_recorded_on='2026-10-23')
    value['data']['sport_history'][0].update(role='secondary', current_level='beginner')
    saved = post(automatic, 'profiles', value)
    assert saved['artifact']['proposal']['data']['body_mass_kg'] == '72.500'
    assert saved['artifact']['proposal']['data']['sport_history'][0]['current_level'] == 'beginner'
    value['request_id'] = str(UUID(int=211901)); value['previous_reference'] = ref(saved['artifact'])
    value['data']['body_measurements_recorded_on'] = '2099-01-01'
    response = automatic.client.post('/api/v1/planning/athlete/profiles', json=value)
    assert response.status_code == 409 and response.json()['detail']['code'] == 'ATHLETE_OBSERVATION_IN_FUTURE'
