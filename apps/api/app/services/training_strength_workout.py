"""Independent work-volume prescription, never duplicated measurement evidence.

Counts, timing and feedback thresholds are transparent starting product rules.
No 1RM, personal response fit or automatic load progression is inferred.
"""
from copy import deepcopy
from datetime import date
from app.services import training_strength_assessment as assessment, strength_catalog

SCHEMA = 'strength-workout-dose-v0.1'
RULES = 'strength-workout-policy-v0.1'
SOURCE = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/'
MAXIMUM = 4500
# Selection preference only; overlapping pattern sets still share one limit.
VERTICAL_PULL = {'pullup', 'lat_pulldown', 'chinup', 'assisted_pullup'}


def selected(context, data, sport, day, group):
    location = group['constraints'].get('location_id')
    if not location:
        return None, ['STRENGTH_NAMED_LOCATION_REQUIRED']
    evaluated = assessment.evaluate(context, data, sport, day, location, group['constraints']['resources'])
    if evaluated['issues']:
        return None, evaluated['issues']
    place = next((p for p in context['receipt']['artifact']['snapshot']['locations'] if p['id'] == location), None)
    catalogue = context['receipt']['artifact']['snapshot']['catalog']
    available = set(strength_catalog.available_exercise_ids(place, catalogue, group['constraints']['resources'])) if place else set()
    labels = {e['id']: e['label'] for e in catalogue['exercises']}
    pool, blocked = {}, set()
    def key(e):
        return (e['exercise_id'], e['side'])
    for e in evaluated['entries']:
        if e['eligible']:
            pool[key(e)] = {**deepcopy(e), 'source': {'kind': 'assessment',
                'artifact_id': context['receipt']['artifact']['artifact_id'],
                'content_hash': context['receipt']['artifact']['content_hash']}, 'observed_work_sets': None, 'feedback_reduced': False}
    preferred = set(pool)
    # A session log is an actual work-volume source, not another assessment.
    logs = sorted(data['strength_workout_context']['logs'], key=lambda r: (r['log']['artifact']['session']['started_at'], r['log']['artifact']['artifact_id']))
    for record in logs:
        a = record['log']['artifact']
        p = a['proposal']
        if p['purpose'] != 'training':
            continue
        feedback = [f['artifact']['proposal'] for f in record['feedback']]
        reduced = any(any(f.get(k) is not None and f[k] >= threshold for k, threshold in [('rpe', 9), ('fatigue', 7), ('soreness', 7)])
                      or f.get('recovery') is not None and f['recovery'] <= 3 for f in feedback)
        for e in p['exercises']:
            age = (date.fromisoformat(day) - date.fromisoformat(e['performed_on'])).days
            if e['location_id'] != location or not 0 <= age <= 56 or e['exercise_id'] not in available:
                continue
            k = key(e)
            if k in pool and e['performed_on'] < pool[k]['performed_on']:
                continue  # An older log cannot replace a newer exercise reference.
            if e['comfort'] in {'symptoms', 'avoid'} or any(s['symptoms'] in {'pain', 'discomfort'} or s['technique'] == 'breakdown' for s in e['sets']):
                blocked.add(e['exercise_id'])
                for old in [old for old, value in pool.items() if value['exercise_id'] == e['exercise_id']]:
                    pool.pop(old)
                continue
            all_safe = [s for s in e['sets'] if assessment.usable_sets({**e, 'sets': [s]})]
            safe = all_safe[:1]
            if e['familiarity'] not in {'independent', 'regular'} or e['comfort'] != 'none' or not safe:
                if k in pool:
                    pool[k]['feedback_reduced'] = True
                continue
            blocked.discard(e['exercise_id'])
            signature = lambda s: (s['load_kind'], float(s['load_value']) if s['load_value'] is not None else None, s['load_basis'], s['load_note'])
            matching = [s for s in all_safe if signature(s) == signature(safe[0]) and (s['repetitions'] is None) == (safe[0]['repetitions'] is None)]
            reference_set = min(matching, key=lambda s: float(s['repetitions'] if s['repetitions'] is not None else s['hold_seconds']))
            pool[k] = {'entry_id': e['id'], 'exercise_id': e['exercise_id'], 'label': labels[e['exercise_id']],
                'pattern': e['pattern'], 'location_id': location, 'performed_on': e['performed_on'], 'side': e['side'],
                'machine_note': e['machine_note'], 'sets': [deepcopy(reference_set)],
                'source': {'kind': 'workout_log', 'artifact_id': a['artifact_id'], 'content_hash': a['content_hash']},
                'observed_work_sets': len(matching), 'feedback_reduced': reduced or len(all_safe) != len(e['sets'])}
    offset = date.fromisoformat(day).toordinal() % len(assessment.PATTERNS)
    priority = assessment.PATTERNS[offset:] + assessment.PATTERNS[:offset]
    ordered = sorted(pool.values(), key=lambda e: (priority.index(e['pattern']), key(e) not in preferred, -date.fromisoformat(e['performed_on']).toordinal(), e['exercise_id'], e['entry_id']))
    mains, used = [], set()
    for e in ordered:
        if e['pattern'] not in used:
            mains.append(e)
            used.add(e['pattern'])
        if len(mains) == 2:
            break
    if len(mains) < 2:
        return None, ['STRENGTH_TWO_PATTERNS_REQUIRED', *(['STRENGTH_MOVEMENT_SYMPTOMS'] if blocked else []), *sorted({r for e in evaluated['entries'] if e['location_id'] == location for r in e['reasons']})]
    # Accessories need their OWN usable load/repetition reference. An unfamiliar
    # fly or pull-up cannot inherit the bench press's kg or repetition count.
    accessories = []
    for main in mains:
        candidates = [e for e in ordered if key(e) not in {key(m) for m in mains + accessories} and e['pattern'] == main['pattern']]
        candidates.sort(key=lambda e: ((e['exercise_id'] in VERTICAL_PULL) == (main['exercise_id'] in VERTICAL_PULL), e['exercise_id']))
        if candidates:
            accessories.append(candidates[0])
    return [{'entry': e, 'role': 'main' if e in mains else 'accessory'} for e in mains + accessories], []


