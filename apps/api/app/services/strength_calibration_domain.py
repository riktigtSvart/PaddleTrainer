"""Assessment measurements and conservative starter targets remain separate."""
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.planning.domain.athlete_setup import digest
from app.schemas.initial_assessment import SetObservation
from app.schemas.strength_calibration import PROTOCOL

DYNAMIC = {'weighted_repetitions', 'bodyweight_repetitions', 'assisted_repetitions', 'band_repetitions'}


@lru_cache(maxsize=2)
def _protocols(filename):
    value = json.loads(Path(__file__).with_name(filename).read_text(encoding='utf-8'))
    from app.services.strength_catalog import catalog
    known = {v['id']: v['label'] for v in catalog()['exercises']}
    assert value['schema_version'] == 'strength-calibration-protocols-v0.3'
    assert len(value['entries']) == len({v['exercise_id'] for v in value['entries']}) == 120
    assert all(known[v['exercise_id']] == v['label'] and len(v['steps']) == 7 for v in value['entries'])
    assert value['planning_authorized'] is False and value['workouts_changed'] is False and value['clinical_validation_claim'] is False
    value['content_hash'] = digest(value)
    return value


def protocols(content_hash=None):
    # The released bank stays immutable so saved occasions and pending starts
    # retain the exact instructions that were reviewed.
    for filename in ('strength_calibration_protocols_v0_3_1.json', 'strength_calibration_protocols_v0_3.json'):
        value = _protocols(filename)
        if content_hash is None or value['content_hash'] == content_hash:
            return deepcopy(value)
    raise ValueError('CALIBRATION_PROTOCOL_CHANGED')


def is_calibration(progress):
    return progress.get('protocol_version') == PROTOCOL


def safety_stop(progress):
    return any(v['performed_confirmed'] and (v['symptoms'] in {'pain', 'discomfort'}
               or v['technique'] == 'breakdown' or v['stop_reason'] in {'symptom', 'technique_limit'})
               for r in progress['results'] for v in r['observations'])


def selected_protocols(initial, ids, mode='calibration', protocol_hash=None):
    bank = protocols(protocol_hash)
    by_id = {v['exercise_id']: v for v in bank['entries']}
    entries = {v['id']: v for v in initial['data']['exercises']}
    if mode == 'repeatability':
        for protocol in by_id.values():
            repeatability = bank['repeatability']
            steps = repeatability.get('bodyweight_steps', repeatability['steps']) if protocol['family'] == 'bodyweight_repetitions' else repeatability['steps']
            protocol['steps'] = deepcopy(steps)
            protocol['planned_measurement'].update(bank['repeatability']['planned_measurement'])
    value = {'schema_version': 'selected-calibration-protocols-v0.1', 'protocol_version': PROTOCOL,
             'measurement_mode': mode,
             'protocol_hash': bank['content_hash'],
             'entries': [{'entry_id': key, 'protocol': by_id[entries[key]['exercise_id']]} for key in ids]}
    value['content_hash'] = digest(value)
    return value


def initial_progress(data, ids):
    from app.services.guided_strength_domain import initial_progress as legacy_progress
    value = legacy_progress(data, ids)
    value['protocol_version'] = PROTOCOL
    return value


