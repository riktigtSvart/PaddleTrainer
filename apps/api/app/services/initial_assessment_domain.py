"""Assessment completeness is distinct from exercise prescription or clearance."""
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.planning.domain.athlete_setup import digest
from app.planning.domain.calendar_constraints import require
from app.services import strength_catalog


@lru_cache(maxsize=1)
def _registry():
    value = json.loads(Path(__file__).with_name('assessment_registry.json').read_text(encoding='utf-8'))
    require(value['planning_authorized'] is False and value['clinical_clearance'] is False, 'ASSESSMENT_REGISTRY_INVALID')
    known = {e['id'] for e in strength_catalog.catalog()['exercises']}
    require(all(set(p['exercise_ids']) <= known for p in value['patterns']), 'ASSESSMENT_REGISTRY_INVALID')
    value['content_hash'] = digest(value)
    return value


def registry():
    return deepcopy(_registry())


def validate_sources(data, snapshot):
    places = {v['id'] for v in snapshot['locations']}
    patterns = {v['key']: set(v['exercise_ids']) for v in snapshot['registry']['patterns']}
    sports = {v['key'] for v in snapshot['registry']['sports']}
    require(all(v['sport_key'] in sports for v in data['sports']), 'INITIAL_ASSESSMENT_SPORT_UNKNOWN')
    require(data['default_location_id'] is None or data['default_location_id'] in places, 'INITIAL_ASSESSMENT_LOCATION_UNKNOWN')
    require(data['program_reference'] is None or any(p['reference'] == data['program_reference'] for p in snapshot['programs']), 'INITIAL_ASSESSMENT_PROGRAM_UNKNOWN')
    for item in data['exercises']:
        require(item['exercise_id'] is None or item['exercise_id'] in patterns[item['pattern']], 'INITIAL_ASSESSMENT_EXERCISE_UNKNOWN')
        require(item['location_id'] is None or item['location_id'] in places, 'INITIAL_ASSESSMENT_LOCATION_UNKNOWN')
    require(all(v['location_id'] is None or v['location_id'] in places for v in data['sport_references']), 'INITIAL_ASSESSMENT_LOCATION_UNKNOWN')


def summary(data, snapshot, today):
    profile_review = snapshot['profile_review'] or {}
    review = data['state_change'] != 'unchanged' or profile_review.get('global_entry_gate') not in {'OPEN', 'OPEN_WITH_CONSTRAINTS'}
    locations = {v['id']: v for v in snapshot['locations']}
    states = []
    cutoff = date.fromisoformat(today)
    for item in data['exercises']:
        reasons = []
        place = locations.get(item['location_id'])
        if item['exercise_id'] is None:
            reasons.append('EXERCISE_MISSING')
        if item['familiarity'] in {'unknown', 'unfamiliar', 'assisted'}:
            reasons.append('INSTRUCTION_OR_FAMILIARITY_NEEDED')
        if item['comfort'] != 'none':
            reasons.append('COMFORT_UNRESOLVED')
        if not place or place['archived'] or 'STRENGTH' not in place['sports']:
            reasons.append('LOCATION_REVIEW')
        else:
            if item['exercise_id'] not in strength_catalog.available_exercise_ids(place, snapshot['catalog']):
                reasons.append('EQUIPMENT_MISSING')
        recent = item['performed_on'] is not None and 0 <= (cutoff - date.fromisoformat(item['performed_on'])).days <= snapshot['registry']['history_days']
        if not recent:
            reasons.append('RECENT_REFERENCE_MISSING')
        usable = []
        for observation in item['sets']:
            dose = (observation['repetitions'] is not None and observation['repetitions'] > 0
                    or observation['hold_seconds'] is not None and Decimal(observation['hold_seconds']) > 0)
            load = (observation['load_kind'] == 'bodyweight'
                    or observation['load_kind'] == 'band' and bool(observation['load_note'].strip())
                    or observation['load_kind'] in {'external_kg', 'assistance_kg', 'machine_level'}
                    and observation['load_value'] is not None and observation['load_basis'] != 'unknown')
            usable.append(dose and load and observation['rir'] != 'unknown' and observation['technique'] == 'stable' and observation['symptoms'] == 'none')
        if not any(usable):
            reasons.append('SET_REFERENCE_INCOMPLETE')
        state = ('review' if review else 'avoid' if item['comfort'] in {'symptoms', 'avoid'} or any(s['symptoms'] in {'pain', 'discomfort'} for s in item['sets'])
                 else 'needs_instruction' if item['familiarity'] in {'unfamiliar', 'assisted'}
                 else 'unassessed' if item['exercise_id'] is None or item['familiarity'] == 'unknown'
                 else 'needs_reference' if reasons else 'recorded_reference')
        states.append({'id': item['id'], 'state': state, 'reasons': reasons})
    sports_ready = bool(data['sports']) and any(v['role'] == 'primary' for v in data['sports']) and all(v['role'] != 'unknown' for v in data['sports'])
    selected = {e['pattern'] for e in data['exercises'] if e['exercise_id'] is not None}
    steps = [data['state_change'] != 'unknown', data['experience'] != 'unknown' and data['strength_frequency'] != 'unknown' and data['supervision'] != 'unknown',
             sports_ready, all(p['key'] in selected for p in snapshot['registry']['patterns'])
             and all(e['familiarity'] != 'unknown' and e['comfort'] != 'unknown' for e in data['exercises']),
             data['references_reviewed'], data['reviewed']]
    return {'steps': steps, 'completed_steps': sum(steps), 'total_steps': 6, 'form_complete': all(steps),
            'state_review_required': review, 'exercise_states': states,
            'recorded_reference_count': sum(v['state'] == 'recorded_reference' for v in states),
            'planning_authorized': False, 'clinical_clearance': False, 'workouts_changed': False,
            'source_kind': 'self_report', 'evaluated_on': today}
