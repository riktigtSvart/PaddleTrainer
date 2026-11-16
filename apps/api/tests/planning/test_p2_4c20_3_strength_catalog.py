"""Location-owned equipment declarations, catalog relations and unchanged receipts."""
from copy import deepcopy
from uuid import UUID

import pytest

from app.models.entities import PlannedWorkout
from app.planning.domain.athlete_setup import digest
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import strength_catalog as library
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c18_4_training_plan import review
from tests.planning.test_p2_4c19_training_options import HOME, WATER, body, context, save
from tests.planning.test_p2_4c19_training_options import opportunities as opportunities_fixture


@pytest.fixture
def opportunities(tmp_path, monkeypatch):
    yield from opportunities_fixture.__wrapped__(tmp_path, monkeypatch)


def test_catalog_is_complete_and_hash_bound_without_mutable_shared_state():
    value = library.catalog()
    assert len(value['equipment']) >= 50 and len(value['exercises']) >= 75
    assert value['content_hash'] == digest({k:v for k,v in value.items() if k != 'content_hash'})
    assert value['planning_authorized'] is False and value['workouts_changed'] is False
    ids = [item['id'] for item in value['equipment']]
    assert len(ids) == len(set(ids))
    assert set(library.exercise_ids([e['resource'] for e in value['equipment']])) == {e['id'] for e in value['exercises']}
    assert library.equipment_ids([]) == library.exercise_ids([]) == []
    value['equipment'][0]['resource'] = 'edited'
    assert library.catalog()['equipment'][0]['resource'] != 'edited'


@pytest.mark.parametrize('resources,exercise,expected', [
    (['Kézisúlyzó'], 'goblet_squat', True), (['Kettlebell'], 'goblet_squat', True),
    (['Súlyzórúd'], 'barbell_row', False), (['Súlyzórúd','Súlytárcsák'], 'barbell_row', False),
    (['Súlyzórúd','Súlytárcsák','Tárcsarögzítők'], 'barbell_row', True),
    (['Állítható csigás állvány'], 'face_pull', False),
    (['Állítható csigás állvány','Kötélfogantyú'], 'face_pull', True),
    (['Gumiszalag'], 'pallof_press', False),
    (['Gumiszalag','Gumiszalag-rögzítési pont'], 'pallof_press', True),
])
def test_or_alternatives_and_all_required_accessories_are_distinct(resources, exercise, expected):
    assert (exercise in library.exercise_ids(resources)) == expected


def test_old_aliases_remain_recognizable_without_guessing_other_equipment():
    assert library.equipment_ids(['Dumbbell','Kézisúlyzók']) == ['dumbbells']
    assert library.equipment_ids(['Saját evezőgép', 'Multigép', 'Labda']) == []
    assert library.equipment_ids(['Kajakergométer']) == ['kayak_erg']
    assert library.equipment_ids(['RowErg']) == ['row_erg']


def test_read_context_adds_catalog_without_writes(opportunities):
    before = count(opportunities, PlanningAuditArtifactRow), count(opportunities, PlannedWorkout)
    value = context(opportunities)
    assert value['strength_catalog'] == library.catalog()
    assert value['strength_options'] == []
    assert before == (count(opportunities, PlanningAuditArtifactRow), count(opportunities, PlannedWorkout))


def test_equipment_and_exercises_are_scoped_to_each_location(opportunities):
    value = body()
    value['data']['locations'][0].update(sports=['STRENGTH'], resources=['Kézisúlyzó'])
    value['data']['locations'][2].update(sports=['STRENGTH'], resources=['Állítható csigás állvány','Kötélfogantyú'])
    save(opportunities, value)
    resolved = {v['location_id']:v for v in context(opportunities)['strength_options']}
    assert 'dumbbell_row' in resolved[WATER]['exercise_ids'] and 'face_pull' not in resolved[WATER]['exercise_ids']
    assert 'face_pull' in resolved[HOME]['exercise_ids'] and 'dumbbell_row' not in resolved[HOME]['exercise_ids']
    assert all(v['planning_authorized'] is False for v in resolved.values())


def test_whole_inventory_roundtrips_and_reaches_real_calendar_inputs(opportunities):
    value = body()
    resources = [e['resource'] for e in library.catalog()['equipment']]
    value['data']['locations'][0].update(sports=['KAYAK','STRENGTH'], resources=resources)
    before = count(opportunities, PlannedWorkout)
    first = save(opportunities, value)
    assert save(opportunities, value, 200)['artifact'] == first['artifact']
    assert first['artifact']['proposal'] == value
    assert context(opportunities)['data']['locations'][0]['resources'] == resources
    capture = review(opportunities)
    group = next(g for g in capture['inputs']['days'][0]['opportunities'] if g['constraints'].get('location_id') == WATER)
    assert group['constraints']['resources'] == resources and group['constraints']['resources_scope'] == 'location'
    # An equipment census alone is not an athlete's strength-training reference.
    assert not any(item.get('strength_prescription') for item in capture['result']['proposals'])
    assert all(item['template_version'] == 'v0.4' for item in capture['result']['proposals'] if item['sport'] == 'STRENGTH')
    assert count(opportunities, PlannedWorkout) == before


def test_custom_and_legacy_resource_bytes_are_preserved(opportunities):
    value = body()
    value['data']['locations'][0].update(sports=['STRENGTH'], resources=['Dumbbell','Saját gép: A-17','Tornaszőnyeg'])
    receipt = save(opportunities, value)
    assert receipt['artifact']['proposal'] == value
    resolved = context(opportunities)
    assert resolved['data']['locations'][0]['resources'] == value['data']['locations'][0]['resources']
    assert resolved['strength_options'][0]['equipment_ids'] == ['mat','dumbbells']


def test_archived_and_non_strength_places_do_not_gain_strength_options(opportunities):
    value = body()
    value['data']['locations'][0]['resources'] = ['Kézisúlyzó']
    value['data']['locations'][2].update(sports=['STRENGTH'], archived=True, resources=['Kézisúlyzó'])
    save(opportunities, value)
    assert context(opportunities)['strength_options'] == []


def test_resource_bound_is_128_and_rejection_does_not_partially_save(opportunities):
    value = body()
    value['data']['locations'][0]['resources'] = [f'Saját eszköz {i}' for i in range(128)]
    save(opportunities, value)
    changed = deepcopy(value)
    changed['request_id'] = str(UUID(int=203001))
    changed['data']['locations'][0]['resources'].append('129. eszköz')
    response = opportunities.client.post('/api/v1/planning/training-options', json=changed)
    assert response.status_code == 422
    assert len(context(opportunities)['data']['locations'][0]['resources']) == 128
