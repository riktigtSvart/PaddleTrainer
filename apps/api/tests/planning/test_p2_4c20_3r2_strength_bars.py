"""Explicit wall bars and pull-up frames, with source-preserving legacy bars."""
import pytest

from app.models.entities import PlannedWorkout
from app.services import strength_catalog as catalog
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c19_training_options import HOME, WATER, body, context, save
from tests.planning.test_p2_4c20_3_strength_catalog import opportunities as opportunities_fixture


@pytest.fixture
def opportunities(tmp_path, monkeypatch):
    yield from opportunities_fixture.__wrapped__(tmp_path, monkeypatch)


@pytest.mark.parametrize('resource,expected', [
    ('Húzódzkodó rúd', True), ('Nyújtó', True), ('Húzódzkodó keret', True),
    ('Erőkeret / guggolókeret', False), ('Bordásfal', False), ('Vízszintes edzőpad', False),
])
def test_only_declared_pullup_capability_supports_both_pullup_exercises(resource, expected):
    exercises = catalog.exercise_ids([resource])
    assert ('pullup' in exercises) is expected
    assert ('scapular_pullup' in exercises) is expected


@pytest.mark.parametrize('resource', ['Bordásfal', 'Húzódzkodó rúd', 'Nyújtó'])
def test_hanging_knee_and_leg_raises_have_three_explicit_equipment_alternatives(resource):
    exercises = catalog.exercise_ids([resource])
    assert 'hanging_knee_raise' in exercises and 'hanging_leg_raise' in exercises


def test_wall_bar_support_needs_a_floor_without_invented_attachments():
    assert 'wall_bars_supported_squat' not in catalog.exercise_ids(['Bordásfal'])
    assert 'wall_bars_supported_squat' in catalog.exercise_ids(['Bordásfal', 'Szabad padlófelület'])
    assert catalog.equipment_ids(['Bordásfal']) == ['wall_bars']
    assert catalog.equipment_ids(['Húzódzkodó rúd']) == ['pullup_bar']
    assert catalog.exercise_ids([]) == []


def test_both_declarations_roundtrip_locally_without_rewriting_names_or_workouts(opportunities):
    request = body(token=203121)
    request['data']['locations'][0].update(sports=['STRENGTH'], resources=[
        'Nyújtó / húzódzkodó keret', 'Saját fogantyú, régi névvel',
    ])
    request['data']['locations'][2].update(sports=['STRENGTH'], resources=['Bordásfal', 'Szabad padlófelület'])
    before = count(opportunities, PlannedWorkout)
    receipt = save(opportunities, request)
    assert save(opportunities, request, 200)['artifact'] == receipt['artifact']
    assert receipt['artifact']['proposal'] == request
    result = context(opportunities)
    options = {item['location_id']: item for item in result['strength_options']}
    assert options[WATER]['equipment_ids'] == ['pullup_frame']
    assert 'pullup' in options[WATER]['exercise_ids']
    assert 'pullup' not in options[HOME]['exercise_ids']
    assert 'hanging_leg_raise' in options[HOME]['exercise_ids']
    assert 'wall_bars_supported_squat' in options[HOME]['exercise_ids']
    assert result['data']['locations'][0]['resources'] == request['data']['locations'][0]['resources']
    assert all(item['planning_authorized'] is False for item in options.values())
    assert count(opportunities, PlannedWorkout) == before
