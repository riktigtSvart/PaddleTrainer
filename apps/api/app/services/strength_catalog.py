"""Versioned location inventory. Equipment matching is not exercise prescription."""
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from app.planning.domain.athlete_setup import digest


@lru_cache(maxsize=1)
def _catalog():
    value = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
    categories = {v['id'] for v in value['categories']}
    equipment = {v['id']:v for v in value['equipment']}
    guides = {v['id'] for v in value['guides']}
    movements = {v['id'] for v in value['movements']}
    if (value['schema_version'] != 'strength-catalog-v0.1' or value['planning_authorized'] is not False
            or value['workouts_changed'] is not False or len(equipment) != len(value['equipment'])
            or len({v['id'] for v in value['exercises']}) != len(value['exercises'])):
        raise ValueError('STRENGTH_CATALOG_INVALID')
    aliases = {}
    for item in equipment.values():
        if item['category'] not in categories or item['resource'] != item['label']:
            raise ValueError('STRENGTH_CATALOG_INVALID')
        for label in [item['resource'], *item['aliases']]:
            key = label.strip().casefold()
            if key in aliases and aliases[key] != item['id']:
                raise ValueError('STRENGTH_CATALOG_AMBIGUOUS_RESOURCE')
            aliases[key] = item['id']
    for exercise in value['exercises']:
        if (exercise['movement'] not in movements or exercise['guide_id'] is not None and exercise['guide_id'] not in guides
                or not exercise['requirements'] or any(not group or len(set(group)) != len(group)
                    or not set(group) <= equipment.keys() for group in exercise['requirements'])):
            raise ValueError('STRENGTH_CATALOG_INVALID')
    value['content_hash'] = digest(value)
    return value


def catalog():
    return deepcopy(_catalog())


def equipment_ids(resources, catalogue=None):
    values = {value.strip().casefold() for value in resources}
    return [item['id'] for item in (catalogue or _catalog())['equipment']
            if any(label.casefold() in values for label in [item['resource'], *item['aliases']])]


def exercise_ids(resources, catalogue=None):
    value = catalogue or _catalog()
    available = set(equipment_ids(resources, value))
    return [item['id'] for item in value['exercises']
            if any(set(group) <= available for group in item['requirements'])]


def declared_exercise_ids(location, catalogue=None):
    value = catalogue or _catalog()
    declared = [v['exercise_id'] for v in location.get('exercise_confirmations') or []]
    known = {e['id'] for e in value['exercises']}
    if len(set(declared)) != len(declared) or not set(declared) <= known:
        raise ValueError('STRENGTH_DECLARATION_INVALID')
    if location['archived'] or 'STRENGTH' not in location['sports']:
        return []
    return [e['id'] for e in value['exercises'] if e['id'] in declared]


def available_exercise_ids(location, catalogue=None, resources=None):
    value = catalogue or _catalog()
    declared = declared_exercise_ids(location, value)
    if location['archived'] or 'STRENGTH' not in location['sports']:
        return []
    known = set(exercise_ids(location['resources'] if resources is None else resources, value)) | set(declared)
    return [e['id'] for e in value['exercises'] if e['id'] in known]


def location_options(locations):
    result = []
    for location in locations:
        if location['archived'] or 'STRENGTH' not in location['sports']:
            continue
        item = {'location_id': location['id'], 'equipment_ids': equipment_ids(location['resources']),
                'exercise_ids': available_exercise_ids(location), 'planning_authorized': False}
        if 'exercise_confirmations' in location:
            item.update(declared_exercise_ids=declared_exercise_ids(location),
                        equipment_exercise_ids=exercise_ids(location['resources']))
        result.append(item)
    return result
