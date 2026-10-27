"""Validate a complete native phase tree before replacing any stored blocks."""
import math


class TargetStructureError(ValueError):
    pass


def native_id(value):
    if type(value) is int and value > 0:
        return str(value)
    if type(value) is str and value and value == value.strip() and len(value) <= 128:
        return value
    return None


def phase_structure(raw):
    """Return absent/complete/incomplete; malformed structure is never normalized."""
    if not isinstance(raw, dict):
        raise TargetStructureError("invalid_phase_structure")
    exercises = raw.get("exercise")
    if exercises is None:
        return "absent"
    if not isinstance(exercises, list) or len(exercises) > 64:
        raise TargetStructureError("invalid_phase_structure")
    nodes = expanded = 0
    present = missing = unknown_empty = False

    def numeric(value, minimum=0):
        return type(value) in (int, float) and minimum <= value <= 1e12 and math.isfinite(value)

    def walk(phases, depth=0, multiplier=1):
        nonlocal nodes, expanded
        if not isinstance(phases, list) or depth > 16:
            raise TargetStructureError("invalid_phase_structure")
        for phase in phases:
            nodes += 1
            if nodes > 4000 or not isinstance(phase, dict):
                raise TargetStructureError("invalid_phase_structure")
            name = phase.get("name")
            if name is not None and (not isinstance(name, str) or len(name) > 120):
                raise TargetStructureError("invalid_phase_structure")
            children = phase.get("phaseOrRepeat")
            if children is not None and not isinstance(children, list):
                raise TargetStructureError("invalid_phase_structure")
            repeats = phase.get("repeatCount")
            if children:
                if type(repeats) is not int or not 1 <= repeats <= 99:
                    raise TargetStructureError("invalid_phase_structure")
                walk(children, depth + 1, multiplier * repeats)
                continue
            if repeats is not None and (type(repeats) is not int or repeats != 1):
                raise TargetStructureError("invalid_phase_structure")
            expanded += multiplier
            if expanded > 2048:
                raise TargetStructureError("invalid_phase_structure")
            goal = phase.get("goal")
            if not isinstance(goal, dict) or goal.get("type") not in ("MANUAL", "DURATION", "DISTANCE"):
                raise TargetStructureError("invalid_phase_structure")
            if goal["type"] == "DURATION" and not numeric(goal.get("duration")):
                raise TargetStructureError("invalid_phase_structure")
            if goal["type"] == "DISTANCE" and not numeric(goal.get("distance")):
                raise TargetStructureError("invalid_phase_structure")
            intensity = phase.get("intensity")
            if intensity is not None:
                if not isinstance(intensity, dict):
                    raise TargetStructureError("invalid_phase_structure")
                kind = intensity.get("type")
                if kind is not None and (not isinstance(kind, str) or len(kind) > 32):
                    raise TargetStructureError("invalid_phase_structure")
                for key in ("lowerZone", "upperZone"):
                    if intensity.get(key) is not None and not numeric(intensity[key]):
                        raise TargetStructureError("invalid_phase_structure")
                if intensity.get("lowerZone") is not None and intensity.get("upperZone") is not None and intensity["lowerZone"] > intensity["upperZone"]:
                    raise TargetStructureError("invalid_phase_structure")

    for exercise in exercises:
        if not isinstance(exercise, dict):
            raise TargetStructureError("invalid_phase_structure")
        phases = exercise.get("phaseOrRepeat")
        if phases is not None and not isinstance(phases, list):
            raise TargetStructureError("invalid_phase_structure")
        if phases:
            walk(phases)
            present = True
        elif exercise.get("type") == "PHASED":
            missing = True
        elif exercise.get("type") not in ("FREE", "VOLUME", "STEADY_RACE_PACE", "ROUTE", "SEGMENT", "STRENGTH"):
            unknown_empty = True
    return "incomplete" if missing or (present and unknown_empty) else "complete" if present else "absent"


def same_blocks(existing, normalized):
    """Compare the ordered hierarchy without replacing persistent block IDs."""
    old = sorted(existing, key=lambda b: b.position)
    if len(old) != len(normalized) or len({b.position for b in old}) != len(old):
        return False
    keys = {b.id: i for i, b in enumerate(old)}
    wanted = {b["key"]: i for i, b in enumerate(normalized)}
    fields = ("name", "duration_sec", "distance_m", "intensity_type", "intensity_min", "intensity_max", "repeat_count")
    for index, (block, proposed) in enumerate(zip(old, normalized)):
        parent = keys.get(block.parent_block_id, -1) if block.parent_block_id is not None else None
        target = wanted.get(proposed["parent_key"], -1) if proposed["parent_key"] is not None else None
        if block.position != index or parent != target or block.block_type.value != proposed["block_type"]:
            return False
        if any(getattr(block, key) != proposed[key] for key in fields):
            return False
    return True
