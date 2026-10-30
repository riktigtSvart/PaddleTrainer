"""GPS projection, source preservation and owned HTTP on isolated fixtures."""
from copy import deepcopy
from uuid import UUID
from sqlalchemy.orm import Session
import pytest
from app.models.entities import WorkoutSession
from app.services.session_route_projection import project_routes
from app.services.polar_session_details import merge_details, FEATURES, LAP_FEATURES
from tests.planning.test_p2_4c6_calendar_workspace import agenda, ACTUAL


def raw():
    return {"exerciseSamples": [{"identifier": {"id": "e1"}, "startTime": "2026-10-26T06:00:00+01:00", "routes": {"route": {
        "startTime": "2026-10-26T05:00:02Z", "wayPoints": [
            {"elapsedMillis": 0, "latitude": 0, "longitude": 0},
            {"elapsedMillis": 1000, "latitude": 47.1, "longitude": 19.1},
            {"elapsedMillis": 2000, "latitude": True, "longitude": 19.2},
            {"elapsedMillis": 3000, "latitude": 47.3, "longitude": 19.3},
        ]}}, "samples": {"samples": [{"type": "HEART_RATE", "intervalMillis": 1000, "values": [100, 101, None, 103]}]}}]}


def test_owned_http_exposes_bounded_gps_and_keeps_native_source(agenda):
    source = raw()
    with Session(agenda.engine) as db:
        db.get(WorkoutSession, UUID(ACTUAL)).raw_data = source
        db.commit()
    response = agenda.client.get('/api/v1/planning/calendar/sessions/' + ACTUAL)
    assert response.status_code == 200
    data = response.json()
    points = data['samples']['routes'][0]['points']
    assert [p['index'] for p in points] == [0, 1, 2, 3]
    assert [p['ms'] for p in points] == [2000, 3000, 4000, 5000]
    assert points[0]['lat'] == points[0]['lon'] == 0
    assert points[2]['lat'] is None and points[2]['lon'] is None
    assert data['samples']['routes'][0]['issues'] == ['ROUTE_COORDINATE_MISSING']
    assert data['planning_authorized'] is data['workouts_changed'] is False
    changed=deepcopy(source);changed['exerciseSamples'][0]['routes']['route']['wayPoints'][0]['latitude']=1
    with Session(agenda.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).raw_data=changed;db.commit()
    enriched=agenda.client.get('/api/v1/planning/calendar/sessions/'+ACTUAL).json()
    assert enriched['samples']['content_hash']==data['samples']['content_hash']
    assert enriched['samples']['route_content_hash']!=data['samples']['route_content_hash']
    with Session(agenda.engine) as db:
        db.get(WorkoutSession,UUID(ACTUAL)).raw_data=source;db.commit()

    with Session(agenda.engine) as db:
        assert db.get(WorkoutSession, UUID(ACTUAL)).raw_data == source


@pytest.mark.parametrize('mutate', [
    lambda x: x['exerciseSamples'][0]['routes']['route'].pop('startTime'),
    lambda x: x['exerciseSamples'][0].pop('startTime'),
    lambda x: x['exerciseSamples'][0].update(startTime='2026-10-26T06:00:00'),
])
def test_unknown_or_mixed_timezone_route_clock_is_never_rebuilt_from_order(mutate):
    source = raw(); mutate(source)
    route = project_routes(source, 'POLAR')[0]
    assert all(p['ms'] is None for p in route['points'])
    assert route['points'][1]['lat'] == 47.1
    assert 'ROUTE_CLOCK_UNKNOWN_OR_NONMONOTONIC' in route['issues']


def test_nonmonotonic_and_boolean_elapsed_keep_slots_without_invented_times():
    source=raw(); points=source['exerciseSamples'][0]['routes']['route']['wayPoints']
    points[1]['elapsedMillis']=True;points[2]['elapsedMillis']=0
    assert [p['ms'] for p in project_routes(source,'POLAR')[0]['points']] == [2000,None,None,5000]


@pytest.mark.parametrize('lat,lon', [(91,19),(47,181),(float('inf'),19),(47,float('nan')),('47',19)])
def test_invalid_coordinates_remain_missing(lat,lon):
    source=raw();source['exerciseSamples'][0]['routes']['route']['wayPoints'][0].update(latitude=lat,longitude=lon)
    assert project_routes(source,'POLAR')[0]['points'][0]['lat'] is None


def test_route_enrichment_preserves_native_routes_by_explicit_exercise_identity():
    stored={'identifier':{'id':'session'},'exercises':[{'identifier':{'id':'e1'},'routes':{'route':{'kept':'native'}}}]}
    incoming={'identifier':{'id':'session'},'exercises':[{'identifier':{'id':'e1'},'samples':{'samples':[]}}]}
    original=deepcopy(stored)
    merged=merge_details(stored,incoming,'session')
    assert merged['exercises']==stored['exercises'] and stored==original
    assert merged['exerciseSamples'][0]['routes']==stored['exercises'][0]['routes']
    assert FEATURES==[*LAP_FEATURES,'routes']


def test_projection_limits_and_other_provider_remain_honest(monkeypatch):
    import app.services.session_route_projection as module
    monkeypatch.setattr(module,'MAX_POINTS',2)
    assert project_routes(raw(),'POLAR')[0]['issues']==['ROUTE_TOO_LARGE']
    assert project_routes(raw(),'GARMIN')==[]
    assert project_routes(None,'POLAR')==[]