def validate(proposal, start_day, today, snapshot):
    if proposal['protocol_hash'] != snapshot['protocol_hash']:
        raise ValueError('CALIBRATION_PROTOCOL_CHANGED')
    by_entry = {v['entry_id']: v['protocol'] for v in snapshot['entries']}
    p = proposal['progress']
    if proposal['action'] in {'finish', 'apply'} and any(not v['performed_confirmed'] for r in p['results'] for v in r['observations']):
        raise ValueError('CALIBRATION_UNCONFIRMED_RESULT')
    if p['phase'] != 'warmup' and not p['warmup_completed'] and not safety_stop(p):
        raise ValueError('GUIDED_WARMUP_NOT_CONFIRMED')
    all_ids = []
    for row in p['results']:
        protocol = by_entry[row['entry_id']]
        family = protocol['family']
        if protocol['scope'] == 'sport_route':
            raise ValueError('CALIBRATION_SPORT_PROTOCOL_REQUIRED')
        if proposal['measurement_mode'] == 'repeatability' and family not in DYNAMIC:
            raise ValueError('CALIBRATION_REPEATABILITY_UNSUPPORTED')
        for v in row['observations']:
            all_ids.append(v['id'])
            if not start_day <= v['performed_on'] <= today:
                raise ValueError('GUIDED_OBSERVATION_DATE_INVALID')
            expected = 'repeatability' if proposal['measurement_mode'] == 'repeatability' else 'calibration' if family in DYNAMIC or family == 'timed_hold' or family == 'carry' else 'quality'
            if v['purpose'] != expected:
                raise ValueError('CALIBRATION_PURPOSE_INVALID')
            if family == 'timed_hold' and any(v[k] is not None for k in ['repetitions', 'duration_seconds', 'distance_m', 'measured_height_m']):
                raise ValueError('CALIBRATION_METRIC_INVALID')
            if family == 'carry' and any(v[k] is not None for k in ['repetitions', 'hold_seconds', 'measured_height_m']):
                raise ValueError('CALIBRATION_METRIC_INVALID')
            if family in DYNAMIC | {'controlled_repetitions', 'ballistic_short_set'} and any(v[k] is not None for k in ['hold_seconds', 'duration_seconds', 'distance_m', 'measured_height_m']):
                raise ValueError('CALIBRATION_METRIC_INVALID')
            if family == 'explosive_single_attempts':
                allowed = 'measured_height_m' if protocol['exercise_id'] == 'jump_squat' else 'distance_m' if protocol['exercise_id'] in {'rotational_throw', 'forward_throw'} else None
                if any(v[k] is not None for k in ['hold_seconds', 'duration_seconds', *[k for k in ['distance_m', 'measured_height_m'] if k != allowed]]):
                    raise ValueError('CALIBRATION_METRIC_INVALID')
            if v['load_value'] is not None and Decimal(v['load_value']) > 100000:
                raise ValueError('CALIBRATION_LOAD_INVALID')
        if row['state'] == 'recorded' and not any(v['performed_confirmed'] for v in row['observations']):
            raise ValueError('CALIBRATION_COMPLETION_REQUIRED')
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('CALIBRATION_DUPLICATE_OBSERVATION')


def project_intake(original, progress, today):
    """Publish actual sets only; full measurements remain in the durable occasion."""
    data = deepcopy(original)
    data['assessment_date'] = today
    fields = set(SetObservation.model_fields)
    by_id = {v['id']: v for v in data['exercises']}
    dates = []
    for row in progress['results']:
        source = by_id[row['entry_id']]
        groups = {}
        for v in row['observations']:
            if not v['performed_confirmed']:
                continue
            dates.append(v['performed_on'])
            if v['symptoms'] in {'pain', 'discomfort'}:
                source['comfort'] = 'symptoms'
            # Non-repetition measurements are preserved in their native units in the occasion.
            if v['purpose'] not in {'calibration', 'repeatability'} or (v['repetitions'] is None and v['hold_seconds'] is None):
                continue
            key = (v['performed_on'], v['side'], v['setup_note'] or row['machine_note'])
            groups.setdefault(key, []).append({k: v[k] for k in fields})
        for index, ((performed, side, setup), sets) in enumerate(groups.items()):
            target = source if index == 0 else deepcopy(source)
            if index:
                target['id'] = str(uuid5(NAMESPACE_URL, row['entry_id'] + ':' + performed + ':' + side + ':' + setup))
                old = next((i for i, e in enumerate(data['exercises']) if e['id'] == target['id']), None)
                if old is None:
                    data['exercises'].append(target)
                else:
                    data['exercises'][old] = target
            target.update(performed_on=performed, side=side, machine_note=setup, sets=sets)
    if safety_stop(progress):
        data['state_change'] = 'changed'
    if dates:
        data['last_strength_date'] = max(dates)
    data['references_reviewed'] = True
    data['reviewed'] = True
    return data


