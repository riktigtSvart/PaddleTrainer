"""Astronomical light windows, independent of weather and external providers.

NOAA/Meeus solar declination and equation of time; geometric centre altitude
-0.833 degrees for sunrise/set and -6 degrees for civil dawn/dusk. Modelled
flat horizon, no terrain/elevation correction. UTC instants are authoritative;
the venue IANA zone determines which civil date is displayed.
"""
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from math import asin, atan2, ceil, cos, degrees, floor, radians, sin, tan
from zoneinfo import ZoneInfo

METHOD = "noaa-meeus-light-v1"
THRESHOLDS = {"daylight": -0.833, "civil_twilight": -6.0}


def solar_position(timestamp):
    """Return declination (radians) and equation of time (minutes)."""
    t = (timestamp / 86400 + 2440587.5 - 2451545) / 36525
    longitude = (280.46646 + t * (36000.76983 + t * .0003032)) % 360
    anomaly = radians(357.52911 + t * (35999.05029 - .0001537 * t))
    eccentricity = .016708634 - t * (.000042037 + .0000001267 * t)
    centre = (sin(anomaly) * (1.914602 - t * (.004817 + .000014 * t))
              + sin(2 * anomaly) * (.019993 - .000101 * t) + sin(3 * anomaly) * .000289)
    omega = radians(125.04 - 1934.136 * t)
    apparent = radians(longitude + centre - .00569 - .00478 * sin(omega))
    obliquity = radians(23 + (26 + (21.448 - t * (46.815 + t * (.00059 - t * .001813))) / 60) / 60
                        + .00256 * cos(omega))
    declination = asin(sin(obliquity) * sin(apparent))
    y = tan(obliquity / 2) ** 2
    l = radians(longitude)
    eq = 4 * degrees(y * sin(2 * l) - 2 * eccentricity * sin(anomaly)
        + 4 * eccentricity * y * sin(anomaly) * cos(2 * l)
        - .5 * y * y * sin(4 * l) - 1.25 * eccentricity * eccentricity * sin(2 * anomaly))
    return declination, eq


def altitude(timestamp, latitude, longitude):
    declination, eq = solar_position(timestamp)
    hour_angle = radians(((timestamp % 86400) / 60 + eq + 4 * longitude) / 4 - 180)
    lat = radians(latitude)
    return degrees(asin(max(-1, min(1, sin(lat) * sin(declination)
        + cos(lat) * cos(declination) * cos(hour_angle)))))


def extrema(low, high, latitude, longitude, maximum):
    # Include extrema explicitly: sampling alone can miss a very short polar
    # night/day and incorrectly permit a workout across the dark interval.
    for _ in range(40):
        a, b = (2 * low + high) / 3, (low + 2 * high) / 3
        if (altitude(a, latitude, longitude) < altitude(b, latitude, longitude)) == maximum:
            low = a
        else:
            high = b
    return (low + high) / 2


@lru_cache(maxsize=8192)
def _windows(first_day, last_day, latitude, longitude, mode):
    """Continuous above-threshold intervals, with two padded UTC days each side."""
    low, high = (first_day - 2) * 86400, (last_day + 3) * 86400
    points = [low, high]
    for day in range(first_day - 3, last_day + 4):
        noon = day * 86400 + 43200 - longitude * 240
        for _ in range(3):
            noon = day * 86400 + 43200 - longitude * 240 - solar_position(noon)[1] * 60
        for centre, maximum in ((noon, True), (noon + 43200, False)):
            value = extrema(centre - 7200, centre + 7200, latitude, longitude, maximum)
            if low < value < high:
                points.append(value)
    points.sort()
    threshold = THRESHOLDS[mode]
    boundaries = [low]
    rising, setting = [], []
    for a, b in zip(points, points[1:]):
        above = altitude(a, latitude, longitude) >= threshold
        if above == (altitude(b, latitude, longitude) >= threshold):
            continue
        left, right = a, b
        for _ in range(45):
            middle = (left + right) / 2
            if (altitude(middle, latitude, longitude) >= threshold) == above:
                left = middle
            else:
                right = middle
        crossing = (left + right) / 2
        boundaries.append(crossing)
        (setting if above else rising).append(crossing)
    boundaries.append(high)
    windows = [(a, b) for a, b in zip(boundaries, boundaries[1:])
               if altitude((a + b) / 2, latitude, longitude) >= threshold]
    return tuple(windows), tuple(rising), tuple(setting)


