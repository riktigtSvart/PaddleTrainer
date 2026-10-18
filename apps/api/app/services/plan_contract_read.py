"""Owner-scoped, stateless plan snapshot exports. No provider or storage writes."""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID

from app.models.entities import PlannedWorkout, WorkoutBlock
from app.planning_contracts import contract_checks
from app.planning_contracts.legacy_plan_adapter import (
    AdapterError, adapt_legacy_workout, adapt_polar_target, canonical_bytes,
    digest, plan_type_routing, verify_result,
)

API_RULES_VERSION = "plan-contract-read-api-0.1-draft1"
MAX_STORED_PLAN_BYTES = 256 * 1024
MAX_PLAN_BLOCKS = 1000
MAX_PLAN_OCCURRENCES = 1000
CAPTURE_KEY = "__paddletrainer_plan_contract_api_capture__"
WORKOUT_FIELDS = (
    "id", "user_id", "training_period_id", "date", "planned_start_time", "sport",
    "title", "description", "duration_sec", "distance_m", "intensity_type", "status",
    "source", "polar_target_id", "raw_data", "created_at", "updated_at",
)
BLOCK_FIELDS = (
    "id", "workout_id", "parent_block_id", "position", "block_type", "name",
    "duration_sec", "distance_m", "intensity_type", "intensity_min", "intensity_max", "repeat_count",
)
CONTRACT_TYPES = (
    "WorkoutPlanContract", "ExecutedWorkout", "SessionFeedback", "PlanExecutionComparison",
    "SpeedModelApplicabilityDecision", "IntegrationBundle",
)