def observed(progress):
    return [v for r in progress['results'] for v in r['observations'] if v['performed_confirmed']]


def starter_targets(receipt):
    """A product starting rule: one reduced set, not a personal capacity estimate."""
    a = receipt['artifact']
    base = receipt['base'] or a
    if a['state'] != 'finished' or not a['result'].get('assessment_reference') or a['result']['stop_required']:
        return []
    bank = {v['entry_id']: v['protocol'] for v in base['measurement_protocols']['entries']}
    initial = a['application_context']['data']
    projected = project_intake(initial, a['proposal']['progress'], a['application_context']['local_today'])
    original_entries = {v['id']: v for v in base['intake_context']['data']['exercises']}
    result = []
    for row in a['proposal']['progress']['results']:
        protocol = bank[row['entry_id']]
        if protocol['family'] not in DYNAMIC or protocol['load_kind'] in {'landmine_components', 'variant_dependent_load'}:
            continue
        original = original_entries[row['entry_id']]
        for entry in projected['exercises']:
            if entry['exercise_id'] != original['exercise_id'] or entry['location_id'] != original['location_id']:
                continue
            candidates = [v for v in row['observations'] if v['performed_confirmed']
                          and v['id'] in {s['id'] for s in entry['sets']}
                          and v['repetitions'] is not None and v['repetitions'] >= 4
                          and v['rir'] in {'2', '3', '4', '5_plus'} and v['technique'] == 'stable'
                          and v['symptoms'] == 'none' and v['side'] != 'unknown'
                          and (v['side'] in {'left', 'right'} if protocol['side'] in {'each_side', 'alternating_sides'} else v['side'] == 'both')
                          and v['stop_reason'] in {'planned_cap', 'reserve_target', 'effort_limit'}]
            if not candidates:
                continue
            measured = candidates[-1]
            load = measured['load_kind'] == 'bodyweight' or measured['load_kind'] == 'band' and bool(measured['load_note'].strip()) or measured['load_value'] is not None and measured['load_basis'] != 'unknown'
            machine = protocol['load_kind'] in {'machine_display', 'machine_plate_components', 'assistance_display'}
            if not load or machine and not entry['machine_note'].strip():
                continue
            if protocol['load_kind'] == 'machine_plate_components':
                config = measured['plate_configuration']
                parts = [measured['shared_plates_kg']] if config == 'shared' else [measured['left_plates_kg'], measured['right_plates_kg']] if config == 'paired' else []
                if not parts or any(v is None for v in parts) or measured['load_value'] is None or sum(Decimal(v) for v in parts) != Decimal(measured['load_value']):
                    continue
            planned = {k: measured[k] for k in SetObservation.model_fields}
            planned.update(repetitions=min(8, measured['repetitions'] - 2), rir='unknown')
            result.append({'entry_id': entry['id'], 'source_entry_id': row['entry_id'], 'exercise_id': entry['exercise_id'],
                           'location_id': entry['location_id'], 'performed_on': entry['performed_on'], 'side': entry['side'],
                           'machine_note': entry['machine_note'], 'actual_sets': entry['sets'], 'sets': [planned],
                           'derivation': {'rules_version': 'calibration-starter-v0.1',
                                          'guided_reference': {'artifact_id': a['artifact_id'], 'content_hash': a['content_hash']},
                                          'observation_id': measured['id'], 'source_repetitions': measured['repetitions'],
                                          'planned_repetitions': planned['repetitions'], 'source_rir': measured['rir'],
                                          'load_kind': protocol['load_kind'], 'planned_minimum_rir': 3,
                                          'personal_capacity_estimated': False, 'one_rm_estimated': False}})
    return result
