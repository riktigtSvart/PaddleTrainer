"""Machine types and bench-pull equipment stay explicit and location-owned."""
from copy import deepcopy

import pytest

from app.models.entities import PlannedWorkout
from app.services import strength_catalog as catalog
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c19_training_options import HOME, WATER, body, context, save
from tests.planning.test_p2_4c20_3_strength_catalog import opportunities as opportunities_fixture


@pytest.fixture
def opportunities(tmp_path, monkeypatch):
    yield from opportunities_fixture.__wrapped__(tmp_path, monkeypatch)


@pytest.mark.parametrize('resources,expected', [
    (['Mellhezhúzó pad'], False),
    (['Vízszintes edzőpad', 'Súlyzórúd', 'Súlytárcsák', 'Tárcsarögzítők'], False),
    (['Mellhez lehúzó gép', 'Súlyzórúd', 'Súlytárcsák', 'Tárcsarögzítők'], False),
    (['Mellhezhúzó pad', 'Súlyzórúd', 'Súlytárcsák', 'Tárcsarögzítők'], True),
])
def test_bench_pull_is_not_a_flat_bench_or_a_pulldown_machine(resources, expected):
    assert ('seal_row_barbell' in catalog.exercise_ids(resources)) is expected
    assert catalog.equipment_ids(['Mellhez húzó pad']) == ['seal_row_bench']


@pytest.mark.parametrize('resources,expected', [
    (['Evezőgép (tárcsasúlyos)'], False),
    (['Súlytárcsák'], False),
    (['Ülő evezőgép', 'Súlytárcsák'], False),
    (['Evezőgép (tárcsasúlyos)', 'Súlytárcsák'], True),
])
def test_plate_loaded_station_needs_its_own_declaration_and_plates(resources, expected):
    assert ('plate_loaded_row' in catalog.exercise_ids(resources)) is expected


def test_new_machine_and_bench_resources_do_not_borrow_across_locations(opportunities):
    request = body(token=203111)
    request['data']['locations'][0].update(sports=['STRENGTH'], resources=[
        'Mellhezhúzó pad', 'Súlyzórúd', 'Súlytárcsák', 'Tárcsarögzítők',
    ])
    request['data']['locations'][2].update(sports=['STRENGTH'], resources=['Evezőgép (tárcsasúlyos)'])
    before = count(opportunities, PlannedWorkout)
    receipt = save(opportunities, request)
    assert save(opportunities, request, 200)['artifact'] == receipt['artifact']
    options = {item['location_id']: item for item in context(opportunities)['strength_options']}
    assert 'seal_row_barbell' in options[WATER]['exercise_ids']
    assert 'plate_loaded_row' not in options[HOME]['exercise_ids']
    assert options[HOME]['exercise_ids'] == []
    assert options[WATER]['planning_authorized'] is False
    assert count(opportunities, PlannedWorkout) == before


def test_extended_inventory_roundtrips_with_legacy_custom_names(opportunities):
    request = body(token=203112)
    inventory = [item['resource'] for item in catalog.catalog()['equipment']]
    resources = [*inventory, 'Saját húzógép, külön fogantyúval']
    request['data']['locations'][0].update(sports=['STRENGTH'], resources=resources)
    original = deepcopy(request)
    receipt = save(opportunities, request)
    assert receipt['artifact']['proposal'] == original
    result = context(opportunities)
    assert result['data']['locations'][0]['resources'] == resources
    assert set(result['strength_options'][0]['exercise_ids']) == {e['id'] for e in result['strength_catalog']['exercises']}
    assert len(result['strength_options'][0]['equipment_ids']) == len(inventory)
    assert request == original
