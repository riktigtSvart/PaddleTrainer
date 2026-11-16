"""Per-option start deadlines, derived from the captured real opportunity.

These are upper time bounds, not a forecast or a guarantee that mutable
eligibility remains unchanged. Choice and acceptance still recheck all inputs.
Reviewed records are retained; only their live projection expires.
"""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.planning.domain import daylight

SCHEMA = 'training-alternative-availability-v0.1'
ROLES = {'primary_development': 0, 'secondary_development': 1, 'maintenance': 2}


def at(value):
    return datetime.fromisoformat(value).astimezone(UTC)


def derive(data, candidate, cache=None):
    day = next(d for d in data['days'] if d['date'] == candidate['date'])
    group = next(g for g in day['opportunities'] if g['key'] == candidate['opportunity_key'])
    light = (data.get('daylight_context') or {}).get('options_receipt', {}).get('artifact', {}).get('proposal', {}).get('data', {})
    cache = cache if cache is not None else {}
    key = (candidate['date'], group['key'], candidate['sport'])
    if key not in cache:
        cache[key] = daylight.allowed_intervals(light, group, candidate['sport'])[0]
    start, end = at(candidate['start_at']), at(candidate['end_at'])
    window = next(i for i in cache[key] if at(i['start_at']) <= start and end <= at(i['end_at']))
    raw = next(i for i in group['intervals'] if at(i['start_at']) <= start and end <= at(i['end_at']))
    window_end = at(window['end_at'])
    day_end = datetime.combine(date.fromisoformat(candidate['date']) + timedelta(days=1), time.min,
                               ZoneInfo(data['timezone_name'])).astimezone(UTC)
    last_fit = window_end - timedelta(seconds=candidate['duration_sec'])
    expires = min(last_fit, day_end)
    role = next(r['role'] for r in day['capability_roles'] if r['capability_key'] == candidate['capability_key'])
    if role != candidate['role'] or role not in ROLES:
        raise ValueError('Candidate goal differs from its saved mesocycle role')
    factors = ['availability_end']
    if window_end < at(raw['end_at']):
        factors.append('daylight_end')
    if day_end <= last_fit:
        factors.append('local_day_end')
    return {'window_start_at': at(window['start_at']).isoformat(), 'window_end_at': window_end.isoformat(),
            'day_end_at': day_end.isoformat(), 'duration_sec': candidate['duration_sec'],
            'expires_at': expires.isoformat(), 'expires_inclusive': last_fit < day_end,
            'limiting_factors': factors, 'goal_role': role, 'goal_rank': ROLES[role],
            'goal_key': candidate['capability_key']}


def attach(data, result):
    cache, rows = {}, {}
    for c in [*result['proposals'], *(c for g in result['alternatives'] for c in g['candidates'])]:
        rows[c['candidate_key']] = derive(data, c, cache)
    result['alternative_availability'] = {'schema_version': SCHEMA, 'weather_evaluated': False,
                                           'requires_fresh_check': True, 'by_candidate': rows}


def live(value, now):
    deadline = at(value['expires_at'])
    return now <= deadline if value['expires_inclusive'] else now < deadline
