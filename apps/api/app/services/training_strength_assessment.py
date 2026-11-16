"""Starting strength sessions copied from owned, reviewed assessment observations.

All numeric limits below are transparent product bounds, not a fitted response
model. A reference set is never multiplied into extra sets or converted to 1RM.
"""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services import guided_strength, strength_catalog
from app.services import initial_assessment as assessment
from app.services import initial_assessment_domain as intake
from app.services import strength_calibration_domain as calibration

SCHEMA = 'training-strength-assessment-v0.1'
RULES = 'assessment-strength-start-v0.1'
FAMILY = 'STRENGTH_REFERENCE_AND_DEVELOPMENT'
PATTERNS = ['pull', 'push', 'knee', 'hip', 'core']
MAX_SETS = 2
REST_SECONDS = 120
MINIMUM_SECONDS, MAXIMUM_SECONDS, DEFAULT_SECONDS = 1200, 1800, 1200


async def capture(*, session, repo, owner, user, data):
    # Use the athlete's civil day, never the server/browser time zone.
    today = datetime.fromisoformat(data['captured_at']).astimezone(ZoneInfo(user.timezone)).date().isoformat()
    current = await assessment.sources(repo, session, owner, user, today)
    saved = await assessment.latest(repo, session, owner)
    if saved and (saved[1].persisted_at > datetime.fromisoformat(data['captured_at'])
                  or datetime.fromisoformat(saved[0]['created_at']) > datetime.fromisoformat(data['captured_at'])):
        raise ValueError('STRENGTH_ASSESSMENT_SOURCE_AFTER_CAPTURE')
    activities = await guided_strength.planning_activities(repo, session, owner, datetime.fromisoformat(data['captured_at']))
    result = {'guided_activities': activities, 'schema_version': SCHEMA, 'rules_version': RULES, 'athlete_id': owner,
            'source_body': assessment.source_body(current), 'source_hash': current['source_hash'],
            'receipt': assessment.receipt(*saved, True) if saved else None,
            'planning_authorized': False, 'workouts_changed': False,
            'automatic_progression_applied': False, 'personal_response_model_applied': False}
    if saved and current['options_reference'] != saved[0]['snapshot']['options_reference']:
        result['options_source_receipt'] = current['options_receipt']
    profile_reference = {k: data['profile']['reference'][k] for k in ('artifact_id', 'content_hash')} if data.get('profile') else None
    if saved and current['profile_reference'] != saved[0]['snapshot']['profile_reference']:
        result['profile_source_receipt'] = current['profile_receipt']
    if current['profile_receipt'] is not None:
        result['current_profile_receipt'] = current['profile_receipt']
    if current['profile_reference'] != profile_reference:
        from app.planning.application import register_athlete_setup as setup
        latest_profile = await setup.latest(repo, session, owner, 'profile')
        if not latest_profile or assessment.reference(latest_profile[0]) != profile_reference:
            raise ValueError('STRENGTH_ASSESSMENT_PROFILE_CHANGED_RETRY')
        result['current_profile_receipt'] = setup.receipt(*latest_profile, True)
    if current['options_reference'] != data.get('training_options_reference'):
        # Keep the current full options and the assessment-relevant revision
        # independently verifiable, including coordinate-only saves without an
        # active daylight context. Historical receipts are never rewritten.
        frozen = saved[0]['snapshot']['options_reference'] if saved else None
        if frozen != current['options_reference']:
            result['options_source_receipt'] = current['options_receipt']
        if not data.get('daylight_context'):
            from app.services import training_options
            latest_options = await training_options.latest(repo, session, owner)
            if latest_options is None or training_options.reference(latest_options[0]) != data.get('training_options_reference'):
                raise ValueError('STRENGTH_ASSESSMENT_OPTIONS_CHANGED_RETRY')
            result['current_options_receipt'] = training_options.receipt(*latest_options, True)
    evidence = await guided_strength.calibration_evidence(repo, session, owner, datetime.fromisoformat(data['captured_at']))
    if evidence:
        result['calibration_evidence'] = evidence
    from app.services.assessment_source_compatibility import compare
    result['source_comparison'] = compare(result)
    from app.services.assessment_profile_compatibility import compare as compare_profile
    result['profile_comparison'] = compare_profile(result)
    return result


def calibration_targets(context):
    targets, measured_ids = {}, set()
    for receipt in reversed(context.get('calibration_evidence', [])):
        measured_ids.update(v['id'] for v in calibration.observed(receipt['artifact']['proposal']['progress']))
        for target in calibration.starter_targets(receipt):
            targets[target['entry_id']] = target
    return targets, measured_ids


