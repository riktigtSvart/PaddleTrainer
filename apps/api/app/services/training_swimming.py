"""Pool swimming from declared skill and current evidence, never an old peak pace."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

FAMILY = "SWIM_EASY_AEROBIC"
STROKES = {"freestyle": "gyorsúszás", "breaststroke": "mellúszás", "backstroke": "hátúszás", "butterfly": "pillangóúszás"}


def declared_ability(data):
    """An explicit swimming answer wins; otherwise reuse current sport skill.

    Proficiency declares independent skill, never a pace or continuous capacity.
    A generic/mixed discipline does not imply a particular stroke is known.
    """
    settings = options(data).get('prescription_settings') or {}
    if settings.get('swimming') is not None:
        return settings['swimming'], None
    profile = data.get('profile') or {}
    history = (profile.get('data') or {}).get('sport_history', [])
    from app.services.training_prescriptions import sport_code
    code = lambda value: next((sport_code(part.strip()) for part in str(value).split('/') if sport_code(part.strip())), None)
    target = code(data.get('program_sport'))
    eligible = [(index, row) for index, row in enumerate(history) if code(row.get('sport')) == 'SWIMMING'
                and row.get('current') is True and row.get('role') in {'primary', 'secondary'}
                and (row.get('role') == 'primary' or not (row.get('planning') or {}).get('supported_sports')
                     or any(code(sport) == target for sport in row['planning']['supported_sports']))]
    if any((row.get('planning') or {}).get('proficiency') == 'learning' for _, row in eligible):
        return None, None
    for index, row in eligible:
        proficiency = (row.get('planning') or {}).get('proficiency')
        if proficiency not in {'independent', 'experienced'}:
            continue
        discipline = row.get('discipline', '').strip().casefold()
        aliases = {'freestyle': {'gyors', 'gyorsúszás', 'freestyle', 'crawl'}, 'breaststroke': {'mell', 'mellúszás', 'breaststroke'},
                   'backstroke': {'hát', 'hátúszás', 'backstroke'}, 'butterfly': {'pillangó', 'pillangóúszás', 'butterfly'}}
        preferred = next((key for key, names in aliases.items() if discipline in names), 'self_selected')
        reference = profile['reference']
        reported = datetime.fromisoformat(reference['available_at']).astimezone(ZoneInfo(data['timezone_name'])).date().isoformat()
        skill = {'reported_on': reported, 'independent': True, 'strokes': [preferred] if preferred in STROKES else [],
                 'preferred_stroke': preferred, 'continuous_minutes': None, 'continuous_distance_m': None}
        basis = {'kind': 'sport_history', 'profile_reference': {k: reference[k] for k in ('artifact_id', 'content_hash')},
                 'history_index': index, 'proficiency': proficiency}
        return skill, basis
    return None, None


def options(data):
    return (data.get("daylight_context") or {}).get("options_receipt", {}).get("artifact", {}).get("proposal", {}).get("data", {})


def template(block):
    return {"key": FAMILY, "sport": "SWIMMING", "minutes": 30, "title": "Könnyű aerob úszás",
        "effort": "easy", "capabilities": ["PERIPHERAL_OXIDATIVE_CAPACITY"], "description": "",
        "blocks": [block(1, "WARMUP", "Bemelegítés", 300), block(2, "WORK", "Könnyű úszás", 1200), block(3, "COOLDOWN", "Levezetés", 300)]}


def reference(data, completed):
    skill, basis = declared_ability(data)
    today = datetime.fromisoformat(data["captured_at"]).astimezone(ZoneInfo(data["timezone_name"])).date()
    recent = [s for s in completed if s["sport"] == "SWIMMING" and not s.get("reference_occasion") and s["duration_sec"] >= 1200][:3]
    fresh = bool(skill and today - timedelta(days=56) <= datetime.fromisoformat(skill["reported_on"]).date() <= today)
    continuous = bool(fresh and ((skill.get("continuous_minutes") or 0) >= 10 or (skill.get("continuous_distance_m") or 0) >= 1000))
    observed_cap = min((s["duration_sec"] for s in recent), default=None)
    declared_cap = (skill["continuous_minutes"] + 10) * 60 if continuous and skill.get("continuous_minutes") else None
    caps = [v for v in [observed_cap, declared_cap] if v is not None]
    cap = min(caps) if caps else 1800 if continuous else 1200
    return {"session_ids": [s["id"] for s in recent], "cap_seconds": cap,
        "anchor_id": next((s["id"] for s in recent if s["duration_sec"] == observed_cap), None),
        "swimming": {"skill": skill, "fresh": fresh, "mode": "self_paced" if basis else "continuous" if continuous else "length_repeats", "ability_basis": basis,
            "observed_cap_seconds": observed_cap, "declared_cap_seconds": declared_cap,
            "product_default_used": not caps, "options_reference": data.get("training_options_reference")}}


def parameterize(template, *, available_seconds, reference, block, location, preferred_seconds=None):
    context = reference["swimming"]
    skill = context["skill"]
    if not skill or not skill["independent"]:
        return None, "SWIMMING_ABILITY_REQUIRED"
    if context.get('ability_basis') and (not location or 'Úszómedence' not in location['resources']):
        return None, 'SWIMMING_POOL_REQUIRED'
    if not location or (not location.get("pool_length_m") and not context.get('ability_basis')) or "Úszómedence" not in location["resources"]:
        return None, "SWIMMING_POOL_LENGTH_REQUIRED"
    if context.get('ability_basis'):
        return profile_parameterize(template, available_seconds=available_seconds, reference=reference, block=block, location=location, preferred_seconds=preferred_seconds)
    pool = Decimal(location["pool_length_m"])
    cap = min(available_seconds, reference["cap_seconds"], 3600)
    seconds = int(cap // 300) * 300
    if type(preferred_seconds) is int and preferred_seconds % 300 == 0 and 1200 <= preferred_seconds <= cap:
        seconds = preferred_seconds
    if seconds < 1200:
        return None, "PERSONAL_DURATION_REFERENCE_TOO_SHORT" if reference["cap_seconds"] < 1200 else "OPPORTUNITY_OR_DAILY_MINUTE_CAP"
    mode = context["mode"]
    # A known short continuous limit must not be turned into two longer lengths.
    limit = skill.get("continuous_distance_m") if context["fresh"] else None
    lengths = 2 if limit is not None and Decimal(limit) >= 2 * pool else 1
    if limit is not None and Decimal(limit) < pool:
        return None, "SWIMMING_CONTINUOUS_LIMIT_BELOW_POOL_LENGTH"
    stroke = STROKES[skill["preferred_stroke"]]
    work_minutes = (seconds - 600) // 60
    work = f"{work_minutes} perc folyamatos, könnyű {stroke}, szükség szerint pihenővel" if mode == "continuous" else f"{lengths} medencehossz könnyű {stroke}, majd 30 másodperc pihenő; ismételd az időkeretben"
    title = "Folyamatos könnyű úszás" if mode == "continuous" else "Könnyű úszás rövid szakaszokban"
    description = f"Medence: {location['pool_length_m']} m. 5 perc fokozatos, könnyű úszás bemelegítésként; {work}; 5 perc nagyon könnyű levezetés. RPE 2–3/10, egyenletes, kényelmes légzéssel. A teljes időkeret a pihenőket is tartalmazza. Egész medencehosszakat ússz; új hosszt csak akkor kezdj, ha várhatóan belefér a maradék időbe. Nem kell mindenáron kitölteni a keretet; szükség szerint pihenj, rövidíts, panasz esetén állj meg. Nincs régi csúcsból vagy pillanatnyi óra-sebességből számolt tempó- vagy pulzuscél."
    if mode == "continuous":
        description += " Nem szükséges minden 50 méter után megállnod; a folyamatos végrehajtás a most megadott kényelmes teljesítésedre épül."
        if skill.get("continuous_distance_m"):
            description += f" Egy folyamatos szakasz legfeljebb {skill['continuous_distance_m']} méter legyen; a táv vagy az időkeret elérésekor tarts pihenőt."
    dose = {"schema_version": "swimming-prescription-v0.1", "mode": mode, "stroke": skill["preferred_stroke"],
        "pool_length_m": location["pool_length_m"], "lengths_per_repeat": None if mode == "continuous" else lengths,
        "rest_seconds": None if mode == "continuous" else 30, "source_kind": "self_report_and_stored_durations",
        "reported_on": skill["reported_on"], "report_is_recent": context["fresh"], "options_reference": context["options_reference"],
        "observed_cap_seconds": context["observed_cap_seconds"], "declared_cap_seconds": context["declared_cap_seconds"],
        "continuous_distance_limit_m": skill.get("continuous_distance_m") if context["fresh"] else None,
        "pace_estimated": False, "current_capacity_measured": False}
    result = {**template, "version": "v0.1", "minutes": seconds // 60, "title": f"{title} · {seconds // 60} perc", "description": description,
        "blocks": [block(1, "WARMUP", "Könnyű úszás bemelegítésként", 300), block(2, "WORK", work, seconds - 600), block(3, "COOLDOWN", "Nagyon könnyű levezető úszás", 300)]}
    metadata = {"schema_version": "training-prescription-v0.4", "family_key": FAMILY, "duration_sec": seconds,
        "minimum_seconds": 1200, "maximum_seconds": 3600, "reference_session_ids": reference["session_ids"],
        "reference_cap_seconds": context["observed_cap_seconds"], "product_default_used": context["product_default_used"],
        "soft_duration_reduced": seconds < 1800, "progression_applied": False, "personal_response_model_applied": False,
        "intensity_basis": "product_default_not_personal_threshold", "rpe": {"min": 2, "max": 3}, "swimming": dose}
    return (result, metadata), None


def profile_parameterize(template, *, available_seconds, reference, block, location, preferred_seconds=None):
    context = reference['swimming']
    skill = context['skill']
    cap = min(available_seconds, reference['cap_seconds'], 3600)
    seconds = int(cap // 300) * 300
    if type(preferred_seconds) is int and preferred_seconds % 300 == 0 and 1200 <= preferred_seconds <= cap:
        seconds = preferred_seconds
    if seconds < 1200:
        return None, 'OPPORTUNITY_OR_DAILY_MINUTE_CAP'
    stroke = STROKES.get(skill['preferred_stroke'], 'választott, ismert úszásnem')
    work = f"{(seconds - 600) // 60} perc könnyű úszás · {stroke}, saját szakaszokkal és szükség szerinti pihenővel"
    description = ('A mentett sportelőéletben önálló/rutinos úszást jelöltél. 5 perc fokozatos, könnyű bemelegítés; '
                   + work + '; 5 perc nagyon könnyű levezetés. Nem szükséges minden 50 méter után megállni: válassz kényelmes szakaszokat, '
                   'és pihenj, amikor szükséges. RPE 2–3/10, nyugodt légzés; nem kell kitölteni az időkeretet. '
                   'Panasz, romló kontroll vagy nehéz légzés esetén fejezd be. A terv medencés úszásra szól. '
                   'Nem következtetünk egyéni tempóra, pulzusra vagy folyamatosan leúszható távra a jártasságból.')
    dose = {'schema_version': 'swimming-prescription-v0.2', 'mode': 'self_paced', 'stroke': skill['preferred_stroke'],
            'pool_length_m': location.get('pool_length_m'), 'lengths_per_repeat': None, 'rest_seconds': None,
            'source_kind': 'declared_sport_proficiency', 'reported_on': skill['reported_on'], 'report_is_recent': context['fresh'],
            'options_reference': context['options_reference'], 'ability_basis': context['ability_basis'],
            'observed_cap_seconds': context['observed_cap_seconds'], 'declared_cap_seconds': None,
            'continuous_distance_limit_m': None, 'pace_estimated': False, 'current_capacity_measured': False}
    result = {**template, 'version': 'v0.2', 'minutes': seconds // 60, 'title': f'Könnyű úszás saját szakaszokkal · {seconds // 60} perc',
              'description': description, 'blocks': [block(1, 'WARMUP', 'Könnyű úszás bemelegítésként', 300), block(2, 'WORK', work, seconds - 600),
                                                    block(3, 'COOLDOWN', 'Nagyon könnyű levezető úszás', 300)]}
    metadata = {'schema_version': 'training-prescription-v0.4', 'family_key': FAMILY, 'duration_sec': seconds, 'minimum_seconds': 1200,
                'maximum_seconds': 3600, 'reference_session_ids': reference['session_ids'], 'reference_cap_seconds': context['observed_cap_seconds'],
                'product_default_used': context['product_default_used'], 'soft_duration_reduced': seconds < 1800, 'progression_applied': False,
                'personal_response_model_applied': False, 'intensity_basis': 'product_default_not_personal_threshold', 'rpe': {'min': 2, 'max': 3}, 'swimming': dose}
    return (result, metadata), None
