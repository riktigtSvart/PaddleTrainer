"""Concrete preparatory routines inside the existing time envelope.

Work sets are copied from the verified prescription. No new weight, repetition
target, recovery effect or capacity gain is inferred by this presentation layer.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

SCHEMA = 'workout-instructions-v0.1'
LIBRARY_FILE = Path(__file__).parent / 'data/training_routines_v0_1.json'


@lru_cache(maxsize=1)
def library():
    return json.loads(LIBRARY_FILE.read_text(encoding='utf-8'))


def derive(candidate, metadata):
    return _derive(candidate, metadata, library())


def _derive(candidate, metadata, routines):
    routine = routines['sports'][candidate['sport']]
    blocks = candidate['blocks']
    warm, finish = blocks[0]['duration_sec'], blocks[-1]['duration_sec']
    strength = metadata.get('strength')
    if not isinstance(strength, dict) or strength.get('schema_version') not in {'assessed-strength-dose-v0.1', 'strength-workout-dose-v0.1'}:
        strength = None
    independent = strength is not None and strength.get('schema_version') == 'strength-workout-dose-v0.1'
    return {'schema_version': SCHEMA, 'library_version': 'training-routines-v0.2' if independent else routines['schema_version'],
        'sport': candidate['sport'], 'duration_sec': candidate['duration_sec'],
        'source_kind': 'verified_prescription_and_product_routines',
        'warmup': {'duration_sec': warm, 'purpose': 'Fokozatos ráhangolás és kontrollált átmozgatás.',
            'steps': [{'name': routine['easy'], 'duration_sec': 90,
                       'instruction': 'Kényelmes, könnyű erőfeszítés; a légzés maradjon nyugodt.'},
                      {'name': routine['gym'], 'duration_sec': 90, 'instruction': routine['gym_instruction']},
                      {'name': 'Ismert sportmozgás előkészítése', 'duration_sec': warm-180, 'instruction': ('A főgyakorlatok ismert, fokozatos, könnyű rávezetését végezd. Csak már bevált terhelést használj, kifáradás nélkül; ne ugorj közvetlenül a munkasúlyra. A rávezető sorozatok nem munkasorozatok. Ha a szokásos előkészítés nem fér bele, hagyd el a hátralévő munkát.' if independent else routine['specific'])}]},
        'main': {'duration_sec': sum(b['duration_sec'] for b in blocks[1:-1]), 'instruction': candidate['description'],
                 'strength': deepcopy(strength), 'introductory_strength': deepcopy(metadata.get('introductory_strength'))},
        'finish': {'duration_sec': finish, 'easy_duration_sec': finish-120,
            'purpose': 'Könnyű levezetés; a választható nyújtás célja a mozgástartomány gyakorlása.',
            'stretching_optional': True, 'stretching_replaces_easy_finish': True,
            'stretches': [{'key': key, 'name': name, 'duration_sec': 60, 'instruction': instruction}
                          for key, name, instruction in routine['stretches']],
            'instruction': 'Először nagyon könnyű sportmozgás vagy séta. A két választható nyújtás a levezetés utolsó két percének alternatívája, nem többletidő. Ha a helyszín, az idő vagy a mozdulat nem megfelelő, maradj könnyű mozgásnál vagy fejezd be. Enyhe húzódásig dolgozz, fájdalom és rugóztatás nélkül.'},
        'stop_rule': 'Csak ismert, panaszmentes mozdulatot végezz. Romló kontroll, fájdalom vagy szokatlan rosszullét esetén állj meg; az időkeretet nem kell kitölteni.',
        'external_load_increased': False, 'sets_added': False, 'recovery_effect_claimed': False,
        'personal_response_model_applied': False, 'source_urls': routines['source_urls']}


@lru_cache(maxsize=1)
def _legacy_libraries():
    """Only reproduce the two known pre-fix Windows interpretations of v0.1.

    This never decodes an athlete's prose or changes a captured source record.
    Full expected-object equality below keeps work sets and times unchanged.
    """
    raw = LIBRARY_FILE.read_bytes()
    result = []
    for encoding in ('cp1250', 'cp1252'):
        try:
            result.append(json.loads(raw.decode(encoding)))
        except (UnicodeError, ValueError):
            continue
    return result


def matches_stored(stored, candidate, metadata):
    if stored == derive(candidate, metadata):
        return True
    return any(stored == _derive(candidate, metadata, old) for old in _legacy_libraries())


def attach(result):
    candidates = {c['candidate_key']: c for c in result['proposals']}
    metadata = result['prescription_context']['by_candidate']
    result['instruction_context'] = {'schema_version': 'training-instructions-v0.1',
        'by_candidate': {key: derive(c, metadata[key]) for key, c in candidates.items()}}
    return result