def receipt_data(context):
    receipt = context.get('receipt')
    return receipt['artifact']['proposal']['data'] if receipt else None


def global_issues(context, data, sport):
    value = receipt_data(context)
    if value is None:
        return ['STRENGTH_ASSESSMENT_MISSING']
    artifact = context['receipt']['artifact']
    issues = []
    from app.services.assessment_source_compatibility import compare
    if artifact['proposal']['source_hash'] != context['source_hash'] and not compare(context)['reusable']:
        issues.append('STRENGTH_ASSESSMENT_SOURCES_CHANGED')
    if value['program_reference'] is not None and value['program_reference'] != data['program_reference']:
        issues.append('STRENGTH_ASSESSMENT_PROGRAM_MISMATCH')
    roles = {v['sport_key']: v['role'] for v in value['sports']}
    if roles.get('STRENGTH') not in {'primary', 'secondary'} or roles.get(sport) != 'primary':
        issues.append('STRENGTH_ASSESSMENT_SPORT_ROLE_REQUIRED')
    if not value['reviewed'] or not value['references_reviewed']:
        issues.append('STRENGTH_ASSESSMENT_REVIEW_REQUIRED')
    if value['state_change'] != 'unchanged':
        issues.append('STRENGTH_ASSESSMENT_STATE_REVIEW')
    guided_reference = any(v['artifact']['state'] == 'finished' and v['artifact']['assessment_reference'] == assessment.reference(artifact) for v in context.get('guided_activities', []))
    if (value['experience'] == 'unknown' or value['experience'] == 'none' and not guided_reference) or value['strength_frequency'] == 'unknown' or value['supervision'] in {'unknown', 'needed'}:
        issues.append('STRENGTH_ASSESSMENT_HISTORY_REVIEW')
    if artifact['snapshot']['profile_review'] is None or artifact['snapshot']['profile_review']['global_entry_gate'] != 'OPEN':
        issues.append('STRENGTH_ASSESSMENT_STATE_REVIEW')
    return list(dict.fromkeys(issues))


def usable_sets(entry):
    """Copy actual qualifying observations, including their original set IDs."""
    result = []
    for row in entry['sets']:
        dose = (row['repetitions'] is not None and 1 <= row['repetitions'] <= 15
                or row['hold_seconds'] is not None and 0 < Decimal(row['hold_seconds']) <= 60)
        load = (row['load_kind'] == 'bodyweight'
                or row['load_kind'] == 'band' and bool(row['load_note'].strip())
                or row['load_kind'] in {'external_kg', 'machine_level'} and row['load_value'] is not None and Decimal(row['load_value']) > 0 and row['load_basis'] != 'unknown'
                or row['load_kind'] == 'assistance_kg' and row['load_value'] is not None and row['load_basis'] == 'assistance')
        machine = row['load_kind'] in {'machine_level', 'assistance_kg'} or row['load_basis'] == 'machine_display'
        if dose and load and (not machine or entry['machine_note'].strip()) and row['rir'] in {'3', '4', '5_plus'} and row['technique'] == 'stable' and row['symptoms'] == 'none':
            result.append(dict(row))
    return result[:MAX_SETS]


def evaluate(context, data, sport, day, location_id=None, resources=None):
    issues = global_issues(context, data, sport)
    receipt = context.get('receipt')
    entries = []
    targets, measured_ids = calibration_targets(context)
    if receipt:
        artifact = receipt['artifact']
        value = artifact['proposal']['data']
        saved_summary = intake.summary(value, artifact['snapshot'], day)
        states = {e['id']: e for e in saved_summary['exercise_states']}
        exercises = {e['id']: e for e in artifact['snapshot']['catalog']['exercises']}
        place = next((p for p in artifact['snapshot']['locations'] if p['id'] == location_id), None)
        available = set(strength_catalog.available_exercise_ids(place, artifact['snapshot']['catalog'], resources or [])) if place else set()
        for entry in value['exercises']:
            reasons = list(states[entry['id']]['reasons'])
            if states[entry['id']]['state'] == 'avoid':
                reasons.append('STRENGTH_MOVEMENT_SYMPTOMS')
            if entry['side'] == 'unknown':
                reasons.append('STRENGTH_EXECUTION_SIDE_REQUIRED')
            sets = usable_sets(entry)
            target = targets.get(entry['id'])
            if any(v['id'] in measured_ids for v in entry['sets']):
                matches = target and all(entry[k] == target[k] for k in ['exercise_id', 'location_id', 'performed_on', 'side', 'machine_note']) and entry['sets'] == target['actual_sets']
                sets = target['sets'] if matches else []
            if not sets:
                reasons.append('STRENGTH_QUALIFYING_SET_REQUIRED')
            if location_id is not None:
                if entry['location_id'] != location_id:
                    reasons.append('STRENGTH_REFERENCE_AT_OTHER_LOCATION')
                if entry['exercise_id'] not in available:
                    reasons.append('STRENGTH_LOCATION_EQUIPMENT_MISSING')
            if entry['exercise_id'] is not None:
                label = exercises[entry['exercise_id']]['label']
            else:
                label = next(p['label'] for p in artifact['snapshot']['registry']['patterns'] if p['key'] == entry['pattern'])
            evaluated = {'entry_id': entry['id'], 'exercise_id': entry['exercise_id'], 'label': label,
                            'pattern': entry['pattern'], 'location_id': entry['location_id'],
                            'performed_on': entry['performed_on'], 'side': entry['side'], 'machine_note': entry['machine_note'],
                            'eligible': not issues and not reasons and states[entry['id']]['state'] == 'recorded_reference',
                            'reasons': list(dict.fromkeys(reasons)), 'sets': sets}
            if target and sets == target['sets']:
                evaluated['calibration_derivation'] = target['derivation']
            entries.append(evaluated)
    return {'issues': issues, 'entries': entries}


