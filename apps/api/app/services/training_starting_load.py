"""Evidence-labelled weekly envelopes and sport-aware starting spacing.

Only completed, sufficiently covered recent weeks or an explicit fresh current
baseline can lift the three-session starting envelope. Availability, old PBs and
planned workouts never become evidence of current fitness. Spacing and aerobic/
strength weights are transparent starting product rules, not a response model.
"""
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from app.services.training_swimming import options

SCHEMA = "training-starting-budget-v0.2"
SPACING = "training-start-spacing-v0.1"


def starting_budget(data, reconciliation):
    from app.services.training_prescriptions import starting_budget as legacy_budget
    legacy = legacy_budget(data, reconciliation)
    today = datetime.fromisoformat(data["captured_at"]).astimezone(ZoneInfo(data["timezone_name"])).date()
    profile = (data.get("profile") or {}).get("data") or {}
    baseline = (options(data).get("prescription_settings") or {}).get("current_baseline")
    recent_baseline = bool(baseline and today - timedelta(days=14) <= datetime.fromisoformat(baseline["to_date"]).date() <= today)
    weeks = legacy["weeks"]
    covered = []
    for week in reversed(weeks[-4:]):
        if week["status"] != "covered":
            break
        covered.insert(0, week)
    observed = len(covered) >= 2 and all(w["sessions"] > 0 for w in covered[-2:])
    if recent_baseline:
        count, minutes = baseline["weekly_sessions"], baseline["weekly_minutes"]
        mode, used = "declared_current_training", []
    elif observed:
        count = int(median(w["sessions"] for w in covered))
        minutes = int(median(w["duration_sec"] for w in covered)) // 60
        mode, used = "observed_covered_weeks", [w["start_date"] for w in covered]
    else:
        count, minutes = 3, 180
        mode, used = "declared_and_product_defaults", []
    count = min(7, count, profile.get("typical_days_per_week") if profile.get("typical_days_per_week") is not None else count if mode != "declared_and_product_defaults" else 2)
    minutes = min(10080, minutes, profile.get("typical_minutes_per_week") if profile.get("typical_minutes_per_week") is not None else minutes if mode != "declared_and_product_defaults" else 90)
    return {"schema_version": SCHEMA, "history_days": 56, "mode": mode, "weeks": weeks,
        "used_week_starts": used, "max_sessions_per_7_days": count, "max_minutes_per_7_days": minutes,
        "baseline_status": "used" if recent_baseline else "stale" if baseline else "not_provided",
        "current_baseline": baseline, "source_reference": data.get("training_options_reference") if baseline else None,
        "personal_response_model_applied": False, "historical_records_are_current_capacity": False}


def spacing_hours(first_sport, second_sport, *, known=False, rpe=None):
    if first_sport == second_sport == "STRENGTH":
        return 48
    if not known and not (type(rpe) in {int, float} and 0 < rpe <= 3):
        return 36
    if "STRENGTH" in {first_sport, second_sport}:
        return 24
    if first_sport == second_sport or {first_sport, second_sport} <= {"KAYAK", "SWIMMING"}:
        return 24
    return 12


def conflicts(loads, start, sport):
    return any(v.get("at") and abs((v["at"] - start).total_seconds()) < spacing_hours(v.get("sport"), sport,
        known=v.get("known", False), rpe=v.get("rpe")) * 3600 for v in loads)


def domain(sport):
    return "strength" if sport == "STRENGTH" else "aerobic"


def target_weights(roles, templates, program_sport):
    priorities = {}
    for template in templates:
        relevant = [r for r in roles if r["capability_key"] in template["capabilities"] and r["role"] in {"primary_development", "secondary_development"}]
        if relevant:
            key = domain(template["sport"])
            priorities[key] = max(priorities.get(key, 0), max(2 if r["role"] == "primary_development" else 1 for r in relevant))
    if priorities.get("aerobic") == priorities.get("strength") and len(priorities) == 2:
        priorities[domain(program_sport)] = 2
        priorities["aerobic" if domain(program_sport) == "strength" else "strength"] = 1
    return priorities


def allocation_pressure(loads, target, sport, weights):
    key = domain(sport)
    seconds = sum(v["seconds"] or 0 for v in loads if abs((v["date"] - target).days) <= 6 and domain(v.get("sport")) == key)
    return seconds / max(1, weights.get(key, 1)), -weights.get(key, 1)
