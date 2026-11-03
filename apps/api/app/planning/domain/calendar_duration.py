"""Labeled timetable estimates, separate from source prescriptions and measured truth."""

from datetime import datetime, timedelta
from math import ceil, floor, isfinite, log2
from statistics import median
import re

LOOKBACK_DAYS = 90
SAMPLE_LIMIT = 12
MAX_SECONDS = 86400
SPORTS = {"KAYAK", "RUNNING", "CYCLING", "SWIMMING"}
DEFAULT_SLOWDOWN_PCT = 5
SPORT_NAMES = {
    "KAYAK": {"kajak", "kayak", "kayaking"}, "RUNNING": {"futás", "futásra", "running"},
    "CYCLING": {"kerékpár", "kerékpározás", "cycling"}, "SWIMMING": {"úszás", "swimming"},
}


def profile_matches_sport(target, sport):
    return bool(set(re.findall(r"[^\W\d_]+", str(target).casefold())) & SPORT_NAMES.get(sport, set()))


def positive(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def estimate(*, owner, plan_id, sport, distance_m, cutoff, observations,
             doubling_slowdown_pct=DEFAULT_SLOWDOWN_PCT, coefficient_profile_reference=None):
    if (sport not in SPORTS or not positive(distance_m)
            or type(doubling_slowdown_pct) is not int or not 0 <= doubling_slowdown_pct <= 20):
        return None
    exponent = round(1 + log2(1 + doubling_slowdown_pct / 100), 12)
    candidates = []
    low = cutoff - timedelta(days=LOOKBACK_DAYS)
    for row in observations:
        if row["sport"] != sport or not positive(row["distance_m"]) or not 0.5 <= row["distance_m"] / distance_m <= 2:
            continue
        if row.get("available_at") and datetime.fromisoformat(row["available_at"]) > cutoff:
            continue
        started = datetime.fromisoformat(row["started_at"])
        if row["ended_at"] is not None:
            ended = datetime.fromisoformat(row["ended_at"])
            elapsed, basis = (ended - started).total_seconds(), "elapsed"
        elif positive(row["duration_sec"]):
            elapsed, basis = row["duration_sec"], "reported_duration"
            ended = started + timedelta(seconds=elapsed)
        else:
            continue
        if not low <= started < ended <= cutoff or not 300 <= elapsed <= MAX_SECONDS:
            continue
        scaled = elapsed * (distance_m / row["distance_m"]) ** exponent
        if 0 < scaled <= MAX_SECONDS:
            candidates.append({"session_id": row["id"], "started_at": started.isoformat(), "ended_at": ended.isoformat(),
                "distance_m": row["distance_m"], "elapsed_sec": elapsed, "basis": basis, "projected_sec": scaled, "used": True})
    candidates.sort(key=lambda x: (x["started_at"], x["session_id"]), reverse=True)
    candidates = candidates[:SAMPLE_LIMIT]
    if not candidates:
        return None
    values = [x["projected_sec"] for x in candidates]
    center = median(values)
    if len(values) == 2 and max(values) / min(values) > 1.75:
        return None
    if len(values) >= 3:
        tolerance = max(center * 0.25, 3 * median(abs(x - center) for x in values))
        for row in candidates:
            row["used"] = abs(row["projected_sec"] - center) <= tolerance
    used = [x["projected_sec"] for x in candidates if x["used"]]
    duration = max(1, int(floor(median(used) + 0.5)))
    used_rows = [s for s in candidates if s["used"]]
    extrapolated = not min(s["distance_m"] for s in used_rows) <= distance_m <= max(s["distance_m"] for s in used_rows)
    margin = 0.1 + 0.1 * max(abs(log2(distance_m / s["distance_m"])) for s in used_rows)
    lower = max(1, int(floor(min(used) * (1 - margin) / 60) * 60))
    upper = int(ceil(max(used) * (1 + margin) / 60) * 60)
    if upper > MAX_SECONDS:
        return None
    return {"schema_version": "calendar-duration-estimate-v0.2", "method": "personal_power_law_median_v1",
        "athlete_id": owner, "plan_id": plan_id, "sport": sport, "distance_m": distance_m, "as_of": cutoff.isoformat(),
        "lookback_days": LOOKBACK_DAYS, "candidate_limit": SAMPLE_LIMIT, "duration_sec": duration,
        "lower_sec": min(lower, duration), "upper_sec": max(upper, duration), "sample_count": len(used),
        "samples": candidates, "range_is_calibrated": False,
        "doubling_slowdown_pct": doubling_slowdown_pct, "exponent": exponent,
        "coefficient_source": "profile_setting" if coefficient_profile_reference else "planning_default",
        "coefficient_profile_reference": coefficient_profile_reference, "extrapolated": extrapolated,
        "max_distance_ratio": 2, "conditions_verified": False, "personal_coefficient_fitted": False}
