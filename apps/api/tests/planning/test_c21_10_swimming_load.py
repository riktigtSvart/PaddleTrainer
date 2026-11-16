"""Owned swimming, current weekly baselines and sport-aware allocation."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.entities import Sport
from app.schemas.training_options import OptionsInput, PrescriptionSettings
from app.services import training_starting_load as training_load, training_options
from tests.planning.test_c21_9_1_calendar_endurance import env, prepare, review
from tests.planning.test_c21_10_area import export, AREA
from tests.planning.test_p2_4c19_training_options import save, BASE, context as options_context
from tests.planning.test_p2_4c20_1_prescriptions import completed, historic_weeks, locations, planner
from tests.planning.test_p2_4c20_execution_reconciliation import sync_receipt
from tests.planning.test_p2_4c18_4_training_plan import accept, review as short_review
from tests.planning.test_p2_4c20_4_initial_assessment import context as assessment_context

SETTINGS = {'schema_version': 'training-prescription-settings-v0.1',
    'current_baseline': {'from_date': '2026-09-26', 'to_date': '2026-10-23', 'weekly_sessions': 6, 'weekly_minutes': 450},
    'swimming': {'reported_on': '2026-10-23', 'independent': True, 'strokes': ['freestyle', 'breaststroke', 'backstroke', 'butterfly'],
        'preferred_stroke': 'freestyle', 'continuous_distance_m': 1800, 'continuous_minutes': 30}}


def configure(e, *, settings=None, light=True, area=False):
    from tests.planning.test_p2_4c5r2_athlete_setup import profile, post
    personal = profile(token=211100, previous=e.profile)
    personal['data'].update(typical_days_per_week=6, typical_minutes_per_week=450)
    post(e, 'profiles', personal)
    saved = prepare(e, light=light, swimming=True)
    if area:
        # Transport is an explicit precondition, never inferred from an area.
        transport = deepcopy(saved['artifact']['proposal'])
        transport.update(request_id=str(UUID(int=211110)), previous_reference=training_options.reference(saved['artifact']))
        transport['data']['locations'][0]['boat_transport'] = True
        saved = save(e, transport)
        from tests.planning.test_p2_4c20_4_initial_assessment import save as save_initial
        from tests.planning.test_p2_4c20_5_assessed_strength import request
        save_initial(e, request(e, token=211111))
    p = deepcopy(saved['artifact']['proposal']); p.update(request_id=str(UUID(int=211101)), previous_reference=training_options.reference(saved['artifact']))
    p['data']['locations'][0]['pool_length_m'] = '33.333333'
    p['data']['prescription_settings'] = deepcopy(SETTINGS if settings is None else settings)
    if area:
        p['data']['locations'][0].pop('coordinates'); p['data']['locations'][0].update(kind='mobile', area=deepcopy(AREA))
    source = assessment_context(e)['sources']['source_hash']
    result = save(e, p)
    assert assessment_context(e)['sources']['source_hash'] == source
    return result


def swims(value):
    return [c for g in value['result']['alternatives'] for c in g['candidates'] if c['sport'] == 'SWIMMING']


def test_current_baseline_expands_only_the_shared_upper_envelope_and_builds_a_mixed_plan(env):
    configure(env, area=True)
    v = review(env); budget = v['result']['prescription_context']['starting_budget']
    export('mixed_review', v)
    assert budget['mode'] == 'declared_current_training'
    assert budget['max_sessions_per_7_days'] == 6 and budget['max_minutes_per_7_days'] == 450
    assert budget['historical_records_are_current_capacity'] is False
    assert {'RUNNING', 'SWIMMING', 'STRENGTH', 'KAYAK'} <= {c['sport'] for c in v['result']['proposals']}
    assert len(v['result']['proposals']) > 6
    for c in v['result']['proposals']:
        group = [r for r in v['result']['proposals'] if 0 <= (datetime.fromisoformat(r['date'])-datetime.fromisoformat(c['date'])).days <= 6]
        assert len(group) <= 6 and sum(r['duration_sec'] for r in group) <= 450*60
    export('mixed_review', v); export('mixed_options', options_context(env))
    accept(env, v)
    repeated = review(env)
    export('mixed_repeated', repeated)
    assert not repeated['result']['create'] and not repeated['result']['cancel']


def test_swimming_continuous_protocol_is_pool_specific_and_not_a_watch_peak_pace(env):
    configure(env)
    completed(env, 211102, Sport.SWIMMING, minutes=38, day='2026-10-21')
    v = review(env); candidates = swims(v); assert candidates
    for c in candidates:
        m = v['result']['prescription_context']['by_candidate'][c['candidate_key']]
        assert m['swimming']['mode'] == 'continuous'
        assert m['swimming']['pool_length_m'] == '33.333333'
        assert m['reference_cap_seconds'] == 38*60 and m['duration_sec'] <= 38*60
        assert m['swimming']['declared_cap_seconds'] == 40*60
        assert m['swimming']['current_capacity_measured'] is False and m['swimming']['pace_estimated'] is False
        assert sum(b['duration_sec'] for b in c['blocks']) == c['duration_sec']
        assert all(b['intensity_min'] is None and b['intensity_max'] is None and b['distance_m'] is None for b in c['blocks'])
        assert 'folyamatos' in c['blocks'][1]['name'] and '1800 méter' in c['description']
    export('swim_recent_review', v)


@pytest.mark.parametrize('distance,lengths', [(25, 1), (60, 1), (100, 2)])
def test_short_repeats_use_whole_pool_lengths_and_keep_rest_inside_total_time(env, distance, lengths):
    settings = deepcopy(SETTINGS); settings['swimming'].update(continuous_distance_m=distance, continuous_minutes=None)
    configure(env, settings=settings)
    # 25m limit is deliberately below this pool length: no invented ability.
    v = review(env)
    if distance == 25:
        assert not swims(v)
        assert 'SWIMMING_CONTINUOUS_LIMIT_BELOW_POOL_LENGTH' in next(r for r in v['result']['preparation']['sport_availability']['sports'] if r['sport']=='SWIMMING')['reasons']
    else:
        assert swims(v)
        for c in swims(v):
            m = v['result']['prescription_context']['by_candidate'][c['candidate_key']]
            assert m['swimming']['mode'] == 'length_repeats'
            assert m['swimming']['lengths_per_repeat'] == lengths and m['swimming']['rest_seconds'] == 30
            assert c['duration_sec'] == 1200
        export('swim_repeats_review', v)


@pytest.mark.parametrize('change,code', [({'independent': False}, 'SWIMMING_ABILITY_REQUIRED'), ({'reported_on': '2026-08-01'}, None)])
def test_old_or_unconfirmed_skill_cannot_become_current_continuous_capacity(env, change, code):
    settings = deepcopy(SETTINGS); settings['swimming'].update(change)
    configure(env, settings=settings); v = review(env)
    if code:
        assert not swims(v)
        assert code in next(r for r in v['result']['preparation']['sport_availability']['sports'] if r['sport']=='SWIMMING')['reasons']
    else:
        assert swims(v) and all(v['result']['prescription_context']['by_candidate'][c['candidate_key']]['swimming']['mode']=='length_repeats' for c in swims(v))


def test_swimming_cannot_borrow_another_venues_pool_length(env):
    saved = configure(env)
    p = deepcopy(saved['artifact']['proposal']); p.update(request_id=str(UUID(int=211104)), previous_reference=training_options.reference(saved['artifact']))
    p['data']['locations'][0].pop('pool_length_m')
    p['data']['locations'][1].update(sports=['SWIMMING'], resources=['Úszómedence'], pool_length_m='25')
    save(env, p); v = review(env)
    assert not swims(v)
    assert 'SWIMMING_POOL_LENGTH_REQUIRED' in next(r for r in v['result']['preparation']['sport_availability']['sports'] if r['sport']=='SWIMMING')['reasons']


def test_changing_current_settings_rebalances_an_existing_all_strength_plan_without_light_rules(env, monkeypatch):
    from app.services import training_prescriptions
    # Existing own plans survive source upgrades, but their reservation cannot
    # starve the newly supported aerobic alternatives.
    saved = prepare(env, light=False, swimming=False, running=False)
    original = training_prescriptions.references
    def unavailable(data):
        values = original(data)
        for key in ['RUN_EASY_AEROBIC_FALLBACK', 'KAYAK_EASY_TECHNICAL', 'KAYAK_LONG_AEROBIC']:
            values[key] = {'cap_seconds': None, 'session_ids': [], 'anchor_id': None}
        return values
    with monkeypatch.context() as old:
        old.setattr(training_prescriptions, 'references', unavailable)
        for key in ['RUN_EASY_AEROBIC_FALLBACK', 'KAYAK_EASY_TECHNICAL']:
            old.setitem(training_prescriptions.FAMILIES, key, {**training_prescriptions.FAMILIES[key], 'default': None})
        before = review(env); assert {c['sport'] for c in before['result']['proposals']} == {'STRENGTH'}
        accept(env, before, token=211105)
    p = deepcopy(saved['artifact']['proposal']); p.update(request_id=str(UUID(int=211106)), previous_reference=training_options.reference(saved['artifact']))
    p['data']['prescription_settings'] = deepcopy(SETTINGS)
    save(env, p)
    after = review(env)
    sports = {c['sport'] for c in after['result']['proposals']}
    assert 'STRENGTH' in sports and sports & {'RUNNING', 'KAYAK'}
    assert after['result']['cancel'] and after['result']['create']
    accept(env, after, token=211107)
    repeat = review(env); export('rebalanced_before_repeat', after); export('rebalanced_repeat', repeat)
    assert not repeat['result']['create'] and not repeat['result']['cancel']
    export('rebalanced_review', after)


def test_stale_baseline_does_not_lift_defaults_and_future_state_is_rejected(env):
    settings = deepcopy(SETTINGS); settings['current_baseline'].update(from_date='2026-08-01', to_date='2026-08-28')
    saved = configure(env, settings=settings); v = review(env)
    b = v['result']['prescription_context']['starting_budget']
    assert b['mode'] == 'declared_and_product_defaults' and b['baseline_status'] == 'stale'
    assert b['max_sessions_per_7_days'] == 3 and b['max_minutes_per_7_days'] == 180
    p = deepcopy(saved['artifact']['proposal']); p.update(request_id=str(UUID(int=211109)), previous_reference=training_options.reference(saved['artifact']))
    p['data']['prescription_settings']['swimming']['reported_on'] = '2027-01-01'
    rejected = env.client.post(BASE, json=p)
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'TRAINING_OPTIONS_FUTURE_SWIMMING'


@pytest.mark.parametrize('change', [{'weekly_sessions': True}, {'weekly_minutes': 0}, {'from_date': '2026-10-22'}, {'to_date': '2027-01-01'}])
def test_baseline_requires_a_real_two_to_eight_week_interval(change):
    value = deepcopy(SETTINGS); value['current_baseline'].update(change)
    with pytest.raises(ValidationError): PrescriptionSettings.model_validate(value)


def test_complete_recent_weeks_in_other_sports_are_current_load_not_zero(planner):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models.entities import WorkoutSession
    historic_weeks(planner); locations(planner)
    with Session(planner.engine) as db:
        for row in db.scalars(select(WorkoutSession)):
            row.sport = Sport.RUNNING
        db.commit()
    sync_receipt(planner, first='2026-10-05', last='2026-10-19')
    v = short_review(planner); b = v['result']['prescription_context']['starting_budget']
    assert b['mode'] == 'observed_covered_weeks' and b['max_sessions_per_7_days'] == 4
    assert all(not w['main_sport_present'] for w in b['weeks'] if w['status']=='covered')
    export('observed_review', v)


@pytest.mark.parametrize('first,second,known,rpe,hours', [('STRENGTH','STRENGTH',True,None,48), ('SWIMMING','KAYAK',True,None,24),
    ('RUNNING','SWIMMING',True,None,12), ('RUNNING','STRENGTH',True,None,24), ('RUNNING','SWIMMING',False,None,36),
    ('RUNNING','SWIMMING',False,2,12), ('RUNNING','SWIMMING',False,8,36)])
def test_spacing_distinguishes_known_easy_samples_and_unknown_effort(first,second,known,rpe,hours):
    assert training_load.spacing_hours(first, second, known=known, rpe=rpe) == hours
    now = datetime(2026, 10, 25, tzinfo=UTC)
    item = {'sport':first,'at':now,'known':known,'rpe':rpe}
    assert training_load.conflicts([item],now+timedelta(hours=hours,seconds=-1),second)
    assert not training_load.conflicts([item],now+timedelta(hours=hours),second)