def intervals(start, end, coordinates, rule):
    """Clip the whole opportunity to light, with inward-rounded second bounds."""
    a, b = start.timestamp(), end.timestamp()
    windows, _, _ = _windows(floor(a / 86400), floor(b / 86400),
        float(coordinates["latitude"]), float(coordinates["longitude"]), rule["mode"])
    before, after = rule.get("start_buffer_minutes", 0) * 60, rule.get("end_buffer_minutes", 0) * 60
    return [(datetime.fromtimestamp(max(a, ceil(x + before)), UTC),
             datetime.fromtimestamp(min(b, floor(y - after)), UTC))
            for x, y in windows if max(a, ceil(x + before)) < min(b, floor(y - after))]


def day_preview(day, coordinates):
    zone = ZoneInfo(coordinates["timezone_name"])
    target = date.fromisoformat(day)
    start = datetime.combine(target, time.min, zone).astimezone(UTC)
    end = datetime.combine(target + timedelta(days=1), time.min, zone).astimezone(UTC)
    result = {}
    for mode in THRESHOLDS:
        windows, rising, setting = _windows(floor(start.timestamp() / 86400), floor(end.timestamp() / 86400),
            float(coordinates["latitude"]), float(coordinates["longitude"]), mode)
        allowed = intervals(start, end, coordinates, {"mode": mode})
        full = any(a <= start.timestamp() and b >= end.timestamp() for a, b in windows)
        result[mode] = {
            "state": "all_day" if full else "no_light" if not allowed else "crossings",
            "rises_at": [datetime.fromtimestamp(round(t), UTC).isoformat() for t in rising if start.timestamp() <= t < end.timestamp()],
            "sets_at": [datetime.fromtimestamp(round(t), UTC).isoformat() for t in setting if start.timestamp() <= t < end.timestamp()],
            "intervals": [{"start_at": a.isoformat(), "end_at": b.isoformat()} for a, b in allowed],
        }
    return {"method": METHOD, "day_start_at": start.isoformat(), "day_end_at": end.isoformat(), **result}


def effective_rule(data, location_id, sport):
    location = next((l for l in data.get("locations", []) if l["id"] == location_id), None)
    rule = next((r for r in (location or {}).get("daylight_overrides", []) if r["sport"] == sport), None)
    if rule is None:
        rule = next((r for r in data.get("daylight_rules", []) if r["sport"] == sport), None)
    return rule, location


def allowed_intervals(data, group, sport):
    rule, location = effective_rule(data, group["constraints"].get("location_id"), sport)
    if rule is None or rule["mode"] == "none":
        return group["intervals"], []
    if not location or location.get("archived") or not (location.get("coordinates") or location.get("area")):
        return [], ["DAYLIGHT_COORDINATES_REQUIRED"]
    from app.planning.domain.area_daylight import area_intervals
    calculate = area_intervals if location.get("area") else intervals
    geography = location.get("area") or location["coordinates"]
    clipped = []
    for interval in group["intervals"]:
        for a, b in calculate(datetime.fromisoformat(interval["start_at"]), datetime.fromisoformat(interval["end_at"]), geography, rule):
            clipped.append({"start_at": a.isoformat(), "end_at": b.isoformat()})
    return clipped, [] if clipped else ["DAYLIGHT_NO_ALLOWED_INTERVAL"]


def permits(data, location_id, sport, start, end):
    group = {"constraints": {"location_id": location_id},
             "intervals": [{"start_at": start.isoformat(), "end_at": end.isoformat()}]}
    allowed, codes = allowed_intervals(data, group, sport)
    return not codes and any(datetime.fromisoformat(v["start_at"]) <= start
                            and datetime.fromisoformat(v["end_at"]) >= end for v in allowed)
