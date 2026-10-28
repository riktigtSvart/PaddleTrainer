"""Read-only planned phase clocks, preserving unknown durations and repeat structure."""
import hashlib
import json
import math
import re

from app.services.polar_target_structure import same_blocks
from app.services.polar_targets import normalize_phase_tree

from app.planning.application.calendar_workspace import CalendarRuleError

NODE_LIMIT = 4000
PHASE_LIMIT = 2048
DEPTH_LIMIT = 32
MAX_MS = 1_000_000_000_000


class InvalidPlan(ValueError):
    pass


def duration(value, factor=1):
    if type(value) not in (int, float) or not 0 <= value <= MAX_MS / factor or not math.isfinite(value):
        return None
    result = value * factor
    return int(result) if float(result).is_integer() else result


def repeat(value, *, container):
    if value is None and not container:
        return 1
    if type(value) is not int or not 1 <= value <= 99:
        raise InvalidPlan("PLAN_REPEAT_COUNT_UNKNOWN")
    return value


def label(value, fallback):
    return value[:200] if isinstance(value, str) and value.strip() else fallback


def expand(nodes, part_index, state):
    phases, issues = [], []
    cursor = 0
    def walk(node, suffix, depth):
        nonlocal cursor
        if depth > DEPTH_LIMIT:
            raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
        count = node["repeat"]
        for i in range(count):
            cycle = suffix + ([f"{i + 1}/{count}"] if count > 1 else [])
            if node["children"]:
                for child in node["children"]:
                    walk(child, cycle, depth + 1)
            else:
                state["phases"] += 1
                if state["phases"] > PHASE_LIMIT:
                    raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
                length = node["duration_ms"]
                end = cursor + length if cursor is not None and length is not None and cursor + length <= MAX_MS else None
                name = node["label"] + (" · " + " / ".join(cycle) if cycle else "")
                phases.append({"id": node["id"] + "#" + str(len(phases)), "label": name,
                    "source_block_id": node["source_block_id"], "from_ms": cursor, "to_ms": end,
                    "duration_ms": length, "advance": node.get("advance", "UNKNOWN"),
                    "target": node.get("target"), "source_pointer": node.get("source_pointer"),
                    **({"distance_m": node["distance_m"]} if node.get("distance_m") is not None else {})})
                if length is None and "PLAN_DURATION_UNKNOWN" not in issues:
                    issues.append("PLAN_DURATION_UNKNOWN")
                if cursor is not None and length is not None and end is None and "PLAN_TIME_TOO_LARGE" not in issues:
                    issues.append("PLAN_TIME_TOO_LARGE")
                cursor = end
    for node in nodes:
        walk(node, [], 0)
    return {"index": part_index, "phases": phases, "total_ms": cursor, "issues": issues}


def stored_nodes(blocks):
    ids = {str(b.id) for b in blocks}
    groups = {}
    for b in blocks:
        parent = str(b.parent_block_id) if b.parent_block_id else None
        if parent is not None and parent not in ids:
            raise InvalidPlan("PLAN_STRUCTURE_INVALID")
        groups.setdefault(parent, []).append(b)
    visited = set()
    def children(parent, depth):
        if depth > DEPTH_LIMIT:
            raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
        siblings = sorted(groups.get(parent, []), key=lambda b: b.position)
        if len({b.position for b in siblings}) != len(siblings):
            raise InvalidPlan("PLAN_ORDER_AMBIGUOUS")
        result = []
        for b in siblings:
            key = str(b.id)
            if key in visited:
                raise InvalidPlan("PLAN_STRUCTURE_INVALID")
            visited.add(key)
            nested = children(key, depth + 1)
            if b.block_type.value == "REPEAT" and not nested:
                raise InvalidPlan("PLAN_REPEAT_EMPTY")
            result.append({"id": key, "label": label(b.name, b.block_type.value), "source_block_id": key,
                "duration_ms": duration(b.duration_sec, 1000),
                "distance_m": duration(getattr(b, "distance_m", None)) if b.duration_sec is None else None,
                "advance": "UNKNOWN", "target": target(getattr(b, "intensity_type", None), getattr(b, "intensity_min", None), getattr(b, "intensity_max", None)),
                "repeat": repeat(b.repeat_count, container=bool(nested)), "children": nested})
        return result
    result = children(None, 0)
    if len(visited) != len(blocks):
        raise InvalidPlan("PLAN_STRUCTURE_INVALID")
    return result


def target(kind, low, high):
    if not isinstance(kind, str) or len(kind) > 32:
        return None
    a, b = duration(low), duration(high)
    return {"type": kind, "low": a, "high": b} if a is not None and b is not None and a <= b else None


