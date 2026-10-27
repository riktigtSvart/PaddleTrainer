"""Bounded source exercise/lap summaries. No inferred match to planned phases."""
import math

from app.planning.application.calendar_workspace import CalendarRuleError

ROW_LIMIT = 4000


def number(value):
    return value if type(value) in (float, int) and 0 <= value <= 1e12 and math.isfinite(value) else None


def summary(value, path, index, exercise_index):
    issues = []
    stats = value.get("statistics")
    stats = stats.get("statistics") if isinstance(stats, dict) else None
    if isinstance(stats, list) and len(stats) > 128:
        raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
    def average(kind):
        found = [s for s in stats if isinstance(s, dict) and s.get("type") == kind] if isinstance(stats, list) else []
        if len(found) > 1:
            issues.append("AMBIGUOUS_STATISTIC:" + kind)
        return number(found[0].get("avg")) if len(found) == 1 else None
    duration = number(value.get("durationMillis"))
    return {"id": path, "position": index, "exercise_index": exercise_index,
            "duration_sec": duration / 1000 if duration is not None else None,
            "distance_m": number(value.get("distanceMeters")),
            "avg_hr": average("STATISTICS_TYPE_HEART_RATE"),
            "avg_speed": average("STATISTICS_TYPE_SPEED"), "avg_power": average("STATISTICS_TYPE_POWER"),
            "split_time_sec": number(value.get("splitTimeMillis")) / 1000 if number(value.get("splitTimeMillis")) is not None else None,
            "issues": issues}


def section_groups(raw, provider):
    result = {"groups": [], "row_count": 0, "issues": []}
    if provider != "POLAR" or not isinstance(raw, dict):
        return result
    key = "exerciseSamples" if isinstance(raw.get("exerciseSamples"), list) and raw["exerciseSamples"] else "exercises"
    exercises = raw.get(key)
    if not isinstance(exercises, list):
        return result
    if len(exercises) > 64:
        raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
    overview = {"id": "exercises", "kind": "exercises", "exercise_index": None, "source_path": key, "rows": []}
    result["groups"].append(overview)
    def append(group, value, path, index, exercise_index):
        result["row_count"] += 1
        if result["row_count"] > ROW_LIMIT:
            raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
        if isinstance(value, dict):
            group["rows"].append(summary(value, path, index, exercise_index))
        else:
            result["issues"].append("SECTION_INVALID:" + path)
    for exercise_index, exercise in enumerate(exercises):
        path = f"{key}[{exercise_index}]"
        append(overview, exercise, path, exercise_index, exercise_index)
        if not isinstance(exercise, dict):
            continue
        laps = exercise.get("laps")
        if not isinstance(laps, dict):
            continue
        for native, kind in (("laps", "manual_laps"), ("autoLaps", "automatic_laps")):
            source = laps.get(native)
            if source is None:
                continue
            if not isinstance(source, list):
                result["issues"].append("SECTION_CONTAINER_INVALID:" + path + ".laps." + native)
                continue
            group_path = f"{path}.laps.{native}"
            group = {"id": group_path, "kind": kind, "exercise_index": exercise_index, "source_path": group_path, "rows": []}
            result["groups"].append(group)
            for i, value in enumerate(source):
                append(group, value, f"{group_path}[{i}]", i, exercise_index)
    # Count retained rows; invalid source slots remain explicitly reported in issues.
    result["row_count"] = sum(len(g["rows"]) for g in result["groups"])
    return result
