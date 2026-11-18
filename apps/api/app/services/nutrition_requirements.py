"""Read-only daily food reference values and estimated intake for saved plans."""
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import json
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import PlannedWorkout, WorkoutSession, WorkoutStatus
from app.planning.application import register_athlete_setup as intake
from app.planning.domain.athlete_setup import digest, require
from app.planning.infrastructure.adapters.athlete_history import aware
from app.schemas.nutrition_journal import JournalData
from app.services import body_mass, nutrition_calendar
from app.services.nutrition_domain import quantity

SCHEMA = 'nutrition-requirements-v0.1'
UNITS = {
    'energy': 'kcal', 'protein': 'g', 'carbohydrate': 'g', 'fat': 'g', 'fiber': 'g',
    'calcium': 'mg', 'iron': 'mg', 'magnesium': 'mg', 'zinc': 'mg',
    'iodine': 'µg', 'selenium': 'µg', 'b12': 'µg', 'folate': 'µg',
    'vitamin_d': 'µg', 'vitamin_c': 'mg', 'potassium': 'mg',
}
# Compendium example activities in each sport, not individual measured intensity.
# 12028/12045, 18100/18106, 18240/18230, 02054/02050, 01010/01040.
MET = {
    'RUNNING': (6.5, 9), 'KAYAK': (5, 9), 'SWIMMING': (5.8, 9.8),
    'STRENGTH': (3.5, 6), 'CYCLING': (4, 6.8),
}
OLDER_MET = {'STRENGTH': (2.3, 4.3)}  # 0205360 and 0205460
ENDURANCE = {'RUNNING', 'KAYAK', 'SWIMMING', 'CYCLING'}
ACTIVE_PLANS = (WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED)


@lru_cache(maxsize=1)
def composition():
    path = Path(__file__).with_name('data') / 'nutrition_composition_v0_1.json'
    return json.loads(path.read_text(encoding='utf-8'))


def rounded(value, digits='0.1'):
    return quantity(Decimal(str(value)).quantize(Decimal(digits), rounding=ROUND_HALF_UP))


def reference(lower, upper=None, source='efsa', scope=None, **details):
    return {
        'minimum': rounded(lower, '0.01') if lower is not None else None,
        'maximum': rounded(upper, '0.01') if upper is not None else None,
        'source': source, 'scope': scope, **details,
    }


def age_on(birth, on):
    if not birth:
        return None
    birth = date.fromisoformat(birth)
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def baseline(age, sex, height, kg):
    if age is None or age < 19 or not height or not kg:
        return None
    if sex == 'male':
        return 753.07 - 10.83 * age + 6.50 * height + 14.10 * kg
    if sex == 'female':
        return 584.90 - 7.01 * age + 5.72 * height + 11.71 * kg
    return None


def micronutrients(age, sex):
    if age is not None and age < 19:
        return {}
    level = {
        'fiber': (25,), 'calcium': (1000,) if age is not None and age < 25 else (950,),
        'magnesium': (350,) if sex == 'male' else (300,) if sex == 'female' else (300, 350),
        'iron': (11,) if sex == 'male' else (11, 16),
        'zinc': (9.4, 16.3) if sex == 'male' else (7.5, 12.7) if sex == 'female' else (7.5, 16.3),
        'iodine': (150,), 'selenium': (70,), 'b12': (4,), 'folate': (330,),
        'vitamin_d': (15,), 'vitamin_c': (110,) if sex == 'male' else (95,) if sex == 'female' else (95, 110),
        'potassium': (3500,),
    }
    if age is None:
        level['calcium'] = (950, 1000)
    return {key: reference(*values) for key, values in level.items()}


def macro_references(age, kg, totals, energy, training, strength):
    if age is None or age < 19:
        return {}
    values = {}
    if kg:
        if strength:
            values['protein'] = reference(1.6 * kg, 2 * kg, 'sport_strength')
        elif training:
            values['protein'] = reference(1.2 * kg, 2 * kg, 'sport')
        else:
            values['protein'] = reference(0.83 * kg)
    if kg and totals['planned'] + totals['recorded'] > totals['missing_duration']:
        duration = totals['endurance_seconds']
        if duration >= 5400:
            values['carbohydrate'] = reference(6 * kg, 10 * kg, 'sport')
        elif duration >= 3600:
            values['carbohydrate'] = reference(5 * kg, 7 * kg, 'sport')
        else:
            values['carbohydrate'] = reference(3 * kg, 5 * kg, 'sport')
    elif energy:
        low, high = energy
        values['carbohydrate'] = reference(.45 * low / 4, .60 * high / 4)
    if energy:
        low, high = energy
        values['fat'] = reference(.20 * low / 9, .35 * high / 9)
    return values


def effective_targets(journal, day):
    targets = {}
    for target in sorted(journal['targets'], key=lambda target: target['assessed_on']):
        if target['assessed_on'] <= day and (target['valid_until'] is None or day <= target['valid_until']):
            targets[target['nutrient']] = {
                'minimum': target['minimum'], 'maximum': target['maximum'],
                'source': 'assessment', 'scope': target['scope'], 'source_name': target['source_name'],
                'assessed_on': target['assessed_on'], 'valid_until': target['valid_until'],
            }
    return targets


