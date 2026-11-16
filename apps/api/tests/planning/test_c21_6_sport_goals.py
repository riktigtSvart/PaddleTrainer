"""Owned, immutable goal edits and role-specific sport history, with real HTTP persistence."""
from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, TrainingPeriod
from app.planning.domain.cycle_program import reference
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.athlete_setup import SportHistory
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c5_cycle_creation import get, post, proposal, mesocycles
from tests.planning.test_p2_4c5r2_athlete_setup import intake as intake_fixture, profile


@pytest.fixture
def environment(tmp_path, monkeypatch):
    fixture = intake_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(fixture)
    try:
        yield env
    finally:
        fixture.close()


def result():
    return dict(result_id=str(UUID(int=216001)), kind='personal_best', distance_m='500.000',
        time='1:42.500', recorded_on=None, year=2001, conditions='K1, állóvíz', source='self_report')


def start(env):
    body = profile(216002)
    sport = body['data']['sport_history'][0]
    sport.update(role='primary', performances=[result()])
    secondary = deepcopy(sport)
    secondary.update(sport='Futás', discipline='', role='secondary', level='unknown', performances=[],
        planning=dict(version='sport-planning-context-v0.1', supported_sports=['Kajak'],
            purposes=['aerobic_substitution', 'general_conditioning'], proficiency='independent'))
    body['data']['sport_history'].append(secondary)
    response = env.client.post('/api/v1/planning/athlete/profiles', json=body)
    assert response.status_code == 201, response.text
    athlete = response.json()
    p = proposal(token=216003)
    p['athlete_context'] = dict(profile_reference=reference(athlete['artifact']), availability_reference=None)
    saved = post(env, '/programs', p)
    return athlete, saved


def replacement(saved, token=216004):
    artifact = saved['artifact']
    p = deepcopy(artifact['proposal'])
    p.update(program_id=str(UUID(int=token)), title='Módosított saját felkészülés')
    p['replacement'] = dict(version='cycle-program-replacement-v0.1', revision=artifact['proposal'].get('replacement', {}).get('revision', 0) + 1,
        program_reference=reference(artifact), competition_reference=reference(artifact), boundary_reference=None)
    return p


def test_goal_dates_and_targets_save_as_owned_version_without_rewriting_history(environment):
    env = environment
    athlete, old = start(env)
    p = replacement(old)
    p['start_date'] = '2030-01-03'
    p['macrocycles'][0].update(start_date='2030-01-03', end_date='2030-04-01', mesocycles=mesocycles('2030-01-03', '2030-04-01'))
    p['goals'] = [dict(key='strength', target_description='Erő fejlesztése')]
    before = count(env, TrainingPeriod)
    viewed = post(env, '/preview', p, 200)
    assert count(env, TrainingPeriod) == before
    saved = post(env, '/programs', p)
    assert saved['artifact']['proposal'] == p
    assert saved['artifact']['program_family_id'] == old['artifact']['program_family_id']
    assert saved['artifact']['artifact_id'] != old['artifact']['artifact_id']
    assert saved['artifact']['periods'] == viewed['periods']
    assert count(env, TrainingPeriod) == before + len(saved['artifact']['periods'])
    assert post(env, '/programs', p, 200)['artifact'] == saved['artifact']
    detail = get(env, '/programs/' + saved['artifact']['artifact_id'])
    assert detail['program']['artifact'] == saved['artifact']
    assert get(env, '/programs/' + old['artifact']['artifact_id'])['program']['artifact'] == old['artifact']
    assert get(env, '/programs')['items'][0]['artifact'] == saved['artifact']
    response = env.client.get('/api/v1/planning/athlete/context').json()
    assert response['profile']['artifact'] == athlete['artifact']
    with Session(env.engine) as session:
        old_rows = session.scalars(select(TrainingPeriod).where(TrainingPeriod.id.in_([UUID(v['id']) for v in old['artifact']['periods']]))).all()
        expected = {v['id']: v for v in old['artifact']['periods']}
        assert all(v.start_date.isoformat() == expected[str(v.id)]['start_date'] and v.end_date.isoformat() == expected[str(v.id)]['end_date'] for v in old_rows)


def test_latest_competition_snapshot_is_required_for_goal_replacement(environment):
    _, old = start(environment)
    revision = dict(program_reference=reference(old['artifact']), revision=1, previous_reference=None, competitions=[], rationale='Versenyadatok áttekintve')
    changed = post(environment, '/competition-revisions', revision)
    p = replacement(old)
    before = count(environment, TrainingPeriod), count(environment, PlanningAuditArtifactRow)
    response = post(environment, '/programs', p, 409)
    assert response['detail']['code'] == 'CYCLE_REPLACEMENT_SOURCE_CHANGED'
    assert (count(environment, TrainingPeriod), count(environment, PlanningAuditArtifactRow)) == before
    p['replacement']['competition_reference'] = reference(changed['artifact'])
    saved = post(environment, '/programs', p)
    assert get(environment, '/programs/' + saved['artifact']['artifact_id'])['program']['artifact'] == saved['artifact']
    assert post(environment, '/competition-revisions', revision, 200)['reused']
    revision.update(revision=2, previous_reference=reference(changed['artifact']))
    assert post(environment, '/competition-revisions', revision, 409)['detail']['code'] == 'CYCLE_PROGRAM_SUPERSEDED'


