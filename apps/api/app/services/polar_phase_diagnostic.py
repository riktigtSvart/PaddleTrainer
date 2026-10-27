"""Read-only, credential-free evidence for one owned calendar day's phase import."""
from datetime import UTC, datetime, time, timedelta
import hashlib
import json
import math
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models.entities import PlannedWorkout, ProviderDataRecord, WorkoutSession
from app.services.polar_target_structure import TargetStructureError, native_id, phase_structure

ARCHIVE_LIMIT = 500
ITEM_LIMIT = 256
SENSITIVE = ("token", "secret", "password", "authorization", "cookie", "email", "latitude", "longitude", "waypoint")


def iso(value):
    return value.isoformat() if value is not None else None


def safe(value, depth=0):
    """Preserve relevant native phase/lap fields, not GPS or credentials."""
    if depth > 20:
        return {"diagnostic_omitted": "depth_limit"}
    if isinstance(value, dict):
        result = {str(k)[:120]: safe(v, depth + 1) for k, v in list(value.items())[:ITEM_LIMIT]
                  if not any(word in str(k).lower() for word in SENSITIVE)}
        if len(value) > ITEM_LIMIT:
            result["diagnostic_omitted"] = "field_limit"
        return result
    if isinstance(value, list):
        result = [safe(v, depth + 1) for v in value[:ITEM_LIMIT]]
        if len(value) > ITEM_LIMIT:
            result.append({"diagnostic_omitted": "item_limit", "source_count": len(value)})
        return result
    if isinstance(value, str):
        return value[:300]
    if type(value) is float and not math.isfinite(value):
        return {"diagnostic_invalid": "non_finite_number"}
    if value is None or type(value) in (bool, int, float):
        return value
    return {"diagnostic_omitted": "unsupported_type"}


def related_fields(raw):
    """Discover undocumented phase/lap metadata without exporting sample arrays."""
    result = []
    nodes = 0
    omitted = False
    def walk(value, path, depth):
        nonlocal nodes, omitted
        nodes += 1
        if depth > 20 or nodes > 12000:
            omitted = True
            return
        if isinstance(value, dict):
            for key, child in value.items():
                name = str(key)
                if any(word in name.lower() for word in SENSITIVE) or name in ("values", "rrSamples", "transitionRrSamples"):
                    continue
                at = path + "." + name
                if any(word in name.lower() for word in ("phase", "lap")):
                    result.append({"path": at, "value": safe(child)})
                    if len(result) >= ITEM_LIMIT:
                        omitted = True
                        return
                else:
                    walk(child, at, depth + 1)
        elif isinstance(value, list):
            if len(value) > ITEM_LIMIT:
                omitted = True
            for index, child in enumerate(value[:ITEM_LIMIT]):
                if isinstance(child, (dict, list)):
                    walk(child, f"{path}[{index}]", depth + 1)
    walk(raw, "$", 0)
    return {"fields": result, "scan_truncated": omitted}


def target_view(raw):
    session = raw.get("session") if isinstance(raw, dict) else None
    session = session if isinstance(session, dict) else {}
    try:
        structure = phase_structure(raw)
    except TargetStructureError:
        structure = "invalid"
    exercises = raw.get("exercise") if isinstance(raw, dict) else None
    return {"native_target_id": native_id(session.get("id")), "name": safe(session.get("name")),
            "done": session.get("done") if type(session.get("done")) is bool else None,
            "startTime": safe(session.get("startTime")), "structure": structure,
            "exercise_count": len(exercises) if isinstance(exercises, list) else None,
            "phase_fields": related_fields(raw)}