def selection(context, data, sport, day, group):
    location_id = group['constraints'].get('location_id')
    if not location_id:
        return None, ['STRENGTH_NAMED_LOCATION_REQUIRED']
    evaluated = evaluate(context, data, sport, day, location_id, group['constraints']['resources'])
    if evaluated['issues']:
        return None, evaluated['issues']
    eligible = [e for e in evaluated['entries'] if e['eligible']]
    offset = date.fromisoformat(day).toordinal() % len(PATTERNS)
    priority = PATTERNS[offset:] + PATTERNS[:offset]
    eligible.sort(key=lambda e: (priority.index(e['pattern']), -date.fromisoformat(e['performed_on']).toordinal(), e['exercise_id'], e['entry_id']))
    chosen, used = [], set()
    for entry in eligible:
        if entry['pattern'] not in used:
            chosen.append(entry)
            used.add(entry['pattern'])
        if len(chosen) == 2:
            break
    if len(chosen) < 2:
        details = sorted({code for e in evaluated['entries'] if e['location_id'] == location_id for code in e['reasons']})
        return None, ['STRENGTH_TWO_PATTERNS_REQUIRED', *details]
    return chosen, []


def duration_reference(reference, context):
    declared = (receipt_data(context) or {}).get('usual_strength_minutes')
    caps = [v for v in [reference['cap_seconds'], declared * 60 if declared is not None else None] if v is not None]
    cap = min(caps) if caps else None
    return {**reference, 'cap_seconds': cap if cap is not None else DEFAULT_SECONDS,
            'recorded_cap_seconds': reference['cap_seconds'], 'declared_minutes': declared,
            'product_default_used': not caps}