def midnight(day, zone):
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)


def activity_days(workouts, sessions, zone, first, last, now):
    """Use past recorded activity, today's recorded plus outstanding plans, and future plans."""
    days = defaultdict(list)
    today = now.astimezone(zone).date()
    actual = [s for s in sessions if aware(s.started_at) <= now]
    fulfilled = {s.planned_workout_id for s in actual if s.planned_workout_id is not None}

    def place(start, planned_day, duration, sport, kind):
        if not start or duration is None or duration <= 0:
            if first <= planned_day <= last:
                days[planned_day].append((sport.value, kind, duration if duration and duration > 0 else None))
            return
        start = aware(start).astimezone(UTC)
        # Use elapsed seconds so the civil split remains correct through a DST transition.
        end = start + timedelta(seconds=duration)
        day = max(first, start.astimezone(zone).date())
        while day <= last:
            left, right = midnight(day, zone), midnight(day + timedelta(days=1), zone)
            seconds = int((min(end, right) - max(start, left)).total_seconds())
            if seconds > 0:
                days[day].append((sport.value, kind, seconds))
            if right >= end:
                break
            day += timedelta(days=1)

    for session in actual:
        start = aware(session.started_at)
        duration = session.duration_sec
        if duration is None and session.ended_at:
            elapsed = int((aware(session.ended_at) - start).total_seconds())
            duration = elapsed if elapsed > 0 else None
        place(start, start.astimezone(zone).date(), duration, session.sport, 'recorded')
    for workout in workouts:
        if workout.date >= today and workout.id not in fulfilled and workout.status in ACTIVE_PLANS:
            place(workout.planned_start_time, workout.date, workout.duration_sec, workout.sport, 'planned')
    return days


def activity_summary(events, age, kg):
    low = high = 0.0
    counts = dict(planned=0, recorded=0, missing_duration=0, unestimated=0, seconds=0, endurance_seconds=0)
    strength = False
    table = OLDER_MET if age is not None and age >= 60 else MET if age is not None and age >= 19 else {}
    # The standardized oxygen cost expressed in kcal/hour/kg (about 5 kcal/L oxygen).
    factor = 0.81 if table is OLDER_MET else 1.05
    for sport, kind, duration in events:
        counts[kind] += 1
        strength = strength or sport == 'STRENGTH'
        if duration is None:
            counts['missing_duration'] += 1
        else:
            counts['seconds'] += duration
            if sport in ENDURANCE:
                counts['endurance_seconds'] += duration
        if not kg or not duration or sport not in table:
            counts['unestimated'] += 1
            continue
        lo, hi = table[sport]
        low += (lo - 1) * factor * kg * duration / 3600
        high += (hi - 1) * factor * kg * duration / 3600
    estimated = len(events) > counts['unestimated']
    counts['extra_kcal'] = [rounded(low, '1'), rounded(high, '1')] if estimated or not events else None
    return counts, strength, (low, high)


def recipe_values(recipes):
    foods = composition()['foods']
    result = {}
    for recipe in recipes:
        amounts = {key: Decimal(0) for key in UNITS}
        known = set()
        missing = set()
        for ingredient in recipe['ingredients']:
            food = foods[ingredient['food_id']]
            scale = Decimal(ingredient['quantity']) * Decimal(food['grams_per_unit']) / 100
            for key in UNITS:
                number = food['per_100g'].get(key)
                if number is None:
                    missing.add(key)
                else:
                    known.add(key)
                    amounts[key] += scale * Decimal(number)
        result[recipe['id']] = (amounts, known, missing)
    return result


def food_totals(portions, recipes):
    totals = {key: Decimal(0) for key in UNITS}
    known = set()
    missing = set()
    unknown = 0
    for recipe_id, portion in portions:
        if recipe_id is None or portion is None:
            unknown += 1
            continue
        values, present, absent = recipes[recipe_id]
        known.update(present)
        missing.update(absent)
        for key in present:
            totals[key] += values[key] * Decimal(portion)
    return {
        'entries': len(portions), 'unquantified': unknown,
        'amounts': {
            key: {
                'amount': rounded(totals[key], '1' if key == 'energy' else '0.01') if key in known else None,
                'partial': bool(unknown or key in missing),
            }
            for key in UNITS
        },
    }


