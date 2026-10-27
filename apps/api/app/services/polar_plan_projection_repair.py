"""Explicit append-only repair of an empty, report-pinned Polar block projection."""
from copy import deepcopy
from datetime import date, datetime
from enum import Enum
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.models.entities import BlockType, PlannedWorkout, User, WorkoutBlock
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningLogicalPlanRow
from app.services.polar_target_structure import TargetStructureError, native_id, phase_structure, same_blocks
from app.services.polar_targets import normalize_phase_tree
from app.services.provider_payload_archive import archive_payload

CATEGORY = "DATA_SYNC_PLAN_PROJECTION_REPAIR"


class ProjectionRepairError(ValueError):
    pass


def require(value, code):
    if not value:
        raise ProjectionRepairError(code)


def value(item):
    if isinstance(item, Enum): return item.value
    if isinstance(item, UUID): return str(item)
    if isinstance(item, (date, datetime)): return item.isoformat()
    if isinstance(item, dict): return {k: value(v) for k, v in item.items()}
    if isinstance(item, list): return [value(v) for v in item]
    return item


def digest(item):
    encoded = json.dumps(value(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= 4 * 1024 * 1024, "PROJECTION_SOURCE_TOO_LARGE")
    return hashlib.sha256(encoded).hexdigest()


def no_omissions(item):
    if isinstance(item, dict):
        return not any(k.startswith("diagnostic_") for k in item) and all(no_omissions(v) for v in item.values())
    if isinstance(item, list): return all(no_omissions(v) for v in item)
    return True


def complete(raw):
    try:
        return phase_structure(raw) == "complete"
    except TargetStructureError:
        return False


def expected_source(report, plan_id=None):
    require(isinstance(report, dict) and report.get("schema_version") == "polar-phase-import-diagnostic-v1", "PROJECTION_REPORT_INVALID")
    owner = str(UUID(report["athlete_id"]))
    plans = report.get("plans")
    require(isinstance(plans, list), "PROJECTION_REPORT_INVALID")
    selected = [p for p in plans if isinstance(p, dict) and (plan_id is None or p.get("id") == str(UUID(plan_id)))]
    require(len(selected) == 1, "PROJECTION_SELECT_ONE_PLAN")
    plan = selected[0]
    identity = str(UUID(plan["id"]))
    require(plan.get("source") == "POLAR" and native_id(plan.get("native_target_id")) is not None, "PROJECTION_REPORT_IDENTITY_INVALID")
    require(plan.get("blocks") == [], "PROJECTION_REPORT_NOT_EMPTY")
    stored = plan.get("stored")
    require(isinstance(stored, dict) and stored.get("native_target_id") == plan["native_target_id"] and stored.get("structure") == "complete", "PROJECTION_REPORT_SOURCE_INVALID")
    require(type(stored.get("exercise_count")) is int and stored["exercise_count"] == 1, "PROJECTION_SINGLE_EXERCISE_REQUIRED")
    fields = stored.get("phase_fields")
    require(isinstance(fields, dict) and fields.get("scan_truncated") is False, "PROJECTION_REPORT_INCOMPLETE")
    source = [f["value"] for f in fields.get("fields", []) if isinstance(f, dict) and f.get("path") == "$.exercise[0].phaseOrRepeat" and "value" in f]
    require(len(source) == 1 and no_omissions(source[0]), "PROJECTION_REPORT_INCOMPLETE")
    phases = deepcopy(source[0])
    require(complete({"exercise": [{"phaseOrRepeat": phases}]}), "PROJECTION_SOURCE_INVALID")
    day = date.fromisoformat(plan["calendar_date"]).isoformat()
    return {"athlete_id": owner, "plan_id": identity, "native_target_id": plan["native_target_id"],
            "calendar_date": day, "status": plan["status"], "source": "POLAR", "phases": phases}


def current_source(plan):
    raw = plan.raw_data
    session = raw.get("session") if isinstance(raw, dict) else None
    exercises = raw.get("exercise") if isinstance(raw, dict) else None
    require(plan.source == "POLAR" and isinstance(session, dict) and native_id(session.get("id")) == plan.polar_target_id,
            "PROJECTION_NATIVE_IDENTITY_CHANGED")
    require(isinstance(exercises, list) and len(exercises) == 1 and isinstance(exercises[0], dict), "PROJECTION_SINGLE_EXERCISE_REQUIRED")
    require(complete(raw), "PROJECTION_SOURCE_INVALID")
    return {"athlete_id": str(plan.user_id), "plan_id": str(plan.id), "native_target_id": plan.polar_target_id,
            "calendar_date": plan.date.isoformat(), "status": plan.status.value, "source": plan.source,
            "phases": deepcopy(exercises[0].get("phaseOrRepeat"))}


def planned_fields(plan):
    return {c.name: value(getattr(plan, c.name)) for c in PlannedWorkout.__table__.columns}


def normalized(phases):
    result = normalize_phase_tree(phases)
    for b in result:
        b["key"] = "e0:" + b["key"]
        if b["parent_key"] is not None: b["parent_key"] = "e0:" + b["parent_key"]
    return result


async def repair(db, *, owner, expected, apply=False):
    require(not db.in_transaction(), "PROJECTION_FRESH_SESSION_REQUIRED")
    require(str(owner) == expected["athlete_id"], "PROJECTION_OWNER_MISMATCH")
    try:
        if not apply and db.get_bind().dialect.name == "postgresql":
            await db.execute(text("SET TRANSACTION READ ONLY"))
        user_query = select(User).where(User.id == UUID(owner))
        user = (await db.execute(user_query.with_for_update() if apply else user_query)).scalar_one_or_none()
        require(user is not None, "PROJECTION_OWNER_NOT_FOUND")
        query = select(PlannedWorkout).where(PlannedWorkout.id == UUID(expected["plan_id"]), PlannedWorkout.user_id == user.id)
        plan = (await db.execute(query.with_for_update() if apply else query)).scalar_one_or_none()
        require(plan is not None, "PROJECTION_PLAN_NOT_FOUND")
        contract = current_source(plan)
        require(digest(contract) == digest(expected), "PROJECTION_SOURCE_CHANGED_SINCE_REPORT")
        before = planned_fields(plan)
        source_hash = digest(before)
        blocks = (await db.execute(select(WorkoutBlock).where(WorkoutBlock.workout_id == plan.id).order_by(WorkoutBlock.position))).scalars().all()
        wanted = normalized(contract["phases"])
        require(wanted, "PROJECTION_SOURCE_INVALID")
        protected = (await db.execute(select(PlanningLogicalPlanRow.logical_plan_id).where(
            PlanningLogicalPlanRow.source_workout_id == plan.id).limit(1))).first() is not None
        equal = same_blocks(blocks, wanted)
        reason = "PROJECTION_NOT_EMPTY" if blocks and not equal else "PROJECTION_PLANNING_OWNED" if protected and not equal else None
        result = {"schema_version": "polar-plan-projection-repair-v1", "athlete_id": str(owner), "plan_id": str(plan.id),
            "native_target_id": plan.polar_target_id, "source_contract_sha256": digest(contract),
            "planned_row_sha256": source_hash, "existing_block_count": len(blocks), "proposed_block_count": len(wanted),
            "eligible": reason is None, "blocked_reason": reason, "state": "already_repaired" if equal else "preview",
            "committed": False, "measurement_changed": False, "native_source_changed": False,
            "proposed_blocks": wanted}
        if equal or not apply:
            return result
        require(reason is None, reason)
        # This path only INSERTs blocks. It never calls the replacing/deleting importer.
        require(not blocks, "PROJECTION_NOT_EMPTY")
        ids = {b["key"]: uuid4() for b in wanted}
        for index, item in enumerate(wanted):
            parent = item["parent_key"]
            require(parent is None or parent in ids, "PROJECTION_PARENT_INVALID")
            db.add(WorkoutBlock(id=ids[item["key"]], workout_id=plan.id,
                parent_block_id=ids[parent] if parent is not None else None,
                position=index, block_type=BlockType(item["block_type"]),
                **{k: item[k] for k in ("name", "duration_sec", "distance_m", "intensity_type", "intensity_min", "intensity_max", "repeat_count")}))
        await db.flush()
        stored = (await db.execute(select(WorkoutBlock).where(WorkoutBlock.workout_id == plan.id).order_by(WorkoutBlock.position))).scalars().all()
        refreshed = (await db.execute(select(PlannedWorkout).where(PlannedWorkout.id == plan.id,
            PlannedWorkout.user_id == user.id).execution_options(populate_existing=True))).scalar_one()
        require(same_blocks(stored, wanted) and digest(planned_fields(refreshed)) == source_hash, "PROJECTION_POSTWRITE_MISMATCH")
        result.update(state="repaired", existing_block_count=0, committed=True)
        receipt = {**result, "before_blocks": [], "inserted_block_ids": [str(b.id) for b in stored]}
        await archive_payload(db, user, CATEGORY, receipt)
        try:
            await db.commit()
        except Exception as exc:
            raise ProjectionRepairError("PROJECTION_COMMIT_OUTCOME_UNKNOWN") from exc
        return receipt
    finally:
        await db.rollback()
