"""Readiness requires familiarity/equipment, not the reference being created."""
from copy import deepcopy
from datetime import date

from app.planning.domain.athlete_setup import digest
from app.services import strength_catalog
from app.services.assessment_source_updates import registry_extension

SCHEMA = 'guided-strength-session-v0.1'
RULES = 'guided-strength-start-v0.1'


def preparation(context):
    data = context['data']
    issues = []
    if data is None:
        issues.append('GUIDED_INTAKE_REQUIRED')
    elif context['sources_changed'] and not registry_extension(context):
        issues.append('GUIDED_SOURCES_CHANGED')
    if data:
        if not data['reviewed']:
            issues.append('GUIDED_INTAKE_REVIEW_REQUIRED')
        if data['state_change'] != 'unchanged' or (context['sources']['profile_review'] or {}).get('global_entry_gate') != 'OPEN':
            issues.append('GUIDED_STATE_REVIEW')
        if data['experience'] == 'unknown' or data['strength_frequency'] == 'unknown' or data['supervision'] in {'unknown', 'needed'}:
            issues.append('GUIDED_HISTORY_OR_SUPERVISION_REVIEW')
        if not any(s['sport_key'] == 'STRENGTH' and s['role'] in {'primary', 'secondary'} for s in data['sports']):
            issues.append('GUIDED_STRENGTH_ROLE_REQUIRED')
    catalog = context['sources']['catalog']
    exercises = {e['id']: e for e in catalog['exercises']}
    choices = []
    for place in context['sources']['locations']:
        if place['archived'] or 'STRENGTH' not in place['sports']:
            continue
        available = set(strength_catalog.available_exercise_ids(place, catalog))
        entries = []
        for entry in (data or {}).get('exercises', []):
            if entry['location_id'] != place['id']:
                continue
            codes = []
            exercise = exercises.get(entry['exercise_id'])
            if not exercise:
                codes.append('GUIDED_EXERCISE_REQUIRED')
            elif exercise['id'] not in available:
                codes.append('GUIDED_EQUIPMENT_MISSING')
            if entry['familiarity'] not in {'independent', 'regular'}:
                codes.append('GUIDED_INSTRUCTION_REQUIRED')
            if entry['comfort'] != 'none':
                codes.append('GUIDED_COMFORT_REVIEW')
            if any(s['symptoms'] in {'pain', 'discomfort'} for s in entry['sets']):
                codes.append('GUIDED_REPORTED_SYMPTOMS')
            entries.append({'entry_id': entry['id'], 'exercise_id': entry['exercise_id'],
                            'pattern': entry['pattern'], 'label': exercise['label'] if exercise else entry['pattern'],
                            'ready': not codes and not issues, 'issues': codes})
        choices.append({'location_id': place['id'], 'name': place['name'], 'entries': entries})
    return {'rules_version': RULES, 'issues': issues, 'locations': choices,
            'fresh_reference_required_to_start': False,
            'protocol': {'warmup_minutes': [5, 10], 'practice_repetitions': [3, 5],
                         'reference_repetitions': [5, 8], 'reference_hold_seconds': [10, 20],
                         'rest_seconds': 120, 'max_practice_sets': 1, 'max_reference_sets': 1,
                         'numeric_load_prescribed': False, 'maximal_test': False, 'one_rm_estimated': False}}


def stop_required(progress):
    if progress.get('protocol_version'):
        from app.services.strength_calibration_domain import safety_stop
        return safety_stop(progress)
    return any(row['state'] == 'stopped' or any(v['symptoms'] in {'pain', 'discomfort'} or v['technique'] == 'breakdown' or v['rir'] in {'0', '1'}
               for v in row['observations']) for row in progress['results'])


def validate_progress(proposal, start_day, today, measurement_protocols=None):
    if proposal.get('protocol_version'):
        from app.services.strength_calibration_domain import validate
        validate(proposal, start_day, today, measurement_protocols)
        return
    for result in proposal['progress']['results']:
        for observation in result['observations']:
            date.fromisoformat(observation['performed_on'])
            if not start_day <= observation['performed_on'] <= today:
                raise ValueError('GUIDED_OBSERVATION_DATE_INVALID')
    if proposal['progress']['phase'] != 'warmup' and not proposal['progress']['warmup_completed'] and not stop_required(proposal['progress']):
        raise ValueError('GUIDED_WARMUP_NOT_CONFIRMED')


def initial_progress(data, ids):
    entries = {v['id']: v for v in data['exercises']}
    return {'phase': 'warmup', 'current_index': 0, 'warmup_completed': False,
            'results': [{'entry_id': key, 'state': 'pending', 'side': entries[key]['side'],
                         'machine_note': entries[key]['machine_note'], 'note': '', 'observations': []} for key in ids], 'note': ''}


def project_intake(original, progress, today):
    if progress.get('protocol_version'):
        from app.services.strength_calibration_domain import project_intake as project_calibration
        return project_calibration(original, progress, today)
    data = deepcopy(original)
    data['assessment_date'] = today
    results = {r['entry_id']: r for r in progress['results']}
    dates = []
    for entry in data['exercises']:
        row = results.get(entry['id'])
        if not row:
            continue
        reference = [v for v in row['observations'] if v['purpose'] == 'reference']
        pain = any(v['symptoms'] in {'pain', 'discomfort'} for v in row['observations'])
        if reference:
            entry['sets'] = [{k: v for k, v in observation.items() if k not in {'purpose', 'performed_on'}} for observation in reference]
            entry['performed_on'] = reference[-1]['performed_on']
            entry['side'], entry['machine_note'] = row['side'], row['machine_note']
            dates.append(entry['performed_on'])
        if pain:
            entry['comfort'] = 'symptoms'
            data['state_change'] = 'changed'
    if stop_required(progress):
        data['state_change'] = 'changed'
    if dates:
        data['last_strength_date'] = max(dates)
    data['references_reviewed'] = True
    data['reviewed'] = True
    return data


def reference(artifact):
    return {'artifact_id': artifact['artifact_id'], 'content_hash': artifact['content_hash']}


def freeze(value):
    value['content_hash'] = digest(value)
    return value
