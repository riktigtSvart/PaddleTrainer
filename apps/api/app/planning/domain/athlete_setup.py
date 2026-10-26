"""Versioned intake evidence and real calendar opportunities, without dose inference."""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from app.planning.domain.common.serialization import compute_content_hash

SCHEMA = "athlete-setup-v0.1"
POLICY = "athlete-intake-review-policy-v0.1"
UNITS = {
    "training_sessions": "count",
    "training_minutes": "min",
    "sleep_duration_sec": "s",
    "sleep_score": "score",
    "daily_steps": "count",
    "background_hr_mean_bpm": "bpm",
    "background_hr_median_bpm": "bpm",
    "resting_hr_bpm": "bpm",
    "hrv_rmssd_ms": "ms",
    "body_mass_kg": "kg",
    "vo2max_ml_kg_min": "ml/kg/min",
    "strength_load_kg": "kg",
    "test_duration_sec": "s",
    "test_distance_m": "m",
}


class SetupRuleError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise SetupRuleError(code)


def digest(value):
    # Nested source/parent hashes are part of the frozen evidence, too.
    return compute_content_hash(value, exclude_fields=frozenset())


def identity(owner, kind, request_id):
    return "pt-athlete:" + digest({"owner": owner, "kind": kind, "request_id": request_id})


