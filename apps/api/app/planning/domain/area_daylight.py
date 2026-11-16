"""Common light across a whole rectangle, without replacing it by its centre.

At each UTC minute we minimize solar altitude analytically over both geographic
axes. Accept a whole minute only when its midpoint clears the threshold by
0.2 degrees. The Sun's apparent angular rate is below 0.005 degrees/second for
the supported 1900–2100 dates; a half-minute needs at most 0.15 degrees. This
inward approximation therefore preserves the entire cell, including near-polar
short dark intervals. The usual flat-horizon model still applies.
"""
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from math import asin, atan2, ceil, cos, degrees, floor, pi, radians, sin
from zoneinfo import ZoneInfo

from app.planning.domain.daylight import solar_position, THRESHOLDS

METHOD = "area-common-light-v0.1"
STEP_SECONDS = 60
MARGIN_DEGREES = .2


def minimum_altitude(timestamp, south, north, west, east):
    declination, equation = solar_position(timestamp)
    angle = ((timestamp % 86400) / 60 + equation) / 4 - 180
    a, b = radians(angle + west), radians(angle + east)
    minimum_cos = min(cos(a), cos(b))
    if ceil((a - pi) / (2 * pi)) <= floor((b - pi) / (2 * pi)):
        minimum_cos = -1
    x, y = sin(declination), cos(declination) * minimum_cos
    low, high = radians(south), radians(north)
    latitudes = [low, high]
    stationary = atan2(x, y)
    for k in range(-2, 3):
        candidate = stationary + k * pi
        if low <= candidate <= high:
            latitudes.append(candidate)
    return degrees(asin(max(-1, min(1, min(x * sin(v) + y * cos(v) for v in latitudes)))))


@lru_cache(maxsize=512)
def daily_altitudes(day, south, north, west, east):
    return tuple(minimum_altitude(day * 86400 + minute * 60 + 30, south, north, west, east)
                 for minute in range(1440))


def area_intervals(start, end, area, rule):
    first, last = start.timestamp(), end.timestamp()
    bounds = tuple(float(area[k]) for k in ("south", "north", "west", "east"))
    # Include complete rising/setting windows before applying buffers, so an
    # opportunity beginning at midday does not receive another dawn buffer.
    windows, opened = [], None
    for day in range(floor(first / 86400) - 2, floor(last / 86400) + 3):
        for minute, value in enumerate(daily_altitudes(day, *bounds)):
            instant = day * 86400 + minute * 60
            above = value >= THRESHOLDS[rule["mode"]] + MARGIN_DEGREES
            if above and opened is None:
                opened = instant
            elif not above and opened is not None:
                windows.append((opened, instant)); opened = None
    if opened is not None:
        windows.append((opened, (floor(last / 86400) + 3) * 86400))
    before, after = rule.get("start_buffer_minutes", 0) * 60, rule.get("end_buffer_minutes", 0) * 60
    return [(datetime.fromtimestamp(max(first, a + before), UTC),
             datetime.fromtimestamp(min(last, b - after), UTC))
            for a, b in windows if max(first, a + before) < min(last, b - after)]


def day_preview(day, area):
    target = date.fromisoformat(day)
    zone = ZoneInfo(area["timezone_name"])
    start = datetime.combine(target, time.min, zone).astimezone(UTC)
    end = datetime.combine(target + timedelta(days=1), time.min, zone).astimezone(UTC)
    modes = {}
    for mode in THRESHOLDS:
        allowed = area_intervals(start, end, area, {"mode": mode})
        modes[mode] = {"state": "all_day" if allowed == [(start, end)] else "no_light" if not allowed else "crossings",
            "rises_at": [a.isoformat() for a, _ in allowed if a > start],
            "sets_at": [b.isoformat() for _, b in allowed if b < end],
            "intervals": [{"start_at": a.isoformat(), "end_at": b.isoformat()} for a, b in allowed]}
    return {"method": METHOD, "day_start_at": start.isoformat(), "day_end_at": end.isoformat(), **modes}
