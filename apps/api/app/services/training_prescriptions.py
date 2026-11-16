"""Transparent starting prescriptions from stored durations, not a response model.

History/window thresholds and shortened family forms are explicit product
choices. No training progression, personal HR threshold or strength load is
inferred from a completed session's duration.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

HISTORY_DAYS = 56
SPORTS = {
    "KAYAK": {"kajak", "kayak", "kayaking", "kayak_flatwater"},
    "STRENGTH": {"erőnlét", "erőedzés", "erősítés", "strength", "kondi"},
    "RUNNING": {"futás", "futas", "run", "running"},
    "SWIMMING": {"úszás", "uszas", "swimming", "swim"},
}
FAMILIES = {
    "KAYAK_EASY_TECHNICAL": {"sport": "KAYAK", "minimum": 1200, "maximum": 2700, "nominal_minimum": 1800, "default": 1800},
    "KAYAK_LONG_AEROBIC": {"sport": "KAYAK", "minimum": 3600, "maximum": 4500, "nominal_minimum": 3600, "default": None},
    "STRENGTH_REFERENCE_AND_DEVELOPMENT": {"sport": "STRENGTH", "minimum": 1200, "maximum": 1800, "nominal_minimum": None, "default": None},
    "RUN_EASY_AEROBIC_FALLBACK": {"sport": "RUNNING", "minimum": 1200, "maximum": 2700, "nominal_minimum": 1800, "default": 1200},
    "SWIM_EASY_AEROBIC": {"sport": "SWIMMING", "minimum": 1200, "maximum": 3600, "nominal_minimum": 1800, "default": 1200},
}


def sport_code(value):
    normalized = str(value).strip().casefold()
    return next((code for code, aliases in SPORTS.items() if normalized in aliases), None)


def valid_completed(session, cutoff):
    seconds = session["duration_sec"]
    if type(seconds) is not int or seconds < 0 or not session["ended_at"]:
        return False
    start, end = (datetime.fromisoformat(session[key]) for key in ("started_at", "ended_at"))
    return start <= end <= cutoff and seconds <= (end - start).total_seconds()


def references(data):
    cutoff = datetime.fromisoformat(data["captured_at"])
    completed = [session for session in data["recent_sessions"]
                 if valid_completed(session, cutoff) and session["duration_sec"] > 0]
    completed.sort(key=lambda session: (session["started_at"], session["id"]), reverse=True)
    result = {}
    for key, family in FAMILIES.items():
        eligible = [session for session in completed if session["sport"] == family["sport"]
                    and not session.get("reference_occasion", False)
                    and (key != "KAYAK_LONG_AEROBIC" or session["duration_sec"] >= 3600)][:3]
        cap = min((session["duration_sec"] for session in eligible), default=None)
        anchor = next((session["id"] for session in eligible if session["duration_sec"] == cap), None)
        result[key] = {"session_ids": [session["id"] for session in eligible],
                       "cap_seconds": cap, "anchor_id": anchor}
    from app.services import training_running
    result[training_running.FAMILY] = training_running.reference(data, completed, valid_completed, sport_code)
    from app.services import training_swimming
    result[training_swimming.FAMILY] = training_swimming.reference(data, completed)
    return result


def running_template(block):
    return {"key": "RUN_EASY_AEROBIC_FALLBACK", "sport": "RUNNING", "minutes": 30,
            "title": "Könnyű aerob futás · 30 perc", "effort": "easy",
            "capabilities": ["PERIPHERAL_OXIDATIVE_CAPACITY"],
            "description": "5 perc könnyű bemelegítés; 20 perc könnyű, beszélgetős futás; 5 perc levezetés. RPE 2–3/10, pulzus- és tempókényszer nélkül. Általános aerob támogatás; a kajakspecifikus technikai edzést nem helyettesíti.",
            "blocks": [block(1, "WARMUP", "Könnyű bemelegítés", 300),
                       block(2, "WORK", "Könnyű, beszélgetős futás", 1200),
                       block(3, "COOLDOWN", "Levezetés", 300)]}


def parameterize(template, *, available_seconds, reference, block, preferred_seconds=None):
    if template["sport"] == "RUNNING" and "running" in reference:
        from app.services.training_running import parameterize as running_start
        return running_start(template, available_seconds, reference, block, preferred_seconds)
    family = FAMILIES[template["key"]]
    historical = reference["cap_seconds"]
    reference_cap = historical if historical is not None else family["default"]
    if reference_cap is None:
        return None, "PERSONAL_DURATION_REFERENCE_MISSING"
    if reference_cap < family["minimum"]:
        return None, "PERSONAL_DURATION_REFERENCE_TOO_SHORT"
    cap = min(available_seconds, reference_cap, family["maximum"])
    seconds = int(cap // 300) * 300
    if type(preferred_seconds) is int and preferred_seconds % 300 == 0 and family["minimum"] <= preferred_seconds <= cap:
        seconds = preferred_seconds
    if seconds < family["minimum"]:
        return None, "OPPORTUNITY_OR_DAILY_MINUTE_CAP"
    minutes = seconds // 60
    result = dict(template)
    if seconds != template["minutes"] * 60 or template["sport"] == "RUNNING":
        result["version"] = "v0.2"
        warmup = 300 if seconds < 1800 or template["sport"] in {"STRENGTH", "RUNNING"} else 600
        cooldown = 300
        work = seconds - warmup - cooldown
        if template["sport"] == "STRENGTH":
            result.update(title=f"Erőreferencia · {minutes} perces időkeret",
                          description=f"5 perc ismert bemelegítés. Ismert kézisúlyzós evezés és goblet guggolás: gyakorlatonként 2 × 6 kontrollált ismétlés, 2 perc pihenő; már ismert teherrel, legalább 3–4 ismétlés tartalékkal. A {work // 60} perces főrész időkeret a pihenőkkel együtt, nem folyamatos munkadózis. Ha nem fér bele kényelmesen, rövidíts, a pihenőt ne siettesd. 5 perc levezetés és terhelésnapló. Nincs maximális teszt, új gyakorlat vagy automatikus súlyemelés.")
            work_name = "Két ismert gyakorlat: 2 × 6, RIR 3–4; pihenőkkel"
        else:
            running = template["sport"] == "RUNNING"
            title = "Könnyű aerob futás" if running else "Hosszabb könnyű evezés" if template["key"] == "KAYAK_LONG_AEROBIC" else "Könnyű technikai kajak"
            work_name = "Könnyű, beszélgetős futás" if running else "Nyugodt evezés, ismert technikai fókusszal"
            result.update(title=f"{title} · {minutes} perc",
                          description=f"{warmup // 60} perc könnyű bemelegítés; {work // 60} perc {'könnyű, beszélgetős futás' if running else 'nyugodt evezés, ismert technikai fókusszal'}; 5 perc levezetés. RPE 2–3/10, pulzus- és tempókényszer nélkül. Az időtartam a saját rögzített előzményhez és az elérhető időhöz igazodik; nem kötelező kitölteni. " + ("Általános aerob támogatás; a kajakspecifikus technikai edzést nem helyettesíti." if running else "A technika romlásakor rövidíts."))
        result["blocks"] = [block(1, "WARMUP", "Könnyű bemelegítés", warmup),
                            block(2, "WORK", work_name, work),
                            block(3, "COOLDOWN", "Levezetés", cooldown)]
    result["minutes"] = minutes
    metadata = {"schema_version": "training-prescription-v0.1", "family_key": template["key"],
                "duration_sec": seconds, "minimum_seconds": family["minimum"],
                "maximum_seconds": family["maximum"], "reference_session_ids": reference["session_ids"],
                "reference_cap_seconds": historical, "product_default_used": historical is None,
                "soft_duration_reduced": family["nominal_minimum"] is not None and seconds < family["nominal_minimum"],
                "progression_applied": False, "personal_response_model_applied": False,
                "intensity_basis": "product_default_not_personal_threshold"}
    if template["sport"] == "STRENGTH":
        metadata["strength"] = {"movements": 2, "sets_per_movement": 2, "repetitions": 6,
                                "rir_min": 3, "rir_max": 4, "load_kg": None}
    else:
        metadata["rpe"] = {"min": 2, "max": 3}
    return (result, metadata), None


def starting_budget(data, reconciliation):
    profile = (data["profile"] or {}).get("data") or {}
    zone = ZoneInfo(data["timezone_name"])
    cutoff = datetime.fromisoformat(data["captured_at"])
    today = cutoff.astimezone(zone).date()
    current_monday = today - timedelta(days=today.weekday())
    low = datetime.fromisoformat(data["recent_window"]["start_at"]).astimezone(zone).date()
    monday = low + timedelta(days=(-low.weekday()) % 7)
    weeks = []
    main_sport = sport_code(data["program_sport"])
    while monday < current_monday:
        end_day = monday + timedelta(days=7)
        first = datetime.combine(monday, time.min, zone)
        last = datetime.combine(end_day, time.min, zone)
        source = next((value for value in reconciliation["sync_windows"]
                       if datetime.fromisoformat(value["from_at"]) <= first
                       and last <= datetime.fromisoformat(value["to_exclusive_at"])
                       and last <= datetime.fromisoformat(value["started_at"])), None)
        recorded = [session for session in data["recent_sessions"]
                    if first <= datetime.fromisoformat(session["started_at"]) < last]
        complete = source is not None and all(valid_completed(session, cutoff) for session in recorded)
        positive = [session for session in recorded if valid_completed(session, cutoff) and session["duration_sec"] > 0]
        weeks.append({"start_date": monday.isoformat(), "end_date": (end_day - timedelta(days=1)).isoformat(),
                      "from_at": first.isoformat(), "to_exclusive_at": last.isoformat(),
                      "source_reference": source["result_reference"] if source else None,
                      "status": "covered" if complete else "incomplete_records" if source else "coverage_missing",
                      "session_ids": [session["id"] for session in positive],
                      "sessions": len(positive),
                      "duration_sec": sum(session["duration_sec"] for session in positive) if complete else None,
                      "main_sport_present": any(session["sport"] == main_sport for session in positive)})
        monday = end_day
    covered = weeks[-2:]
    observed = (len(covered) == 2 and all(week["status"] == "covered" and week["sessions"] and week["main_sport_present"] for week in covered)
                and (today - datetime.fromisoformat(covered[-1]["end_date"]).date()).days <= 14)
    if observed:
        count = min(7, *(week["sessions"] for week in covered))
        minutes = min(10080, *(week["duration_sec"] // 60 for week in covered))
    else:
        count, minutes = 3, 180
    count = min(count, profile.get("typical_days_per_week") if profile.get("typical_days_per_week") is not None else count if observed else 2)
    minutes = min(minutes, profile.get("typical_minutes_per_week") if profile.get("typical_minutes_per_week") is not None else minutes if observed else 90)
    return {"schema_version": "training-starting-budget-v0.1", "history_days": HISTORY_DAYS,
            "mode": "observed_covered_weeks" if observed else "declared_and_product_defaults",
            "weeks": weeks, "used_week_starts": [week["start_date"] for week in covered] if observed else [],
            "max_sessions_per_7_days": count, "max_minutes_per_7_days": minutes}