def build_days(wanted, calendar, profile, measurements, body_goal, activity):
    journal = calendar['journal']['saved']
    data = journal['proposal']['data'] if journal else JournalData().model_dump()
    recipes = recipe_values(calendar['catalog']['recipes'])
    actual_factors = {e['id']: e['recipe_portions'] for e in journal['result']['entries']} if journal else {}
    plans = {d['date']: [(m['recipe_id'], m['portion_factor']) for m in d['meals']] for d in calendar['result']['days']}
    actual = defaultdict(list)
    for entry in calendar['result']['actual_entries']:
        if entry['status'] == 'eaten':
            actual[entry['date']].append((entry['recipe_id'], actual_factors[entry['id']]))
    today = calendar['journal']['local_today']
    sex = profile.get('sex_reference')
    result = []
    for day in wanted:
        current_date = date.fromisoformat(day)
        age = age_on(profile.get('birth_date'), current_date)
        measurements_day = min(day, today)
        mass = next((v for v in measurements if v['recorded_on'] <= measurements_day), None)
        weight = float(mass['value_kg']) if mass else None
        height_day = profile.get('body_measurements_recorded_on')
        height = float(profile['height_cm']) if profile.get('height_cm') and height_day and height_day <= measurements_day else None
        base = baseline(age, sex, height, weight)
        workouts, has_strength, (extra_low, extra_high) = activity_summary(activity.get(current_date, []), age, weight)
        training = any(activity.get(current_date - timedelta(days=i)) for i in range(7)) or bool(profile.get('typical_minutes_per_week'))
        strength = has_strength or (training and (data['muscle_goal'] == 'gain' or data['performance_goal'] == 'strength'))
        energy = (base + extra_low, base + extra_high) if base is not None and workouts['unestimated'] == 0 else None
        refs = {**micronutrients(age, sex), **macro_references(age, weight, workouts, energy, training, strength)}
        if energy:
            refs['energy'] = reference(rounded(energy[0], '1'), rounded(energy[1], '1'), 'energy_model')
        refs.update(effective_targets(data, day))
        missing = ['adult_age'] if age is None or age < 19 else []
        if sex not in {'female', 'male'}:
            missing.append('sex_reference')
        if height is None:
            missing.append('height')
        if weight is None:
            missing.append('body_mass')
        result.append({
            'date': day, 'baseline_kcal': rounded(base, '1') if base is not None else None,
            'maintenance_kcal': [rounded(v, '1') for v in energy] if energy else None,
            'body_mass_on': mass['recorded_on'] if mass else None, 'missing_profile': missing,
            'workouts': workouts, 'references': refs,
            'planned': food_totals(plans.get(day, []), recipes),
            'logged': food_totals(actual.get(day, []), recipes),
        })
    return {
        'days': result, 'body_goal': body_goal, 'muscle_goal': data['muscle_goal'],
        'performance_goal': data['performance_goal'],
    }


async def read(*, repository, session, owner, start, end):
    wanted = nutrition_calendar.dates(start, end)
    require(len(wanted) <= 14, 'NUTRITION_REQUIREMENTS_RANGE_INVALID')
    calendar = await nutrition_calendar.read(repository=repository, session=session, owner=owner, start=start, end=end)
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        require(user.timezone == calendar['timezone'], 'NUTRITION_REQUIREMENTS_ZONE_CHANGED')
        zone = ZoneInfo(user.timezone)
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        recent = first - timedelta(days=6)
        # Include the previous civil date for overnight training and inspect the
        # planned counterpart of any session in the selected history.
        from_instant = midnight(recent - timedelta(days=1), zone)
        to_instant = midnight(last + timedelta(days=1), zone)
        workout_rows = (await session.execute(select(
            PlannedWorkout.id, PlannedWorkout.date, PlannedWorkout.planned_start_time,
            PlannedWorkout.duration_sec, PlannedWorkout.sport, PlannedWorkout.status,
        ).where(
            PlannedWorkout.user_id == UUID(owner), PlannedWorkout.date >= recent - timedelta(days=1),
            PlannedWorkout.date <= last, PlannedWorkout.status.in_(ACTIVE_PLANS),
        ))).all()
        linked = [w.id for w in workout_rows]
        session_rows = (await session.execute(select(
            WorkoutSession.planned_workout_id, WorkoutSession.started_at, WorkoutSession.ended_at,
            WorkoutSession.duration_sec, WorkoutSession.sport,
        ).where(
            WorkoutSession.user_id == UUID(owner),
            ((WorkoutSession.started_at >= from_instant) & (WorkoutSession.started_at < to_instant))
            | WorkoutSession.planned_workout_id.in_(linked),
        ))).all()
        loaded = await intake.latest(repository, session, owner, 'profile')
        profile = loaded[0]['proposal']['data'] if loaded else {}
        measurements = await body_mass.observations(repository, session, owner)
        goals = await body_mass.rows(repository, session, owner, body_mass.GOAL)
        goal = body_mass.checked(goals[-1], owner, body_mass.GOAL)['proposal']['goal'] if goals else None
        activity = activity_days(workout_rows, session_rows, zone, recent, last, datetime.fromisoformat(calendar['journal']['now']))
        value = {
            'schema_version': SCHEMA, 'athlete_id': owner, 'start_date': start, 'end_date': end,
            'timezone': user.timezone, 'read_only': True,
            **build_days(wanted, calendar, profile, measurements, goal, activity),
        }
        value['content_hash'] = digest(value)
        return value
    finally:
        await intake.rollback(session)