def work_seconds(movements):
    count = sum(m['work_sets'] for m in movements)
    execution = sum(m['execution_seconds_per_set'] * m['work_sets'] for m in movements)
    rest = max((m['rest_seconds'] for m in movements), default=120)
    return execution + max(0, count - 1) * rest + max(0, len(movements) - 1) * 60


def make_dose(context, chosen, cap):
    regular = assessment.receipt_data(context)['experience'] == 'regular'
    movements = []
    for choice in chosen:
        e, role = choice['entry'], choice['role']
        source = e['sets'][0]
        count = (min(5, max(2, e['observed_work_sets'])) if e['observed_work_sets'] is not None and e['observed_work_sets'] >= 2 else 3 if regular else 2) if role == 'main' else 2
        if e['feedback_reduced']:
            count = max(1, count - 1)
        target = {k: source[k] for k in ['repetitions', 'hold_seconds', 'load_kind', 'load_value', 'load_basis', 'load_note']}
        movements.append({k: e[k] for k in ['entry_id', 'exercise_id', 'label', 'pattern', 'location_id', 'performed_on', 'side', 'machine_note']} | {
            'role': role, 'reference': {**e['source'], 'set_id': source['id']}, 'reference_set': deepcopy(source),
            'target': target, 'work_sets': count,
            'volume_basis': 'feedback_reduced' if e['feedback_reduced'] else 'observed_workout' if e['observed_work_sets'] is not None and e['observed_work_sets'] >= 2 and role == 'main' else 'literature_starting_rule',
            'observed_work_sets': e['observed_work_sets'], 'minimum_rir': 3,
            'rest_seconds': 180 if e.get('calibration_derivation') else 120,
            'execution_seconds_per_set': max(45, int(float(source['hold_seconds'] or 0)) * (2 if e['side'] == 'alternating' else 1)),
            'calibration_derivation': deepcopy(e.get('calibration_derivation'))})
    def duration():
        warm = 600 if sum(m['work_sets'] for m in movements) >= 6 else 300
        return ((warm + work_seconds(movements) + 300 + 299) // 300) * 300, warm
    desired, _ = duration()
    omitted = []
    while duration()[0] > cap and any(m['role'] == 'accessory' for m in movements):
        removed = movements.pop()
        omitted.append(removed['exercise_id'])
    while duration()[0] > cap and any(m['work_sets'] > 1 for m in movements):
        m = max(enumerate(movements), key=lambda v: (v[1]['work_sets'], v[0]))[1]
        m['work_sets'] -= 1
    seconds, warm = duration()
    if seconds > cap:
        return None
    return {'schema_version': SCHEMA, 'rules_version': RULES, 'assessment_reference': {
        'artifact_id': context['receipt']['artifact']['artifact_id'], 'content_hash': context['receipt']['artifact']['content_hash']},
        'movements': movements, 'duration_sec': max(1200, seconds), 'desired_duration_sec': max(1200, desired),
        'warmup_seconds': warm, 'cooldown_seconds': 300, 'work_seconds': work_seconds(movements),
        'shortened_for_time': seconds < desired, 'omitted_accessory_ids': omitted,
        'minimum_rir': 3, 'max_pattern_sets': 7, 'rest_between_sets_preserved': True,
        'load_increased': False, 'one_rm_estimated': False, 'personal_response_model_applied': False,
        'source_url': SOURCE}


def presentation(dose):
    minutes = dose['duration_sec'] // 60
    def text(m):
        t = m['target']
        reps = f"{t['repetitions']} ismétlés" if t['repetitions'] is not None else f"{t['hold_seconds']} mp tartás"
        basis = {'total': 'összesen', 'per_hand': 'kézenként', 'machine_display': 'gép kijelzése', 'assistance': 'rásegítés', 'not_applicable': '', 'unknown': ''}[t['load_basis']]
        if m['calibration_derivation'] and m['calibration_derivation']['load_kind'] == 'machine_plate_components':
            basis = 'felrakott tárcsák össztömege'
        load = 'saját testsúly' if t['load_kind'] == 'bodyweight' else t['load_note'] if t['load_kind'] == 'band' else f"{t['load_value']} {'fokozat' if t['load_kind'] == 'machine_level' else 'kg'} · {basis}"
        return f"{m['label']}: {m['work_sets']} × {reps}, {load}" + (f". Gép/beállítás: {m['machine_note']}" if m['machine_note'] else '')
    description = (f"{dose['warmup_seconds'] // 60} perc bemelegítés és ismert, könnyű rávezetés. " + ' | '.join(text(m) for m in dose['movements'])
        + '. A sorozatok között a táblázat szerinti teljes pihenő; legalább 3 szabályos ismétlés maradjon tartalékban. '
        'A terhelés saját referencia, a sorozatszám külön tervezett munkamennyiség. Az ismétlésszám felső cél, nem kifáradásig végzett teszt. '
        'Romló technika vagy panasz esetén állj meg. 5 perc levezetés. A megmaradt idő miatt ne adj hozzá sorozatot; nincs automatikus súlyemelés.')
    if dose['shortened_for_time']:
        description += ' Az időkeret miatt rövidített edzés: először a kiegészítők, majd munkasorozatok maradtak ki; a pihenő nem rövidült.'
    return {'title': f"Erőfejlesztés · {minutes} perc", 'description': description,
            'names': ['Bemelegítés és rávezető mozgások', 'Főgyakorlatok és saját referenciájú kiegészítők', 'Levezetés és edzésnapló']}


def parameterize(template, *, context, chosen, reference, available_seconds, block, preferred_seconds=None):
    cap = min(MAXIMUM, available_seconds)
    if cap < 1200:
        return None, 'OPPORTUNITY_OR_DAILY_MINUTE_CAP'
    dose = make_dose(context, chosen, cap)
    if not dose:
        return None, 'OPPORTUNITY_OR_DAILY_MINUTE_CAP'
    seconds = dose['duration_sec']
    p = presentation(dose)
    result = {**template, 'version': 'v0.5', 'minutes': seconds // 60, 'title': p['title'], 'description': p['description'],
              'blocks': [block(1, 'WARMUP', p['names'][0], dose['warmup_seconds']),
                         block(2, 'WORK', p['names'][1], seconds - dose['warmup_seconds'] - 300),
                         block(3, 'COOLDOWN', p['names'][2], 300)], 'strength_prescription': dose}
    metadata = {'schema_version': 'training-prescription-v0.6', 'family_key': assessment.FAMILY, 'duration_sec': seconds,
                'minimum_seconds': 1200, 'maximum_seconds': MAXIMUM, 'reference_session_ids': reference['session_ids'],
                'reference_cap_seconds': reference['recorded_cap_seconds'], 'assessment_duration_minutes': reference['declared_minutes'],
                'product_default_used': any(m['volume_basis'] == 'literature_starting_rule' for m in dose['movements']),
                'soft_duration_reduced': dose['shortened_for_time'], 'progression_applied': False,
                'personal_response_model_applied': False, 'intensity_basis': 'own_reference_independent_volume', 'strength': dose}
    return (result, metadata), None