def parameterize(template, *, context, chosen, reference, available_seconds, block, preferred_seconds=None):
    if reference['cap_seconds'] < MINIMUM_SECONDS:
        return None, 'PERSONAL_DURATION_REFERENCE_TOO_SHORT'
    seconds = min(available_seconds, reference['cap_seconds'], MAXIMUM_SECONDS)
    seconds = int(seconds // 300) * 300
    if type(preferred_seconds) is int and preferred_seconds % 300 == 0 and MINIMUM_SECONDS <= preferred_seconds <= seconds:
        seconds = preferred_seconds
    if seconds < MINIMUM_SECONDS:
        return None, 'OPPORTUNITY_OR_DAILY_MINUTE_CAP'
    receipt = context['receipt']['artifact']
    movements = [{k: e[k] for k in ('entry_id', 'exercise_id', 'label', 'pattern', 'location_id', 'performed_on', 'side', 'machine_note', 'sets')} for e in chosen]
    prescription = {'schema_version': 'assessed-strength-dose-v0.1', 'rules_version': RULES,
                    'assessment_reference': assessment.reference(receipt), 'source_kind': 'self_report',
                    'movements': movements, 'max_sets_per_movement': MAX_SETS, 'rest_seconds': REST_SECONDS,
                    'minimum_rir': 3, 'load_increased': False, 'sets_added': False, 'one_rm_estimated': False,
                    'full_development_claim': False}
    derivations = [{'entry_id': e['entry_id'], **e['calibration_derivation']} for e in chosen if e.get('calibration_derivation')]
    if derivations:
        prescription['calibration_derivations'] = derivations
        prescription['rest_seconds'] = 180
    def set_text(row, entry_id):
        amount = f"{row['repetitions']} ismétlés" if row['repetitions'] is not None else f"{row['hold_seconds']} másodperc"
        basis = {'total': 'összsúly', 'per_hand': 'kézenként', 'machine_display': 'gép kijelzése', 'assistance': 'rásegítés', 'not_applicable': '', 'unknown': ''}[row['load_basis']]
        if any(v['entry_id'] == entry_id and v['load_kind'] == 'machine_plate_components' for v in derivations):
            basis = 'felrakott tárcsák össztömege'
        load = ('saját testsúly' if row['load_kind'] == 'bodyweight' else row['load_note'] if row['load_kind'] == 'band'
                else f"{row['load_value']} {'fokozat' if row['load_kind'] == 'machine_level' else 'kg'} · {basis}")
        return f'{amount}, {load}'
    side_labels = {'both': 'kétoldali', 'left': 'bal oldal', 'right': 'jobb oldal', 'alternating': 'váltott oldal'}
    descriptions = [f"{e['label']} ({side_labels[e['side']]}): " + '; '.join(set_text(s, e['entry_id']) for s in e['sets']) + (f". Gép/beállítás: {e['machine_note']}" if e['machine_note'] else '') for e in movements]
    result = {**template, 'version': 'v0.3', 'minutes': seconds // 60,
              'title': f"Saját erőreferenciák · {seconds // 60} perces időkeret",
              'description': '5 perc ismert bemelegítés. ' + ' | '.join(descriptions) + '. Sorozatok között legalább 2 perc nyugodt pihenő; az ismétléses sorozatoknál legalább 3 szabályos ismétlés tartalék maradjon. A tartás is maradjon kényelmes, kifáradás nélkül. Ha a technika romlik, panasz jelentkezik vagy elfogy a kényelmes idő, hagyd el a hátralévő részt. 5 perc levezetés. Az időkeret a pihenőket is tartalmazza; nem kitöltendő munkadózis. A súlyok és sorozatok a mentett saját referenciából származnak; nincs automatikus emelés.',
              'blocks': [block(1, 'WARMUP', 'Ismert bemelegítés', 300),
                         block(2, 'WORK', ' / '.join(e['label'] for e in movements) + ' · rögzített sorozatok, pihenőkkel', seconds - 600),
                         block(3, 'COOLDOWN', 'Levezetés és terhelésnapló', 300)],
              'strength_prescription': prescription}
    if derivations:
        result['title'] = f"Erőfelmérésből induló edzés · {seconds // 60} perces időkeret"
        result['description'] = ('5 perc ismert bemelegítés. ' + ' | '.join(descriptions)
            + '. Az új kalibrálásból gyakorlatonként egy kezdő sorozat készült: a mért ismétlésszámnál kettővel kevesebb, legfeljebb nyolc ismétlés, azonos terheléssel. '
            'Ez felülvizsgálható kezdő alkalmazásszabály, nem mért sorozatkapacitás. A sorozatok között 3 perc pihenő. '
            'Legalább 3 szabályos ismétlés tartalék maradjon; ha ez nem tartható, előbb állj meg. Panasz vagy romló kontroll esetén hagyd el a hátralévő részt. '
            '5 perc levezetés. Az időkeret felső határ, nem kitöltendő munkamennyiség. Nincs automatikus súly- vagy sorozatszám-emelés.')
    metadata = {'schema_version': 'training-prescription-v0.2', 'family_key': FAMILY, 'duration_sec': seconds,
                'minimum_seconds': MINIMUM_SECONDS, 'maximum_seconds': MAXIMUM_SECONDS,
                'reference_session_ids': reference['session_ids'], 'reference_cap_seconds': reference['recorded_cap_seconds'],
                'assessment_duration_minutes': reference['declared_minutes'],
                'product_default_used': reference['product_default_used'], 'soft_duration_reduced': False,
                'progression_applied': False, 'personal_response_model_applied': False,
                'intensity_basis': 'reviewed_assessment_sets', 'strength': prescription}
    return (result, metadata), None


def summary(context, data, sport, today):
    evaluated = evaluate(context, data, sport, today)
    return {'schema_version': SCHEMA, 'rules_version': RULES,
            'reference': assessment.reference(context['receipt']['artifact']) if context.get('receipt') else None,
            'issues': evaluated['issues'], 'exercise_readiness': [{k: v for k, v in e.items() if k != 'sets'} for e in evaluated['entries']],
            'source_kind': 'self_report', 'automatic_progression_applied': False,
            'personal_response_model_applied': False, 'workouts_changed': False}
