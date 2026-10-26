"""Labeled timetable estimates, separate from source prescriptions and measured truth."""

from datetime import datetime, timedelta
from math import ceil, floor, isfinite
from statistics import median

LOOKBACK_DAYS = 90
SAMPLE_LIMIT = 12
MAX_SECONDS = 86400


def positive(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def estimate(*, owner, plan_id, sport, distance_m, cutoff, observations):
    if sport in ("OTHER", "STRENGTH") or not positive(distance_m):
        return None
    candidates = []
    low = cutoff - timedelta(days=LOOKBACK_DAYS)
    for row in observations:
        if row["sport"] != sport or not positive(row["distance_m"]) or not 0.8 <= row["distance_m"] / distance_m <= 1.25:
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
        if not low <= started < ended <= cutoff or not 0 < elapsed <= MAX_SECONDS:
            continue
        scaled = elapsed * distance_m / row["distance_m"]
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
    lower = max(1, int(floor(min(used) * 0.9 / 60) * 60))
    upper = int(ceil(max(used) * 1.1 / 60) * 60)
    if upper > MAX_SECONDS:
        return None
    return {"schema_version": "calendar-duration-estimate-v0.1", "method": "personal_similar_distance_median_v1",
        "athlete_id": owner, "plan_id": plan_id, "sport": sport, "distance_m": distance_m, "as_of": cutoff.isoformat(),
        "lookback_days": LOOKBACK_DAYS, "candidate_limit": SAMPLE_LIMIT, "duration_sec": duration,
        "lower_sec": min(lower, duration), "upper_sec": max(upper, duration), "sample_count": len(used),
        "samples": candidates, "range_is_calibrated": False}
