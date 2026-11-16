"""Explain proposals without inventing physiological readiness."""
from datetime import datetime
from app.planning.domain import daylight
from app.services import training_prescriptions as prescriptions

ALIASES = {**prescriptions.SPORTS, "SWIMMING": {"swimming", "swim", "úszás", "uszas"},
           "CYCLING": {"cycling", "bike", "kerékpár", "kerekpar"},
           "GYMNASTICS": {"gymnastics", "gimnasztika"}, "STRETCHING": {"stretching", "nyújtás", "nyujtas"}}


def goal_coverage(data, templates, proposals, alternatives, sport_rows):
    """Prescription focus coverage, not proof of adaptation or a sufficient dose."""
    scopes = {}
    for day in data['days']:
        if not day['mesocycle_id']:
            continue
        for role in day['capability_roles']:
            if role['role'] == 'permitted_decline':
                continue
            scopes.setdefault((day['mesocycle_id'], role['capability_key'], role['role']), []).append(day['date'])
    rows = []
    for (period, key, role), dates in sorted(scopes.items()):
        matching = [t for t in templates if key in t['capabilities']]
        template_keys = {t['key'] for t in matching}
        sports = sorted({t['sport'] for t in matching})
        candidates = {g['date'] for g in alternatives if g['date'] in dates and any(
            c['training_period_id'] == period and c['template_key'] in template_keys for c in g['candidates'])}
        planned = sum(c['training_period_id'] == period and c['date'] in dates and c['capability_key'] == key and c['role'] == role for c in proposals)
        status = 'represented' if planned else 'available_unselected' if candidates else 'unavailable' if matching else 'unsupported'
        reasons = [] if planned else ['GOAL_NOT_SELECTED'] if candidates else sorted({c for r in sport_rows if r['sport'] in sports for c in r['reasons']})
        if not planned and not reasons:
            reasons = ['CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT']
        rows.append({'mesocycle_id': period, 'capability_key': key, 'role': role,
                     'start_date': min(dates), 'end_date': max(dates), 'planned_sessions': planned,
                     'candidate_days': len(candidates), 'template_sports': sports, 'status': status, 'reasons': reasons})
    return rows


def report(data, templates, proposals, alternatives, attempt_issues, opportunity_issues, blockers=(), starting_budget=None):
    light_data = (data.get("daylight_context") or {}).get("options_receipt", {}).get("artifact", {}).get("proposal", {}).get("data", {})
    resources = ((data.get("profile") or {}).get("data") or {}).get("resources", [])
    declared = {str(s).strip().casefold() for d in data["days"] for g in d["opportunities"] for s in g["constraints"]["sports"]}
    rows = []
    for sport, aliases in ALIASES.items():
        supported = sport in prescriptions.SPORTS
        if not supported and not aliases & declared:
            continue
        families = [t for t in templates if t["sport"] == sport]
        opportunity_days, light_days = set(), set()
        for day in data["days"]:
            for group in day["opportunities"]:
                c = group["constraints"]
                matches = c["sport_scope"] == "any" or aliases & {str(s).strip().casefold() for s in c["sports"]}
                if not matches:
                    continue
                opportunity_days.add(day["date"])
                for template in families:
                    if opportunity_issues(group, template, resources):
                        continue
                    minimum = prescriptions.FAMILIES[template["key"]]["minimum"]
                    intervals, _ = daylight.allowed_intervals(light_data, group, sport)
                    room = min(group["max_minutes"], day.get("daily_max_minutes") if day.get("daily_max_minutes") is not None else 1440) * 60
                    if room >= minimum and any((datetime.fromisoformat(i["end_at"]) - datetime.fromisoformat(i["start_at"])).total_seconds() >= minimum for i in intervals):
                        light_days.add(day["date"])
        candidates = {g["date"] for g in alternatives if any(c["sport"] == sport for c in g["candidates"])}
        issues = set(attempt_issues.get(sport, set())) - {"SPORT_NOT_ALLOWED"}
        if not supported:
            issues = {"SPORT_TEMPLATE_NOT_SUPPORTED"}
        elif not opportunity_days:
            issues.add("NO_KNOWN_OPPORTUNITY")
        elif not candidates and not issues:
            issues.update(blockers or ["CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT"])
        rows.append({"sport": sport, "supported": supported, "opportunity_days": len(opportunity_days),
                     "daylight_days": len(light_days), "candidate_days": len(candidates),
                     "planned_sessions": sum(c["sport"] == sport for c in proposals), "reasons": sorted(issues)})
    budget = starting_budget or {}
    return {"schema_version": "training-sport-availability-v0.3", "sports": rows,
            "goal_coverage": goal_coverage(data, templates, proposals, alternatives, rows),
            "weekly_budget": {k: budget.get(k) for k in ("mode", "max_sessions_per_7_days", "max_minutes_per_7_days", "baseline_status")}}
