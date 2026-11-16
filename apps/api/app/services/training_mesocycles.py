"""Civil-date mesocycle coordination within the recorded starting envelope.

Percentages are explicit product defaults, not validated physiological loads.
Strength blocks reserve time; their weights/sets are never scaled by this policy.
"""

from datetime import date, datetime, timedelta

SCHEMA = "training-mesocycle-coordination-v0.1"
RULES = "training-mesocycle-policy-v0.1"
WAVE = [80, 90, 100, 70]


def day(value):
    return date.fromisoformat(value)


def build(data, budget, coordinated=None):
    first, last = day(data["start_date"]), day(data["end_date"])
    periods = sorted((p for p in data["periods"] if p["period_type"] == "MESOCYCLE"), key=lambda p: (p["start_date"], p["id"]))
    future = [p for p in periods if p["end_date"] >= data["start_date"]][:2]
    coordinated = (last - first).days >= 7 if coordinated is None else coordinated
    blocks = []
    for period in periods:
        start, end = day(period["start_date"]), day(period["end_date"])
        if end < first or start > last:
            continue
        count = ((end - start).days + 7) // 7
        for index in range(count):
            low, high = start + timedelta(days=index * 7), min(end, start + timedelta(days=index * 7 + 6))
            if high < first or low > last:
                continue
            # A short remainder is not an invented full recovery week.
            substantial = (high - low).days >= 3
            if not coordinated or count == 1:
                percent, kind = 100, "steady"
            elif index == count - 1 and substantial:
                percent, kind = 70, "consolidation"
            elif count == 2:
                percent, kind = 100, "build"
            else:
                percent = WAVE[index % 4]
                if percent == 70 and index == count - 2 and (end - (start + timedelta(days=(count - 1) * 7))).days >= 3:
                    percent = 100
                kind = "consolidation" if percent == 70 else "entry" if percent == 80 else "build"
            # Short remainders share the rolling budget with their neighbours;
            # only the civil-date block ceiling is prorated.
            days = (high - low).days + 1
            minutes = budget["max_minutes_per_7_days"] * percent * days // 700
            minutes = minutes // 5 * 5
            if not coordinated:
                minutes = budget["max_minutes_per_7_days"]
            blocks.append({"key": period["id"] + ":" + str(index + 1),
                           "mesocycle_id": period["id"], "ordinal": index + 1,
                           "start_date": low.isoformat(), "end_date": high.isoformat(),
                           "kind": kind, "volume_percent": percent,
                           "max_sessions": min(budget["max_sessions_per_7_days"], days),
                           "max_minutes": minutes})
    return {"schema_version": SCHEMA, "rules_version": RULES,
            "mode": "coordinated" if coordinated else "short_review",
            "wave_percentages": WAVE, "date_basis": "civil_days_from_saved_mesocycle_start",
            "above_starting_budget_allowed": False, "intensity_progression_applied": False,
            "personal_response_model_applied": False,
            "recommended_end_date": min(future[-1]["end_date"], (first + timedelta(days=365)).isoformat()) if future else data["end_date"],
            "recommended_mesocycle_ids": [p["id"] for p in future],
            "blocks": blocks}


def block_on(context, value):
    return next((b for b in context["blocks"] if b["start_date"] <= value <= b["end_date"]), None)


def remaining(context, value, loads):
    block = block_on(context, value)
    if not block or context["mode"] != "coordinated":
        return None
    within = [v for v in loads if block["start_date"] <= v["date"].isoformat() <= block["end_date"]]
    if len(within) >= block["max_sessions"] or any(v["seconds"] is None and not v.get("missed_reservation") for v in within):
        return 0
    return max(0, block["max_minutes"] * 60 - sum(v["seconds"] for v in within if v["seconds"] is not None))


def duration_ceiling(context, value, family, reference):
    block = block_on(context, value)
    if not block or context["mode"] != "coordinated" or family["sport"] == "STRENGTH":
        return family["maximum"]
    cap = reference["cap_seconds"] if reference["cap_seconds"] is not None else family["default"]
    if cap is None or cap < family["minimum"]:
        return family["maximum"]  # Parameterization reports the actual missing reference.
    return max(family["minimum"], min(cap, family["maximum"]) * block["volume_percent"] // 100)


def order_days(context, data, templates, references, opportunity_issues, families, preferences, *, global_scarcity=False):
    if context["mode"] != "coordinated":
        return data["days"]
    resources = ((data["profile"] or {}).get("data") or {}).get("resources", [])
    from app.planning.domain import daylight
    light_data = (data.get("daylight_context") or {}).get("options_receipt", {}).get("artifact", {}).get("proposal", {}).get("data", {})

    def usable(group, template, day):
        if opportunity_issues(group, template, resources):
            return False
        intervals, _ = daylight.allowed_intervals(light_data, group, template["sport"])
        minimum = families[template["key"]]["minimum"]
        if min(group["max_minutes"], day.get("daily_max_minutes") if day.get("daily_max_minutes") is not None else 1440) * 60 < minimum:
            return False
        return any((datetime.fromisoformat(v["end_at"]) - datetime.fromisoformat(v["start_at"])).total_seconds() >= minimum for v in intervals)
    supported = {}
    for d in data["days"]:
        supported[d["date"]] = {r["capability_key"] for r in d["capability_roles"] if r["role"] == "primary_development"
            for t in templates if r["capability_key"] in t["capabilities"]
            and (references[t["key"]]["cap_seconds"] or families[t["key"]]["default"] or 0) >= families[t["key"]]["minimum"]
            and any(usable(g, t, d) for g in d["opportunities"])}

    def priority(d):
        block = block_on(context, d["date"])
        peers = [v for v in data["days"] if block and block["start_date"] <= v["date"] <= block["end_date"]]
        rarity = min((sum(key in supported[v["date"]] for v in peers) for key in supported[d["date"]]), default=1000)
        if global_scarcity:
            # A rolling seven-day quota crosses saved microcycle boundaries.
            # Reserve scarce opportunities before an earlier flexible week
            # consumes the quota needed by its weekend in the next block.
            return (d["date"] not in preferences, rarity, block["start_date"] if block else d["date"], d["date"])
        return (block["start_date"] if block else d["date"], d["date"] not in preferences, rarity, d["date"])

    return sorted(data["days"], key=priority)
