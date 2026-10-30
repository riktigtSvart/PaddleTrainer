"""Bounded display-only GPS projection; never infer an exercise clock from point order."""
from datetime import datetime
import math

MAX_POINTS = 100_000


def number(value):
    try:
        return value if type(value) in (int, float) and math.isfinite(value) else None
    except OverflowError:
        return None


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
    except ValueError:
        return None


def project_routes(raw, provider):
    if provider != "POLAR" or not isinstance(raw, dict):
        return []
    key = "exerciseSamples" if isinstance(raw.get("exerciseSamples"), list) and raw["exerciseSamples"] else "exercises"
    exercises = raw.get(key)
    if not isinstance(exercises, list) or len(exercises) > 64:
        return []
    result, count = [], 0
    for index, exercise in enumerate(exercises):
        if not isinstance(exercise, dict):
            continue
        container = exercise.get("routes")
        route = container.get("route") if isinstance(container, dict) else None
        if not isinstance(route, dict) or not isinstance(route.get("wayPoints"), list):
            continue
        values = route["wayPoints"]
        if len(values) + count > MAX_POINTS:
            result.append({"exercise_index": index, "source_path": f"{key}[{index}].routes.route", "points": [], "issues": ["ROUTE_TOO_LARGE"]})
            continue
        count += len(values)
        start, route_start = stamp(exercise.get("startTime")), stamp(route.get("startTime"))
        offset = None
        if start is not None and route_start is not None and (start.tzinfo is None) == (route_start.tzinfo is None):
            offset = round((route_start - start).total_seconds() * 1000)
        points, previous, issues = [], None, []
        for position, value in enumerate(values):
            value = value if isinstance(value, dict) else {}
            lat, lon = number(value.get("latitude")), number(value.get("longitude"))
            elapsed = value.get("elapsedMillis")
            ms = offset + elapsed if offset is not None and type(elapsed) is int and elapsed >= 0 else None
            if ms is not None and (ms < 0 or ms > 7 * 86400000 or previous is not None and ms <= previous):
                ms = None
            if ms is not None:
                previous = ms
            if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                lat, lon = None, None
            points.append({"index": position, "ms": ms, "lat": lat, "lon": lon})
        if any(p["ms"] is None for p in points):
            issues.append("ROUTE_CLOCK_UNKNOWN_OR_NONMONOTONIC")
        if any(p["lat"] is None for p in points):
            issues.append("ROUTE_COORDINATE_MISSING")
        result.append({"exercise_index": index, "source_path": f"{key}[{index}].routes.route", "points": points, "issues": issues})
    return result
