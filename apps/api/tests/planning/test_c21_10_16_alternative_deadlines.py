"""Individual deadlines, unchanged dose on retiming, and saved goal roles."""
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import training_alternative_availability as availability
from app.services.training_alternative_variants import variant
from tests.planning.test_c21_10_15_today_and_variants import env, prepare, review, feed
from tests.planning.test_p2_4c19_plan_choices import choice
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c3_goal_workflow_api import count


def export(name, value):
    if os.getenv('C21_10_16_EXPORT'):
        path = Path(os.environ['C21_10_16_EXPORT'])
        values = json.loads(path.read_text()) if path.exists() else {}
        values[name] = value
        path.write_text(json.dumps(values), encoding='utf-8')


def early(e):
    target, scope = prepare(e)
    e.clock.current = datetime(2026, 10, 26, 7, 10, tzinfo=UTC)  # 08:10 Budapest; morning plan start has passed
    value = review(e, scope)
    return target, scope, value


def today_options(value):
    return next(g for g in value['result']['alternatives'] if g['date'] == '2026-10-26')['candidates']


def morning(value):
    return [c for c in today_options(value) if datetime.fromisoformat(c['start_at']).hour < 9]


def test_each_real_alternative_has_its_own_duration_based_deadline(env):
    target, scope, value = early(env)
    context = value['result']['alternative_availability']
    assert context['weather_evaluated'] is False and context['requires_fresh_check'] is True
    rows = morning(value)
    assert len({c['duration_sec'] for c in rows}) > 1
    for c in rows:
        actual = context['by_candidate'][c['candidate_key']]
        assert datetime.fromisoformat(actual['expires_at']) == datetime.fromisoformat(actual['window_end_at']) - timedelta(seconds=c['duration_sec'])
        assert datetime.fromisoformat(actual['expires_at']) > datetime.fromisoformat(c['start_at'])
        assert actual['goal_role'] == c['role'] and actual['goal_key'] == c['capability_key']
    assert target['id'] in value['result']['cancel']
    export('early', value)
    export('target', next(p for p in feed(env)['planned'] if p['id'] == target['id']))


def test_elapsed_proposed_start_is_retimed_before_its_own_deadline_without_shortening(env):
    target, scope, value = early(env)
    c = next(c for c in morning(value) if c['sport'] == 'STRENGTH')
    env.clock.current = datetime(2026, 10, 26, 8, 15, tzinfo=UTC)
    assert datetime.fromisoformat(c['start_at']) < env.clock.current
    before = (count(env, PlannedWorkout), count(env, WorkoutSession))
    selected = choice(env, value, c['date'], c['candidate_key'])['review']
    fresh = next(c for c in today_options(selected) if c['candidate_key'] == next(g for g in selected['result']['alternatives'] if g['date'] == '2026-10-26')['selected_candidate_key'])
    assert fresh['start_at'] != c['start_at'] and fresh['duration_sec'] == c['duration_sec']
    assert variant(c, value['result']['prescription_context']['by_candidate'][c['candidate_key']]) == variant(fresh, selected['result']['prescription_context']['by_candidate'][fresh['candidate_key']])
    assert before == (count(env, PlannedWorkout), count(env, WorkoutSession))
    env.clock.current += timedelta(minutes=5)
    accept(env, selected, token=21116001)
    rows = [p for p in feed(env)['planned'] if p['date'] == target['date']]
    assert len(rows) == 1 and rows[0]['planning_context']['candidate_key'] == fresh['candidate_key']
    assert count(env, WorkoutSession) == before[1]
    export('retimed', selected)
    export('after', feed(env))


def test_fifteen_minute_lead_does_not_close_the_last_feasible_minutes(env):
    target, scope, value = early(env)
    c = next(c for c in morning(value) if c['sport'] == 'STRENGTH')
    deadline = datetime.fromisoformat(value['result']['alternative_availability']['by_candidate'][c['candidate_key']]['expires_at'])
    env.clock.current = deadline - timedelta(minutes=5)
    selected = choice(env, value, c['date'], c['candidate_key'])['review']
    g = next(g for g in selected['result']['alternatives'] if g['date'] == c['date'])
    fresh = next(x for x in g['candidates'] if x['candidate_key'] == g['selected_candidate_key'])
    assert datetime.fromisoformat(fresh['start_at']) == deadline
    assert fresh['duration_sec'] == c['duration_sec']
    assert datetime.fromisoformat(fresh['end_at']) == datetime.fromisoformat(value['result']['alternative_availability']['by_candidate'][c['candidate_key']]['window_end_at'])
    accept(env, selected, token=21116002)


