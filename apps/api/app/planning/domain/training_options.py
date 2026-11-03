"""Resolve each location separately while retaining one shared opportunity budget."""

from copy import deepcopy
from datetime import timedelta

from app.planning.domain import calendar_constraints as calendar


def empty(zone):
    return {"timezone_name": zone, "schedule_start_date": None, "schedule_end_date": None, "locations": [], "weekly_slots": [], "exceptions": [], "restrictions": []}


def expand(data, first, last, display_zone):
    a, b = calendar.bounded_range(first, last)
    locations = {location["id"]: location for location in data["locations"]}
    exceptions = {(item["slot_id"], item["date"]): item["replacement"] for item in data["exceptions"]}
    rules, override_days, groups = [], set(), []
    # Include a previous source day so an overnight opportunity can reach the view.
    current = a - timedelta(days=1)
    while current <= b:
        day = current.isoformat()
        in_timetable = data.get("schedule_start_date") is not None and data["schedule_start_date"] <= day and (data.get("schedule_end_date") is None or day <= data["schedule_end_date"])
        if in_timetable:
            override_days.add(day)
        for slot in data["weekly_slots"]:
            if not in_timetable or not (slot["start_date"] <= day and (slot["end_date"] is None or day <= slot["end_date"]) and current.weekday() in slot["weekdays"]):
                continue
            override_days.add(day)
            override = (slot["id"], day) in exceptions
            details = exceptions[(slot["id"], day)] if override else slot["details"]
            group = {"key": "options:" + slot["id"] + ":" + day, "slot_id": slot["id"], "date": day, "overridden": override, "details": deepcopy(details), "alternatives": []}
            groups.append(group)
            if details is None:
                continue
            for location_id in details["location_ids"]:
                location = locations[location_id]
                restrictions = [item for item in data["restrictions"] if item["location_id"] == location_id and item["start_date"] <= day <= item["end_date"]]
                blocked = {sport for item in restrictions for sport in item["unavailable_sports"]}
                available = [sport for sport in location["sports"] if sport not in blocked]
                issues = []
                if location["archived"]:
                    available = []
                    issues.append("LOCATION_ARCHIVED")
                if location["kind"] == "mobile" and "KAYAK" in available and not location["boat_transport"]:
                    available.remove("KAYAK")
                    issues.append("BOAT_TRANSPORT_NOT_DECLARED")
                if restrictions:
                    issues.append("LOCATION_TEMPORARILY_RESTRICTED")
                group["alternatives"].append({"location_id": location_id, "name": location["name"], "sports": available, "resources": location["resources"], "combine_allowed": details["combine_allowed"] and location["combine_allowed"], "restrictions": deepcopy(restrictions), "issues": issues})
                declaration = {"kind": "available", "category": "training", "title": location["name"], "firmness": "flexible", "start_time": details["start_time"], "end_time": details["end_time"], "ends_next_day": details["ends_next_day"], "start_fold": details["start_fold"], "end_fold": details["end_fold"], "max_minutes": details["max_minutes"], "sport_scope": "specified", "sports": available, "effort_cap": details["effort_cap"], "resources": location["resources"], "location": location["name"], "notes": details["notes"], "location_id": location_id, "resources_scope": "location", "alternative_group_key": group["key"], "combine_allowed": details["combine_allowed"] and location["combine_allowed"], "location_issues": issues}
                rules.append({"id": "options:" + slot["id"] + ":" + location_id, "start_date": day, "end_date": day, "repeat": "once", "weekdays": [], "details": declaration})
                calendar.require(len(rules) <= calendar.MAX_OCCURRENCES, "CALENDAR_CONSTRAINT_RANGE_TOO_DENSE")
        current += timedelta(days=1)
    occurrences = calendar.expand({"timezone_name": data["timezone_name"], "rules": rules, "exceptions": []}, first, last, display_zone)
    return {"occurrences": occurrences, "override_days": sorted(override_days), "groups": groups}
