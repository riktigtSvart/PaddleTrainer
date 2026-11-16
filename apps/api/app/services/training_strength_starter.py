"""A labelled introductory default, never invented assessed sets or kilograms.

Healthy-adult RT participation is supported by ACSM 2026. The small rehearsal
bounds here are product defaults, not a validated personalized strength dose.
"""
from app.planning.domain.athlete_setup import review_profile
from app.services import training_strength_assessment as assessed

RULES = 'introductory-strength-v0.1'
ALLOWED_GAPS = {'STRENGTH_ASSESSMENT_MISSING', 'STRENGTH_ASSESSMENT_HISTORY_REVIEW'}
MOVEMENTS = [
    {'key': 'shallow_squat', 'label': 'Kényelmes részleges guggolás', 'instruction': 'Csak kényelmes mélységig ereszkedj, majd állj fel; a térd kövesse a lábfej irányát.'},
    {'key': 'unloaded_hip_hinge', 'label': 'Csípőhajlítás állva, külső teher nélkül', 'instruction': 'Enyhén hajlított térddel told hátra a csípőt, tartsd kényelmesen a hátad, majd egyenesedj fel.'},
    {'key': 'standing_scapular_control', 'label': 'Lapockazárás állva', 'instruction': 'Külső teher nélkül közelítsd finoman a lapockákat, a vállakat ne húzd a füledhez, majd lazíts.'},
]


def allowed(context, data):
    profile = (data.get('profile') or {}).get('data')
    if not profile or review_profile(profile, data['local_today'])['global_entry_gate'] != 'OPEN':
        return False
    from app.services.training_prescriptions import sport_code
    if not set(assessed.global_issues(context, data, sport_code(data['program_sport']))) <= ALLOWED_GAPS:
        return False
    value = assessed.receipt_data(context) or {}
    if value.get('supervision') == 'needed':
        return False
    if value.get('usual_strength_minutes') is not None and value['usual_strength_minutes'] < 20:
        return False
    return not any(e.get('comfort') in {'symptoms', 'avoid', 'uncertain'} or any(s.get('symptoms') in {'pain', 'discomfort'} for s in e.get('sets', [])) for e in value.get('exercises', []))


def parameterize(template, *, context, data, available_seconds, reference, block):
    if reference['cap_seconds'] is not None and reference['cap_seconds'] < 1200:
        return None, 'PERSONAL_DURATION_REFERENCE_TOO_SHORT'
    if available_seconds < 1200:
        return None, 'OPPORTUNITY_OR_DAILY_MINUTE_CAP'
    if not allowed(context, data):
        return None, 'STRENGTH_ASSESSMENT_REVIEW_REQUIRED'
    movements = [dict(m) for m in MOVEMENTS]
    work = ' / '.join(m['label'] for m in movements)
    description = ('Erőfejlesztést előkészítő, könnyű technikai alkalom, számszerű erőreferencia nélkül. '
                   '5 perc könnyű séta és kényelmes ízületi átmozgatás. A főrészben gyakorlatonként egy sorozat, legfeljebb 5 lassú, könnyű ismétlés: '
                   + ' | '.join(m['label'] + ': ' + m['instruction'] for m in movements)
                   + ' A gyakorlatok között 1–2 perc nyugodt pihenő. Maradj RPE 2–3/10 erőfeszítésnél; külső súlyt ne használj. '
                   'Az ismeretlen, bizonytalan vagy panaszt okozó mozdulatot hagyd ki; ilyenkor maradj könnyű sétánál vagy fejezd be. '
                   '5 perc levezetés. A 20 perc felső időkeret, a pihenőkkel együtt; nem kell kitölteni. '
                   'Ez bevezető gyakorlás, nem maximáliserő-teszt vagy mért kapacitásból számított fejlesztési dózis.')
    dose = {'schema_version': 'introductory-strength-v0.1', 'rules_version': RULES, 'source_kind': 'literature_and_product_default',
            'profile_reference': {k: data['profile']['reference'][k] for k in ('artifact_id', 'content_hash')},
            'assessment_reference': assessed.assessment.reference(context['receipt']['artifact']) if context.get('receipt') else None,
            'movements': movements, 'sets_per_movement': 1, 'max_repetitions': 5, 'rest_seconds': {'min': 60, 'max': 120},
            'external_load_prescribed': False, 'one_rm_estimated': False, 'progression_applied': False, 'preparatory_only': True,
            'full_development_claim': False, 'source_url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/'}
    result = {**template, 'version': 'v0.4', 'effort': 'easy', 'minutes': 20, 'title': 'Bevezető erőnléti gyakorlás · 20 perces időkeret',
              'description': description, 'blocks': [block(1, 'WARMUP', 'Könnyű séta és átmozgatás', 300),
                  block(2, 'WORK', work + ' · 1 sorozat, legfeljebb 5 könnyű ismétlés', 600), block(3, 'COOLDOWN', 'Könnyű levezetés', 300)]}
    metadata = {'schema_version': 'training-prescription-v0.5', 'family_key': assessed.FAMILY, 'duration_sec': 1200,
                'minimum_seconds': 1200, 'maximum_seconds': 1200, 'reference_session_ids': [], 'reference_cap_seconds': None,
                'product_default_used': True, 'soft_duration_reduced': False, 'progression_applied': False,
                'personal_response_model_applied': False, 'intensity_basis': 'introductory_product_default',
                'rpe': {'min': 2, 'max': 3}, 'introductory_strength': dose}
    return (result, metadata), None
