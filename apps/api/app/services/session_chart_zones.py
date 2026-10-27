"""Project the zone limits captured with this Polar exercise, without estimation."""
import math


def heart_rate_zones(exercise, path):
    return zone_limits(exercise, path, "ZONE_TYPE_HEART_RATE", "bpm")


def zone_limits(exercise, path, kind, unit):
    groups = exercise.get("zones")
    if not isinstance(groups, list):
        return None
    selected = [g for g in groups if isinstance(g, dict) and g.get("type") == kind]
    # Do not number a partial list, reorder it, or choose between conflicting definitions.
    if len(selected) != 1:
        return None
    group = selected[0]
    zones = group.get("zones")
    if not isinstance(zones, list) or len(zones) != 5:
        return None
    result = []
    for index, zone in enumerate(zones):
        if not isinstance(zone, dict):
            return None
        low, high = zone.get("lowerLimit"), zone.get("higherLimit")
        if (type(low) not in (float, int) or type(high) not in (float, int)
                or not 0 <= low < high <= 1e12 or not math.isfinite(low) or not math.isfinite(high)
                or unit == "bpm" and not 0 < low < high < 1000):
            return None
        if result and (low < result[-1]["high"] or high <= result[-1]["high"]):
            return None
        result.append({"index": index + 1, "low": low, "high": high})
    return {"unit": unit, "source_path": f"{path}.zones[{groups.index(group)}]", "zones": result}
