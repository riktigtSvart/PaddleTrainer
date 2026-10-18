from datetime import datetime
from typing import Mapping

from ...domain.common.serialization import canonical_json, compute_content_hash
from ...domain.integration.models import finalize_existing_workout_plan_capture


SUPPORTED_API_RULES_VERSION = "plan-contract-read-api-0.1-draft1"
SUPPORTED_CONTRACT_RELEASE = "DRAFT1"
SUPPORTED_PLAN_SCHEMA_VERSION = "0.1"
SUPPORTED_SOURCE_KINDS = frozenset(
    {"STORED_ORM_WORKOUT", "STORED_POLAR_TARGET"}
)


class CurrentAppPlanReadAdapterError(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise CurrentAppPlanReadAdapterError(code)


def _mapping(value, code: str) -> Mapping[str, object]:
    _require(isinstance(value, Mapping), code)
    return value


def _string(value, code: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), code)
    return value


def _bool(value, expected: bool, code: str) -> None:
    _require(value is expected, code)


def _collect_block_ids(blocks) -> tuple[str, ...]:
    _require(isinstance(blocks, list), "PLAN_BLOCKS_NOT_ARRAY")
    out: list[str] = []

    def walk(block) -> None:
        node = _mapping(block, "PLAN_BLOCK_NOT_OBJECT")
        block_id = _string(node.get("block_id"), "PLAN_BLOCK_ID_INVALID")
        out.append(block_id)
        children = node.get("children")
        _require(isinstance(children, list), "PLAN_CHILDREN_NOT_ARRAY")
        for child in children:
            walk(child)
        recovery = node.get("recovery")
        if recovery is not None:
            recovery_obj = _mapping(recovery, "PLAN_RECOVERY_NOT_OBJECT")
            walk(recovery_obj.get("block"))

    for block in blocks:
        walk(block)

    _require(len(out) == len(set(out)), "DUPLICATE_CONTRACT_BLOCK_ID")
    return tuple(out)


def _occurrence_ids(items) -> tuple[str, ...]:
    _require(isinstance(items, list), "EXPANDED_OCCURRENCES_NOT_ARRAY")
    result = tuple(
        _string(
            _mapping(item, "EXPANDED_OCCURRENCE_NOT_OBJECT").get(
                "planned_occurrence_id"
            ),
            "PLANNED_OCCURRENCE_ID_INVALID",
        )
        for item in items
    )
    _require(
        len(result) == len(set(result)),
        "DUPLICATE_PLANNED_OCCURRENCE_ID",
    )
    return result