def session_view(raw):
    raw = raw if isinstance(raw, dict) else {}
    identifier = raw.get("identifier")
    target = raw.get("trainingTarget")
    views = {}
    for key in ("exercises", "exerciseSamples"):
        source = raw.get(key)
        if not isinstance(source, list):
            continue
        exercises = []
        for index, exercise in enumerate(source[:64]):
            if not isinstance(exercise, dict):
                continue
            part_id = exercise.get("identifier")
            samples = exercise.get("samples")
            series = samples.get("samples") if isinstance(samples, dict) else None
            exercises.append({"index": index, "native_exercise_id": native_id(part_id.get("id")) if isinstance(part_id, dict) else None,
                "startTime": safe(exercise.get("startTime")), "stopTime": safe(exercise.get("stopTime")),
                "durationMillis": safe(exercise.get("durationMillis")), "distanceMeters": safe(exercise.get("distanceMeters")),
                "sample_clocks": [{"type": safe(s.get("type")), "intervalMillis": safe(s.get("intervalMillis")),
                    "slot_count": len(s["values"]) if isinstance(s.get("values"), list) else None}
                    for s in series[:128] if isinstance(s, dict)] if isinstance(series, list) else [],
                "pauseTimes": safe(exercise.get("pauseTimes")), "phase_fields": related_fields(exercise)})
        views[key] = {"source_count": len(source), "exercises": exercises, "truncated": len(source) > 64}
    return {"native_session_id": native_id(identifier.get("id")) if isinstance(identifier, dict) else None,
        "native_target_id": native_id(target.get("id")) if isinstance(target, dict) else None,
        "startTime": safe(raw.get("startTime")), "stopTime": safe(raw.get("stopTime")),
        "durationMillis": safe(raw.get("durationMillis")), "distanceMeters": safe(raw.get("distanceMeters")),
        "root_fields": sorted(str(k)[:120] for k in raw), "exercise_views": views, "phase_fields": related_fields(raw)}


async def local_report(db, user, day):
    """Only SELECT statements. Caller owns rollback/read-only transaction setup."""
    first = datetime.combine(day, time.min, ZoneInfo(user.timezone)).astimezone(UTC)
    last = datetime.combine(day + timedelta(days=1), time.min, ZoneInfo(user.timezone)).astimezone(UTC)
    sessions = (await db.execute(select(WorkoutSession).where(WorkoutSession.user_id == user.id,
        WorkoutSession.external_provider == "POLAR", WorkoutSession.started_at >= first,
        WorkoutSession.started_at < last).order_by(WorkoutSession.started_at, WorkoutSession.id).limit(65))).scalars().all()
    if len(sessions) > 64:
        raise ValueError("DIAGNOSTIC_TOO_MANY_SESSIONS")
    links = {s.planned_workout_id for s in sessions if s.planned_workout_id is not None}
    references = {native_id(s.raw_data.get("trainingTarget", {}).get("id")) for s in sessions
                  if isinstance(s.raw_data, dict) and isinstance(s.raw_data.get("trainingTarget"), dict)} - {None}
    plans = (await db.execute(select(PlannedWorkout).options(selectinload(PlannedWorkout.blocks)).where(
        PlannedWorkout.user_id == user.id, or_(PlannedWorkout.date == day, PlannedWorkout.id.in_(links),
            PlannedWorkout.polar_target_id.in_(references))).order_by(PlannedWorkout.id).limit(65))).scalars().all()
    if len(plans) > 64:
        raise ValueError("DIAGNOSTIC_TOO_MANY_PLANS")
    owned = {p.id for p in plans}
    target_ids = references | {p.polar_target_id for p in plans if p.polar_target_id}
    archive_rows = (await db.execute(select(ProviderDataRecord).where(
        ProviderDataRecord.user_id == user.id, ProviderDataRecord.provider == "POLAR",
        ProviderDataRecord.data_type.in_(["DATA_SYNC_TARGETS", "DATA_SYNC_PREVIOUS_TARGET"])
    ).order_by(ProviderDataRecord.fetched_at.desc(), ProviderDataRecord.id.desc()).limit(ARCHIVE_LIMIT + 1))).scalars().all()
    archives = []
    for record in archive_rows[:ARCHIVE_LIMIT]:
        raw = record.raw_data
        candidates = []
        if isinstance(raw, dict) and record.data_type == "DATA_SYNC_PREVIOUS_TARGET":
            # Never expose a foreign or stale owner reference from an archive wrapper.
            if raw.get("workout_id") in {str(identity) for identity in owned}:
                candidates = [raw.get("raw_data")]
        elif isinstance(raw, dict):
            candidates = raw.get("trainingTarget", raw.get("targets", []))
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            native = candidate.get("session") if isinstance(candidate, dict) else None
            if not isinstance(native, dict) or native_id(native.get("id")) not in target_ids:
                continue
            view = target_view(candidate)
            encoded = json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()
            archives.append({"category": record.data_type, "fetched_at": iso(record.fetched_at),
                "native_payload_sha256": hashlib.sha256(encoded).hexdigest(), "target": view})
    return {"schema_version": "polar-phase-import-diagnostic-v1", "date": day.isoformat(),
        "timezone": user.timezone, "athlete_id": str(user.id),
        "sessions": [{"id": str(s.id), "external_id": s.external_id,
            "linked_plan_id": str(s.planned_workout_id) if s.planned_workout_id in owned else None,
            "stored": session_view(s.raw_data)} for s in sessions],
        "plans": [{"id": str(p.id), "native_target_id": p.polar_target_id,
            "status": p.status.value, "source": p.source, "title": p.title, "calendar_date": iso(p.date),
            "stored": target_view(p.raw_data), "blocks": [{"id": str(b.id),
                "parent_id": str(b.parent_block_id) if b.parent_block_id else None,
                "position": b.position, "name": b.name, "type": b.block_type.value,
                "duration_sec": b.duration_sec, "distance_m": b.distance_m,
                "repeat_count": b.repeat_count} for b in sorted(p.blocks, key=lambda b: b.position)]} for p in plans],
        "archives": {"scanned": min(len(archive_rows), ARCHIVE_LIMIT), "scan_truncated": len(archive_rows) > ARCHIVE_LIMIT,
            "matches": archives},
        "provider": {"requested": False}, "application_data_changed": False}