def test_an_expired_long_option_cannot_silently_become_a_shorter_workout(env):
    target, scope, value = early(env)
    c = max(morning(value), key=lambda c: c['duration_sec'])
    deadline = datetime.fromisoformat(value['result']['alternative_availability']['by_candidate'][c['candidate_key']]['expires_at'])
    env.clock.current = deadline + timedelta(seconds=1)
    before = tuple(count(env, t) for t in (PlanningAuditArtifactRow, PlannedWorkout, WorkoutSession))
    r = env.client.post(env.plan_url + '/choose', json={'review_reference': {'artifact_id': value['artifact_id'], 'content_hash': value['content_hash']}, 'date': c['date'], 'candidate_key': c['candidate_key']})
    assert r.status_code == 409 and 'TRAINING_PLAN_ALTERNATIVE_EXPIRED' in r.text
    assert before == tuple(count(env, t) for t in (PlanningAuditArtifactRow, PlannedWorkout, WorkoutSession))
    fresh = review(env, scope)
    assert any(availability.live(fresh['result']['alternative_availability']['by_candidate'][x['candidate_key']], env.clock.current) for x in morning(fresh))
    export('after_long_expiry', fresh)


def test_expiry_at_exact_last_start_is_inclusive_but_next_second_is_not(env):
    target, scope, value = early(env)
    c = next(c for c in morning(value) if c['sport'] == 'STRENGTH')
    row = value['result']['alternative_availability']['by_candidate'][c['candidate_key']]
    boundary = datetime.fromisoformat(row['expires_at'])
    assert availability.live(row, boundary)
    assert not availability.live(row, boundary + timedelta(microseconds=1))
    env.clock.current = boundary - timedelta(seconds=1)  # the fixture ticks microseconds on every call
    chosen = choice(env, value, c['date'], c['candidate_key'])['review']
    accept(env, chosen, token=21116003)


def test_expired_approved_preview_never_cancels_the_original_plan(env):
    target, scope, value = early(env)
    c = next(c for c in morning(value) if c['sport'] == 'STRENGTH')
    chosen = choice(env, value, c['date'], c['candidate_key'])['review']
    env.clock.current = datetime.fromisoformat(value['result']['alternative_availability']['by_candidate'][c['candidate_key']]['expires_at']) + timedelta(seconds=1)
    before = (count(env, PlannedWorkout), count(env, WorkoutSession))
    accept(env, chosen, token=21116004, expected=409)
    assert before == (count(env, PlannedWorkout), count(env, WorkoutSession))
    assert any(p['id'] == target['id'] for p in feed(env)['planned'])


def test_expired_options_leave_the_calendar_count_without_deleting_review_evidence(env):
    target, scope, value = early(env)
    before = next(p for p in feed(env)['planned'] if p['id'] == target['id'])['planning_context']['alternatives_count']
    env.clock.current = datetime(2026, 10, 26, 8, 50, tzinfo=UTC)
    after = next(p for p in feed(env)['planned'] if p['id'] == target['id'])['planning_context']['alternatives_count']
    assert 0 < after < before
    stored = env.client.get(env.plan_url).json()['review']
    assert stored == value


def test_daylight_clips_each_sport_at_its_own_location(env):
    target, scope, value = early(env)
    data = deepcopy(value['inputs'])
    c = next(c for c in today_options(value) if c['sport'] == 'KAYAK' and datetime.fromisoformat(c['start_at']).hour >= 13)
    options = data['daylight_context']['options_receipt']['artifact']['proposal']['data']
    options['daylight_rules'] = [{'sport': 'KAYAK', 'mode': 'daylight', 'start_buffer_minutes': 0, 'end_buffer_minutes': 10}]
    location = next(l for l in options['locations'] if l['id'] == c['location_id'])
    location['coordinates'] = {'latitude': '47.5', 'longitude': '19.0', 'timezone_name': 'Europe/Budapest'}
    location['daylight_overrides'] = []
    bound = availability.derive(data, c)
    assert 'daylight_end' in bound['limiting_factors']
    assert datetime.fromisoformat(bound['window_end_at']) < datetime(2026, 10, 26, 17, tzinfo=UTC)
    assert datetime.fromisoformat(bound['expires_at']) == datetime.fromisoformat(bound['window_end_at']) - timedelta(seconds=c['duration_sec'])