def adapt_current_app_plan_read(
    read_result: Mapping[str, object],
):
    """Capture the current app's plan-read output without promoting it.

    The adapter is pinned to the inspected DRAFT1 read API. Any semantic
    version change fails closed so a future API cannot silently acquire
    revision or execution authority through this bridge.
    """
    source = _mapping(read_result, "PLAN_READ_NOT_OBJECT")

    _require(
        source.get("status") == "PLAN_CONTRACT_READ_WITH_LIMITATIONS",
        "PLAN_READ_STATUS_NOT_SUPPORTED",
    )
    _require(
        source.get("api_rules_version") == SUPPORTED_API_RULES_VERSION,
        "PLAN_READ_API_RULES_VERSION_CHANGED",
    )
    _require(
        source.get("contract_release") == SUPPORTED_CONTRACT_RELEASE,
        "PLAN_READ_CONTRACT_RELEASE_CHANGED",
    )
    _require(
        source.get("schema_version") == SUPPORTED_PLAN_SCHEMA_VERSION,
        "PLAN_READ_SCHEMA_VERSION_CHANGED",
    )
    _require(
        source.get("source_kind") in SUPPORTED_SOURCE_KINDS,
        "PLAN_READ_SOURCE_KIND_UNSUPPORTED",
    )

    _require(source.get("database_writes") == 0, "SOURCE_READ_PERFORMED_WRITE")
    _require(source.get("provider_calls") == 0, "SOURCE_READ_CALLED_PROVIDER")
    _bool(
        source.get("numeric_output_authorized"),
        False,
        "SOURCE_READ_NUMERIC_AUTHORITY_CHANGED",
    )
    _bool(
        source.get("capability_update_performed"),
        False,
        "SOURCE_READ_CAPABILITY_AUTHORITY_CHANGED",
    )
    _bool(
        source.get("historical_plan_content_verified"),
        False,
        "SOURCE_READ_HISTORICAL_VERIFICATION_CHANGED",
    )
    _bool(
        source.get("actual_phase_alignment_verified"),
        False,
        "SOURCE_READ_PHASE_ALIGNMENT_AUTHORITY_CHANGED",
    )

    workout_id = _string(source.get("workout_id"), "WORKOUT_ID_INVALID")
    capture_id = _string(source.get("capture_id"), "CAPTURE_ID_INVALID")
    captured_at_raw = _string(source.get("captured_at"), "CAPTURED_AT_INVALID")
    try:
        captured_at = datetime.fromisoformat(
            captured_at_raw.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise CurrentAppPlanReadAdapterError("CAPTURED_AT_INVALID") from exc
    _require(
        captured_at.tzinfo is not None and captured_at.utcoffset() is not None,
        "CAPTURED_AT_REQUIRES_OFFSET",
    )

    source_snapshot = _mapping(
        source.get("source_snapshot"),
        "SOURCE_SNAPSHOT_NOT_OBJECT",
    )
    _require(
        source_snapshot.get("id") == workout_id,
        "SOURCE_SNAPSHOT_WORKOUT_ID_MISMATCH",
    )
    athlete_id = _string(
        source_snapshot.get("user_id"),
        "SOURCE_SNAPSHOT_ATHLETE_ID_INVALID",
    )

    adapter_result = _mapping(
        source.get("adapter_result"),
        "ADAPTER_RESULT_NOT_OBJECT",
    )
    _require(
        adapter_result.get("historical_plan_content_status") == "UNVERIFIED",
        "ADAPTER_HISTORICAL_STATUS_CHANGED",
    )
    _bool(
        adapter_result.get("execution_inferred"),
        False,
        "ADAPTER_EXECUTION_INFERENCE_CHANGED",
    )

    plan = _mapping(adapter_result.get("plan"), "PLAN_NOT_OBJECT")
    _require(
        plan.get("contract_type") == "WorkoutPlanContract",
        "PLAN_CONTRACT_TYPE_CHANGED",
    )
    _require(
        plan.get("schema_version") == SUPPORTED_PLAN_SCHEMA_VERSION,
        "PLAN_CONTRACT_SCHEMA_VERSION_CHANGED",
    )
    _require(
        plan.get("athlete_id") == athlete_id,
        "PLAN_ATHLETE_ID_MISMATCH",
    )
    external_plan_id = _string(
        plan.get("plan_id"),
        "EXTERNAL_PLAN_ID_INVALID",
    )
    external_revision = plan.get("plan_revision")
    _require(
        isinstance(external_revision, int)
        and not isinstance(external_revision, bool)
        and external_revision >= 1,
        "EXTERNAL_PLAN_REVISION_INVALID",
    )

    block_ids = _collect_block_ids(plan.get("blocks"))
    occurrence_ids = _occurrence_ids(
        adapter_result.get("expanded_occurrences")
    )

    limitations = source.get("limitations")
    _require(isinstance(limitations, list), "SOURCE_LIMITATIONS_NOT_ARRAY")
    limitation_strings = tuple(
        _string(item, "SOURCE_LIMITATION_INVALID") for item in limitations
    )
    _require(
        "STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION"
        in limitation_strings,
        "PERSISTED_REVISION_LIMITATION_MISSING",
    )
    _require(
        "HISTORICAL_PLAN_CONTENT_UNVERIFIED" in limitation_strings,
        "HISTORICAL_PLAN_LIMITATION_MISSING",
    )

    differences = source.get("provider_orm_basic_field_differences")
    _require(
        isinstance(differences, list),
        "PROVIDER_ORM_DIFFERENCES_NOT_ARRAY",
    )
    difference_strings = tuple(
        _string(item, "PROVIDER_ORM_DIFFERENCE_INVALID")
        for item in differences
    )

    source_read_json = canonical_json(source)
    source_read_hash = compute_content_hash(
        source,
        exclude_fields=frozenset(),
    )
    plan_hash = compute_content_hash(
        plan,
        exclude_fields=frozenset(),
    )

    return finalize_existing_workout_plan_capture(
        api_rules_version=SUPPORTED_API_RULES_VERSION,
        contract_release=SUPPORTED_CONTRACT_RELEASE,
        capture_id=capture_id,
        captured_at=captured_at,
        source_workout_id=workout_id,
        athlete_id=athlete_id,
        source_kind=_string(source.get("source_kind"), "SOURCE_KIND_INVALID"),
        source_content_sha256=_string(
            source.get("source_content_sha256"),
            "SOURCE_CONTENT_SHA256_INVALID",
        ),
        planning_logical_plan_id=f"planned-workout:{workout_id}",
        external_contract_plan_id=external_plan_id,
        external_contract_plan_revision=external_revision,
        external_contract_schema_version=SUPPORTED_PLAN_SCHEMA_VERSION,
        external_plan_content_hash=plan_hash,
        external_contract_snapshot_sha256=_string(
            adapter_result.get("contract_snapshot_sha256"),
            "CONTRACT_SNAPSHOT_SHA256_INVALID",
        ),
        external_adapter_version=_string(
            adapter_result.get("adapter_version"),
            "EXTERNAL_ADAPTER_VERSION_INVALID",
        ),
        contract_block_ids=block_ids,
        external_occurrence_ids=occurrence_ids,
        source_limitations=limitation_strings,
        provider_orm_basic_field_differences=difference_strings,
        source_read_json=source_read_json,
        source_read_content_hash=source_read_hash,
    )


async def capture_current_app_plan(
    session,
    *,
    source_workout_id: str,
    athlete_id: str,
    captured_at: datetime | None = None,
):
    """Read one owner-scoped current plan through the existing DRAFT1 service.

    This performs no writes and no provider calls. The returned object remains a
    capture/evidence boundary until an explicit adoption service call succeeds.
    """
    from uuid import UUID

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.entities import PlannedWorkout
    from app.services.plan_contract_read import (
        PlanReadError,
        build_plan_read,
        stored_workout_snapshot,
    )

    try:
        workout_uuid = UUID(source_workout_id)
        athlete_uuid = UUID(athlete_id)
    except ValueError as exc:
        raise ValueError("source_workout_id and athlete_id must be UUID strings.") from exc

    with session.no_autoflush:
        row = await session.scalar(
            select(PlannedWorkout)
            .options(selectinload(PlannedWorkout.blocks))
            .where(
                PlannedWorkout.id == workout_uuid,
                PlannedWorkout.user_id == athlete_uuid,
            )
        )
    if row is None:
        raise PlanReadError("PLAN_CONTRACT_WORKOUT_NOT_FOUND", 404)

    snapshot = stored_workout_snapshot(row, athlete_uuid)
    captured_value = None
    if captured_at is not None:
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("captured_at must be offset-aware.")
        captured_value = captured_at.isoformat()
    read_result = build_plan_read(snapshot, captured_at=captured_value)
    return adapt_current_app_plan_read(read_result)
