"""Read-only snapshot adapters for Planning/Data Contract 0.1 DRAFT1.

Only Python's standard library is used. Source JSON is retained in full. A
successful conversion is not evidence of execution, adherence or fitness.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path

from .contract_checks import (
    ContractError, MODEL_ID, MODEL_VERSION, check_schema_subset, expand_plan,
    make_decision, timestamp, validate_contract,
)

ADAPTER_VERSION = "legacy-plan-adapter-0.1-draft1"
P = Path(__file__).resolve().parent
SPORTS = {"95": "KAYAK", "1": "RUNNING"}  # Pinned existing app mapping.
LEGACY_TYPES = {"RECOVERY": "RECOVERY", "WARMUP": "WARMUP", "COOLDOWN": "COOLDOWN"}
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}\Z")


class AdapterError(ValueError):
    """An unresolved source structure must not be silently coerced."""


def require(condition, message):
    if not condition:
        raise AdapterError(message)


def canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise AdapterError("SOURCE_NOT_FINITE_JSON") from exc


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json_loads(content):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "DUPLICATE_JSON_KEY: " + key)
            out[key] = value
        return out
    def nonfinite(value):
        raise AdapterError("NONFINITE_JSON_NUMBER: " + value)
    return json.loads(content, object_pairs_hook=pairs, parse_constant=nonfinite)


def contract_snapshot_sha256():
    files = [P / "contract_checks.py"] + sorted((P / "schemas").glob("*.json"))
    # Preserve the original package's logical names and digest after relocation.
    hashes = {"contract_v01/" + f.relative_to(P).as_posix():
              hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    return digest(hashes)


def _number(value, label, *, positive=True):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), label + ": INVALID_NUMBER")
    require(value > 0 if positive else value >= 0, label + ": OUT_OF_RANGE")
    return value


def _repeat(value):
    require(isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 1000,
            "REPEAT_COUNT_NOT_INTEGER_1_TO_1000")
    return value


def unknown_intensity(reason):
    return {"type": "UNKNOWN", "target_mode": "UNKNOWN", "value": None,
            "lower": None, "upper": None, "bounds": None,
            "zone_definition_ref": None, "unknown_reason": reason}


def free_intensity():
    out = unknown_intensity(None)
    out.update(type="FREE", target_mode="FREE")
    return out


def _pointer_part(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _leaves(value, path=""):
    if isinstance(value, dict) and value:
        for key in sorted(value):
            yield from _leaves(value[key], path + "/" + _pointer_part(key))
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from _leaves(child, path + "/" + str(index))
    else:
        yield path


def _read_pointer(value, pointer):
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


class _Audit:
    def __init__(self):
        self.mapped = {}
        self.issues = []
        self.blocks = []

    def map(self, source, target, transform="COPY"):
        self.mapped[source] = {"source_pointer": source, "disposition": "MAPPED",
                               "contract_pointer": target, "transform": transform}

    def issue(self, code, pointer="", detail=None):
        self.issues.append({"code": code, "source_pointer": pointer, "detail": detail})

    def fields(self, raw):
        return [self.mapped.get(path, {"source_pointer": path,
                "disposition": "PRESERVED_IN_SOURCE_ONLY", "contract_pointer": None,
                "transform": None}) for path in _leaves(raw)]


def _base_block(block_id, description=None):
    return {"block_id": block_id, "block_type": "UNKNOWN", "structure": "SEGMENT",
            "duration_s": None, "distance_m": None, "completion_condition": "MANUAL",
            "intensity": unknown_intensity("SOURCE_INTENSITY_NOT_SPECIFIED"),
            "repeat_count": 1, "recovery": None, "execution_role": "UNSPECIFIED",
            "children": [], "description": description}


def _set_goal(block, duration, distance, *, completion=None):
    if duration is not None:
        block["duration_s"] = _number(duration, "duration_s")
    if distance is not None:
        block["distance_m"] = _number(distance, "distance_m")
    if duration is not None and distance is not None:
        require(completion in ("FIRST_REACHED", "BOTH_REACHED"), "DUAL_GOAL_COMPLETION_NOT_DECLARED")
        block["completion_condition"] = completion
    elif duration is not None:
        block["completion_condition"] = "DURATION"
    elif distance is not None:
        block["completion_condition"] = "DISTANCE"
    else:
        block["completion_condition"] = "MANUAL"
        block["description"] = block["description"] or (
            "Unresolved/manual placeholder: no structured completion goal in source. "
            "This does not establish the actual execution transition.")


def _source_intensity(source, pointer, target, audit, *, polar):
    require(isinstance(source, dict), "INTENSITY_NOT_OBJECT")
    typ = source.get("type") if polar else source.get("intensity_type")
    lo = source.get("lowerZone") if polar else source.get("intensity_min")
    hi = source.get("upperZone") if polar else source.get("intensity_max")
    if typ in ("HEART_RATE_ZONES", "HR_ZONE"):
        audit.issue("HR_ZONE_DEFINITION_NOT_BOUND", pointer,
                    {"source_type": typ, "lower": lo, "upper": hi})
        return unknown_intensity("HR_ZONE_DEFINITION_NOT_BOUND; original zone indices are retained in source and audit.")
    if typ == "SPEED_ZONES":
        audit.issue("SPEED_ZONE_PHYSICAL_UNITS_NOT_BOUND", pointer,
                    {"source_type": typ, "lower": lo, "upper": hi})
        return unknown_intensity("SPEED_ZONE_PHYSICAL_UNITS_NOT_BOUND; zone numbers are not m/s or pace.")
    if typ == "NONE" and lo in (None, 0) and hi in (None, 0):
        field = "/type" if polar else "/intensity_type"
        audit.map(pointer + field, target + "/type", "EXPLICIT_NONE_TO_FREE")
        return free_intensity()
    if not polar and typ in ("HR_BPM", "POWER_W", "SPEED_MPS", "PACE_S_PER_KM", "RPE_0_10") and lo is not None and hi is not None:
        _number(lo, "intensity_min", positive=False)
        _number(hi, "intensity_max", positive=False)
        require(lo <= hi, "REVERSED_INTENSITY_RANGE")
        out = unknown_intensity(None)
        out.update(type=typ)
        if lo == hi:
            out.update(target_mode="POINT", value=lo)
            audit.map(pointer + "/intensity_min", target + "/value", "EQUAL_MIN_MAX_TO_POINT")
            audit.map(pointer + "/intensity_max", target + "/value", "EQUAL_MIN_MAX_TO_POINT")
        else:
            out.update(target_mode="RANGE", lower=lo, upper=hi, bounds="UNKNOWN")
            audit.map(pointer + "/intensity_min", target + "/lower")
            audit.map(pointer + "/intensity_max", target + "/upper")
            audit.issue("INTENSITY_ENDPOINT_POLICY_UNKNOWN", pointer)
        audit.map(pointer + "/intensity_type", target + "/type")
        return out
    audit.issue("INTENSITY_UNRESOLVED", pointer, {"source_type": typ, "lower": lo, "upper": hi})
    return unknown_intensity("INTENSITY_UNRESOLVED; missing, unsupported or one-sided target retained in source.")


def _context(raw, *, source_format, athlete_id, collected_at, source_ref, capture):
    require(isinstance(raw, dict), "SOURCE_NOT_OBJECT")
    canonical_bytes(raw)
    require(isinstance(athlete_id, str) and ID_PATTERN.fullmatch(athlete_id), "ATHLETE_ID_INVALID")
    try:
        timestamp(collected_at)
    except ContractError as exc:
        raise AdapterError("CAPTURE_TIME_REQUIRES_OFFSET") from exc
    require(isinstance(source_ref, str) and bool(source_ref), "SOURCE_REF_REQUIRED")
    return {"format": source_format, "payload": copy.deepcopy(raw),
            "canonical_json_sha256": digest(raw), "source_ref": source_ref,
            "collected_at": collected_at, "available_at": None,
            "capture": copy.deepcopy(capture)}


def _new_plan(source, athlete_id, plan_id, revision, day, title, sport, description=None, start=None):
    return {"contract_type": "WorkoutPlanContract", "schema_version": "0.1",
            "plan_id": plan_id, "plan_revision": revision, "athlete_id": athlete_id,
            "planned_date": day, "planned_start_time": start, "sport": sport,
            "session_type": "FARTLEK" if re.search(r"\bfartlek\b", title, re.I) else "UNKNOWN",
            "title": title, "description": description, "blocks": [], "evidence": [{
                "evidence_id": "plan_snapshot_" + digest({k: v for k, v in source.items() if k != "payload"}),
                "kind": "PLAN_SNAPSHOT", "scope": (
                    "CAPTURED_PLAN_JSON_CANONICAL_PAYLOAD_SHA256; source_ref points to the "
                    "JSON payload/entry, canonicalized as sorted-key compact UTF-8 JSON. "
                    "Source preservation only; historical effective content is unverified."),
                "source_ref": source["source_ref"], "sha256": source["canonical_json_sha256"],
                "collected_at": source["collected_at"], "available_at": None,
                "verification_status": "VERIFIED_WITH_LIMITATIONS",
                "limitations": ["HISTORICAL_PLAN_CONTENT_UNVERIFIED", "AVAILABLE_AT_NOT_ESTABLISHED",
                                "HASH_MATCH_DOES_NOT_VERIFY_EXECUTION_OR_SENSOR_ACCURACY"]}]}


def _finish(plan, source, audit):
    try:
        validate_contract(plan)
        occurrences = expand_plan(plan)
    except (ContractError, KeyError, TypeError) as exc:
        raise AdapterError("CONTRACT_VALIDATION_FAILED: " + str(exc)) from exc
    for item in audit.fields(source["payload"]):
        if item["contract_pointer"] is not None:
            _read_pointer(plan, item["contract_pointer"])
    return {"artifact_type": "LegacyPlanAdapterResult", "adapter_version": ADAPTER_VERSION,
            "contract_snapshot_sha256": contract_snapshot_sha256(), "source": source,
            "plan": plan, "expanded_occurrences": occurrences,
            "field_disposition": audit.fields(source["payload"]),
            "block_mapping": audit.blocks, "limitations": audit.issues,
            "historical_plan_content_status": "UNVERIFIED", "execution_inferred": False}


def adapt_polar_target(raw, *, athlete_id, collected_at, source_ref, capture=None):
    source = _context(raw, source_format="POLAR_TARGET_SNAPSHOT", athlete_id=athlete_id,
                      collected_at=collected_at, source_ref=source_ref, capture=capture)
    audit = _Audit()
    session = raw.get("session")
    exercises = raw.get("exercise")
    require(isinstance(session, dict) and isinstance(exercises, list) and exercises, "POLAR_SESSION_AND_EXERCISE_REQUIRED")
    target_id = session.get("id")
    require(isinstance(target_id, str) and ID_PATTERN.fullmatch(target_id), "POLAR_TARGET_ID_INVALID")
    revision = session.get("version")
    require(isinstance(revision, int) and not isinstance(revision, bool) and revision >= 1,
            "PROVIDER_VERSION_REQUIRED_POSITIVE_INTEGER")
    local = session.get("startTime")
    require(isinstance(local, dict), "PLANNED_LOCAL_DATE_REQUIRED")
    try:
        # Validate all supplied clock components but do not invent its UTC offset.
        components = [local[k] for k in ("year", "month", "day", "hour", "min", "sec")]
        require(all(isinstance(n, int) and not isinstance(n, bool) for n in components), "LOCAL_CLOCK_COMPONENT_NOT_INTEGER")
        day = datetime(*components).date().isoformat()
    except (KeyError, ValueError, TypeError) as exc:
        raise AdapterError("INVALID_PROVIDER_LOCAL_CLOCK") from exc
    title = session.get("name")
    require(isinstance(title, str), "POLAR_TITLE_REQUIRED")
    codes = {str(e.get("sportId")) for e in exercises if isinstance(e, dict)}
    require(len(codes) == 1 and len(exercises) == sum(isinstance(e, dict) for e in exercises), "MULTI_SPORT_TARGET_NOT_SUPPORTED")
    code = next(iter(codes))
    require(code != "None", "SPORT_ID_REQUIRED")
    sport = SPORTS.get(code, "POLAR_SPORT_" + code)
    if code not in SPORTS:
        audit.issue("SPORT_MAPPING_NOT_ESTABLISHED", "/exercise", {"sport_id": code})
    plan_id = "polar-target:" + target_id + ":a01:" + source["canonical_json_sha256"]
    plan = _new_plan(source, athlete_id, plan_id, revision, day, title, sport, session.get("description"))
    audit.map("/session/name", "/title")
    audit.map("/session/version", "/plan_revision")
    for key in ("year", "month", "day"):
        audit.map("/session/startTime/" + key, "/planned_date", "LOCAL_DATE_COMPONENTS_ONLY")
    if "description" in session:
        audit.map("/session/description", "/description")
    audit.issue("PROVIDER_LOCAL_TIME_OFFSET_UNKNOWN", "/session/startTime")
    audit.issue("HISTORICAL_PLAN_CONTENT_UNVERIFIED", "/session/version")
    modified = session.get("modified", {})
    if all(isinstance(modified.get(k), int) and not isinstance(modified.get(k), bool) for k in ("year", "month", "day")):
        try:
            if date(modified["year"], modified["month"], modified["day"]) > date.fromisoformat(day):
                audit.issue("PROVIDER_MODIFIED_DATE_AFTER_PLANNED_DATE", "/session/modified")
        except ValueError:
            audit.issue("PROVIDER_MODIFIED_DATE_INVALID", "/session/modified")

    def phase(node, sp, tp, path, depth=0):
        require(depth <= 12 and isinstance(node, dict), "PHASE_DEPTH_OR_TYPE_INVALID")
        children = node.get("phaseOrRepeat", [])
        require(isinstance(children, list), "PHASE_CHILDREN_NOT_ARRAY")
        name = node.get("name")
        require(name is None or isinstance(name, str), "PHASE_NAME_NOT_STRING")
        b = _base_block("polar-block:" + path, name or None)
        if "name" in node:
            audit.map(sp + "/name", tp + "/description", "EMPTY_NAME_TO_NULL")
        b["repeat_count"] = _repeat(node.get("repeatCount", 1))
        if "repeatCount" in node:
            audit.map(sp + "/repeatCount", tp + "/repeat_count")
        change = node.get("changeType")
        require(change in ("AUTOMATIC", "MANUAL"), "PHASE_CHANGE_TYPE_UNSUPPORTED")
        if children:
            require("goal" not in node and "intensity" not in node,
                    "CONTAINER_HAS_UNSUPPORTED_OWN_GOAL_OR_INTENSITY")
            b.update(structure="SEQUENCE", completion_condition="CHILDREN")
            b["intensity"] = unknown_intensity("STRUCTURAL_CONTAINER_NOT_AN_INTENSITY_TARGET")
            b["children"] = [phase(c, sp + "/phaseOrRepeat/" + str(i),
                                   tp + "/children/" + str(i), path + "." + str(i), depth + 1)
                             for i, c in enumerate(children)]
        else:
            require("repeatCount" not in node, "EMPTY_REPEAT_CONTAINER")
            goal = node.get("goal")
            require(isinstance(goal, dict), "PHASE_GOAL_REQUIRED")
            goal_type = goal.get("type")
            if goal_type == "DURATION":
                ds, dm = _number(goal.get("duration"), "duration_ms") / 1000, None
                value_path, contract_field, transform = "/duration", "/duration_s", "MILLISECONDS_TO_SECONDS_NO_TRUNCATION"
            elif goal_type == "DISTANCE":
                ds, dm = None, _number(goal.get("distance"), "distance_m")
                value_path, contract_field, transform = "/distance", "/distance_m", "METRES_UNCHANGED"
            else:
                raise AdapterError("UNSUPPORTED_POLAR_GOAL_TYPE: " + str(goal_type))
            if change == "MANUAL":
                # Contract draft has no independent manual-advance flag. Keep the
                # requested goal in audit/source, not as a false automatic end.
                _set_goal(b, None, None)
                audit.issue("MANUAL_ADVANCE_GOAL_RETAINED_OUTSIDE_CONTRACT_TARGET", sp,
                            {"source_goal": copy.deepcopy(goal), "duration_s": ds, "distance_m": dm})
            else:
                _set_goal(b, ds, dm)
                audit.map(sp + "/goal" + value_path, tp + contract_field, transform)
                audit.map(sp + "/goal/type", tp + "/completion_condition")
            b["intensity"] = _source_intensity(node.get("intensity", {}), sp + "/intensity", tp + "/intensity", audit, polar=True)
            audit.issue("POLAR_BLOCK_SEMANTIC_TYPE_UNDECLARED", sp,
                        {"source_name": name, "contract_block_type": "UNKNOWN"})
        if change == "MANUAL":
            audit.issue("MANUAL_ADVANCE_PRESERVED_IN_AUDIT", sp + "/changeType")
        audit.blocks.append({"source_pointer": sp, "block_id": b["block_id"],
                             "source_type": "REPEAT" if children else "PHASE",
                             "source_name": name, "source_change_type": change,
                             "semantic_type_basis": "UNKNOWN", "contract_block_type": b["block_type"]})
        return b

    for i, exercise in enumerate(exercises):
        ep = "/exercise/" + str(i)
        require(exercise.get("type") in ("PHASED", "VOLUME"), "EXERCISE_TYPE_UNSUPPORTED")
        nodes = exercise.get("phaseOrRepeat", [])
        require(isinstance(nodes, list), "EXERCISE_PHASES_NOT_ARRAY")
        root = _base_block("polar-block:e" + str(i), None)
        tp = "/blocks/" + str(i)
        if nodes:
            require(exercise["type"] == "PHASED", "VOLUME_EXERCISE_WITH_PHASES")
            root.update(structure="SEQUENCE", completion_condition="CHILDREN")
            root["intensity"] = unknown_intensity("STRUCTURAL_CONTAINER_NOT_AN_INTENSITY_TARGET")
            root["children"] = [phase(n, ep + "/phaseOrRepeat/" + str(j), tp + "/children/" + str(j), "e" + str(i) + "." + str(j))
                                for j, n in enumerate(nodes)]
            audit.issue("EXERCISE_TOTALS_RETAINED_AS_SOURCE_NOT_ADDED_TO_CHILD_TARGETS", ep)
        else:
            require(exercise["type"] == "VOLUME", "PHASED_EXERCISE_WITHOUT_PHASES")
            ds = _number(exercise["duration"], "duration_ms") / 1000 if exercise.get("duration") is not None else None
            dm = exercise.get("distance")
            require(ds is not None or dm is not None, "VOLUME_TARGET_WITHOUT_DIMENSION")
            _set_goal(root, ds, dm)
            if ds is not None:
                audit.map(ep + "/duration", tp + "/duration_s", "MILLISECONDS_TO_SECONDS_NO_TRUNCATION")
            if dm is not None:
                audit.map(ep + "/distance", tp + "/distance_m")
            audit.issue("VOLUME_TARGET_INTENSITY_AND_SEMANTIC_TYPE_UNDECLARED", ep)
        plan["blocks"].append(root)
    return _finish(plan, source, audit)


def adapt_legacy_workout(raw, *, athlete_id, collected_at, source_ref, capture=None):
    """Accept a JSON snapshot with flat id/parent_block_id/position block rows.

    This deliberately does not open SQLAlchemy sessions, import app code or
    mutate a schema. It is an adapter for the inspected old snapshot shape.
    """
    source = _context(raw, source_format="LEGACY_WORKOUT_SNAPSHOT", athlete_id=athlete_id,
                      collected_at=collected_at, source_ref=source_ref, capture=capture)
    require(raw.get("user_id") in (None, athlete_id), "CROSS_ATHLETE_WORKOUT_REJECTED")
    source_id = raw.get("id")
    require(isinstance(source_id, str) and ID_PATTERN.fullmatch(source_id), "LEGACY_WORKOUT_ID_REQUIRED")
    require(isinstance(raw.get("date"), str), "LEGACY_DATE_REQUIRED")
    require(isinstance(raw.get("sport"), str) and raw["sport"], "LEGACY_SPORT_REQUIRED")
    require(isinstance(raw.get("title"), str), "LEGACY_TITLE_REQUIRED")
    start = raw.get("planned_start_time")
    audit = _Audit()
    if start is not None:
        try:
            parsed = timestamp(start)
        except ContractError:
            audit.issue("LEGACY_START_OFFSET_UNKNOWN", "/planned_start_time")
            start = None
        else:
            require(parsed.date().isoformat() == raw["date"], "LEGACY_START_DATE_CONFLICT")
            audit.map("/planned_start_time", "/planned_start_time")
    plan = _new_plan(source, athlete_id, "legacy-workout:" + source_id + ":a01:" + digest(raw),
                     1, raw["date"], raw["title"], raw["sport"], raw.get("description"), start)
    for field, target in [("date", "planned_date"), ("title", "title"), ("sport", "sport"), ("description", "description")]:
        if field in raw:
            audit.map("/" + field, "/" + target)
    audit.issue("SNAPSHOT_IDENTITY_NOT_PERSISTED_PLAN_REVISION", "/id")
    audit.issue("HISTORICAL_PLAN_CONTENT_UNVERIFIED")
    rows = raw.get("blocks", [])
    require(isinstance(rows, list) and len(rows) <= 10000, "LEGACY_BLOCKS_NOT_BOUNDED_ARRAY")
    if not rows:
        b = _base_block("legacy-block:unstructured", raw.get("description"))
        _set_goal(b, raw.get("duration_sec"), raw.get("distance_m"), completion=raw.get("completion_condition"))
        plan["blocks"] = [b]
        audit.issue("UNSTRUCTURED_PLAN_PLACEHOLDER", "/blocks")
        for field, target in [("duration_sec", "duration_s"), ("distance_m", "distance_m")]:
            if raw.get(field) is not None:
                audit.map("/" + field, "/blocks/0/" + target)
        return _finish(plan, source, audit)
    by_id, children = {}, {}
    for i, row in enumerate(rows):
        require(isinstance(row, dict), "LEGACY_BLOCK_ROW_NOT_OBJECT")
        bid = row.get("id")
        require(isinstance(bid, str) and ID_PATTERN.fullmatch(bid), "LEGACY_BLOCK_ID_REQUIRED")
        require(bid not in by_id, "DUPLICATE_LEGACY_BLOCK_ID")
        require(row.get("workout_id") in (None, source_id), "CROSS_WORKOUT_BLOCK_REJECTED")
        position = row.get("position")
        require(isinstance(position, int) and not isinstance(position, bool), "BLOCK_POSITION_NOT_INTEGER")
        by_id[bid] = (i, row)
        children.setdefault(row.get("parent_block_id"), []).append(bid)
    for parent, ids in children.items():
        require(parent is None or parent in by_id, "ORPHAN_PARENT_BLOCK")
        positions = [by_id[bid][1]["position"] for bid in ids]
        require(len(positions) == len(set(positions)), "AMBIGUOUS_SIBLING_POSITION")
        ids.sort(key=lambda bid: by_id[bid][1]["position"])
    visiting, visited = set(), set()

    def block(bid, tp, depth=0):
        require(depth <= 12, "LEGACY_BLOCK_DEPTH_EXCEEDED")
        require(bid not in visiting, "LEGACY_BLOCK_CYCLE")
        visiting.add(bid)
        i, row = by_id[bid]
        sp = "/blocks/" + str(i)
        typ = row.get("block_type")
        require(typ in ("WORK", "RECOVERY", "WARMUP", "COOLDOWN", "REPEAT"), "LEGACY_BLOCK_TYPE_UNSUPPORTED")
        b = _base_block("legacy-block:" + bid, row.get("name"))
        b["repeat_count"] = _repeat(row.get("repeat_count") if row.get("repeat_count") is not None else 1)
        if "name" in row:
            audit.map(sp + "/name", tp + "/description")
        if row.get("repeat_count") is not None:
            audit.map(sp + "/repeat_count", tp + "/repeat_count")
        else:
            audit.issue("ABSENT_REPEAT_COUNT_SINGLE_OCCURRENCE", sp + "/repeat_count")
        child_ids = children.get(bid, [])
        if typ == "REPEAT":
            require(child_ids, "EMPTY_LEGACY_REPEAT_CONTAINER")
            require(all(row.get(k) is None for k in ("duration_sec", "distance_m", "intensity_type", "intensity_min", "intensity_max")),
                    "LEGACY_CONTAINER_HAS_OWN_GOAL_OR_INTENSITY")
            b.update(structure="SEQUENCE", completion_condition="CHILDREN")
            b["intensity"] = unknown_intensity("STRUCTURAL_CONTAINER_NOT_AN_INTENSITY_TARGET")
            b["children"] = [block(cid, tp + "/children/" + str(j), depth + 1) for j, cid in enumerate(child_ids)]
        else:
            require(not child_ids, "NON_REPEAT_BLOCK_HAS_CHILDREN")
            b["block_type"] = LEGACY_TYPES.get(typ, "UNKNOWN")
            b["execution_role"] = {"RECOVERY": "RECOVERY", "WARMUP": "PREPARATION", "COOLDOWN": "TRANSITION"}.get(typ, "UNSPECIFIED")
            _set_goal(b, row.get("duration_sec"), row.get("distance_m"), completion=row.get("completion_condition"))
            for field, target in [("duration_sec", "duration_s"), ("distance_m", "distance_m")]:
                if row.get(field) is not None:
                    audit.map(sp + "/" + field, tp + "/" + target)
            b["intensity"] = _source_intensity(row, sp, tp + "/intensity", audit, polar=False)
            if typ == "WORK":
                audit.issue("LEGACY_WORK_IS_NOT_A_SEMANTIC_STEADY_LABEL", sp + "/block_type")
            else:
                audit.map(sp + "/block_type", tp + "/block_type")
        audit.blocks.append({"source_pointer": sp, "block_id": b["block_id"], "source_type": typ,
                             "source_name": row.get("name"), "source_change_type": None,
                             "semantic_type_basis": "LEGACY_ENUM_DECLARED" if typ in LEGACY_TYPES else "UNKNOWN",
                             "contract_block_type": b["block_type"]})
        visiting.remove(bid)
        visited.add(bid)
        return b

    roots = children.get(None, [])
    require(roots, "LEGACY_BLOCK_CYCLE_OR_NO_ROOT")
    plan["blocks"] = [block(bid, "/blocks/" + str(i)) for i, bid in enumerate(roots)]
    require(len(visited) == len(rows), "LEGACY_UNREACHABLE_BLOCK_OR_CYCLE")
    return _finish(plan, source, audit)


def restore_source(result):
    require(result.get("adapter_version") == ADAPTER_VERSION, "ADAPTER_VERSION_MISMATCH")
    require(result.get("contract_snapshot_sha256") == contract_snapshot_sha256(), "CONTRACT_SNAPSHOT_MISMATCH")
    source = result["source"]
    require(digest(source["payload"]) == source["canonical_json_sha256"], "SOURCE_PAYLOAD_HASH_MISMATCH")
    return copy.deepcopy(source["payload"])


def verify_result(result):
    raw = restore_source(result)
    source = result["source"]
    adapter = {"POLAR_TARGET_SNAPSHOT": adapt_polar_target,
               "LEGACY_WORKOUT_SNAPSHOT": adapt_legacy_workout}.get(source["format"])
    require(adapter is not None, "SOURCE_FORMAT_UNSUPPORTED")
    regenerated = adapter(raw, athlete_id=result["plan"]["athlete_id"], collected_at=source["collected_at"],
                          source_ref=source["source_ref"], capture=source["capture"])
    require(result == regenerated, "ADAPTER_RESULT_REPLAY_MISMATCH")
    return True


def plan_type_routing(plan):
    """No fitted parameters or observed data: no numeric output is possible."""
    validate_contract(plan)
    blocks = {}
    def walk(b):
        blocks[b["block_id"]] = b
        for child in b["children"]:
            walk(child)
        if b["recovery"] is not None:
            walk(b["recovery"]["block"])
    for b in plan["blocks"]:
        walk(b)
    decisions = []
    for occurrence in expand_plan(plan):
        block = blocks[occurrence["block_id"]]
        decision = make_decision(
            athlete_id=plan["athlete_id"], plan_ref={"plan_id": plan["plan_id"], "plan_revision": plan["plan_revision"]},
            execution_ref=None, subject={"planned_block_id": block["block_id"],
                "planned_occurrence_id": occurrence["planned_occurrence_id"], "executed_block_id": None},
            model_id=MODEL_ID, model_version=MODEL_VERSION, model_variant="HR_GEOGRAPHY",
            parameter_set_id=None, model_artifact_sha256=None,
            assessment_scope="BLOCK_TYPE_ROUTING", block_type=block["block_type"],
            block_type_basis="PLAN_DECLARED" if block["block_type"] != "UNKNOWN" else "UNKNOWN",
            structure="SEGMENT", checks={"hr_input": "UNKNOWN", "boundaries": "UNRESOLVED",
                "native_time_origin": "UNKNOWN", "geographical_support": "UNKNOWN", "numeric_range": "UNKNOWN",
                "sensor_quality": "UNKNOWN", "environment": "UNKNOWN", "plan_content_at_execution": "UNVERIFIED"},
            evidence_refs=[e["evidence_id"] for e in plan["evidence"]], evidence=copy.deepcopy(plan["evidence"]))
        validate_contract(decision)
        require(not decision["numeric_result_allowed"], "TYPE_ROUTING_MUST_NOT_AUTHORIZE_NUMERIC_OUTPUT")
        decisions.append(decision)
    return decisions
