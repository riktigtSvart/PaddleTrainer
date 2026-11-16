"""Geographic persistence, astronomical windows and real plan/move enforcement."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.planning.domain import daylight
from app.planning.domain.athlete_setup import digest
from app.schemas.training_options import Coordinates, DaylightRule, OptionsInput
from app.services import training_options
from tests.planning.test_p2_4c19_training_options import opportunities, body, save, context, BASE, WATER
from tests.planning.test_p2_4c18_4_training_plan import review, accept
from tests.planning.test_p2_4c20_5_assessed_strength import planner as assessed, request as initial_request, strength_candidates
from tests.planning.test_p2_4c20_4_initial_assessment import context as intake_context, save as save_initial

POINT = {"latitude": "47.5", "longitude": "19.04", "timezone_name": "Europe/Budapest"}
RULE = {"sport": "KAYAK", "mode": "daylight", "start_buffer_minutes": 0, "end_buffer_minutes": 0}


def at(s): return datetime.fromisoformat(s)


def declared(token=219001, previous=None, start="21:00", end="23:00", rule=True):
    p = body(token, previous)
    p['data']['locations'][0]['coordinates'] = deepcopy(POINT)
    p['data']['weekly_slots'][0]['details'].update(start_time=start, end_time=end, location_ids=[WATER])
    if rule: p['data']['daylight_rules'] = [deepcopy(RULE)]
    return p


def test_legacy_shape_does_not_gain_nulls_or_change_its_hash():
    old = body()
    assert OptionsInput.model_validate(old).model_dump(mode='json') == old
    assert 'coordinates' not in old['data']['locations'][0] and 'daylight_rules' not in old['data']


@pytest.mark.parametrize('lat,lon', [('0','0'), ('-90','180'), ('90','-180'), ('-33.8688','151.2093')])
def test_coordinate_zero_and_negative_values_are_explicit(lat, lon):
    assert Coordinates.model_validate({**POINT, 'latitude': lat, 'longitude': lon}).latitude == lat


@pytest.mark.parametrize('changes', [{'latitude': True}, {'latitude': 0}, {'latitude': ''}, {'longitude': '180.00001'}, {'latitude': '-90.1'}, {'latitude': 'NaN'}, {'latitude': '1e1'}, {'latitude': '47,5'}, {'longitude':'019.04'}, {'timezone_name':'Europe/Unknown'}, {'latitude': '1.12345678'}])
def test_bad_coordinate_is_never_guessed(changes):
    with pytest.raises(ValidationError): Coordinates.model_validate({**POINT, **changes})


@pytest.mark.parametrize('changes', [{'mode':'future'}, {'start_buffer_minutes':True}, {'end_buffer_minutes':121}, {'start_buffer_minutes':-1}, {'mode':'none','end_buffer_minutes':1}])
def test_bad_light_rule_rejected(changes):
    with pytest.raises(ValidationError): DaylightRule.model_validate({**RULE, **changes})


def test_unique_sport_rules_and_only_supported_venue_overrides():
    p = declared(); p['data']['daylight_rules'] *= 2
    with pytest.raises(ValidationError): OptionsInput.model_validate(p)
    p = declared();p['data']['locations'][0]['daylight_overrides'] = [{**RULE, 'sport':'RUNNING'}]
    with pytest.raises(ValidationError): OptionsInput.model_validate(p)


def test_published_nrel_spa_reference_is_consistent_with_simpler_geometric_model():
    # Reda & Andreas, NREL/TP-560-34302, Appendix A example: geometric
    # topocentric elevation 39.872046 degrees; no refraction in our altitude.
    t = at('2003-10-17T19:30:30+00:00').timestamp()
    assert abs(daylight.altitude(t, 39.742476, -105.1786) - 39.872046) < .02


def test_crossings_order_thresholds_and_conservative_rounding():
    p = daylight.day_preview('2026-11-12', POINT)
    dawn, rise, setting, dusk = [at(p[m][k][0]) for m,k in [('civil_twilight','rises_at'),('daylight','rises_at'),('daylight','sets_at'),('civil_twilight','sets_at')]]
    assert dawn < rise < setting < dusk
    assert abs(daylight.altitude(rise.timestamp(), 47.5, 19.04) + .833) < .003
    assert abs(daylight.altitude(dawn.timestamp(), 47.5, 19.04) + 6) < .003
    allowed = p['daylight']['intervals'][0]
    assert at(allowed['start_at']) >= rise and at(allowed['end_at']) <= setting
    assert 8 < (setting-rise).total_seconds()/3600 < 10


@pytest.mark.parametrize('day,hours', [('2026-03-29',23),('2026-10-25',25),('2028-02-29',24)])
def test_local_day_respects_dst_and_leap_dates(day, hours):
    p = daylight.day_preview(day, POINT)
    assert (at(p['day_end_at'])-at(p['day_start_at'])).total_seconds() == hours*3600
    for mode in daylight.THRESHOLDS:
        assert all(at(p['day_start_at']) <= at(t) < at(p['day_end_at']) for k in ('rises_at','sets_at') for t in p[mode][k])


@pytest.mark.parametrize('lat,day,state', [('78.2','2026-06-21','all_day'),('78.2','2026-12-21','no_light'),('-78.2','2026-06-21','no_light'),('-78.2','2026-12-21','all_day')])
def test_polar_day_and_night_have_no_fabricated_sunrise(lat, day, state):
    p = daylight.day_preview(day, {**POINT,'latitude':lat, 'longitude':'15.6','timezone_name':'Arctic/Longyearbyen'})
    assert p['daylight']['state'] == state
    assert p['daylight']['rises_at'] == p['daylight']['sets_at'] == []


@pytest.mark.parametrize('lon,zone', [('179.99','Pacific/Auckland'),('-179.99','Pacific/Pago_Pago'),('0','UTC')])
def test_date_line_and_equator_are_utc_continuous(lon,zone):
    p = daylight.day_preview('2026-03-20', {**POINT,'latitude':'0','longitude':lon,'timezone_name':zone})
    assert p['daylight']['state'] == 'crossings'
    assert sum((at(v['end_at'])-at(v['start_at'])).total_seconds() for v in p['daylight']['intervals']) > 11*3600


def test_whole_workout_and_buffers_crossing_midnight():
    p = declared()['data']; start, end = at('2026-11-12T14:00:00+00:00'), at('2026-11-12T15:00:00+00:00')
    assert daylight.permits(p,WATER,'KAYAK',start,end)
    assert not daylight.permits(p,WATER,'KAYAK',start,end+timedelta(minutes=20))
    p['daylight_rules'][0]['end_buffer_minutes'] = 20
    assert not daylight.permits(p,WATER,'KAYAK',start,end)
    assert daylight.permits(p,WATER,'STRENGTH',start,end+timedelta(hours=8))
    assert not daylight.permits(p,WATER,'KAYAK',at('2026-11-12T22:00:00+00:00'),at('2026-11-13T08:00:00+00:00'))


def test_unknown_location_fails_only_for_restricted_sport_and_override_is_local():
    p = declared()['data']; a,b = at('2026-11-12T20:00:00+00:00'),at('2026-11-12T21:00:00+00:00')
    assert not daylight.permits(p,None,'KAYAK',a,b)
    assert daylight.permits(p,None,'STRENGTH',a,b)
    p['locations'][0]['daylight_overrides'] = [{**RULE,'mode':'none'}]
    assert daylight.permits(p,WATER,'KAYAK',a,b)
    assert not daylight.permits(p,p['locations'][1]['id'],'KAYAK',a,b)


def test_real_http_persists_point_rules_and_preview_without_writes(opportunities):
    e=opportunities;proposal=declared(); receipt=save(e,proposal)
    assert save(e,proposal,200)['artifact'] == receipt['artifact']
    c=context(e);assert c['data']==proposal['data']
    request={'date':'2026-11-12','coordinates':POINT}
    response=e.client.post(BASE+'/daylight/preview',json=request)
    assert response.status_code==200,response.text
    p=response.json();assert p['request']==request and p['request_hash']==digest(request)
    assert p['result']==daylight.day_preview(request['date'],POINT)
    assert response.headers['Cache-Control']=='no-store'
    assert context(e)['reference']==training_options.reference(receipt['artifact'])
    assert e.client.get(BASE+'/daylight/preview').status_code==405
    assert e.client.post(BASE+'/daylight/preview?evil=1',json=request).status_code==422
    assert e.client.post(BASE+'/daylight/preview',json={**request,'coordinates':{**POINT,'latitude':False}}).status_code==422
    result=review(e)
    assert result['result']['proposals']==[]
    assert any('DAYLIGHT_NO_ALLOWED_INTERVAL' in i['codes'] for i in result['result']['preparation']['selection_issues'])
    assert result['inputs']['daylight_context']['options_receipt']['artifact']==receipt['artifact']
    if os.getenv('C21_9_EXPORT'):
        Path(os.environ['C21_9_EXPORT']).write_text(json.dumps({'preview':p,'receipt':receipt,'context':c,'night_review':result}),encoding='utf-8')


def test_sunrise_clips_start_and_full_duration_and_daylight_can_be_overridden(opportunities):
    e=opportunities;p=declared(start='05:00',end='18:00');p['data']['daylight_rules'][0].update(start_buffer_minutes=15,end_buffer_minutes=30)
    one=save(e,p);result=review(e)
    assert result['result']['proposals']
    for c in result['result']['proposals']:
        assert daylight.permits(p['data'],c.get('location_id'),c['sport'],at(c['start_at']),at(c['end_at']))
        assert at(c['start_at']).hour >= 5
    if os.getenv('C21_9_EXPORT'):
        path=Path(os.environ['C21_9_EXPORT']);value=json.loads(path.read_text());value['day_review']=result
        value['solar_cases']=[{'date':d,'coordinates':point,'result':training_options.preview_daylight(result['athlete_id'],{'date':d,'coordinates':point})} for d,point in [
            ('2026-03-29',POINT),('2026-10-25',POINT),('2028-02-29',POINT),
            ('2026-06-21',{**POINT,'latitude':'78.2','longitude':'15.6','timezone_name':'Arctic/Longyearbyen'}),
            ('2026-12-21',{**POINT,'latitude':'78.2','longitude':'15.6','timezone_name':'Arctic/Longyearbyen'}),
            ('2026-03-20',{'latitude':'0','longitude':'-179.99','timezone_name':'Pacific/Pago_Pago'}),
            ('2026-03-20',{'latitude':'0','longitude':'179.99','timezone_name':'Pacific/Auckland'})]]
        path.write_text(json.dumps(value),encoding='utf-8')
    p=declared(219002,training_options.reference(one['artifact']));p['data']['locations'][0]['daylight_overrides']=[{**RULE,'mode':'none'}]
    save(e,p)
    assert review(e)['result']['proposals']


def test_changed_rule_rejects_stale_acceptance_and_replaces_owned_night_plans(opportunities):
    e=opportunities;one=save(e,declared(rule=False));old=review(e)
    assert old['result']['create']
    accept(e,old)
    p=declared(219002,training_options.reference(one['artifact']));save(e,p)
    accept(e,old,token=219003,expected=409)
    fresh=review(e)
    assert fresh['result']['cancel'] and not fresh['result']['proposals']


def test_coordinates_and_light_only_edits_preserve_saved_assessment_and_strength(assessed):
    e=assessed;saved=save_initial(e,initial_request(e));before=intake_context(e)
    p=deepcopy(e.options['artifact']['proposal']);p.update(request_id=str(UUID(int=219010)), previous_reference=training_options.reference(e.options['artifact']))
    p['data']['locations'][0]['coordinates']=deepcopy(POINT)
    p['data']['daylight_rules']=[deepcopy(RULE)]
    updated=save(e,p);after=intake_context(e)
    assert after['sources']['source_hash']==before['sources']['source_hash']
    assert after['saved']['artifact']==saved['artifact']
    assert strength_candidates(review(e))
    p['request_id']=str(UUID(int=219011));p['previous_reference']=training_options.reference(updated['artifact']);p['data']['locations'][0]['resources'].append('Tornaszőnyeg')
    save(e,p)
    assert intake_context(e)['sources']['source_hash']!=before['sources']['source_hash']


def test_manual_move_cannot_bypass_light_and_rule_edit_invalidates_move_preview(opportunities):
    from app.api.routes import planning_calendar
    e=opportunities;e.app.include_router(planning_calendar.router,prefix='/api/v1')
    one=save(e,declared(start='08:00',end='10:00'));planned=review(e);accept(e,planned)
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models.entities import PlannedWorkout
    with Session(e.engine) as db:
        identity=str(db.scalars(select(PlannedWorkout.id).where(PlannedWorkout.user_id==UUID(planned['athlete_id']))).first())
    base='/api/v1/planning/calendar/moves';r=e.client.get(base+'/'+identity)
    assert r.status_code==200,r.text
    c=r.json();p={'request_id':str(UUID(int=219020)),'plan_id':identity,'expected_source_hash':c['source_hash'],
        'previous_reference':c['previous_reference'],'timezone_name':c['timezone_name'],'date':c['current']['date'],'start_time':'21:00','start_fold':None}
    denied=e.client.post(base+'/preview',json=p)
    assert denied.status_code==409,denied.text
    assert denied.json()['detail']['code']=='CALENDAR_MOVE_DAYLIGHT_EXCLUDED'
    p['start_time']='09:00';r=e.client.post(base+'/preview',json=p)
    assert r.status_code==200,r.text
    viewed=r.json();assert viewed['daylight_reference']==training_options.reference(one['artifact'])
    changed=declared(219021,training_options.reference(one['artifact']),start='08:00',end='10:00');changed['data']['daylight_rules'][0]['end_buffer_minutes']=1
    save(e,changed)
    r=e.client.post(base,json={'proposal':p,'review_hash':viewed['review_hash']})
    assert r.status_code==409,r.text
    assert r.json()['detail']['code']=='CALENDAR_MOVE_REVIEW_CHANGED'
    fresh=e.client.post(base+'/preview',json=p);assert fresh.status_code==200,fresh.text
    r=e.client.post(base,json={'proposal':p,'review_hash':fresh.json()['review_hash']})
    assert r.status_code==201,r.text