def reference(artifact):
    return {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"]}


def age_on(birth, today):
    if birth is None:
        return None
    born, day = date.fromisoformat(birth), date.fromisoformat(today)
    require(born <= day and day.year - born.year <= 130, "ATHLETE_BIRTH_DATE_INVALID")
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def review_profile(data, today):
    age = age_on(data["birth_date"], today)
    reasons, mode = [], "NORMAL_START"
    if age is None:
        reasons.append("AGE_UNKNOWN")
    elif age < 18:
        reasons.append("YOUTH_PLANNING_REVIEW")
    if not data["target_sport"]:
        reasons.append("TARGET_SPORT_UNKNOWN")
    if data["sport_history_status"] == "unknown":
        reasons.append("SPORT_HISTORY_UNKNOWN")
    for item in data["sport_history"]:
        require(
            item["start_year"] is None or item["start_year"] <= int(today[:4]),
            "ATHLETE_HISTORY_IN_FUTURE",
        )
        require(
            item["last_active_date"] is None or item["last_active_date"] <= today,
            "ATHLETE_HISTORY_IN_FUTURE",
        )
    require(
        data["last_training_date"] is None or data["last_training_date"] <= today,
        "ATHLETE_HISTORY_IN_FUTURE",
    )
    if data["constraint_status"] == "unknown":
        reasons.append("FUNCTIONAL_CONSTRAINTS_UNKNOWN")
    if data["participation"] == "unknown":
        reasons.append("PARTICIPATION_UNKNOWN")
    if data["participation"] == "adapted" and not data["constraints"]:
        reasons.append("CONSTRAINT_EFFECT_UNSPECIFIED")
    for item in data["constraints"]:
        if item["duration"] == "temporary":
            reasons.append("TEMPORARY_CONSTRAINT_REVIEW")
        if item["review_on"] and item["review_on"] <= today:
            reasons.append("CONSTRAINT_REVIEW_DUE")
        if not (
            item["restricted_activities"] or item["adaptations"] or item["professional_guidance"]
        ):
            reasons.append("CONSTRAINT_EFFECT_UNSPECIFIED")
        # A review date never clears an injury or a permanent adaptation.
    for item in data["manual_observations"]:
        require(item["end_date"] <= today, "ATHLETE_OBSERVATION_IN_FUTURE")
    if data["interruption"] == "returning":
        mode = "RETURN_FROM_INTERRUPTION"
    elif data["constraint_status"] == "present" or data["participation"] == "adapted":
        mode = "CONSTRAINT_LIMITED"
    if data["participation"] == "paused":
        gate, participation = "HOLD", "BLOCKED"
        reasons.append("USER_DECLARED_PAUSE")
    elif data["participation"] == "professional_review" or any(
        r in reasons
        for r in (
            "TEMPORARY_CONSTRAINT_REVIEW",
            "CONSTRAINT_REVIEW_DUE",
            "CONSTRAINT_EFFECT_UNSPECIFIED",
        )
    ):
        gate, participation = "REVIEW_REQUIRED", "PROFESSIONAL_REVIEW_REQUIRED"
    elif any(r.endswith("UNKNOWN") for r in reasons):
        gate, participation, mode = "REVIEW_REQUIRED", "UNKNOWN", "DATA_LIMITED"
    elif age is not None and age < 18:
        gate, participation, mode = (
            "REVIEW_REQUIRED",
            "READY_WITH_CONSTRAINTS",
            "CONSTRAINT_LIMITED",
        )
    elif data["constraint_status"] == "present" or data["participation"] == "adapted":
        gate, participation = "OPEN_WITH_CONSTRAINTS", "READY_WITH_CONSTRAINTS"
    else:
        gate, participation = "OPEN", "READY"
    return {
        "policy_version": POLICY,
        "evaluated_on": today,
        "age_years": age,
        "age_path": "unknown" if age is None else "youth" if age < 18 else "adult",
        "global_entry_gate": gate,
        "participation_status": participation,
        "entry_mode": mode,
        "reasons": list(dict.fromkeys(reasons)),
        "clinical_clearance": False,
        "weight_change_requires_review": age is None
        or age < 18
        or gate in {"HOLD", "REVIEW_REQUIRED"}
        or any(c["area"] == "medical" for c in data["constraints"]),
        "constraints": deepcopy(data["constraints"]),
        "accessibility_needs": data["accessibility_needs"],
    }


def local_instant(day, clock, timezone_name, fold):
    """Reject missing DST hours and require a deliberate choice in a repeated hour."""
    naive = datetime.fromisoformat(day + "T" + clock)
    tz = ZoneInfo(timezone_name)
    options = {}
    for index in (0, 1):
        local = naive.replace(tzinfo=tz, fold=index)
        utc = local.astimezone(UTC)
        roundtrip = utc.astimezone(tz)
        if roundtrip.replace(tzinfo=None) == naive:
            options[index] = utc
    require(bool(options), "ATHLETE_TIME_DOES_NOT_EXIST")
    unique = set(options.values())
    if len(unique) > 1:
        require(fold is not None, "ATHLETE_TIME_IS_AMBIGUOUS")
    if fold is None:
        return next(iter(options.values()))
    require(type(fold) is int and fold in options, "ATHLETE_TIME_FOLD_INVALID")
    return options[fold]


def resolve_calendar(data):
    first, last = date.fromisoformat(data["start_date"]), date.fromisoformat(data["end_date"])
    require(0 <= (last - first).days < 366, "ATHLETE_CALENDAR_RANGE_INVALID")
    expected = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
    require([d["date"] for d in data["days"]] == expected, "ATHLETE_CALENDAR_CENSUS_INVALID")
    intervals, resolved = [], []
    for day in data["days"]:
        daily = []
        for window in day["windows"]:
            end_date = (
                date.fromisoformat(day["date"]) + timedelta(days=int(window["ends_next_day"]))
            ).isoformat()
            if window["ends_next_day"]:
                following = next((d for d in data["days"] if d["date"] == end_date), None)
                require(
                    following is None or following["status"] != "unavailable",
                    "ATHLETE_OVERNIGHT_DAY_UNAVAILABLE",
                )
            start = local_instant(
                day["date"], window["start_time"], data["timezone_name"], window["start_fold"]
            )
            end = local_instant(
                end_date, window["end_time"], data["timezone_name"], window["end_fold"]
            )
            minutes = (end - start).total_seconds() / 60
            require(
                0 < minutes <= 1440 and window["max_minutes"] <= minutes,
                "ATHLETE_WINDOW_DURATION_INVALID",
            )
            intervals.append((start, end))
            daily.append(
                {
                    **deepcopy(window),
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "elapsed_minutes": int(minutes),
                }
            )
        if day["max_total_minutes"] is not None:
            require(
                day["max_total_minutes"] <= sum(w["max_minutes"] for w in daily),
                "ATHLETE_DAILY_BUDGET_INVALID",
            )
        resolved.append({**deepcopy(day), "windows": daily})
    intervals.sort()
    require(all(a[1] <= b[0] for a, b in pairwise(intervals)), "ATHLETE_WINDOWS_OVERLAP")
    counts = {
        state: sum(d["status"] == state for d in data["days"])
        for state in ("unknown", "available", "unavailable")
    }
    return {
        "days": resolved,
        "coverage": counts,
        "availability_status": (
            "UNKNOWN"
            if counts["unknown"]
            else "AVAILABLE"
            if counts["available"]
            else "NO_TRAINING_WINDOW"
        ),
        "workouts_created": False,
        "all_opportunities_are_required": False,
    }


def make_artifact(*, owner, kind, proposal, created_at, timezone_name, previous, observations=None):
    today = (
        datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone_name)).date().isoformat()
    )
    artifact = {
        "schema_version": SCHEMA,
        "artifact_id": identity(owner, kind, proposal["request_id"]),
        "athlete_id": owner,
        "kind": kind,
        "revision": previous["revision"] + 1 if previous else 1,
        "created_at": created_at,
        "timezone_name": timezone_name,
        "proposal": deepcopy(proposal),
        "planning_authorized": False,
        "workouts_created": False,
    }
    if kind == "profile":
        artifact["review"] = review_profile(proposal["data"], today)
        require(
            all(o["end_date"] <= today for o in (observations or [])),
            "ATHLETE_OBSERVATION_IN_FUTURE",
        )
        artifact["imported_observations"] = deepcopy(observations or [])
    elif kind == "availability":
        require(
            proposal["data"]["timezone_name"] == timezone_name, "ATHLETE_CALENDAR_TIMEZONE_DIFFERS"
        )
        artifact["calendar"] = resolve_calendar(proposal["data"])
    artifact["content_hash"] = digest(artifact)
    return artifact