def polar_nodes(phases, path, state, depth=0):
    if depth > DEPTH_LIMIT:
        raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
    if not isinstance(phases, list):
        raise InvalidPlan("POLAR_PLAN_PHASES_INVALID")
    result = []
    for index, phase in enumerate(phases):
        state["nodes"] += 1
        if state["nodes"] > NODE_LIMIT:
            raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
        if not isinstance(phase, dict):
            raise InvalidPlan("POLAR_PLAN_PHASES_INVALID")
        key = f"{path}[{index}]"
        nested_source = phase.get("phaseOrRepeat")
        nested = polar_nodes([] if nested_source is None else nested_source, key + ".phaseOrRepeat", state, depth + 1)
        if nested and phase.get("changeType") == "MANUAL" and (phase.get("goal") is not None or phase.get("intensity") is not None or type(phase.get("repeatCount")) is not int or phase["repeatCount"] < 2):
            raise InvalidPlan("PLAN_REPEAT_TRANSITION_UNRESOLVED")
        if not nested and phase.get("repeatCount") not in (None, 1):
            raise InvalidPlan("PLAN_REPEAT_EMPTY")
        goal = phase.get("goal")
        goal = goal if isinstance(goal, dict) else {}
        length = duration(goal.get("duration")) if goal.get("type") == "DURATION" else None
        intensity = phase.get("intensity")
        intensity = intensity if isinstance(intensity, dict) else {}
        result.append({"id": key, "label": label(phase.get("name"), f"{index + 1}. szakasz"),
            "source_block_id": None, "duration_ms": length,
            "advance": phase.get("changeType") if phase.get("changeType") in ("AUTOMATIC", "MANUAL") else "UNKNOWN",
            "target": target(intensity.get("type"), intensity.get("lowerZone"), intensity.get("upperZone")),
            "source_pointer": key,
            "distance_m": duration(goal.get("distance")) if goal.get("type") == "DISTANCE" else None,
            "repeat": repeat(phase.get("repeatCount"), container=bool(nested)), "children": nested})
    return result


def matching_native_parts(plan):
    """Recover leaf advance metadata only from a fully matching owned native tree.

    REPEAT wrappers are structural; their changeType never becomes a leaf wait.
    Persistent block IDs remain authoritative when blocks already exist.
    """
    raw = plan.raw_data
    session = raw.get("session") if isinstance(raw, dict) else None
    identity = session.get("id") if isinstance(session, dict) else None
    if plan.source != "POLAR" or type(identity) not in (str, int) or str(identity) != plan.polar_target_id:
        return None
    exercises = raw.get("exercise")
    if not isinstance(exercises, list):
        return None
    if len(exercises) > 64:
        raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
    state = {"nodes": 0, "phases": 0}
    nodes, flattened = [], []
    for index, exercise in enumerate(exercises):
        if not isinstance(exercise, dict):
            raise InvalidPlan("POLAR_PLAN_EXERCISE_INVALID")
        phases = exercise.get("phaseOrRepeat")
        phases = [] if phases is None else phases
        nodes.append(polar_nodes(phases, f"exercise[{index}].phaseOrRepeat", state))
        for item in normalize_phase_tree(phases):
            copied = dict(item)
            copied["key"] = f"e{index}:" + copied["key"]
            if copied["parent_key"] is not None:
                copied["parent_key"] = f"e{index}:" + copied["parent_key"]
            flattened.append(copied)
    if plan.blocks:
        if any(not all(hasattr(block, field) for field in ("name", "duration_sec", "distance_m", "intensity_type", "intensity_min", "intensity_max", "repeat_count")) for block in plan.blocks):
            return None
        if not same_blocks(plan.blocks, flattened):
            return None
        mapping = {item["key"]: str(block.id) for item, block in zip(flattened, sorted(plan.blocks, key=lambda b: b.position))}
        def bind(items):
            for node in items:
                indexes = re.findall(r"\[(\d+)\]", node["id"])
                node["source_block_id"] = mapping[f"e{indexes[0]}:" + ".".join(indexes[1:])]
                bind(node["children"])
        for items in nodes:
            bind(items)
    return nodes


def plan_timeline(plan):
    result = {"schema_version": "session-plan-timeline-v0.1", "plan_id": str(plan.id) if plan else None,
              "source": "unavailable", "parts": [], "issues": []}
    state = {"nodes": 0, "phases": 0}
    try:
        if plan and plan.blocks:
            if len(plan.blocks) > NODE_LIMIT:
                raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
            result["source"] = "stored_blocks"
            try:
                native = matching_native_parts(plan)
            except (InvalidPlan, TypeError, ValueError):
                native = None
            result["parts"] = ([expand(nodes, index, state) for index, nodes in enumerate(native)]
                               if native is not None else [expand(stored_nodes(plan.blocks), 0, state)])
        elif plan:
            raw = plan.raw_data
            session = raw.get("session") if isinstance(raw, dict) else None
            native_id = session.get("id") if isinstance(session, dict) else None
            if plan.source == "POLAR" and type(native_id) in (str, int) and str(native_id) == plan.polar_target_id:
                exercises = raw.get("exercise")
                if isinstance(exercises, list) and len(exercises) > 64:
                    raise CalendarRuleError("CALENDAR_SESSION_SOURCE_TOO_LARGE")
                if isinstance(exercises, list):
                    for index, exercise in enumerate(exercises):
                        if not isinstance(exercise, dict):
                            raise InvalidPlan("POLAR_PLAN_EXERCISE_INVALID")
                        phases = exercise.get("phaseOrRepeat")
                        nodes = polar_nodes([] if phases is None else phases, f"exercise[{index}].phaseOrRepeat", state)
                        result["parts"].append(expand(nodes, index, state))
                    if any(p["phases"] for p in result["parts"]):
                        result["source"] = "stored_polar_target"
            if result["source"] == "unavailable":
                result["parts"] = []
                result["issues"].append("PLAN_PHASES_NOT_STORED")
        else:
            result["issues"].append("PLAN_NOT_LINKED")
    except InvalidPlan as exc:
        result.update(source="unavailable", parts=[], issues=[str(exc)])
    content = json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    result["content_hash"] = hashlib.sha256(content).hexdigest()
    return result
