"""Local meal-clock suggestions, never a nutrient or energy prescription."""
from datetime import date, datetime, time, timedelta, UTC
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.entities import PlannedWorkout, WorkoutStatus
from app.planning.domain.athlete_setup import require
from app.planning.infrastructure.adapters.athlete_history import aware

RULES = 'meal-clock-0.1'
DEFAULTS = {'breakfast': 27000, 'lunch': 45000, 'snack': 57600, 'dinner': 68400}
BOUNDS = {'breakfast': (18000, 39600), 'lunch': (39600, 55800),
    'snack': (50400, 66600), 'dinner': (61200, 81000)}
ORDER = ('breakfast', 'lunch', 'snack', 'dinner')
GAP = 900  # Scheduling margin, not a physiological or medical threshold.
MEAL_WINDOW = 1800


def seconds(clock):
    h, m, s = map(int, clock.split(':'))
    return h*3600+m*60+s


def clock(value):
    return f'{value//3600:02}:{value//60%60:02}:{value%60:02}'


def real_clock(day, value, zone):
    wall = datetime.fromisoformat(day+'T'+clock(value))
    choices = set()
    for fold in (0, 1):
        at = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if at.astimezone(zone).replace(tzinfo=None) == wall:
            choices.add(at)
    return len(choices) == 1  # Auto suggestions avoid both missing and ambiguous hours.


def day_schedule(data, day, slots, context):
    zone = ZoneInfo(context['timezone'])
    now = datetime.fromisoformat(context['now']).astimezone(zone)
    wall_now = now.strftime('%Y-%m-%dT%H:%M:%S')
    blocks = [a for a in context['activities'] if a['date'] == day]
    incomplete = day in context['uncertain_dates']
    overrides = {t['slot']: t['time'] for t in data['timings'] if t['date'] == day}
    used, result, anchors = [], {}, {}

    def collision(value):
        return any(value < a['end_second']+GAP and value+MEAL_WINDOW > a['start_second']-GAP for a in blocks)

    def item(value, origin, shifted=False):
        return {'time': clock(value) if value is not None else None, 'origin': origin,
            'shifted': shifted, 'conflict': value is not None and collision(value), 'incomplete': incomplete}

    for slot in slots:
        if slot in overrides:
            value = seconds(overrides[slot]) if overrides[slot] is not None else None
            result[slot] = item(value, 'manual' if value is not None else 'unset')
            if value is not None:
                used.append(value)
            continue
        routine = data['default_times'][slot]
        if routine is not None:
            anchor, origin = seconds(routine), 'routine'
        else:
            observations = sorted(seconds(e['time']) for e in data['entries']
                if e['status'] == 'eaten' and e['source'] and e['source']['slot'] == slot
                and e['timezone'] == context['timezone'] and e['date']+'T'+e['time'] <= wall_now)
            anchor, origin = (observations[len(observations)//2], 'learned') if len(observations) >= 3 else (DEFAULTS[slot], 'default')
        if day < context['local_today']:
            result[slot] = item(seconds(routine), 'routine') if routine is not None else item(None, 'past_unknown')
            continue
        anchors[slot] = (anchor, origin)

    for slot in sorted(anchors, key=lambda s: (anchors[s][0], ORDER.index(s))):
        anchor, origin = anchors[slot]
        low, high = BOUNDS[slot] if origin == 'default' else (max(0, anchor-7200), min(84600, anchor+7200))

        def free(value):
            return not collision(value) and all(abs(value-v) >= 3600 for v in used) and real_clock(day, value, zone)

        value = anchor if low <= anchor <= high and free(anchor) else None
        if value is None:
            candidates = [v for v in range(((low+299)//300)*300, high+1, 300) if free(v)]
            after = next((v for v in candidates if v >= anchor), None)
            if collision(anchor) and after is not None and after-anchor <= 7200:
                value = after
            elif candidates:
                value = min(candidates, key=lambda v: (abs(v-anchor), v < anchor, v))
        result[slot] = item(value, origin if value is not None else 'no_window', value is not None and value != anchor)
        if value is not None:
            used.append(value)
    return result


async def context(session, owner, timezone, start, end, now):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    require(0 <= (last-first).days < 366, 'NUTRITION_TIMING_RANGE_INVALID')
    zone = ZoneInfo(timezone)
    rows = (await session.execute(select(PlannedWorkout).where(PlannedWorkout.user_id == UUID(owner),
        PlannedWorkout.status.in_((WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED, WorkoutStatus.DRAFT)),
        PlannedWorkout.date >= first-timedelta(days=7), PlannedWorkout.date <= last+timedelta(days=1))
        .order_by(PlannedWorkout.date, PlannedWorkout.id).limit(2001))).scalars().all()
    require(len(rows) <= 2000, 'NUTRITION_TIMING_ACTIVITY_LIMIT')
    activities, uncertain = [], set()
    for row in rows:
        if type(row.duration_sec) is int and row.duration_sec == 0:
            continue  # Known zero occupies no time; it is not an unknown duration.
        if row.planned_start_time is None or type(row.duration_sec) is not int or not 0 < row.duration_sec <= 7*86400:
            if first <= row.date <= last:
                uncertain.add(row.date.isoformat())
            continue
        begins = aware(row.planned_start_time).astimezone(UTC)
        finishes = begins+timedelta(seconds=row.duration_sec)
        cursor = max(first, begins.astimezone(zone).date())
        while cursor <= min(last, finishes.astimezone(zone).date()):
            midnight = datetime.combine(cursor, time.min, zone).astimezone(UTC)
            tomorrow = datetime.combine(cursor+timedelta(days=1), time.min, zone).astimezone(UTC)
            a, b = max(begins, midnight), min(finishes, tomorrow)
            if a < b:
                left = seconds(a.astimezone(zone).strftime('%H:%M:%S')) if a > midnight else 0
                right = seconds(b.astimezone(zone).strftime('%H:%M:%S')) if b < tomorrow else 86400
                if right <= left:  # A fall-back clock interval conservatively reserves the repeated hour.
                    left, right = max(0, min(left, right)-3600), min(86400, max(left, right)+3600)
                activities.append({'workout_id': str(row.id), 'date': cursor.isoformat(), 'start_second': left, 'end_second': right})
            cursor += timedelta(days=1)
    activities.sort(key=lambda a: (a['date'], a['start_second'], a['workout_id']))
    return {'schema_version': 'nutrition-timing-v0.1', 'rules_version': RULES, 'athlete_id': owner,
        'timezone': timezone, 'start_date': start, 'end_date': end, 'now': now.isoformat(),
        'local_today': now.astimezone(zone).date().isoformat(), 'activities': activities, 'uncertain_dates': sorted(uncertain)}
