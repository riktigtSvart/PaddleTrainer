"""Bounded, reviewable sample prescriptions. No inferred personal response model.

The library supplies the family envelopes. Durations, spacing and rolling caps
below are explicit versioned product defaults, not physiological estimates.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.planning.domain.athlete_setup import digest, review_profile
from app.planning.domain.workout_family.builtins import builtin_workout_family_registry_v0_1
from app.services.planning_strategy import main_events, phase_at, recent_signals

RULES = "training-plan-policy-v0.3"
SOURCE = "PADDLETRAINER_C18_4"
FAMILY_REGISTRY = builtin_workout_family_registry_v0_1()
MARKER = "paddletrainer_training_plan"
POLICY = {
    "version": RULES,
    "max_sessions_per_day": 1,
    "default_sessions_per_7_days": 2,
    "max_sessions_per_7_days": 3,
    "default_minutes_per_7_days": 90,
    "max_minutes_per_7_days": 180,
    "minimum_gap_hours": 36,
    "new_session_lead_minutes": 15,
    "personal_response_model_applied": False,
    "missed_load_is_not_repaid": True,
}
SPORTS = {
    "KAYAK": {"kajak", "kayak", "kayaking"},
    "STRENGTH": {"erőnlét", "erőedzés", "erősítés", "strength"},
}


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


def completion_events(data, plans, now):
    """A missing sync never proves a miss, including after successful sync."""
    linked = {}
    events = []
    plan_workouts = {p["workout"]["id"]: p["workout"] for p in plans}
    for session in data["recent_sessions"]:
        started = at(session["started_at"])
        plan = plan_workouts.get(session["planned_workout_id"], {})
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
            state = "planned_completed" if session["planned_workout_id"] else "unplanned_completed"
        if session["planned_workout_id"]:
            linked[session["planned_workout_id"]] = session["id"]
        events.append(
            {
                "kind": state,
                "session_id": session["id"],
                "workout_id": session["planned_workout_id"],
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
        if w["id"] in linked or w["status"] == "CANCELLED":
            continue
        end = (
            at(w["planned_start_time"]) + timedelta(seconds=w["duration_sec"])
            if (w["planned_start_time"] and w["duration_sec"] is not None)
            else None
        )
        if w["status"] == "SKIPPED":
            state = "confirmed_missed"
        elif w["status"] == "COMPLETED":
            state = "reported_completed"
        elif end and end <= now or not end and w["date"] < data["local_today"]:
            state = "execution_unknown"
        else:
            continue
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
    if template["effort"] == "moderate" and c["effort_cap"] not in {"moderate", "any"}:
        issues.append("EFFORT_NOT_ALLOWED")
    equipment = {v.casefold().strip() for v in ([] if c.get("resources_scope") == "location" else resources) + c["resources"]}
    required = (
        {"kajak", "kayak", "hajó", "kajakergométer"}
        if template["sport"] == "KAYAK"
        else {"kézisúlyzó", "dumbbell", "kézisúlyzók"}
    )
    if not equipment & required:
        issues.append("EQUIPMENT_NOT_DECLARED")
    return issues


def allows(group, template, resources):
    return not opportunity_issues(group, template, resources)


def make_candidate(day, group, template, start, role, reference):
    family = FAMILY_REGISTRY.get(template["key"])
    value = {
        "template_key": template["key"],
        "template_version": "v0.1",
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
        **({"location": group["constraints"]["location"], "location_id": group["constraints"]["location_id"], "alternative_group_key": group["constraints"]["alternative_group_key"]} if group["constraints"].get("location_id") else {}),
    }
    value["candidate_key"] = digest(value)
    return value


def fits_rolling_budget(commitments, target, seconds, max_count, max_seconds):
    """Check all seven-day windows containing the candidate, including future plans."""
    for offset in range(7):
        first = target - timedelta(days=offset)
        window = [v for v in commitments if first <= v["date"] <= first + timedelta(days=6)]
        if len(window) + 1 > max_count or any(v["seconds"] is None for v in window):
            return False
        if sum(v["seconds"] for v in window) + seconds > max_seconds:
            return False
    return True


def build(data, plans, now, active_window_end=None, selection_preferences=None):
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
    if str(data["program_sport"]).strip().casefold() not in SPORTS["KAYAK"]:
        blockers.append("PROGRAM_SPORT_NOT_SUPPORTED")
    blockers += [
        g for g in data["gaps"] if g in {"PROGRAM_TIMEZONE_REVIEW", "GOAL_SOURCE_SNAPSHOT_CHANGED"}
    ]
    signals = recent_signals(data, today)
    illness = any(s["kind"] == "reported_illness" for s in signals)
    if illness:
        blockers.append("CURRENT_ILLNESS_REVIEW")
    events = completion_events(data, plans, now)
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
        # A confirmed miss reserves its original planning budget. It is not
        # physiological load and imposes no recovery spacing, but it must not
        # free a quota which the greedy placement would silently repay.
        loads.append(
            {
                "date": date.fromisoformat(w["date"]),
                "seconds": w["duration_sec"] if w["duration_sec"] is not None else
                    (p.get("duration_estimate") or {}).get("upper_sec"),
                "at": at(w["planned_start_time"])
                if w["planned_start_time"] and w["status"] != "SKIPPED"
                else None,
                "sport": w["sport"],
            }
        )
    references = {}
    for s in data["recent_sessions"]:
        day = at(s["started_at"]).astimezone(zone).date()
        occupied.add(day.isoformat())
        loads.append(
            {
                "date": day,
                "seconds": s["duration_sec"],
                "at": at(s["started_at"]),
                "sport": s["sport"],
            }
        )
        if s["duration_sec"] and s["ended_at"] and at(s["ended_at"]) <= now:
            if s["sport"] == "KAYAK" and s["duration_sec"] >= 3600:
                references["KAYAK_LONG_AEROBIC"] = s["id"]
            if s["sport"] == "STRENGTH" and s["duration_sec"] >= 1800:
                references["STRENGTH_REFERENCE_AND_DEVELOPMENT"] = s["id"]
    max_count = min(
        POLICY["max_sessions_per_7_days"],
        profile["typical_days_per_week"]
        if profile and profile["typical_days_per_week"] is not None
        else POLICY["default_sessions_per_7_days"],
    )
    max_seconds = 60 * min(
        POLICY["max_minutes_per_7_days"],
        profile["typical_minutes_per_week"]
        if profile and profile["typical_minutes_per_week"] is not None
        else POLICY["default_minutes_per_7_days"],
    )
    # Reserve reviewed future sessions before filling empty dates. Otherwise a
    # greedy scan can insert an earlier workout and displace the unchanged
    # reviewed session after it, especially immediately after a confirmed miss.
    for p in eligible:
        w = p["workout"]
        loads.append(
            {
                "eligible_id": w["id"],
                "date": date.fromisoformat(w["date"]),
                "seconds": w["duration_sec"],
                "at": at(w["planned_start_time"]),
                "sport": w["sport"],
            }
        )
    proposals, reasons, budgets = [], [], {}
    diagnostics = []
    alternatives = []
    unavailable_alternatives = []
    selection_preferences = selection_preferences or {}
    used_templates = []
    for day in data["days"]:
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
            and (not e["observed_end_at"] or at(e["observed_end_at"]) >= now - timedelta(hours=48))
            for e in events
        ) and target <= today + timedelta(days=1):
            reason = "RECENT_EXECUTION_REVIEW"
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
                            r["role"] != "primary_development",
                            r["role"] != "secondary_development",
                        ),
                    )
                    if r["capability_key"] in template["capabilities"]
                ),
                None,
            )
            if (
                not role
                or template["key"] != "KAYAK_EASY_TECHNICAL"
                and template["key"] not in references
            ):
                if role:
                    issues.add("PERSONAL_DURATION_REFERENCE_MISSING")
                continue
            choices.append((template, role))
        choices.sort(
            key=lambda v: (
                v[1]["role"] != "primary_development",
                used_templates.count(v[0]["key"]),
                v[0]["key"] == "KAYAK_EASY_TECHNICAL",
            )
        )
        available_candidates = []
        group_issues = {group["key"]: set() for group in day["opportunities"]}
        if not reason:
            for template, role in choices:
                for group in day["opportunities"]:
                    if not allows(group, template, profile["resources"]):
                        rejected = opportunity_issues(group, template, profile["resources"])
                        issues.update(rejected)
                        group_issues[group["key"]].update(rejected)
                        continue
                    seconds = template["minutes"] * 60
                    if (
                        min(
                            group["max_minutes"] - budgets.get(group["key"], 0),
                            day["daily_max_minutes"]
                            if day["daily_max_minutes"] is not None
                            else 1440,
                        )
                        * 60
                        < seconds
                    ):
                        issues.add("OPPORTUNITY_OR_DAILY_MINUTE_CAP")
                        group_issues[group["key"]].add("OPPORTUNITY_OR_DAILY_MINUTE_CAP")
                        continue
                    for interval in group["intervals"]:
                        low = max(
                            at(interval["start_at"]),
                            datetime.combine(target, time.min, zone).astimezone(UTC),
                        )
                        old_start = next(
                            (
                                at(p["workout"]["planned_start_time"])
                                for p in eligible
                                if p["template_key"] == template["key"]
                                and p["workout"]["date"] == day["date"]
                                and low
                                <= at(p["workout"]["planned_start_time"])
                                < at(interval["end_at"])
                            ),
                            None,
                        )
                        lead = now + timedelta(minutes=POLICY["new_session_lead_minutes"])
                        lead = datetime.fromtimestamp(
                            ((int(lead.timestamp()) + 899) // 900) * 900, UTC
                        )
                        start = old_start or max(low, lead)
                        if (
                            start <= now
                            or start.astimezone(zone).date() != target
                            or start + timedelta(seconds=seconds) > at(interval["end_at"])
                        ):
                            issues.add("INTERVAL_TOO_SHORT_OR_START_PASSED")
                            group_issues[group["key"]].add("INTERVAL_TOO_SHORT_OR_START_PASSED")
                            continue
                        valid = fits_rolling_budget(loads, target, seconds, max_count, max_seconds)
                        if not valid or any(
                            v["at"]
                            and abs((v["at"] - start).total_seconds())
                            < POLICY["minimum_gap_hours"] * 3600
                            for v in loads
                        ):
                            issues.add("ROLLING_BUDGET_REVIEW" if not valid else "MINIMUM_SPACING")
                            group_issues[group["key"]].add("ROLLING_BUDGET_REVIEW" if not valid else "MINIMUM_SPACING")
                            continue
                        candidate = make_candidate(
                            day, group, template, start, role, references.get(template["key"])
                        )
                        available_candidates.append(candidate)
                        break
            for group in day["opportunities"]:
                if group["constraints"].get("location_id") and not any(candidate["opportunity_key"] == group["key"] for candidate in available_candidates):
                    codes = group_issues[group["key"]] or issues or {"NO_SUPPORTED_SAMPLE_FITS"}
                    unavailable_alternatives.append({"date": day["date"], "opportunity_key": group["key"], "location_id": group["constraints"]["location_id"], "location": group["constraints"]["location"], "codes": sorted(set(codes) | set(group["constraints"].get("location_issues", [])))})
            if available_candidates:
                preference = selection_preferences.get(day["date"])
                found = next((candidate for candidate in available_candidates if preference and candidate["template_key"] == preference["template_key"] and candidate["opportunity_key"] == preference["opportunity_key"]), None) if preference else available_candidates[0]
                if preference and found is None:
                    reason = "SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE"
                alternatives.append({"date": day["date"], "recommended_candidate_key": available_candidates[0]["candidate_key"], "selected_candidate_key": found["candidate_key"] if found else None, "candidates": available_candidates})
                if found:
                    budgets[found["opportunity_key"]] = budgets.get(found["opportunity_key"], 0) + found["duration_sec"] // 60
            if not found:
                reason = reason or "NO_SUPPORTED_SAMPLE_FITS"
        if found:
            proposals.append(found)
            used_templates.append(found["template_key"])
            loads.append(
                {
                    "date": target,
                    "seconds": found["duration_sec"],
                    "at": at(found["start_at"]),
                    "sport": found["sport"],
                }
            )
        else:
            reasons.append({"date": day["date"], "reason": reason})
            if reason == "NO_SUPPORTED_SAMPLE_FITS":
                diagnostics.append({"date": day["date"], "codes": sorted(issues)})
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
    return {
        "policy": POLICY,
        "entry_review": gate,
        "blockers": blockers,
        "events": events,
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
            "version": "training-preparation-v0.1",
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
                and (date.fromisoformat(data["start_date"]) - timedelta(days=6)).isoformat() <= p["workout"]["date"] <= (date.fromisoformat(data["end_date"]) + timedelta(days=6)).isoformat()
                and p["workout"]["duration_sec"] is None and not p.get("duration_estimate")],
            "estimated_duration_workout_ids": [p["workout"]["id"] for p in protected
                if not p["linked"] and p.get("duration_estimate")
                and (date.fromisoformat(data["start_date"]) - timedelta(days=6)).isoformat() <= p["workout"]["date"] <= (date.fromisoformat(data["end_date"]) + timedelta(days=6)).isoformat()],
        },
    }
