"""Bounded, reviewable sample prescriptions. No inferred personal response model.

The library supplies the family envelopes. Durations, spacing and rolling caps
below are explicit versioned product defaults, not physiological estimates.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.planning.domain.athlete_setup import digest, review_profile
from app.services import training_execution_reconciliation as execution
from app.services import training_mesocycles as mesocycles
from app.services import training_prescriptions as prescriptions
from app.services import training_strength_assessment as strength
from app.services.planning_strategy import main_events, phase_at, recent_signals
from app.planning.domain import daylight
from app.services import training_swimming as swimming, training_starting_load as load_policy
from app.services import training_strength_starter as starter
from app.services import training_strength_workout as strength_workout
from app.planning.domain.workout_family.swimming import builtin_workout_family_registry_v0_3

RULES = "training-plan-policy-v0.15"
SOURCE = "PADDLETRAINER_C18_4"
FAMILY_REGISTRY = builtin_workout_family_registry_v0_3()
MARKER = "paddletrainer_training_plan"
POLICY = {
    "version": RULES,
    "max_sessions_per_day": 1,
    "default_sessions_per_7_days": 2,
    "max_sessions_per_7_days": 7,
    "fallback_max_sessions_per_7_days": 3,
    "default_minutes_per_7_days": 90,
    "max_minutes_per_7_days": 10080,
    "fallback_max_minutes_per_7_days": 180,
    "history_days": prescriptions.HISTORY_DAYS,
    "automatic_progression_applied": False,
    "minimum_gap_hours": 12,
    "unknown_effort_gap_hours": 36,
    "strength_gap_hours": 48,
    "spacing_rules_version": load_policy.SPACING,
    "new_session_lead_minutes": 15,
    "personal_response_model_applied": False,
    "missed_load_is_not_repaid": True,
}
SPORTS = prescriptions.SPORTS


def at(value):
    return datetime.fromisoformat(value).astimezone(UTC)


def block(position, kind, name, seconds):
    return {
        "position": position,
        "block_type": kind,
        "name": name,
        "duration_sec": seconds,
        "distance_m": None,
        "intensity_type": None,
        "intensity_min": None,
        "intensity_max": None,
        "repeat_count": None,
        "parent_block_id": None,
    }


TEMPLATES = [
    {
        "key": "KAYAK_EASY_TECHNICAL",
        "sport": "KAYAK",
        "minutes": 30,
        "title": "Könnyű technikai kajak · 30 perc",
        "effort": "easy",
        "capabilities": ["TECHNICAL_SKILL", "PERIPHERAL_OXIDATIVE_CAPACITY", "PADDLING_ECONOMY"],
        "description": "10 perc könnyű bemelegítés; 15 perc nyugodt evezés, egy ismert technikai elemre figyelve; 5 perc levezetés. Könnyű, beszélgetős érzet (RPE 2–3/10), pulzuscél nélkül. A technika romlásakor rövidíts; az időt nem kell kitölteni.",
        "blocks": [
            block(1, "WARMUP", "Könnyű bemelegítés", 600),
            block(2, "WORK", "Nyugodt evezés, egy ismert technikai fókusz", 900),
            block(3, "COOLDOWN", "Levezetés", 300),
        ],
    },
    {
        "key": "KAYAK_LONG_AEROBIC",
        "sport": "KAYAK",
        "minutes": 60,
        "title": "Hosszabb könnyű evezés · 60 perc",
        "effort": "easy",
        "capabilities": [
            "PERIPHERAL_OXIDATIVE_CAPACITY",
            "PADDLING_ECONOMY",
            "LONG_DURATION_DURABILITY",
        ],
        "description": "10 perc könnyű bemelegítés; 45 perc egyenletes, beszélgetős evezés; 5 perc levezetés. RPE 2–3/10, nincs pulzus- vagy tempókényszer. Az ismert saját időtartamreferencia alapján választott minta; nem kötelező időkvóta és nem bizonyított személyes dózisoptimum.",
        "blocks": [
            block(1, "WARMUP", "Könnyű bemelegítés", 600),
            block(2, "WORK", "Egyenletes könnyű evezés", 2700),
            block(3, "COOLDOWN", "Levezetés", 300),
        ],
    },
    {
        "key": "STRENGTH_REFERENCE_AND_DEVELOPMENT",
        "sport": "STRENGTH",
        "minutes": 30,
        "title": "Erőreferencia · 30 perces időkeret",
        "effort": "moderate",
        "capabilities": ["MAX_STRENGTH", "MUSCULOSKELETAL_ROBUSTNESS"],
        "description": "5 perc ismert bemelegítés. Ismert kézisúlyzós evezés és goblet guggolás: gyakorlatonként 2 × 6 kontrollált ismétlés, 2 perc pihenő; válassz már ismert terhet, legalább 3–4 ismétlés tartalékkal. Rögzítsd a terhet, ismétléseket és tartalékot. Nincs maximális teszt vagy kifáradásig végzés. A 20 perces főrész helyfoglalás, nem folyamatos munkadózis; 5 perc levezetés. Új gyakorlatot itt nem tanítunk.",
        "blocks": [
            block(1, "WARMUP", "Ismert bemelegítés", 300),
            block(2, "WORK", "Két ismert gyakorlat: 2 × 6, RIR 3–4; pihenőkkel", 1200),
            block(3, "COOLDOWN", "Levezetés és terhelésnapló", 300),
        ],
    },
]

TEMPLATES.append(prescriptions.running_template(block))
TEMPLATES.append(swimming.template(block))


def completion_events(data, plans, now, reconciliation=None):
    """Resolve stored completions first, then apply covered, reversible absence."""
    reconciliation = reconciliation or execution.empty(data["athlete_id"])
    resolved = {item["session_id"]: item["workout_id"] for item in reconciliation["resolved_links"]}
    linked = {}
    events = []
    plan_workouts = {p["workout"]["id"]: p["workout"] for p in plans}
    for session in data["recent_sessions"]:
        started = at(session["started_at"])
        plan_id = session["planned_workout_id"] or resolved.get(session["id"])
        plan = plan_workouts.get(plan_id, {})
        end = (
            at(session["ended_at"])
            if session["ended_at"]
            else (
                at(session["started_at"]) + timedelta(seconds=session["duration_sec"])
                if session["duration_sec"] is not None
                else None
            )
        )
        if end is None or end > now:
            state = "execution_incomplete"
        else:
            state = "planned_completed" if plan_id else "unplanned_completed"
        if plan_id:
            linked[plan_id] = session["id"]
        events.append(
            {
                "kind": state,
                "session_id": session["id"],
                "workout_id": plan_id,
                "title": session.get("name") or plan.get("title"),
                "sport": session["sport"],
                "started_at": started.isoformat(),
                "date": started.astimezone(ZoneInfo(data["timezone_name"])).date().isoformat(),
                "observed_end_at": end.isoformat() if end else None,
                "duration_sec": session["duration_sec"],
                "cardio_load": session["cardio_load"],
                "rpe": session["rpe"],
            }
        )
    for plan in plans:
        w = plan["workout"]
        if w["id"] in linked or plan["linked"] or w["status"] == "CANCELLED":
            continue
        end = (
            at(w["planned_start_time"]) + timedelta(seconds=w["duration_sec"])
            if (w["planned_start_time"] and w["duration_sec"] is not None)
            else None
        )
        source = None
        if w["status"] == "SKIPPED":
            state = "confirmed_missed"
        elif w["status"] == "COMPLETED":
            state = "reported_completed"
        elif end and end <= now or not end and w["date"] < data["local_today"]:
            source = execution.absence_source(w, data["timezone_name"], reconciliation)
            state = "not_recorded_after_sync" if source else "execution_unknown"
        else:
            continue
        evidence_fields = {}
        if source:
            checked_start, checked_end = execution.planned_span(w, data["timezone_name"])
            evidence_fields = {"sync_reference": source["result_reference"],
                               "checked_through": source["started_at"],
                               "absence_window": {"from_at": checked_start.isoformat(),
                                                  "to_exclusive_at": checked_end.isoformat()}}
        events.append(
            {
                "kind": state,
                "workout_id": w["id"],
                "title": w["title"],
                "sport": w["sport"],
                "started_at": w["planned_start_time"],
                "date": w["date"],
                "observed_end_at": end.isoformat() if end else None,
                "workout_hash": plan["workout_hash"],
                "can_confirm_missed": state == "execution_unknown" and plan["owned_sample"],
                **evidence_fields,
                **({"reconciliation_issue": "AMBIGUOUS_PROVIDER_TARGET"}
                   if w["id"] in reconciliation["ambiguous_workout_ids"] else {}),
            }
        )
    return events


def opportunity_issues(group, template, resources):
    c = group["constraints"]
    issues = []
    if not group["known"]:
        issues.append("OPPORTUNITY_NOT_KNOWN")
    if c["sport_scope"] == "unknown":
        issues.append("SPORT_SCOPE_UNKNOWN")
    if c["effort_cap"] == "unknown":
        issues.append("EFFORT_CAP_UNKNOWN")
    if c["sport_scope"] == "specified" and not any(
        str(s).strip().casefold() in SPORTS[template["sport"]] for s in c["sports"]
    ):
        issues.append("SPORT_NOT_ALLOWED")
        return issues
    if template["effort"] == "moderate" and c["effort_cap"] not in {"moderate", "any"}:
        issues.append("EFFORT_NOT_ALLOWED")
    equipment = {v.casefold().strip() for v in ([] if c.get("resources_scope") == "location" else resources) + c["resources"]}
    required = (
        {"kajak", "kayak", "hajó", "kajakergométer"}
        if template["sport"] == "KAYAK"
        else set()  # Strength matches each assessed exercise at its own venue.
    )
    if required and not equipment & required:
        issues.append("EQUIPMENT_NOT_DECLARED")
    return issues


def allows(group, template, resources):
    return not opportunity_issues(group, template, resources)


def make_candidate(day, group, template, start, role, reference):
    family = FAMILY_REGISTRY.get(template["key"])
    value = {
        "template_key": template["key"],
        "template_version": template.get("version", "v0.1"),
        "family_registry_hash": FAMILY_REGISTRY.content_hash,
        "guardrails": list(family.guardrails),
        "date": day["date"],
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=template["minutes"])).isoformat(),
        "training_period_id": day["mesocycle_id"],
        "sport": template["sport"],
        "title": template["title"],
        "description": template["description"],
        "duration_sec": template["minutes"] * 60,
        "blocks": template["blocks"],
        "opportunity_key": group["key"],
        "capability_key": role["capability_key"],
        "role": role["role"],
        "duration_reference_session_id": reference,
        "rationale": f"{role['capability_key']} · {role['role']}. A megadott sport-, eszköz- és időkeretbe illesztett minta; elmaradt terhelést nem pótol.",
        **({'strength_prescription': template['strength_prescription']} if 'strength_prescription' in template else {}),
        **({"location": group["constraints"]["location"], "location_id": group["constraints"]["location_id"], "alternative_group_key": group["constraints"]["alternative_group_key"]} if group["constraints"].get("location_id") else {}),
    }
    value["candidate_key"] = digest(value)
    return value


def fits_rolling_budget(commitments, target, seconds, max_count, max_seconds):
    """Check all seven-day windows containing the candidate, including future plans."""
    for offset in range(7):
        first = target - timedelta(days=offset)
        window = [v for v in commitments if first <= v["date"] <= first + timedelta(days=6)]
        if len(window) + 1 > max_count or any(v["seconds"] is None and not v.get("missed_reservation") for v in window):
            return False
        if sum(v["seconds"] for v in window if v["seconds"] is not None) + seconds > max_seconds:
            return False
    return True


def build(data, plans, now, active_window_end=None, selection_preferences=None, reconciliation=None, coordinate_mesocycles=None, calibration_review=None):
    from app.services.training_instructions import attach
    from app.services import training_distribution as distribution
    from app.services.training_sport_availability import report
    args = (data, plans, now, active_window_end, selection_preferences, reconciliation, coordinate_mesocycles, calibration_review)
    state = {}
    baseline = _build(*args, _pool_state=state)
    if baseline['blockers'] or state['coordination']['mode'] != 'coordinated':
        _, baseline['distribution'] = distribution.improve(baseline['proposals'], baseline['alternatives'], state, data, selection_preferences or {})
        return attach(baseline)
    hints = {}
    for candidate in baseline['proposals']:
        key = (distribution.block_key(state['coordination'], candidate), candidate['template_key'])
        hints[key] = min(hints.get(key, candidate['duration_sec']), candidate['duration_sec'])
    # Preserve accepted durations when changing dates: spacing alone must not
    # turn a previously accepted short session into a longer prescription.
    for plan in state['eligible']:
        w = plan['workout']
        micro = mesocycles.block_on(state['coordination'], w['date'])
        if micro and w['duration_sec']:
            key = (micro['key'], plan['template_key'])
            hints[key] = min(hints.get(key, w['duration_sec']), w['duration_sec'])
    pooled = _build(*args, _pool=True, _duration_hints=hints)
    alternatives = {a['date']: a for a in pooled['alternatives']}
    for candidate in baseline['proposals']:
        group = alternatives.setdefault(candidate['date'], {'date': candidate['date'],
            'recommended_candidate_key': candidate['candidate_key'], 'selected_candidate_key': None, 'candidates': []})
        if not any(c['candidate_key'] == candidate['candidate_key'] for c in group['candidates']):
            group['candidates'].append(candidate)
    alternatives = sorted(alternatives.values(), key=lambda a: a['date'])
    selected, proof = distribution.improve(baseline['proposals'], alternatives, state, data, selection_preferences or {})
    by_date = {c['date']: c for c in selected}
    for group in alternatives:
        group['selected_candidate_key'] = by_date[group['date']]['candidate_key'] if group['date'] in by_date else None
    pooled['proposals'], pooled['alternatives'], pooled['distribution'] = selected, alternatives, proof
    pooled['prescription_context']['by_candidate'].update(baseline['prescription_context']['by_candidate'])
    eligible = state['eligible']
    existing = {p['candidate_key']: p['workout']['id'] for p in eligible}
    pooled['keep'] = [existing[c['candidate_key']] for c in selected if c['candidate_key'] in existing]
    pooled['create'] = [c for c in selected if c['candidate_key'] not in existing]
    pooled['cancel'] = [p['workout']['id'] for p in eligible if p['workout']['id'] not in pooled['keep']]
    prior_reasons = {r['date']: r['reason'] for r in pooled['days_without_proposal']}
    pooled['days_without_proposal'] = [{'date': d['date'], 'reason':
        'PLANNED_RECOVERY_DAY' if d['date'] in {a['date'] for a in alternatives} else prior_reasons.get(d['date'], 'NO_SUPPORTED_SAMPLE_FITS')}
        for d in data['days'] if d['date'] not in by_date]
    covered = {c['capability_key'] for c in selected}
    pooled['uncovered_capabilities'] = sorted({r['capability_key'] for d in data['days'] for r in d['capability_roles']
        if r['role'] in {'primary_development', 'secondary_development'} and r['capability_key'] not in covered})
    issues = {r['sport']: set(r['reasons']) for r in pooled['preparation']['sport_availability']['sports']}
    pooled['preparation']['sport_availability'] = report(data, TEMPLATES, selected, alternatives, issues,
        opportunity_issues, pooled['blockers'], pooled['prescription_context']['starting_budget'])
    return attach(pooled)


def _build(data, plans, now, active_window_end=None, selection_preferences=None, reconciliation=None, coordinate_mesocycles=None, calibration_review=None, *, _pool=False, _pool_state=None, _duration_hints=None):
    zone = ZoneInfo(data["timezone_name"])
    today = now.astimezone(zone).date()
    data = {**data, "local_today": today.isoformat()}
    profile = (data["profile"] or {}).get("data")
    gate = review_profile(profile, today.isoformat()) if profile else None
    blockers = []
    if not gate or gate["global_entry_gate"] != "OPEN":
        blockers.append("PROFILE_REVIEW_REQUIRED")
    if profile and profile["interruption"] == "returning":
        blockers.append("RETURNING_ATHLETE_REVIEW")
    if prescriptions.sport_code(data["program_sport"]) is None:
        blockers.append("PROGRAM_SPORT_NOT_SUPPORTED")
    blockers += [
        g for g in data["gaps"] if g in {"PROGRAM_TIMEZONE_REVIEW", "GOAL_SOURCE_SNAPSHOT_CHANGED"}
    ]
    signals = recent_signals(data, today)
    illness = any(s["kind"] == "reported_illness" for s in signals)
    if illness:
        blockers.append("CURRENT_ILLNESS_REVIEW")
    reconciliation = reconciliation or execution.empty(data["athlete_id"])
    events = completion_events(data, plans, now, reconciliation)
    absent_ids = {event["workout_id"] for event in events if event["kind"] == "not_recorded_after_sync"}
    eligible = [
        p
        for p in plans
        if p["replaceable"] and data["start_date"] <= p["workout"]["date"] <= data["end_date"]
    ]
    eligible_ids = {p["workout"]["id"] for p in eligible}
    protected = [p for p in plans if p["workout"]["id"] not in eligible_ids]
    occupied, loads = set(), []
    for p in protected:
        w = p["workout"]
        if w["status"] == "CANCELLED" or p["linked"]:
            continue
        occupied.add(w["date"])
        # Imported expired targets without a recorded completion are not actual
        # load. Own accepted misses retain their quota, preventing repayment.
        if w["id"] in absent_ids and not p["owned_sample"]:
            continue
        missed_reservation = w["status"] == "SKIPPED" or w["id"] in absent_ids
        # A confirmed miss reserves its original planning budget. It is not
        # physiological load and imposes no recovery spacing, but it must not
        # free a quota which the greedy placement would silently repay.
        loads.append(
            {
                "date": date.fromisoformat(w["date"]),
                "seconds": w["duration_sec"] if w["duration_sec"] is not None else
                    (p.get("duration_estimate") or {}).get("upper_sec"),
                "at": at(w["planned_start_time"])
                if w["planned_start_time"] and not missed_reservation
                else None,
                "sport": w["sport"],
                "missed_reservation": missed_reservation,
                "known": p["owned_sample"],
            }
        )
    calibration = calibration_review["inputs"] if calibration_review else data
    reference_catalog = prescriptions.references(calibration)
    # Keep accepted movement references, but learn from current endurance
    # evidence. The weekly envelope is rebuilt from current covered weeks or
    # an explicit current baseline, never from old personal bests.
    reference_catalog["RUN_EASY_AEROBIC_FALLBACK"] = prescriptions.references(data)["RUN_EASY_AEROBIC_FALLBACK"]
    reference_catalog[swimming.FAMILY] = prescriptions.references(data)[swimming.FAMILY]
    strength_context = data.get('strength_assessment') or {'receipt': None}
    strength_summary = strength.summary(strength_context, data, prescriptions.sport_code(data['program_sport']), today.isoformat())
    reference_catalog[strength.FAMILY] = strength.duration_reference(reference_catalog[strength.FAMILY], strength_context)
    references = {key: value["anchor_id"] for key, value in reference_catalog.items()
                  if value["anchor_id"] and value["cap_seconds"] >= prescriptions.FAMILIES[key]["minimum"]}
    for s in data["recent_sessions"]:
        day = at(s["started_at"]).astimezone(zone).date()
        occupied.add(day.isoformat())
        loads.append(
            {
                "date": day,
                "seconds": s["duration_sec"] if type(s["duration_sec"]) is int and s["duration_sec"] >= 0 else None,
                "at": at(s["started_at"]),
                "sport": s["sport"],
                "rpe": s.get("rpe"),
            }
        )
    starting_budget = load_policy.starting_budget(data, reconciliation)
    if calibration_review:
        for budget_key, profile_key in (("max_sessions_per_7_days", "typical_days_per_week"), ("max_minutes_per_7_days", "typical_minutes_per_week")):
            if profile and profile.get(profile_key) is not None:
                starting_budget[budget_key] = min(starting_budget[budget_key], profile[profile_key])
    max_count = starting_budget["max_sessions_per_7_days"]
    max_seconds = starting_budget["max_minutes_per_7_days"] * 60
    prescription_metadata = {}
    coordination = mesocycles.build(data, starting_budget, coordinate_mesocycles)
    if _pool_state is not None:
        _pool_state.update(loads=[dict(v) for v in loads], eligible=eligible,
            max_count=max_count, max_seconds=max_seconds, coordination=coordination)
    light_data = (data.get("daylight_context") or {}).get("options_receipt", {}).get("artifact", {}).get("proposal", {}).get("data", {})
    used_capabilities = {}
    # Rebuild only editable own future proposals from the same protected load.
    # Pre-reserving the previous mix would make an accepted strength-only plan
    # bias the next refresh and can oscillate between allocations. Actual,
    # imported, edited and missed commitments were reserved above and stay put.
    proposals, reasons, budgets = [], [], {}
    diagnostics = []
    sport_issues = {sport: set() for sport in SPORTS}
    alternatives = []
    unavailable_alternatives = []
    selection_preferences = selection_preferences or {}
    used_templates = []
    strength_template = next(t for t in TEMPLATES if t['sport'] == 'STRENGTH')
    strength_days = {d['date'] for d in data['days'] if any(
        r['capability_key'] in strength_template['capabilities'] and r['role'] != 'permitted_decline'
        for r in d['capability_roles']) and any(
        not opportunity_issues(g, strength_template, profile['resources'] if profile else [])
        and min(g['max_minutes'], d['daily_max_minutes'] if d['daily_max_minutes'] is not None else 1440) >= 20
        and any((at(i['end_at'])-at(i['start_at'])).total_seconds() >= 1200
                for i in daylight.allowed_intervals(light_data, g, 'STRENGTH')[0])
        for g in d['opportunities'])}
    for day in mesocycles.order_days(coordination, data, TEMPLATES, reference_catalog, opportunity_issues, prescriptions.FAMILIES, selection_preferences, global_scarcity=True):
        micro = mesocycles.block_on(coordination, day["date"])
        usage = used_capabilities.setdefault(micro["key"] if micro else day["date"], {})
        reason = None
        issues = set()
        target = date.fromisoformat(day["date"])
        # Re-evaluate today's own candidates without counting them twice. All
        # later reviewed sessions keep their reservation until their turn.
        todays_ids = {p["workout"]["id"] for p in eligible if p["workout"]["date"] == day["date"]}
        loads = [v for v in loads if v.get("eligible_id") not in todays_ids]
        roles = [r for r in day["capability_roles"] if r["role"] != "permitted_decline"]
        if blockers:
            reason = blockers[0]
        elif active_window_end and day["date"] > active_window_end:
            reason = "ACCEPTED_WINDOW_ENDED"
        elif day["availability_state"] != "opportunities":
            reason = "NO_KNOWN_OPPORTUNITY"
        elif not day["mesocycle_id"] or not roles:
            reason = "CAPABILITY_ROLES_REQUIRED"
        elif day["date"] in occupied:
            reason = "EXISTING_TRAINING_PRESERVED"
        # An unresolved elapsed plan is information uncertainty. Do not replace
        # its potentially completed load with another prescription nearby.
        elif any(
            e["kind"] in {"execution_unknown", "execution_incomplete"}
            and not (e['kind'] == 'execution_unknown' and (data.get('alternatives_for') or
                data.get('same_day_replacement') and e.get('workout_id') == data['same_day_replacement']['workout_id']))
            and (not e["observed_end_at"] or at(e["observed_end_at"]) >= now - timedelta(hours=48))
            for e in events
        ) and target <= today + timedelta(days=1):
            reason = "RECENT_EXECUTION_REVIEW"
        elif any(v['artifact']['state'] == 'active' and at(v['artifact']['created_at']) >= now - timedelta(hours=48)
                 for v in strength_context.get('guided_activities', [])) and target <= today + timedelta(days=1):
            reason = 'GUIDED_ASSESSMENT_PENDING'
        elif signals and target <= today + timedelta(days=1):
            reason = "RECOVERY_REVIEW"
        phase, _ = phase_at(target, main_events(data), today)
        if not reason and phase in {"race_readiness", "transition"}:
            reason = "EVENT_PHASE_REVIEW"
        if not reason and any(
            e["status"] == "planned" and e["start_date"] <= day["date"] <= e["end_date"]
            for e in data["competitions"]
        ):
            reason = "COMPETITION_DAY_PRESERVED"
        found = None
        choices = []
        for template in TEMPLATES:
            role = next(
                (
                    r
                    for r in sorted(
                        roles,
                        key=lambda r: (
                            usage.get(r["capability_key"], 0) > 0 if coordination["mode"] == "coordinated" else False,
                            r["role"] != "primary_development",
                            r["role"] != "secondary_development",
                            usage.get(r["capability_key"], 0) if coordination["mode"] == "coordinated" else 0,
                        ),
                    )
                    if r["capability_key"] in template["capabilities"]
                ),
                None,
            )
            if not role:
                continue
            choices.append((template, role))
        if _pool:
            choices = [(t, r) for t in TEMPLATES for r in roles if r['capability_key'] in t['capabilities']]
        weights = load_policy.target_weights(roles, TEMPLATES, prescriptions.sport_code(data["program_sport"]))
        # Do not spend the sole weekly strength-capable venue on an aerobic
        # alternative which also fits other days. This is availability, not
        # a claim that strength must dominate the primary endurance sport.
        scarce_strength = day['date'] in strength_days and sum(
            abs((date.fromisoformat(d)-target).days) <= 6 for d in strength_days) == 1
        # A represented primary objective must not indefinitely starve a
        # different saved objective, including technical maintenance. This
        # only orders candidates; all dose and feasibility gates still apply.
        choices.sort(
            key=lambda v: (
                usage.get(v[1]["capability_key"], 0) > 0 if coordination["mode"] == "coordinated" else False,
                v[1]["role"] != "primary_development",
                scarce_strength and v[0]['sport'] != 'STRENGTH',
                load_policy.allocation_pressure(loads, target, v[0]["sport"], weights),
                usage.get(v[1]["capability_key"], 0) if coordination["mode"] == "coordinated" else 0,
                v[0]["sport"] != prescriptions.sport_code(data["program_sport"]),
                used_templates.count(v[0]["key"]),
                v[0]["key"] == "KAYAK_EASY_TECHNICAL",
            )
        )
        available_candidates = []
        group_issues = {group["key"]: set() for group in day["opportunities"]}
        rest_issues = set()
        if not reason:
            compatible = {group["key"]: [template for template, _ in choices
                          if "SPORT_NOT_ALLOWED" not in opportunity_issues(group, template, profile["resources"])]
                          for group in day["opportunities"]}
            for group in day["opportunities"]:
                if not compatible[group["key"]]:
                    code = "SPORT_NOT_ALLOWED" if not any("SPORT_NOT_ALLOWED" not in opportunity_issues(group, template, profile["resources"]) for template in TEMPLATES) else "CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT"
                    group_issues[group["key"]].add(code)
                    issues.add(code)
            for template, role in choices:
                for group in day["opportunities"]:
                    rejected = opportunity_issues(group, template, profile["resources"])
                    introductory = template['sport'] == 'STRENGTH' and rejected == ['EFFORT_NOT_ALLOWED'] and starter.allowed(strength_context, data)
                    if introductory:
                        rejected = []
                    if "SPORT_NOT_ALLOWED" in rejected and compatible[group["key"]]:
                        continue
                    if rejected:
                        sport_issues[template["sport"]].update(rejected)
                        issues.update(rejected)
                        group_issues[group["key"]].update(rejected)
                        continue
                    selected_strength = None
                    if template['sport'] == 'STRENGTH':
                        selected_strength, codes = (strength_workout.selected if data.get('strength_workout_context') and POLICY['version'] == 'training-plan-policy-v0.15' else strength.selection)(strength_context, data, prescriptions.sport_code(data['program_sport']), day['date'], group)
                        if codes and 'STRENGTH_MOVEMENT_SYMPTOMS' not in codes and starter.allowed(strength_context, data):
                            introductory = True
                        elif codes:
                            sport_issues[template["sport"]].update(codes)
                            issues.update(codes)
                            group_issues[group['key']].update(codes)
                            continue
                    intervals, light_codes = daylight.allowed_intervals(light_data, group, template["sport"])
                    sport_issues[template["sport"]].update(light_codes)
                    issues.update(light_codes)
                    group_issues[group["key"]].update(light_codes)
                    for interval in intervals:
                        low = max(at(interval["start_at"]), datetime.combine(target, time.min, zone).astimezone(UTC))
                        manual_today = bool((data.get('same_day_replacement') or data.get('alternatives_for')) and target == today)
                        preference = selection_preferences.get(day['date'], {})
                        exact_choice = bool(preference and preference.get('template_key') == template['key']
                                            and preference.get('opportunity_key') == group['key'])
                        previous = next((p for p in eligible if p["template_key"] == template["key"]
                                         and p["workout"]["date"] == day["date"]
                                         and low <= at(p["workout"]["planned_start_time"]) < at(interval["end_at"])), None)
                        lead = now + timedelta(minutes=POLICY["new_session_lead_minutes"])
                        lead = datetime.fromtimestamp(((int(lead.timestamp()) + 899) // 900) * 900, UTC)
                        start = at(previous["workout"]["planned_start_time"]) if previous and at(previous["workout"]["planned_start_time"]) > now else max(low, lead)
                        requested_start = at(preference['start_at']) if exact_choice and preference.get('start_at') else None
                        if requested_start and requested_start > now and low <= requested_start < at(interval['end_at']):
                            start = requested_start
                        if manual_today:
                            # Compute the complete dose against the actual
                            # remaining window first. A product lead time must
                            # not expire an otherwise feasible manual option.
                            start = max(low, now)
                        if start < now or (start == now and not manual_today) or start.astimezone(zone).date() != target or start >= at(interval["end_at"]):
                            sport_issues[template["sport"]].add("INTERVAL_TOO_SHORT_OR_START_PASSED")
                            issues.add("INTERVAL_TOO_SHORT_OR_START_PASSED")
                            group_issues[group["key"]].add("INTERVAL_TOO_SHORT_OR_START_PASSED")
                            continue
                        remaining = max_seconds
                        for offset in range(7):
                            first = target - timedelta(days=offset)
                            window = [value for value in loads if first <= value["date"] <= first + timedelta(days=6)]
                            remaining = min(remaining, max_seconds - sum(value["seconds"] for value in window if value["seconds"] is not None))
                        available = min((at(interval["end_at"]) - start).total_seconds(),
                                        (group["max_minutes"] - budgets.get(group["key"], 0)) * 60,
                                        (day["daily_max_minutes"] if day["daily_max_minutes"] is not None else 1440) * 60)
                        cycle_room = mesocycles.remaining(coordination, day["date"], loads)
                        wave_ceiling = mesocycles.duration_ceiling(coordination, day["date"], prescriptions.FAMILIES[template["key"]], reference_catalog[template["key"]])
                        if template['sport'] == 'STRENGTH' and data.get('strength_workout_context') and POLICY['version'] == 'training-plan-policy-v0.15':
                            wave_ceiling = strength_workout.MAXIMUM
                        effective_room = min(available, remaining, wave_ceiling, cycle_room if cycle_room is not None else remaining)
                        if exact_choice and preference.get('duration_sec') is not None:
                            effective_room = min(effective_room, preference['duration_sec'])
                        parameterizer = (strength_workout.parameterize if data.get('strength_workout_context') and POLICY['version'] == 'training-plan-policy-v0.15' else strength.parameterize) if template['sport'] == 'STRENGTH' else swimming.parameterize if template['sport'] == 'SWIMMING' else prescriptions.parameterize
                        value, error = starter.parameterize(template, context=strength_context, data=data, available_seconds=effective_room, reference=reference_catalog[template['key']], block=block) if introductory else parameterizer(
                            template, available_seconds=effective_room, reference=reference_catalog[template["key"]],
                            block=block, preferred_seconds=preference.get('duration_sec') if exact_choice and preference.get('duration_sec') is not None else (_duration_hints or {}).get((micro['key'] if micro else day['mesocycle_id'], template['key']), previous['workout']['duration_sec'] if previous else None),
                            **({'context': strength_context, 'chosen': selected_strength} if template['sport'] == 'STRENGTH' else {}),
                            **({'location': next((l for l in light_data.get('locations', []) if l['id'] == group['constraints'].get('location_id')), None)} if template['sport'] == 'SWIMMING' else {}),
                        )
                        if error:
                            sport_issues[template["sport"]].add(error)
                            if light_data and error == "OPPORTUNITY_OR_DAILY_MINUTE_CAP" and intervals != group["intervals"]:
                                issues.add("DAYLIGHT_SESSION_DOES_NOT_FIT")
                                group_issues[group["key"]].add("DAYLIGHT_SESSION_DOES_NOT_FIT")
                            if error == "OPPORTUNITY_OR_DAILY_MINUTE_CAP" and cycle_room is not None and cycle_room < prescriptions.FAMILIES[template["key"]]["minimum"] <= min(available, remaining):
                                error = "MICROCYCLE_BUDGET_RESERVED"
                                rest_issues.add(error)
                            if error == "OPPORTUNITY_OR_DAILY_MINUTE_CAP" and remaining < prescriptions.FAMILIES[template["key"]]["minimum"] <= available:
                                error = "ROLLING_BUDGET_REVIEW"
                                rest_issues.add(error)
                            issues.add(error)
                            group_issues[group["key"]].add(error)
                            continue
                        parameterized, metadata = value
                        seconds = metadata["duration_sec"]
                        if manual_today:
                            suggested = requested_start if requested_start and requested_start > now else at(previous['workout']['planned_start_time']) if previous and at(previous['workout']['planned_start_time']) > now else max(low, lead)
                            start = max(low, min(suggested, at(interval['end_at']) - timedelta(seconds=seconds)))
                            if start < now or start.astimezone(zone).date() != target:
                                continue
                        valid = fits_rolling_budget(loads, target, seconds, max_count, max_seconds)
                        if not valid or load_policy.conflicts(loads, start, template["sport"]):
                            error = "ROLLING_BUDGET_REVIEW" if not valid else "MINIMUM_SPACING"
                            sport_issues[template["sport"]].add(error)
                            issues.add(error)
                            rest_issues.add(error)
                            group_issues[group["key"]].add(error)
                            continue
                        candidate = make_candidate(day, group, parameterized, start, role,
                                                   None if introductory or template["key"] == "KAYAK_EASY_TECHNICAL" else reference_catalog[template["key"]]["anchor_id"])
                        if exact_choice and preference.get('workout_variant_hash'):
                            from app.services.training_alternative_variants import variant
                            if digest(variant(candidate, metadata)) != preference['workout_variant_hash']:
                                group_issues[group['key']].add('SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE')
                                continue
                        prescription_metadata[candidate["candidate_key"]] = metadata
                        available_candidates.append(candidate)
                        break
            for group in day["opportunities"]:
                if group["constraints"].get("location_id") and not any(candidate["opportunity_key"] == group["key"] for candidate in available_candidates):
                    codes = group_issues[group["key"]] or issues or {"NO_SUPPORTED_SAMPLE_FITS"}
                    unavailable_alternatives.append({"date": day["date"], "opportunity_key": group["key"], "location_id": group["constraints"]["location_id"], "location": group["constraints"]["location"], "codes": sorted(set(codes) | set(group["constraints"].get("location_issues", [])))})
            if available_candidates:
                preference = selection_preferences.get(day["date"])
                found = next((candidate for candidate in available_candidates if preference and candidate["template_key"] == preference["template_key"] and candidate["opportunity_key"] == preference["opportunity_key"] and (not preference.get('capability_key') or candidate['capability_key'] == preference['capability_key']) and (not preference.get('role') or candidate['role'] == preference['role'])), None) if preference else available_candidates[0]
                if preference and found is None:
                    reason = "SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE"
                alternatives.append({"date": day["date"], "recommended_candidate_key": available_candidates[0]["candidate_key"], "selected_candidate_key": found["candidate_key"] if found else None, "candidates": available_candidates})
                if found and not _pool:
                    budgets[found["opportunity_key"]] = budgets.get(found["opportunity_key"], 0) + found["duration_sec"] // 60
            if not found:
                reason = reason or ("PLANNED_RECOVERY_DAY" if rest_issues else "NO_SUPPORTED_SAMPLE_FITS")
        if found and not _pool:
            proposals.append(found)
            used_templates.append(found["template_key"])
            usage[found["capability_key"]] = usage.get(found["capability_key"], 0) + 1
            loads.append(
                {
                    "date": target,
                    "seconds": found["duration_sec"],
                    "at": at(found["start_at"]),
                    "sport": found["sport"],
                    "known": True,
                }
            )
        elif not found:
            reasons.append({"date": day["date"], "reason": reason})
            if reason == "NO_SUPPORTED_SAMPLE_FITS":
                diagnostics.append({"date": day["date"], "codes": sorted(issues)})
    proposals.sort(key=lambda value: (value["date"], value["candidate_key"]))
    alternatives.sort(key=lambda value: value["date"])
    reasons.sort(key=lambda value: value["date"])
    diagnostics.sort(key=lambda value: value["date"])
    unavailable_alternatives.sort(key=lambda value: (value["date"], value["opportunity_key"]))
    keep, create = [], []
    for p in proposals:
        current = next((v for v in eligible if v["candidate_key"] == p["candidate_key"]), None)
        if current:
            keep.append(current["workout"]["id"])
        else:
            create.append(p)
    cancel = [p["workout"]["id"] for p in eligible if p["workout"]["id"] not in keep]
    # A missing/restricted profile is a review boundary, never permission to
    # automatically cancel a previously reviewed programme.
    if blockers:
        cancel = []
        keep = [p["workout"]["id"] for p in eligible]
    covered = {v["capability_key"] for v in proposals}
    unsupported = sorted(
        {
            r["capability_key"]
            for d in data["days"]
            for r in d["capability_roles"]
            if r["role"] in {"primary_development", "secondary_development"}
            and r["capability_key"] not in covered
        }
    )
    from app.services.training_sport_availability import report
    sport_availability = report(data, TEMPLATES, proposals, alternatives, sport_issues, opportunity_issues, blockers, starting_budget)
    return {
        "policy": POLICY,
        "entry_review": gate,
        "blockers": blockers,
        "events": events,
        "execution_reconciliation": reconciliation,
        "mesocycle_coordination": coordination,
        "strength_assessment": strength_summary,
        "prescription_context": {"schema_version": "training-prescriptions-v0.4", "history_days": prescriptions.HISTORY_DAYS,
                                 "starting_budget": starting_budget, "by_candidate": prescription_metadata,
                                 "calibration_reference": {key: calibration_review[key] for key in ("artifact_id", "content_hash")} if calibration_review else None},
        "review_signals": signals,
        "proposals": proposals,
        "alternatives": alternatives,
        "unavailable_alternatives": unavailable_alternatives,
        "create": create,
        "keep": keep,
        "cancel": cancel,
        "days_without_proposal": reasons,
        "uncovered_capabilities": unsupported,
        "protected_workout_ids": [p["workout"]["id"] for p in protected],
        "personal_model_applied": False,
        "automatic_plan_mutation": False,
        "preparation": {
            "sport_availability": sport_availability,
            "version": "training-preparation-v0.2",
            "available_days_per_week": profile.get("typical_days_per_week") if profile else None,
            "available_minutes_per_week": profile.get("typical_minutes_per_week") if profile else None,
            "max_sessions_per_7_days": max_count,
            "max_minutes_per_7_days": max_seconds // 60,
            "equipment_declared": bool(profile and profile["resources"]) or any(
                g["constraints"]["resources"] for d in data["days"] for g in d["opportunities"]
            ),
            "available_day_count": sum(d["availability_state"] == "opportunities" for d in data["days"]),
            "strategy_ready": all(d["mesocycle_id"] and d["capability_roles"] for d in data["days"]),
            "reference_templates": sorted(references),
            "selection_issues": diagnostics,
            "unknown_duration_workout_ids": [p["workout"]["id"] for p in protected
                if not p["linked"] and p["workout"]["status"] != "CANCELLED"
                and p["workout"]["id"] not in absent_ids
                and (date.fromisoformat(data["start_date"]) - timedelta(days=6)).isoformat() <= p["workout"]["date"] <= (date.fromisoformat(data["end_date"]) + timedelta(days=6)).isoformat()
                and p["workout"]["duration_sec"] is None and not p.get("duration_estimate")],
            "estimated_duration_workout_ids": [p["workout"]["id"] for p in protected
                if not p["linked"] and p.get("duration_estimate")
                and p["workout"]["id"] not in absent_ids
                and (date.fromisoformat(data["start_date"]) - timedelta(days=6)).isoformat() <= p["workout"]["date"] <= (date.fromisoformat(data["end_date"]) + timedelta(days=6)).isoformat()],
        },
    }
