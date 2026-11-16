"""Reuse observations only when their actual strength venues stay equivalent."""
from app.services.initial_assessment import source_body

SCHEMA = 'assessment-source-compatibility-v0.1'


def physical_options(data, location_ids):
    return {'timezone_name': data['timezone_name'], 'locations': sorted([
        {'id': p['id'], 'archived': p['archived'], 'strength_supported': 'STRENGTH' in p['sports'],
         'resources': sorted({r.strip().lower() for r in p['resources']}),
         'confirmed_exercise_ids': sorted(v['exercise_id'] for v in p.get('exercise_confirmations') or [])}
        for p in data['locations'] if p['id'] in location_ids], key=lambda p: p['id'])}


def compare(context):
    saved = (context.get('receipt') or {}).get('artifact')
    if not saved:
        return {'schema_version': SCHEMA, 'reusable': False, 'changes': ['ASSESSMENT_MISSING'], 'location_ids': []}
    snapshot = saved['snapshot']
    before, after = source_body(snapshot), context['source_body']
    locations = sorted({e['location_id'] for e in saved['proposal']['data']['exercises'] if e.get('location_id')})
    changes, reusable = [], True
    for key, code in [('timezone_name', 'TIMEZONE'), ('profile_reference', 'PROFILE'), ('catalog_hash', 'CATALOG'), ('registry_hash', 'REGISTRY')]:
        if before[key] != after[key]:
            changes.append(code)
            reusable = False
    if before['programs'] != after['programs']:
        additions_only = all(p in after['programs'] for p in before['programs'])
        changes.append('PROGRAMS_ADDED' if additions_only else 'PROGRAMS')
        reusable = reusable and additions_only
    if before['options_reference'] != after['options_reference']:
        current = (context.get('options_source_receipt') or {}).get('artifact')
        old = (snapshot.get('options_receipt') or {}).get('artifact')
        equivalent = bool(current and old and
            {'artifact_id': current['artifact_id'], 'content_hash': current['content_hash']} == after['options_reference'] and
            physical_options(old['proposal']['data'], locations) == physical_options(current['proposal']['data'], locations))
        changes.append('OPTIONS_OTHER_FIELDS' if equivalent else 'OPTIONS_REFERENCED_LOCATIONS')
        reusable = reusable and equivalent
    return {'schema_version': SCHEMA, 'reusable': reusable, 'changes': changes, 'location_ids': locations}