@pytest.mark.parametrize('role,rank', [('primary_development', 0), ('secondary_development', 1), ('maintenance', 2)])
def test_goal_classification_uses_saved_roles_not_the_sport_name(env, role, rank):
    target, scope, value = early(env)
    data, c = deepcopy(value['inputs']), deepcopy(next(c for c in morning(value) if c['sport'] == 'STRENGTH'))
    day = next(d for d in data['days'] if d['date'] == c['date'])
    next(r for r in day['capability_roles'] if r['capability_key'] == c['capability_key'])['role'] = role
    c['role'] = role
    bound = availability.derive(data, c)
    assert bound['goal_rank'] == rank and bound['goal_role'] == role


@pytest.mark.parametrize('day', ['2026-03-29', '2026-10-25'])
def test_overnight_opportunity_stops_new_starts_at_the_correct_dst_day_boundary(env, day):
    target, scope, value = early(env)
    data, c = deepcopy(value['inputs']), deepcopy(next(c for c in morning(value) if c['sport'] == 'STRENGTH'))
    zone = ZoneInfo('Europe/Budapest')
    start = datetime.combine(date.fromisoformat(day), time(22), zone).astimezone(UTC)
    end = start + timedelta(hours=5)
    c.update(date=day, start_at=start.isoformat(), end_at=(start + timedelta(seconds=c['duration_sec'])).isoformat())
    d = next(d for d in data['days'] if d['date'] == '2026-10-26'); d['date'] = day
    g = next(g for g in d['opportunities'] if g['key'] == c['opportunity_key']); g['intervals'] = [{'start_at': start.isoformat(), 'end_at': end.isoformat()}]
    bound = availability.derive(data, c)
    midnight = datetime.combine(date.fromisoformat(day) + timedelta(days=1), time.min, zone).astimezone(UTC)
    assert datetime.fromisoformat(bound['expires_at']) == midnight and bound['expires_inclusive'] is False
    assert not availability.live(bound, midnight)


def test_separate_time_intervals_are_not_joined_across_a_busy_gap(env):
    target, scope, value = early(env)
    data, c = deepcopy(value['inputs']), deepcopy(next(c for c in morning(value) if c['sport'] == 'STRENGTH'))
    d = next(d for d in data['days'] if d['date'] == c['date'])
    g = next(g for g in d['opportunities'] if g['key'] == c['opportunity_key'])
    g['intervals'] = [{'start_at': '2026-10-26T07:00:00+00:00', 'end_at': '2026-10-26T08:00:00+00:00'},
                      {'start_at': '2026-10-26T08:30:00+00:00', 'end_at': '2026-10-26T09:00:00+00:00'}]
    c.update(start_at='2026-10-26T07:15:00+00:00', end_at='2026-10-26T07:35:00+00:00', duration_sec=1200)
    bound = availability.derive(data, c)
    assert bound['expires_at'] == '2026-10-26T07:40:00+00:00'


@pytest.mark.parametrize('change', ['dose', 'time', 'cancellation', 'source', 'policy'])
def test_expiry_of_unselected_options_cannot_hide_a_changed_approved_mutation(env, change):
    from app.services.training_plans import same_reviewed_mutation
    target, scope, value = early(env)
    fresh = deepcopy(value['result'])
    if change == 'dose': fresh['create'][0]['duration_sec'] += 300
    if change == 'time': fresh['proposals'][0]['start_at'] = '2026-10-26T18:00:00+00:00'
    if change == 'cancellation': fresh['cancel'] = []
    if change == 'source':
        c = fresh['proposals'][0]
        fresh['prescription_context']['by_candidate'][c['candidate_key']]['reference_session_ids'] = []
    if change == 'policy': fresh['policy']['max_sessions_per_day'] = 2
    assert not same_reviewed_mutation(value, fresh)