def calendar_context(calendar, *, start, end):
    """An unfilled/expired horizon never inherits availability from a weekly average."""
    if calendar is None:
        return {"status": "UNKNOWN", "missing_days": None, "available_days": 0, "windows": []}
    days = {d["date"]: d for d in calendar["calendar"]["days"]}
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    require(0 <= (last - first).days < 366, "ATHLETE_CALENDAR_RANGE_INVALID")
    wanted = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
    missing = [d for d in wanted if d not in days or days[d]["status"] == "unknown"]
    available = [days[d] for d in wanted if d in days and days[d]["status"] == "available"]
    return {
        "status": "UNKNOWN" if missing else "AVAILABLE" if available else "NO_TRAINING_WINDOW",
        "missing_days": missing,
        "available_days": len(available),
        "windows": available,
        "reference": reference(calendar),
    }


def planning_snapshot(profile, calendar, *, created_at, timezone_name, start, end):
    today = (
        datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone_name)).date().isoformat()
    )
    return {
        "schema_version": SCHEMA,
        "references": {
            "profile_reference": reference(profile),
            "availability_reference": reference(calendar) if calendar else None,
        },
        "review": review_profile(profile["proposal"]["data"], today),
        "athlete_background": {
            key: deepcopy(profile["proposal"]["data"][key])
            for key in (
                "birth_date",
                "sex_reference",
                "competition_category",
                "target_sport",
                "sport_history_status",
                "sport_history",
                "interruption",
                "last_training_date",
                "recovery_notes",
            )
        },
        "typical_availability": {
            key: profile["proposal"]["data"][key]
            for key in ("typical_days_per_week", "typical_minutes_per_week", "resources")
        },
        "first_mesocycle_availability": calendar_context(calendar, start=start, end=end),
        "manual_observation_count": len(profile["proposal"]["data"]["manual_observations"]),
        "imported_observation_count": len(profile["imported_observations"]),
        "planning_authorized": False,
        "workouts_created": False,
    }