class PlanReadError(ValueError):
    def __init__(self, code, status_code=409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    return copy.deepcopy(value)


def stored_workout_snapshot(row, owner_id):
    if str(row.user_id) != str(owner_id):
        raise PlanReadError("PLAN_CONTRACT_WORKOUT_NOT_FOUND", 404)
    if set(PlannedWorkout.__table__.columns.keys()) != set(WORKOUT_FIELDS) or set(WorkoutBlock.__table__.columns.keys()) != set(BLOCK_FIELDS):
        raise PlanReadError("PLAN_CONTRACT_SOURCE_SCHEMA_CHANGED")
    if len(row.blocks) > MAX_PLAN_BLOCKS:
        raise PlanReadError("PLAN_CONTRACT_SOURCE_BLOCK_LIMIT", 413)
    result = {field: _value(getattr(row, field)) for field in WORKOUT_FIELDS}
    result["blocks"] = []
    for block in sorted(row.blocks, key=lambda b: (b.position, str(b.id))):
        if str(block.workout_id) != str(row.id):
            raise PlanReadError("PLAN_CONTRACT_BLOCK_SOURCE_CONFLICT")
        result["blocks"].append({field: _value(getattr(block, field)) for field in BLOCK_FIELDS})
    try:
        if len(canonical_bytes(result)) > MAX_STORED_PLAN_BYTES:
            raise PlanReadError("PLAN_CONTRACT_SOURCE_BYTE_LIMIT", 413)
    except AdapterError:
        raise PlanReadError("PLAN_CONTRACT_SOURCE_NOT_FINITE_JSON") from None
    return result


def build_plan_read(snapshot, *, captured_at=None):
    """Each server read is a new capture, not a persisted logical plan revision.

    Binding server capture metadata into the adapter input gives fresh evidence
    fresh snapshot IDs. Equal source_content_sha256 still identifies unchanged
    stored content across reads. A saved response is repeat-importable as is.
    """
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    contract_checks.timestamp(captured_at)
    original = copy.deepcopy(snapshot)
    source_hash = digest(original)
    context = {"rules_version": API_RULES_VERSION, "captured_at": captured_at,
               "source_content_sha256": source_hash,
               "scope": "SERVER_CAPTURE_METADATA_NOT_A_PROVIDER_FIELD"}
    capture_id = "capture_" + digest(context)
    source_ref = "api:workouts/" + original["id"] + "/plan-contract#" + capture_id
    source_kind = "STORED_ORM_WORKOUT"
    differences = []
    if original["source"] == "POLAR":
        raw = original["raw_data"]
        if not isinstance(raw, dict) or not isinstance(raw.get("session"), dict) or not isinstance(raw.get("exercise"), list):
            raise PlanReadError("PLAN_CONTRACT_STORED_POLAR_TARGET_MISSING_OR_INVALID")
        if not original["polar_target_id"] or str(raw["session"].get("id")) != str(original["polar_target_id"]):
            raise PlanReadError("PLAN_CONTRACT_STORED_TARGET_ID_CONFLICT")
        source_kind = "STORED_POLAR_TARGET"
        source = copy.deepcopy(raw)
        if source["session"].get("name") != original["title"]:
            differences.append("TITLE")
        local = source["session"].get("startTime", {})
        try:
            source_day = date(local["year"], local["month"], local["day"]).isoformat()
        except (KeyError, ValueError, TypeError):
            source_day = None
        if source_day != original["date"]:
            differences.append("PLANNED_DATE")
        adapter = adapt_polar_target
    else:
        source = copy.deepcopy(original)
        adapter = adapt_legacy_workout
    if CAPTURE_KEY in source:
        raise PlanReadError("PLAN_CONTRACT_CAPTURE_NAMESPACE_CONFLICT")
    source[CAPTURE_KEY] = context
    try:
        result = adapter(source, athlete_id=original["user_id"], collected_at=captured_at,
                         source_ref=source_ref, capture={"capture_id": capture_id,
                         "source_content_sha256": source_hash, "source_kind": source_kind})
        if len(result["expanded_occurrences"]) > MAX_PLAN_OCCURRENCES:
            raise PlanReadError("PLAN_CONTRACT_OCCURRENCE_LIMIT", 413)
        verify_result(result)
        decisions = plan_type_routing(result["plan"])
    except (AdapterError, contract_checks.ContractError, TypeError, KeyError, RecursionError):
        raise PlanReadError("PLAN_CONTRACT_SOURCE_CONVERSION_WITHHELD") from None
    limitations = ["STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION",
                   "HISTORICAL_PLAN_CONTENT_UNVERIFIED", "ACTUAL_EXECUTION_NOT_ASSESSED",
                   "MODEL_NUMERIC_OUTPUT_NOT_AUTHORIZED"]
    if source_kind == "STORED_POLAR_TARGET":
        limitations.append("PROVIDER_SNAPSHOT_DOES_NOT_ESTABLISH_CURRENT_ORM_EDIT_INTENT")
    if differences:
        limitations.append("STORED_ORM_DESCRIPTIVE_FIELDS_DIFFER_FROM_PROVIDER_SNAPSHOT")
    return {"status": "PLAN_CONTRACT_READ_WITH_LIMITATIONS", "api_rules_version": API_RULES_VERSION,
            "schema_version": "0.1", "contract_release": "DRAFT1",
            "identity_scope": "APPLICATION_DEMO_USER", "workout_id": original["id"],
            "capture_id": capture_id, "captured_at": captured_at,
            "source_content_sha256": source_hash, "source_kind": source_kind,
            "source_snapshot": original, "provider_orm_basic_field_differences": differences,
            "source_views_fully_reconciled": False, "adapter_result": result,
            "applicability_decisions": decisions, "limitations": limitations,
            "historical_plan_content_verified": False, "actual_phase_alignment_verified": False,
            "numeric_output_authorized": False, "capability_update_performed": False,
            "database_writes": 0, "provider_calls": 0, "model_trained": False}


def schema_document(contract_type):
    if contract_type not in CONTRACT_TYPES:
        raise PlanReadError("PLAN_CONTRACT_SCHEMA_NOT_FOUND", 404)
    path = Path(contract_checks.__file__).resolve().parent / "schemas/integration-contracts.schema.json"
    common = json.loads(path.read_text(encoding="utf-8"))
    return {"$schema": common["$schema"], "title": contract_type + " 0.1 DRAFT1",
            "$ref": "#/$defs/" + contract_type, "$defs": common["$defs"]}
