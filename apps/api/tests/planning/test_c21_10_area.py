"""Whole-region light, owner-bound persistence and alternate venues."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.planning.domain import area_daylight, daylight
from app.schemas.training_options import GeographicArea, OptionsInput
from app.services import training_options
from tests.planning.test_p2_4c19_training_options import opportunities, body, save, context, BASE, WATER
from tests.planning.test_p2_4c18_4_training_plan import review, accept

AREA = {"schema_version": "training-area-v0.1", "south": "45.8", "north": "47.9",
        "west": "17.4", "east": "19.4", "timezone_name": "Europe/Budapest"}
RULE = {"sport": "KAYAK", "mode": "daylight", "start_buffer_minutes": 15, "end_buffer_minutes": 20}


def export(name, value):
    if os.getenv('C21_10_EXPORT'):
        path = Path(os.environ['C21_10_EXPORT'])
        current = json.loads(path.read_text()) if path.exists() else {}
        current[name] = value
        path.write_text(json.dumps(current), encoding='utf-8')


@pytest.mark.parametrize('change', [{"south": True}, {"south": 45.8}, {"south": "48"}, {"west": "20"},
    {"east": "180.1"}, {"north": "91"}, {"west": "-179", "east": "179"},
    {"south": "-10", "north": "11"}, {"timezone_name": "Missing/Zone"}])
def test_invalid_or_ambiguous_region_is_not_guessed(change):
    with pytest.raises(ValidationError):
        GeographicArea.model_validate({**AREA, **change})


def test_region_and_point_cannot_be_combined_or_assigned_to_a_fixed_site():
    p = body(); p['data']['locations'][0].update(kind='fixed', area=AREA)
    with pytest.raises(ValidationError): OptionsInput.model_validate(p)
    p['data']['locations'][0].update(kind='mobile', coordinates={"latitude": "47", "longitude": "18", "timezone_name": "UTC"})
    with pytest.raises(ValidationError): OptionsInput.model_validate(p)


@pytest.mark.parametrize('when,area', [
    ('2026-11-12T05:35:00+00:00', AREA), ('2026-11-12T15:50:00+00:00', AREA),
    ('2026-06-21T23:30:00+00:00', {**AREA, 'south': '-10', 'north': '10', 'west': '-2', 'east': '2'}),
    ('2026-12-21T23:50:00+00:00', {**AREA, 'south': '65', 'north': '85', 'west': '-2', 'east': '2'}),
    ('1950-03-21T00:00:00+00:00', {**AREA, 'south': '-10', 'north': '10', 'west': '-10', 'east': '10'}),
])
def test_analytic_minimum_encloses_interior_not_only_corners(when, area):
    instant = datetime.fromisoformat(when).timestamp()
    bounds = [float(area[k]) for k in ['south', 'north', 'west', 'east']]
    minimum = area_daylight.minimum_altitude(instant, *bounds)
    south, north, west, east = bounds
    samples = [daylight.altitude(instant, south+(north-south)*i/30, west+(east-west)*j/30)
               for i in range(31) for j in range(31)]
    assert minimum <= min(samples)+1e-9
    # A 31x31 grid can miss the exact anti-solar point between samples.
    assert min(samples)-minimum < .5
    export('minimum_'+when, {'at': instant, 'area': area, 'minimum': minimum})


def test_accepted_minutes_are_lit_across_the_rectangle_and_buffers_are_not_reapplied():
    first, last = [datetime.fromisoformat(x) for x in ['2026-11-12T00:00:00+00:00', '2026-11-13T00:00:00+00:00']]
    intervals = area_daylight.area_intervals(first, last, AREA, RULE)
    assert len(intervals) == 1
    a, b = intervals[0]
    for lat in [45.8, 46.85, 47.9]:
        for lon in [17.4, 18.4, 19.4]:
            for instant in [a-timedelta(minutes=15), a, b, b+timedelta(minutes=20)]:
                assert daylight.altitude(instant.timestamp(), lat, lon) >= -.833
    midday = first+timedelta(hours=11)
    assert area_daylight.area_intervals(midday, last, AREA, RULE) == [(midday, b)]


@pytest.mark.parametrize('day,hours', [('2026-03-29', 23), ('2026-10-25', 25), ('2028-02-29', 24)])
def test_region_preview_respects_local_days(day, hours):
    preview = area_daylight.day_preview(day, AREA)
    assert (datetime.fromisoformat(preview['day_end_at'])-datetime.fromisoformat(preview['day_start_at'])).total_seconds() == hours*3600
    export('area_day_'+day, {'date': day, 'area': AREA, 'result': preview})


def test_polar_regions_do_not_invent_a_sunrise():
    area = {**AREA, 'south': '78', 'north': '80', 'west': '14', 'east': '16', 'timezone_name': 'Arctic/Longyearbyen'}
    assert area_daylight.day_preview('2026-06-21', area)['daylight']['state'] == 'all_day'
    assert area_daylight.day_preview('2026-12-21', area)['daylight']['state'] == 'no_light'


def test_real_owner_can_save_region_preview_and_choose_another_valid_site(opportunities):
    e = opportunities
    p = body()
    p['data']['locations'][0].update(kind='mobile', area=deepcopy(AREA))
    alternate = deepcopy(p['data']['locations'][0]); alternate['id'] = str(UUID(int=211001))
    alternate.update(name='Másik vízre szállás', kind='fixed', coordinates={"latitude": "47.5", "longitude": "19", "timezone_name": "Europe/Budapest"})
    alternate.pop('area')
    # First venue has no light at this time; the second explicitly permits it.
    alternate['daylight_overrides'] = [{**RULE, 'mode': 'none', 'start_buffer_minutes': 0, 'end_buffer_minutes': 0}]
    p['data']['locations'].append(alternate); p['data']['daylight_rules'] = [RULE]
    p['data']['weekly_slots'][0]['details'].update(location_ids=[WATER, alternate['id']], start_time='21:00', end_time='23:00')
    receipt = save(e, p)
    assert context(e)['data']['locations'][0]['area'] == AREA
    preview = e.client.post(BASE+'/daylight/preview', json={'date': '2026-11-12', 'area': AREA})
    assert preview.status_code == 200, preview.text
    assert preview.json()['result'] == area_daylight.day_preview('2026-11-12', AREA)
    assert e.client.post(BASE+'/daylight/preview', json={'date': '2026-11-12', 'area': AREA, 'coordinates': alternate['coordinates']}).status_code == 422
    value = review(e)
    assert value['result']['proposals']
    assert {c['location_id'] for c in value['result']['proposals']} == {alternate['id']}
    assert all(c['duration_sec'] <= 1800 for c in value['result']['proposals'])
    export('area_preview', preview.json()); export('area_options', receipt); export('area_review', value)
    accept(e, value)
    repeat = review(e); assert not repeat['result']['create'] and not repeat['result']['cancel']