def test_two_different_replacements_cannot_claim_the_same_parent(environment):
    _, old = start(environment)
    first = replacement(old)
    saved = post(environment, '/programs', first)
    before = count(environment, PlanningAuditArtifactRow), count(environment, TrainingPeriod)
    second = replacement(old, token=216005)
    second['title'] = 'Másik párhuzamos szerkesztés'
    assert post(environment, '/programs', second, 409)['detail']['code'] == 'CYCLE_REQUEST_IDENTITY_CONFLICT'
    assert (count(environment, PlanningAuditArtifactRow), count(environment, TrainingPeriod)) == before
    assert post(environment, '/programs', first, 200)['artifact'] == saved['artifact']
    next_version = replacement(saved, token=216006)
    assert post(environment, '/programs', next_version)['artifact']['proposal']['replacement']['revision'] == 2
    assert get(environment, '/programs/' + saved['artifact']['artifact_id'])['program']['artifact'] == saved['artifact']


def test_latest_boundary_is_required_and_old_receipts_still_replay(environment):
    _, old = start(environment)
    periods = [v for v in old['artifact']['periods'] if v['period_type'] == 'MESOCYCLE']
    changed = post(environment, '/boundary-revisions', dict(program_reference=reference(old['artifact']), revision=1,
        previous_reference=None, competition_reference=reference(old['artifact']), left_period_id=periods[0]['id'],
        right_period_id=periods[1]['id'], new_end_date=(date.fromisoformat(periods[0]['end_date']) + timedelta(days=1)).isoformat(),
        reason='calendar', observations='A tervezett időkeret pontosítása', rationale='A közös határ módosítása', review_training_load=True))
    p = replacement(old)
    assert post(environment, '/programs', p, 409)['detail']['code'] == 'CYCLE_REPLACEMENT_SOURCE_CHANGED'
    p['replacement']['boundary_reference'] = reference(changed['artifact'])
    saved = post(environment, '/programs', p)
    old_detail = get(environment, '/programs/' + old['artifact']['artifact_id'])
    assert old_detail['boundary_revisions'][-1]['artifact'] == changed['artifact']
    assert old_detail['replaced_by'] == reference(saved['artifact'])
    assert get(environment, '/programs/' + saved['artifact']['artifact_id'])['replaced_by'] is None


def test_automatic_planning_waits_for_the_replacement_to_be_explicitly_selected(environment):
    from app.api.routes import automatic_planning as api
    env = environment
    env.app.include_router(api.router, prefix='/api/v1')
    _, old = start(env)
    settings = dict(request_id=str(UUID(int=216020)), previous_reference=None, program_reference=reference(old['artifact']),
        enabled=True, onboarding_completed=True)
    response = env.client.post('/api/v1/planning/automation', json=settings)
    assert response.status_code == 201, response.text
    policy = response.json()['artifact']
    post(env, '/programs', replacement(old))
    before = count(env, PlannedWorkout)
    response = env.client.post('/api/v1/planning/automation/run', json={})
    assert response.status_code == 200, response.text
    assert response.json()['run']['blockers'] == ['AUTOMATIC_PLANNING_PROGRAM_SUPERSEDED']
    assert count(env, PlannedWorkout) == before
    settings.update(request_id=str(UUID(int=216021)), previous_reference=reference(policy))
    response = env.client.post('/api/v1/planning/automation', json=settings)
    assert response.status_code == 409, response.text
    settings['enabled'] = False
    assert env.client.post('/api/v1/planning/automation', json=settings).status_code == 201


@pytest.mark.parametrize('damage', ['parent_hash', 'revision', 'date_order', 'mode', 'foreign_parent'])
def test_invalid_goal_edits_leave_no_partial_periods(environment, damage):
    _, old = start(environment)
    p = replacement(old)
    if damage == 'parent_hash': p['replacement']['program_reference']['content_hash'] = 'f' * 64
    if damage == 'revision': p['replacement']['revision'] = 2
    if damage == 'date_order': p['macrocycles'][0]['mesocycles'][0]['end_date'] = '2029-12-31'
    if damage == 'mode': p['mode'] = 'race'
    if damage == 'foreign_parent': p['replacement']['program_reference']['artifact_id'] = 'pt-cycle:' + 'f' * 64
    before = count(environment, PlanningAuditArtifactRow), count(environment, TrainingPeriod)
    response = environment.client.post('/api/v1/planning/cycles/programs', json=p)
    assert response.status_code in {404, 409, 422}, response.text
    assert (count(environment, PlanningAuditArtifactRow), count(environment, TrainingPeriod)) == before


def test_sport_history_preserves_exact_results_roles_and_legacy_shape(environment):
    athlete, _ = start(environment)
    data = athlete['artifact']['proposal']['data']['sport_history']
    assert data[0]['performances'] == [result()]
    assert data[1]['role'] == 'secondary'
    assert data[1]['planning']['purposes'] == ['aerobic_substitution', 'general_conditioning']
    assert 'planning' not in data[0]
    legacy = deepcopy(profile()['data']['sport_history'][0])
    dumped = SportHistory.model_validate(legacy).model_dump()
    assert dumped == legacy


@pytest.mark.parametrize('patch', [dict(time='1:60'), dict(time='0:00'), dict(distance_m='0'), dict(year=2100),
    dict(recorded_on='2100-01-01', year=None), dict(recorded_on='2001-01-01', year=2001)])
def test_invalid_or_future_sport_results_never_become_current_measurements(environment, patch):
    body = profile(216010)
    body['data']['sport_history'][0]['performances'] = [{**result(), **patch}]
    before = count(environment, PlanningAuditArtifactRow)
    response = environment.client.post('/api/v1/planning/athlete/profiles', json=body)
    assert response.status_code in {409, 422}, response.text
    assert count(environment, PlanningAuditArtifactRow) == before
