"""Do not confuse recording pauses with manual waits between planned phases."""
from datetime import datetime


def clock_issues(exercise):
    pauses = exercise.get("pauseTimes")
    if pauses is None or pauses == []:
        return []
    if not isinstance(pauses, list) or len(pauses) > 4000:
        return ["RECORDING_PAUSE_CLOCK_UNRESOLVED"]
    try:
        end = datetime.fromisoformat(exercise["stopTime"].replace("Z", "+00:00"))
        start = datetime.fromisoformat(exercise["startTime"].replace("Z", "+00:00"))
        if end < start:
            raise ValueError()
        for pause in pauses:
            a = datetime.fromisoformat(pause["startTime"].replace("Z", "+00:00"))
            b = datetime.fromisoformat(pause["endTime"].replace("Z", "+00:00"))
            if b < a or a < start:
                raise ValueError()
            if a < end and b > start:
                return ["INTERIOR_RECORDING_PAUSE_REQUIRES_CLOCK_ALIGNMENT"]
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return ["RECORDING_PAUSE_CLOCK_UNRESOLVED"]
    return []


def sample_clock_issues(exercise, raw, index, selected_key):
    issues = clock_issues(exercise)
    if selected_key != "exerciseSamples":
        return issues
    others = raw.get("exercises")
    if not isinstance(others, list) or index >= len(others) or not isinstance(others[index], dict):
        return issues
    other = others[index]
    if not other.get("pauseTimes"):
        return issues
    same = (exercise.get("id") is not None and exercise.get("id") == other.get("id")) or (
        len(others) == len(raw["exerciseSamples"]) == 1 and exercise.get("startTime") is not None and exercise.get("startTime") == other.get("startTime"))
    extra = clock_issues(other) if same else ["RECORDING_PAUSE_CLOCK_UNRESOLVED"]
    return list(dict.fromkeys(issues + extra))