async def provider_report(client, access, scopes, day):
    result = {"requested": True, "from": day.isoformat(), "to_exclusive": (day + timedelta(days=1)).isoformat(), "requests": []}
    for dataset, scope in (("sessions", "training_sessions:read"), ("targets", "training_targets:read")):
        if scope not in scopes:
            result[dataset] = {"state": "scope_missing"}
            continue
        result["requests"].append({"dataset": dataset,
            "features": ["statistics", "laps", "pause-times"] if dataset == "sessions" else []})
        try:
            if dataset == "sessions":
                payload = await client.list_training_sessions(access, day, day + timedelta(days=1), features=["statistics", "laps", "pause-times"])
                rows = payload.get("trainingSessions") if isinstance(payload, dict) else None
                convert = session_view
            else:
                rows = await client.list_training_targets(access, day, day + timedelta(days=1))
                convert = target_view
            if not isinstance(rows, list) or len(rows) > 64:
                result[dataset] = {"state": "payload_invalid"}
            else:
                result[dataset] = {"state": "succeeded", "count": len(rows), "records": [convert(row) for row in rows]}
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            result[dataset] = {"state": "failed", "http_status": status if type(status) is int else None,
                               "error_type": type(exc).__name__}
    return result


def findings(report):
    """Claims concern the selected response/day, never general API availability."""
    result = []
    fresh = report.get("provider", {}).get("targets", {})
    records = fresh.get("records", [])
    for plan in report["plans"]:
        identity = plan["native_target_id"]
        if not plan["blocks"] and plan["stored"]["structure"] == "complete":
            result.append({"plan_id": plan["id"], "code": "STORED_PHASE_SOURCE_NOT_PROJECTED"})
        matches = [a for a in report["archives"]["matches"] if a["target"]["native_target_id"] == identity and a["target"]["structure"] == "complete"]
        if not plan["blocks"] and matches:
            result.append({"plan_id": plan["id"], "code": "ARCHIVED_PHASE_SOURCE_AVAILABLE",
                "distinct_native_payloads": len({a["native_payload_sha256"] for a in matches})})
        matching = [t for t in records if t["native_target_id"] == identity]
        if len(matching) == 1 and matching[0]["structure"] == "complete" and not plan["blocks"]:
            result.append({"plan_id": plan["id"], "code": "API_PHASE_SOURCE_NOT_PROJECTED"})
        if len(matching) == 1 and matching[0]["structure"] != "complete":
            result.append({"plan_id": plan["id"], "code": "API_TARGET_HAS_NO_COMPLETE_PHASES_IN_THIS_RESPONSE"})
        if not matching and fresh.get("state") == "succeeded":
            result.append({"plan_id": plan["id"], "code": "TARGET_NOT_RETURNED_FOR_SELECTED_DAY",
                "planned_calendar_date": plan["calendar_date"]})
    return result
