"""Calendar recurrence, local-time exceptions and bounded, conservative projections."""

from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.planning.domain import athlete_setup

MAX_OCCURRENCES = 4000


class CalendarConstraintError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise CalendarConstraintError(code)


def calendar_day(value):
    try:
        result = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise CalendarConstraintError("CALENDAR_CONSTRAINT_DATE_INVALID") from None
    require(date(1900, 1, 1) <= result <= date(2100, 12, 31), "CALENDAR_CONSTRAINT_DATE_INVALID")
    return result


def bounded_range(first, last):
    a, b = calendar_day(first), calendar_day(last)
    require(0 <= (b - a).days < 366, "CALENDAR_CONSTRAINT_RANGE_INVALID")
    return a, b


def occurs(rule, day):
    value = calendar_day(day)
    return rule["start_date"] <= day and (rule["end_date"] is None or day <= rule["end_date"]) and (
        rule["repeat"] == "once" and day == rule["start_date"]
        or rule["repeat"] == "weekly" and value.weekday() in rule["weekdays"]
    )


def validate_state(data):
    ids = [r["id"] for r in data["rules"]]
    require(len(set(ids)) == len(ids), "CALENDAR_CONSTRAINT_DUPLICATE_RULE")
    by_id = {r["id"]: r for r in data["rules"]}
    for rule in data["rules"]:
        calendar_day(rule["start_date"])
        if rule["end_date"] is not None:
            calendar_day(rule["end_date"])
            require(rule["start_date"] <= rule["end_date"], "CALENDAR_CONSTRAINT_DATE_INVALID")
        if rule["repeat"] == "once":
            require(rule["end_date"] == rule["start_date"] and rule["weekdays"] == [], "CALENDAR_CONSTRAINT_REPEAT_INVALID")
        else:
            require(bool(rule["weekdays"]) and sorted(set(rule["weekdays"])) == rule["weekdays"], "CALENDAR_CONSTRAINT_REPEAT_INVALID")
    seen = set()
    for exception in data["exceptions"]:
        key = exception["rule_id"], exception["date"]
        require(key not in seen, "CALENDAR_CONSTRAINT_DUPLICATE_EXCEPTION")
        seen.add(key)
        require(exception["rule_id"] in by_id and occurs(by_id[exception["rule_id"]], exception["date"]), "CALENDAR_CONSTRAINT_EXCEPTION_NOT_FOUND")
    return data


