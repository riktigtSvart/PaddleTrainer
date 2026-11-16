"""Versioned qualitative paddling demand priorities; scores are product heuristics, not training percentages."""
from decimal import Decimal
import re

VERSION = 'paddling-event-demands-v0.1'
BASIS = 'paddling_demands_v0_1'
KEYS = ('VO2_CAPACITY', 'PERIPHERAL_OXIDATIVE_CAPACITY', 'PADDLING_ECONOMY', 'MAX_STRENGTH', 'POWER_RFD',
    'MUSCULOSKELETAL_ROBUSTNESS', 'TECHNICAL_SKILL', 'TECHNICAL_STABILITY_UNDER_FATIGUE', 'LONG_DURATION_DURABILITY',
    'PACING_COMPETENCE', 'SPRINT_SPEED_AND_START', 'MUSCULAR_ENDURANCE', 'HIGH_INTENSITY_AND_ANAEROBIC_PROFILE')
# Relative 1–5 demand scores, deliberately not energy-system or training-volume percentages.
VALUES = {
    'paddling_200': (3, 2, 4, 5, 5, 3, 5, 4, 1, 2, 5, 3, 5),
    'paddling_500': (4, 3, 4, 4, 4, 3, 5, 5, 1, 3, 4, 4, 5),
    'paddling_1000': (5, 4, 4, 4, 3, 3, 5, 5, 2, 4, 3, 4, 4),
    'paddling_long_distance': (5, 5, 5, 3, 2, 4, 5, 5, 5, 5, 3, 5, 3),
}
SOURCES = [
    {'key': 'icf-coaching', 'url': 'https://www.canoeicf.com/sites/default/files/icf_csp_coaches_manual_level_23_.pdf'},
    {'key': 'flatwater-distances-1991', 'url': 'https://pubmed.ncbi.nlm.nih.gov/1766347/'},
    {'key': 'marathon-power-2019', 'url': 'https://doi.org/10.23937/2469-5718/1510140'},
]


def template(profile, sport=''):
    if profile.get('distance_status') != 'specified' or profile.get('distance_value') is None:
        return None
    discipline = (profile.get('discipline', '') + ' ' + sport).casefold()
    if any(word in discipline for word in ('slalom', 'szlalom', 'polo', 'póló', 'wildwater', 'vadvíz', 'surfski', 'sárkány', 'dragon')):
        return None
    if not any(word in discipline for word in ('kajak', 'kayak', 'kenu', 'canoe')) and not re.search(r'\b[kc]\s?-?\s?[124]\b', discipline):
        return None
    distance = Decimal(profile['distance_value']) * (1000 if profile.get('distance_unit') == 'km' else 1)
    if distance in (200, 500, 1000) and profile.get('event_type') in ('sprint', 'other') and not any(word in discipline for word in ('maraton', 'marathon')):
        return 'paddling_' + str(int(distance))
    if Decimal(5000) <= distance <= Decimal(50000) and profile.get('event_type') in ('endurance', 'mixed', 'other'):
        return 'paddling_long_distance'
    return None


def suggest(profile, sport=''):
    key = template(profile, sport)
    return None if key is None else {'version': VERSION, 'template_key': key,
        'weights': dict(zip(KEYS, VALUES[key])), 'sources': SOURCES,
        'score_kind': 'qualitative_product_priority', 'training_percentages': False}
