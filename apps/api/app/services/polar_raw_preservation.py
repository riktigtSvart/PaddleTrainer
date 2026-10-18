"""Preserve established Polar native views across base and feature refreshes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

MARKER = "__paddletrainer_backfill_v01__"
RULES_VERSION = "polar-raw-preservation-0.1"


class PolarRawPreservationError(ValueError):
    pass


def require(value, code):
    if not value:
        raise PolarRawPreservationError(code)


def _id(value):
    obj = value.get("identifier") if isinstance(value, dict) else None
    return str(obj["id"]) if isinstance(obj, dict) and obj.get("id") is not None else None


def _native(exercises):
    return isinstance(exercises, list) and any(isinstance(e, dict) and (e.get("samples") or e.get("routes")) for e in exercises)


def _assert_compatible(old, new):
    for key in ("startTime", "stopTime", "timezoneOffsetMinutes", "durationMillis", "distanceMeters", "sport", "trainingTarget"):
        if old.get(key) is not None and new.get(key) is not None:
            require(old[key] == new[key], "POLAR_NATIVE_SOURCE_METADATA_CONFLICT:" + key)


def _check_native(old, new):
    require(_id(old) == _id(new), "POLAR_EXERCISE_IDENTITY_CONFLICT")
    _assert_compatible(old, new)
    if old.get("samples") and new.get("samples"):
        left, right = old["samples"], new["samples"]
        left = left.get("samples") if isinstance(left, dict) else left
        right = right.get("samples") if isinstance(right, dict) else right
        require(isinstance(left, list) and isinstance(right, list), "POLAR_NATIVE_SAMPLE_CONTAINER_UNRESOLVED")
        for incoming in right:
            require(isinstance(incoming, dict) and incoming.get("type"), "POLAR_NATIVE_CHANNEL_UNRESOLVED")
            matches = [s for s in left if isinstance(s, dict) and s.get("type") == incoming["type"]]
            if matches:
                require(len(matches) == 1 and matches[0] == incoming, "POLAR_NATIVE_CHANNEL_CONFLICT")
    if old.get("routes") and new.get("routes"):
        require(old["routes"] == new["routes"], "POLAR_NATIVE_ROUTE_CONFLICT")


def merge_polar_raw(stored, incoming, external_id, *, feature=None):
    require(stored is None or isinstance(stored, dict), "POLAR_STORED_RAW_NOT_OBJECT")
    require(isinstance(incoming, dict) and _id(incoming) == str(external_id), "POLAR_INCOMING_SESSION_ID_CONFLICT")
    old = stored or {}
    require(_id(old) in (None, str(external_id)), "POLAR_STORED_SESSION_ID_CONFLICT")
    views = [old[k] for k in ("exerciseSamples", "exercises") if _native(old.get(k))]
    if views:
        _assert_compatible(old, incoming)
        exercises = incoming.get("exercises")
        if exercises:
            require(isinstance(exercises, list), "POLAR_INCOMING_EXERCISES_INVALID")
            for view in views:
                require({_id(e) for e in view} == {_id(e) for e in exercises}, "POLAR_NATIVE_EXERCISE_SET_CONFLICT")
                require(None not in {_id(e) for e in view}, "POLAR_NATIVE_EXERCISE_ID_UNRESOLVED")
                for old_exercise in view:
                    new_exercise = next(e for e in exercises if _id(e) == _id(old_exercise))
                    _check_native(old_exercise, new_exercise)
    require(MARKER not in incoming or incoming[MARKER] == old.get(MARKER), "POLAR_PROVENANCE_NAMESPACE_CONFLICT")
    if feature == "samples":
        if any(_native(old.get(key)) for key in ("exerciseSamples", "exercises")):
            # Keep the full established exercise: a samples-only response may
            # omit its routes, pause records, channels or source metadata.
            return deepcopy(old)
        result = deepcopy(old)
        result["exerciseSamples"] = deepcopy(incoming.get("exercises") or [])
        return result
    if feature in ("statistics", "training-load-report"):
        result = deepcopy(old)
        key, value = ("exerciseStatistics", incoming.get("exercises") or []) if feature == "statistics" else (
            "trainingLoadReport", incoming.get("trainingLoadReport") or {})
        if value:
            result[key] = deepcopy(value)
        return result
    require(feature is None, "POLAR_PRESERVATION_FEATURE_UNSUPPORTED")
    result = {**deepcopy(old), **deepcopy(incoming)}
    for key in ("exerciseSamples", "exerciseStatistics", MARKER):
        if key in old:
            result[key] = deepcopy(old[key])
    if _native(old.get("exercises")):
        result["exercises"] = deepcopy(old["exercises"])
    return result


def polar_session_time(item, key):
    value = item.get(key)
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        offset = item.get("timezoneOffsetMinutes")
        require(type(offset) is int and abs(offset) <= 840, "POLAR_TIMEZONE_OFFSET_UNRESOLVED")
        parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=offset)))
    return parsed.astimezone(timezone.utc)