def expand(data, first, last, display_zone):
    a, b = bounded_range(first, last)
    low = datetime.combine(a, time.min, ZoneInfo(display_zone)).astimezone(UTC)
    high = datetime.combine(b + timedelta(days=1), time.min, ZoneInfo(display_zone)).astimezone(UTC)
    source_zone = ZoneInfo(data["timezone_name"])
    start = low.astimezone(source_zone).date() - timedelta(days=1)
    finish = high.astimezone(source_zone).date()
    exceptions = {(e["rule_id"], e["date"]): e for e in data["exceptions"]}
    result = []
    for rule in data["rules"]:
        current = max(start, date.fromisoformat(rule["start_date"]))
        stop = min(finish, date.fromisoformat(rule["end_date"])) if rule["end_date"] else finish
        while current <= stop:
            day = current.isoformat()
            if occurs(rule, day):
                override = exceptions.get((rule["id"], day))
                details = override["replacement"] if override else rule["details"]
                if details is not None:
                    item = {"key": rule["id"] + ":" + day, "rule_id": rule["id"], "source_date": day,
                        "repeat": rule["repeat"], "overridden": override is not None, "details": deepcopy(details),
                        "start_at": None, "end_at": None, "elapsed_minutes": None, "issue": None}
                    try:
                        end_day = (current + timedelta(days=int(details["ends_next_day"]))).isoformat()
                        x = athlete_setup.local_instant(day, details["start_time"], data["timezone_name"], details["start_fold"])
                        y = athlete_setup.local_instant(end_day, details["end_time"], data["timezone_name"], details["end_fold"])
                        minutes = (y - x).total_seconds() / 60
                        require(0 < minutes <= 1500, "CALENDAR_CONSTRAINT_DURATION_INVALID")
                        require(details["max_minutes"] is None or details["max_minutes"] <= minutes, "CALENDAR_CONSTRAINT_CAPACITY_INVALID")
                        if x < high and y > low:
                            item.update(start_at=x.isoformat(), end_at=y.isoformat(), elapsed_minutes=minutes)
                        else:
                            current += timedelta(days=1)
                            continue
                    except (athlete_setup.SetupRuleError, CalendarConstraintError) as exc:
                        item["issue"] = str(exc)
                        if not a <= current <= b:
                            current += timedelta(days=1)
                            continue
                    result.append(item)
                    require(len(result) <= MAX_OCCURRENCES, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
            current += timedelta(days=1)
    return sorted(result, key=lambda x: (x["start_at"] or x["source_date"], x["key"]))


def overlapping(a, b, x, y):
    return a < y and x < b


def subtract_interval(start, end, blocked):
    parts = [(start, end)]
    for low, high in sorted(blocked):
        remaining = []
        for a, b in parts:
            if not overlapping(a, b, low, high):
                remaining.append((a, b))
            else:
                if a < low:
                    remaining.append((a, min(b, low)))
                if high < b:
                    remaining.append((max(a, high), b))
        parts = remaining
    return parts


def opportunities(availability, occurrences, first, last, zone):
    """Each split retains one shared source budget; overlapping sources are never summed."""
    resolved = athlete_setup.resolve_calendar(availability) if availability else {"days": []}
    days = {d["date"]: d for d in resolved["days"]}
    low = datetime.combine(calendar_day(first), time.min, ZoneInfo(zone)).astimezone(UTC)
    high = datetime.combine(calendar_day(last) + timedelta(days=1), time.min, ZoneInfo(zone)).astimezone(UTC)
    windows = []
    for day in resolved["days"]:
        for w in day["windows"]:
            windows.append({"key": "legacy:" + day["date"] + ":" + w["key"], "source_date": day["date"],
                "start_at": w["start_at"], "end_at": w["end_at"], "max_minutes": w["max_minutes"],
                "source": "athlete_availability", "daily_max_minutes": day["max_total_minutes"]})
    for item in occurrences:
        if item["details"]["kind"] == "available":
            windows.append({"key": item["key"], "source_date": item["source_date"], "start_at": item["start_at"],
                "end_at": item["end_at"], "max_minutes": item["details"]["max_minutes"],
                "source": "calendar_rule", "daily_max_minutes": days.get(item["source_date"], {}).get("max_total_minutes")})
    hard = [o for o in occurrences if o["details"]["kind"] == "busy" and o["details"]["firmness"] == "fixed"]
    blocked = [(datetime.fromisoformat(o["start_at"]), datetime.fromisoformat(o["end_at"])) for o in hard if o["start_at"]]
    if availability:
        tz = ZoneInfo(availability["timezone_name"])
        for day in resolved["days"]:
            if day["status"] == "unavailable":
                d = calendar_day(day["date"])
                blocked.append((datetime.combine(d, time.min, tz).astimezone(UTC),
                    datetime.combine(d + timedelta(days=1), time.min, tz).astimezone(UTC)))
    unknown_days = {d for o in hard if o["issue"] for d in (
        o["source_date"], (calendar_day(o["source_date"]) + timedelta(days=int(o["details"]["ends_next_day"]))).isoformat())}
    result = []
    for window in windows:
        day = window["source_date"]
        if window["start_at"] is None:
            if not first <= day <= last:
                continue
            parts, known, minutes = [], False, None
        else:
            a, b = datetime.fromisoformat(window["start_at"]), datetime.fromisoformat(window["end_at"])
            if not overlapping(a, b, low, high):
                continue
            touched = {a.astimezone(ZoneInfo(zone)).date().isoformat(), b.astimezone(ZoneInfo(zone)).date().isoformat()}
            known = not touched.intersection(unknown_days)
            parts = subtract_interval(max(a, low), min(b, high), blocked) if known else []
            if days.get(day, {}).get("status") == "unavailable":
                parts = []
            minutes = min(window["max_minutes"], sum((b - a).total_seconds() / 60 for a, b in parts)) if known else None
        result.append({**window, "known": known, "usable_minutes": minutes,
            "intervals": [{"start_at": a.isoformat(), "end_at": b.isoformat()} for a, b in parts]})
    return result


def duration_bounds(plan):
    if plan["duration_sec"] is not None:
        return plan["duration_sec"], plan["duration_sec"], False
    estimate = plan.get("duration_estimate")
    return (estimate["lower_sec"], estimate["upper_sec"], True) if estimate else (None, None, False)


def conflicts(plans, occurrences):
    result = []
    busy = [o for o in occurrences if o["details"]["kind"] == "busy"]
    for plan in plans:
        for item in busy:
            code = None
            if plan["start_at"] and item["start_at"]:
                a, x, y = map(datetime.fromisoformat, (plan["start_at"], item["start_at"], item["end_at"]))
                lower, upper, estimated = duration_bounds(plan)
                if upper is None:
                    if x <= a < y:
                        code = "START_IN_COMMITMENT"
                    elif plan["date"] == item["source_date"] and a < y:
                        code = "PLAN_END_UNKNOWN"
                elif estimated and upper > 0 and overlapping(a, a + timedelta(seconds=upper), x, y):
                    code = "START_IN_COMMITMENT" if x <= a < y else "ESTIMATED_WORKOUT_OVERLAP" if a + timedelta(seconds=lower) > x else "ESTIMATED_OVERLAP_POSSIBLE"
                elif not estimated and upper > 0 and overlapping(a, a + timedelta(seconds=upper), x, y):
                    code = "WORKOUT_OVERLAP"
            elif plan["date"] == item["source_date"]:
                code = "PLAN_TIME_UNKNOWN" if plan["start_at"] is None else "COMMITMENT_TIME_UNKNOWN"
            if code:
                result.append({"plan_id": plan["id"], "plan_title": plan["title"], "occurrence_key": item["key"],
                    "constraint_title": item["details"]["title"], "date": item["source_date"],
                    "severity": "review" if "UNKNOWN" in code or code.startswith("ESTIMATED_") else item["details"]["firmness"], "code": code})
                require(len(result) <= MAX_OCCURRENCES, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
    return result


def opportunity_conflicts(plans, groups, availability, already_blocked):
    """Check each plan against declared windows, without treating missing data as zero."""
    days = {d["date"]: d for d in availability["days"]} if availability else {}
    result = []
    for plan in plans:
        if plan["id"] in already_blocked:
            continue
        day = days.get(plan["date"])
        start = datetime.fromisoformat(plan["start_at"]) if plan["start_at"] else None
        candidates = [g for g in groups if g["source_date"] == plan["date"] or start and g["start_at"]
            and datetime.fromisoformat(g["start_at"]) <= start < datetime.fromisoformat(g["end_at"])]
        code, severity = None, "fixed"
        if day and day["status"] == "unavailable":
            code = "TRAINING_DAY_UNAVAILABLE"
        elif candidates:
            if start is None:
                code, severity = "PLAN_TIME_UNKNOWN", "review"
            elif duration_bounds(plan)[1] is None:
                code, severity = "OPPORTUNITY_FIT_UNKNOWN", "review"
            else:
                lower, upper, estimated = duration_bounds(plan)
                def fits(seconds):
                    end = start + timedelta(seconds=seconds)
                    return any(g["known"] and seconds / 60 <= g["max_minutes"]
                        and (g["daily_max_minutes"] is None or seconds / 60 <= g["daily_max_minutes"])
                        and any(datetime.fromisoformat(i["start_at"]) <= start < datetime.fromisoformat(i["end_at"])
                            and end <= datetime.fromisoformat(i["end_at"]) for i in g["intervals"]) for g in candidates)
                if not fits(upper):
                    if any(not g["known"] for g in candidates):
                        code, severity = "OPPORTUNITY_FIT_UNKNOWN", "review"
                    elif estimated:
                        code, severity = ("ESTIMATED_OPPORTUNITY_FIT_REVIEW" if fits(lower) else "ESTIMATED_OUTSIDE_OPPORTUNITY"), "review"
                    else:
                        code = "OUTSIDE_OPPORTUNITY"
        if code:
            result.append({"plan_id": plan["id"], "plan_title": plan["title"],
                "occurrence_key": "availability:" + plan["date"], "constraint_title": "Megadott edzéslehetőség",
                "date": plan["date"], "severity": severity, "code": code})
            require(len(result) <= MAX_OCCURRENCES, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
    return result
