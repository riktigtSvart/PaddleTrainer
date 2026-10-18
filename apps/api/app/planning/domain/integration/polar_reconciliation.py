from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from .models import ExistingWorkoutPlanCapture


POLAR_RECONCILIATION_SCHEMA_VERSION = "0.2"
POLAR_RECONCILIATION_RULES_VERSION = "polar-source-reconciliation-0.2"
POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})


class PolarReconciliationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SYNC_PROJECTION_MATCH = "sync_projection_match"
    MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION = (
        "material_difference_requires_clarification"
    )
    INSUFFICIENT_PROVIDER_EVIDENCE = "insufficient_provider_evidence"
    UNSUPPORTED_OR_AMBIGUOUS_STRUCTURE = "unsupported_or_ambiguous_structure"


class PolarReconciliationMateriality(StrEnum):
    MATERIAL = "material"
    NON_SEMANTIC = "non_semantic"
    UNKNOWN = "unknown"


class FutureBaselineAdoptionSupport(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SUPPORTED_BY_RECONCILIATION = "supported_by_reconciliation"
    CLARIFICATION_REQUIRED = "clarification_required"
    NOT_SUPPORTED = "not_supported"


@dataclass(frozen=True)
class PolarReconciliationDifference:
    field_path: str
    code: str
    materiality: PolarReconciliationMateriality
    expected_value: object
    actual_value: object


@dataclass(frozen=True)
class PolarSourceReconciliationArtifact:
    schema_version: str
    rules_version: str
    capture_id: str
    captured_at: datetime
    logical_plan_id: str
    athlete_id: str
    source_workout_id: str
    source_content_sha256: str
    source_read_content_hash: str
    external_contract_plan_id: str
    external_contract_plan_revision: int
    timezone_context_name: str | None
    timezone_context_source: str | None
    status: PolarReconciliationStatus
    future_baseline_adoption_support: FutureBaselineAdoptionSupport
    semantic_equivalence_claimed: bool
    current_orm_edit_detected: bool | None
    provider_snapshot_selected_as_future_authority_candidate: bool
    adoption_gate_integrated: bool
    compared_fields: tuple[str, ...]
    differences: tuple[PolarReconciliationDifference, ...]
    normalization_notes: tuple[str, ...]
    excluded_fields: tuple[str, ...]
    blockers: tuple[str, ...]
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


class PolarSourceReconciliationError(ValueError):
    pass


class _UnsupportedPolarStructure(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise _UnsupportedPolarStructure(code)


def _mapping(value: object, code: str) -> Mapping[str, object]:
    _require(isinstance(value, Mapping), code)
    return value


def _integer_seconds_from_ms(value: object) -> int | None:
    if value is None:
        return None
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        "POLAR_DURATION_NOT_NUMERIC",
    )
    return int(value / 1000)


def _polar_sport(value: object) -> str:
    code = str(value)
    return {"95": "KAYAK", "1": "RUNNING"}.get(code, "OTHER")


def _derived_block_type(name: object) -> str:
    text = (name or "").strip().lower() if isinstance(name, str) else ""
    if "warm up" in text or "warmup" in text:
        return "WARMUP"
    if "cool down" in text or "cooldown" in text:
        return "COOLDOWN"
    if "recovery" in text or "rest" in text:
        return "RECOVERY"
    return "WORK"


def _normalize_phase_tree(
    phases: object,
    *,
    parent_key: str | None = None,
) -> list[dict[str, object]]:
    _require(isinstance(phases, list), "POLAR_PHASES_NOT_ARRAY")
    result: list[dict[str, object]] = []
    for index, phase_value in enumerate(phases):
        phase = _mapping(phase_value, "POLAR_PHASE_NOT_OBJECT")
        key = f"{parent_key}.{index}" if parent_key is not None else str(index)
        children = phase.get("phaseOrRepeat") or []
        _require(isinstance(children, list), "POLAR_PHASE_CHILDREN_NOT_ARRAY")
        repeat_count = phase.get("repeatCount")
        if children:
            if repeat_count is None:
                repeat_count = 1
            _require(
                isinstance(repeat_count, int)
                and not isinstance(repeat_count, bool)
                and repeat_count >= 1,
                "POLAR_REPEAT_COUNT_INVALID",
            )
            result.append(
                {
                    "key": key,
                    "parent_key": parent_key,
                    "block_type": "REPEAT",
                    "name": phase.get("name") or None,
                    "duration_sec": None,
                    "distance_m": None,
                    "intensity_type": None,
                    "intensity_min": None,
                    "intensity_max": None,
                    "repeat_count": repeat_count,
                }
            )
            result.extend(_normalize_phase_tree(children, parent_key=key))
            continue

        goal = phase.get("goal") or {}
        intensity = phase.get("intensity") or {}
        _require(isinstance(goal, Mapping), "POLAR_GOAL_NOT_OBJECT")
        _require(isinstance(intensity, Mapping), "POLAR_INTENSITY_NOT_OBJECT")
        goal_type = goal.get("type")
        duration_sec = None
        distance_m = None
        if goal_type == "DURATION":
            duration_sec = _integer_seconds_from_ms(goal.get("duration"))
        elif goal_type == "DISTANCE":
            distance_m = goal.get("distance")
        else:
            _require(goal_type is None, "POLAR_GOAL_TYPE_UNSUPPORTED")

        name = phase.get("name") or None
        result.append(
            {
                "key": key,
                "parent_key": parent_key,
                "block_type": _derived_block_type(name),
                "name": name,
                "duration_sec": duration_sec,
                "distance_m": distance_m,
                "intensity_type": intensity.get("type"),
                "intensity_min": intensity.get("lowerZone"),
                "intensity_max": intensity.get("upperZone"),
                "repeat_count": 1,
            }
        )
    return result


def _provider_projection(
    raw: Mapping[str, object],
    *,
    athlete_timezone: str,
) -> tuple[dict[str, object], tuple[str, ...]]:
    session = _mapping(raw.get("session"), "POLAR_SESSION_NOT_OBJECT")
    exercises = raw.get("exercise")
    _require(isinstance(exercises, list), "POLAR_EXERCISE_NOT_ARRAY")
    _require(bool(exercises), "POLAR_EXERCISE_EMPTY")
    _require(all(isinstance(item, Mapping) for item in exercises), "POLAR_EXERCISE_ITEM_NOT_OBJECT")

    target_id = session.get("id")
    _require(target_id is not None, "POLAR_TARGET_ID_MISSING")
    start = _mapping(session.get("startTime"), "POLAR_START_TIME_NOT_OBJECT")
    try:
        local_dt = datetime(
            int(start["year"]),
            int(start["month"]),
            int(start["day"]),
            int(start.get("hour", 0)),
            int(start.get("min", 0)),
            int(start.get("sec", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _UnsupportedPolarStructure("POLAR_START_TIME_INVALID") from exc

    try:
        athlete_zone = ZoneInfo(athlete_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise _UnsupportedPolarStructure("ATHLETE_TIMEZONE_INVALID") from exc

    planned_start_utc = (
        local_dt.replace(tzinfo=athlete_zone)
        .astimezone(timezone.utc)
        .isoformat(timespec="seconds")
    )

    sports = {str(item.get("sportId")) for item in exercises}
    _require(len(sports) == 1, "POLAR_MULTI_SPORT_TARGET_UNSUPPORTED")
    first_exercise = exercises[0]

    normalized: list[dict[str, object]] = []
    normalization_notes: list[str] = [
        "ORM_BLOCK_IDS_ARE_EPHEMERAL_AND_EXCLUDED",
        "WORKOUT_STATUS_IS_OPERATIONAL_AND_EXCLUDED",
        "CREATED_UPDATED_TIMESTAMPS_EXCLUDED",
        "PROVIDER_LOCAL_TIME_OFFSET_NOT_PRESENT_IN_STORED_TARGET",
        "CURRENT_USER_PROFILE_TIMEZONE_USED_FOR_CURRENT_STATE_RECONCILIATION",
        "CURRENT_PROFILE_TIMEZONE_DOES_NOT_PROVE_HISTORICAL_SYNC_TIMEZONE",
        "PLANNED_START_TIME_COMPARED_AS_UTC_INSTANT_AFTER_CURRENT_PROFILE_TIMEZONE_MAPPING",
    ]
    all_intensity_types: set[object] = set()
    saw_fractional_duration = False
    saw_change_type = False
    saw_phase_wrapper = False

    for exercise_index, exercise_value in enumerate(exercises):
        exercise = _mapping(exercise_value, "POLAR_EXERCISE_ITEM_NOT_OBJECT")
        phases = exercise.get("phaseOrRepeat") or []
        _require(isinstance(phases, list), "POLAR_EXERCISE_PHASES_NOT_ARRAY")
        if phases:
            saw_phase_wrapper = True
        blocks = _normalize_phase_tree(phases)
        prefix = f"e{exercise_index}:"
        for block in blocks:
            copied = dict(block)
            copied["key"] = prefix + str(copied["key"])
            if copied["parent_key"] is not None:
                copied["parent_key"] = prefix + str(copied["parent_key"])
            normalized.append(copied)
            if copied["intensity_type"] is not None:
                all_intensity_types.add(copied["intensity_type"])

        duration = exercise.get("duration")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            saw_fractional_duration = saw_fractional_duration or (duration % 1000 != 0)

        def walk_phases(items: list[object]) -> None:
            nonlocal saw_fractional_duration, saw_change_type
            for phase_value in items:
                phase = _mapping(phase_value, "POLAR_PHASE_NOT_OBJECT")
                if "changeType" in phase:
                    saw_change_type = True
                goal = phase.get("goal") or {}
                if isinstance(goal, Mapping):
                    duration_value = goal.get("duration")
                    if isinstance(duration_value, (int, float)) and not isinstance(duration_value, bool):
                        saw_fractional_duration = saw_fractional_duration or (duration_value % 1000 != 0)
                children = phase.get("phaseOrRepeat") or []
                _require(isinstance(children, list), "POLAR_PHASE_CHILDREN_NOT_ARRAY")
                walk_phases(children)

        walk_phases(phases)

    if saw_fractional_duration:
        normalization_notes.append("POLAR_DURATION_MILLISECONDS_TRUNCATED_TO_INTEGER_SECONDS_IN_ORM")
    if saw_change_type:
        normalization_notes.append("POLAR_PHASE_CHANGE_TYPE_NOT_PERSISTED_IN_ORM_COLUMNS")
    if saw_phase_wrapper:
        normalization_notes.append("POLAR_EXERCISE_WRAPPER_NOT_PERSISTED_AS_ORM_BLOCK")
    if normalized:
        normalization_notes.append("ORM_BLOCK_TYPE_IS_DERIVED_FROM_PHASE_NAME")

    key_to_ordinal = {str(block["key"]): index for index, block in enumerate(normalized)}
    expected_blocks: list[dict[str, object]] = []
    for flat_position, block in enumerate(normalized):
        parent_key = block["parent_key"]
        expected_blocks.append(
            {
                "parent_ordinal": None if parent_key is None else key_to_ordinal.get(str(parent_key)),
                "position": flat_position,
                "block_type": block["block_type"],
                "name": block["name"],
                "duration_sec": block["duration_sec"],
                "distance_m": block["distance_m"],
                "intensity_type": block["intensity_type"],
                "intensity_min": block["intensity_min"],
                "intensity_max": block["intensity_max"],
                "repeat_count": block["repeat_count"],
            }
        )

    if len(all_intensity_types) == 1:
        workout_intensity_type = next(iter(all_intensity_types))
    elif len(all_intensity_types) > 1:
        workout_intensity_type = "MIXED"
    else:
        workout_intensity_type = None

    projection = {
        "polar_target_id": str(target_id),
        "date": local_dt.date().isoformat(),
        "planned_start_utc": planned_start_utc,
        "sport": _polar_sport(first_exercise.get("sportId")),
        "title": session.get("name"),
        "description": session.get("description"),
        "duration_sec": _integer_seconds_from_ms(first_exercise.get("duration")),
        "distance_m": first_exercise.get("distance"),
        "intensity_type": workout_intensity_type,
        "source": "POLAR",
        "blocks": expected_blocks,
    }
    return projection, tuple(normalization_notes)


def _actual_projection(snapshot: Mapping[str, object]) -> dict[str, object]:
    blocks_value = snapshot.get("blocks")
    _require(isinstance(blocks_value, list), "ORM_BLOCKS_NOT_ARRAY")
    blocks = sorted(
        (_mapping(item, "ORM_BLOCK_NOT_OBJECT") for item in blocks_value),
        key=lambda item: (item.get("position"), str(item.get("id"))),
    )
    id_to_ordinal = {str(block.get("id")): index for index, block in enumerate(blocks)}
    actual_blocks: list[dict[str, object]] = []
    for block in blocks:
        parent = block.get("parent_block_id")
        parent_ordinal = None if parent is None else id_to_ordinal.get(str(parent), "UNRESOLVED_PARENT")
        actual_blocks.append(
            {
                "parent_ordinal": parent_ordinal,
                "position": block.get("position"),
                "block_type": block.get("block_type"),
                "name": block.get("name"),
                "duration_sec": block.get("duration_sec"),
                "distance_m": block.get("distance_m"),
                "intensity_type": block.get("intensity_type"),
                "intensity_min": block.get("intensity_min"),
                "intensity_max": block.get("intensity_max"),
                "repeat_count": block.get("repeat_count"),
            }
        )

    planned_start = snapshot.get("planned_start_time")
    planned_start_utc = None
    if isinstance(planned_start, str) and planned_start:
        try:
            parsed = datetime.fromisoformat(planned_start.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _UnsupportedPolarStructure("ORM_PLANNED_START_TIME_INVALID") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise _UnsupportedPolarStructure("ORM_PLANNED_START_TIME_OFFSET_MISSING")
        planned_start_utc = (
            parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        )

    return {
        "polar_target_id": snapshot.get("polar_target_id"),
        "date": snapshot.get("date"),
        "planned_start_utc": planned_start_utc,
        "sport": snapshot.get("sport"),
        "title": snapshot.get("title"),
        "description": snapshot.get("description"),
        "duration_sec": snapshot.get("duration_sec"),
        "distance_m": snapshot.get("distance_m"),
        "intensity_type": snapshot.get("intensity_type"),
        "source": snapshot.get("source"),
        "blocks": actual_blocks,
    }


def _compare(expected: dict[str, object], actual: dict[str, object]) -> tuple[tuple[str, ...], tuple[PolarReconciliationDifference, ...]]:
    compared: list[str] = []
    differences: list[PolarReconciliationDifference] = []

    for field in (
        "polar_target_id",
        "date",
        "planned_start_utc",
        "sport",
        "title",
        "description",
        "duration_sec",
        "distance_m",
        "intensity_type",
        "source",
    ):
        path = "/" + field
        compared.append(path)
        if expected.get(field) != actual.get(field):
            differences.append(
                PolarReconciliationDifference(
                    field_path=path,
                    code="ORM_FIELD_DIFFERS_FROM_POLAR_SYNC_PROJECTION",
                    materiality=PolarReconciliationMateriality.MATERIAL,
                    expected_value=expected.get(field),
                    actual_value=actual.get(field),
                )
            )

    expected_blocks = expected.get("blocks")
    actual_blocks = actual.get("blocks")
    _require(isinstance(expected_blocks, list), "EXPECTED_BLOCKS_NOT_ARRAY")
    _require(isinstance(actual_blocks, list), "ACTUAL_BLOCKS_NOT_ARRAY")
    compared.append("/blocks/count")
    if len(expected_blocks) != len(actual_blocks):
        differences.append(
            PolarReconciliationDifference(
                field_path="/blocks/count",
                code="ORM_BLOCK_COUNT_DIFFERS_FROM_POLAR_SYNC_PROJECTION",
                materiality=PolarReconciliationMateriality.MATERIAL,
                expected_value=len(expected_blocks),
                actual_value=len(actual_blocks),
            )
        )

    fields = (
        "parent_ordinal",
        "position",
        "block_type",
        "name",
        "duration_sec",
        "distance_m",
        "intensity_type",
        "intensity_min",
        "intensity_max",
        "repeat_count",
    )
    for index in range(min(len(expected_blocks), len(actual_blocks))):
        expected_block = expected_blocks[index]
        actual_block = actual_blocks[index]
        _require(isinstance(expected_block, Mapping), "EXPECTED_BLOCK_NOT_OBJECT")
        _require(isinstance(actual_block, Mapping), "ACTUAL_BLOCK_NOT_OBJECT")
        for field in fields:
            path = f"/blocks/{index}/{field}"
            compared.append(path)
            if expected_block.get(field) != actual_block.get(field):
                differences.append(
                    PolarReconciliationDifference(
                        field_path=path,
                        code="ORM_BLOCK_FIELD_DIFFERS_FROM_POLAR_SYNC_PROJECTION",
                        materiality=PolarReconciliationMateriality.MATERIAL,
                        expected_value=expected_block.get(field),
                        actual_value=actual_block.get(field),
                    )
                )
    return tuple(compared), tuple(differences)


def _finalize(
    *,
    capture: ExistingWorkoutPlanCapture,
    status: PolarReconciliationStatus,
    future_support: FutureBaselineAdoptionSupport,
    current_orm_edit_detected: bool | None,
    provider_candidate: bool,
    compared_fields: tuple[str, ...],
    differences: tuple[PolarReconciliationDifference, ...],
    normalization_notes: tuple[str, ...],
    blockers: tuple[str, ...],
    timezone_context_name: str | None = None,
    timezone_context_source: str | None = None,
) -> PolarSourceReconciliationArtifact:
    provisional = PolarSourceReconciliationArtifact(
        schema_version=POLAR_RECONCILIATION_SCHEMA_VERSION,
        rules_version=POLAR_RECONCILIATION_RULES_VERSION,
        capture_id=capture.capture_id,
        captured_at=capture.captured_at,
        logical_plan_id=capture.planning_logical_plan_id,
        athlete_id=capture.athlete_id,
        source_workout_id=capture.source_workout_id,
        source_content_sha256=capture.source_content_sha256,
        source_read_content_hash=capture.source_read_content_hash,
        external_contract_plan_id=capture.external_contract_plan_id,
        external_contract_plan_revision=capture.external_contract_plan_revision,
        timezone_context_name=timezone_context_name,
        timezone_context_source=timezone_context_source,
        status=status,
        future_baseline_adoption_support=future_support,
        semantic_equivalence_claimed=False,
        current_orm_edit_detected=current_orm_edit_detected,
        provider_snapshot_selected_as_future_authority_candidate=provider_candidate,
        adoption_gate_integrated=False,
        compared_fields=compared_fields,
        differences=differences,
        normalization_notes=normalization_notes,
        excluded_fields=(
            "/status",
            "/training_period_id",
            "/created_at",
            "/updated_at",
            "/blocks/*/id",
            "/blocks/*/workout_id",
        ),
        blockers=blockers,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=POLAR_RECONCILIATION_HASH_EXCLUDE_FIELDS,
    )
    return PolarSourceReconciliationArtifact(
        **{**provisional.__dict__, "content_hash": digest}
    )


def reconcile_polar_source_capture(
    capture: ExistingWorkoutPlanCapture,
    *,
    athlete_timezone: str | None = None,
) -> PolarSourceReconciliationArtifact:
    """Compare current ORM plan fields with the deterministic Polar sync projection.

    This is intentionally a read-only reconciliation artifact. A projection
    match means that the persisted ORM fields equal what the current known
    Polar sync mapping would derive from the stored provider snapshot. It does
    *not* claim full semantic equivalence, historical continuity, or adoption
    authority. Provider-only semantics remain in the stored raw snapshot and
    the external plan contract.
    """
    if not capture.verify_content_hash():
        raise PolarSourceReconciliationError("CAPTURE_CONTENT_HASH_INVALID")
    if not capture.verify_source_read_hash():
        raise PolarSourceReconciliationError("SOURCE_READ_CONTENT_HASH_INVALID")

    if capture.source_kind != "STORED_POLAR_TARGET":
        return _finalize(
            capture=capture,
            status=PolarReconciliationStatus.NOT_APPLICABLE,
            future_support=FutureBaselineAdoptionSupport.NOT_APPLICABLE,
            current_orm_edit_detected=None,
            provider_candidate=False,
            compared_fields=(),
            differences=(),
            normalization_notes=(),
            blockers=("SOURCE_KIND_IS_NOT_STORED_POLAR_TARGET",),
        )

    if not athlete_timezone:
        return _finalize(
            capture=capture,
            status=PolarReconciliationStatus.UNSUPPORTED_OR_AMBIGUOUS_STRUCTURE,
            future_support=FutureBaselineAdoptionSupport.NOT_SUPPORTED,
            current_orm_edit_detected=None,
            provider_candidate=False,
            compared_fields=(),
            differences=(),
            normalization_notes=(
                "PROVIDER_LOCAL_TIME_OFFSET_NOT_PRESENT_IN_STORED_TARGET",
            ),
            blockers=("ATHLETE_TIMEZONE_CONTEXT_REQUIRED",),
        )

    try:
        source_read = json.loads(capture.source_read_json)
        source_snapshot = _mapping(
            source_read.get("source_snapshot"),
            "SOURCE_SNAPSHOT_NOT_OBJECT",
        )
        _require(
            str(source_snapshot.get("id")) == capture.source_workout_id,
            "SOURCE_WORKOUT_ID_MISMATCH",
        )
        _require(
            str(source_snapshot.get("user_id")) == capture.athlete_id,
            "SOURCE_ATHLETE_ID_MISMATCH",
        )
        raw = _mapping(source_snapshot.get("raw_data"), "POLAR_RAW_DATA_NOT_OBJECT")
        expected, notes = _provider_projection(
            raw, athlete_timezone=athlete_timezone
        )
        actual = _actual_projection(source_snapshot)
        compared, differences = _compare(expected, actual)
    except (_UnsupportedPolarStructure, KeyError, TypeError, ValueError) as exc:
        code = str(exc) or "POLAR_SOURCE_RECONCILIATION_INPUT_INVALID"
        insufficient_codes = {
            "SOURCE_SNAPSHOT_NOT_OBJECT",
            "POLAR_RAW_DATA_NOT_OBJECT",
            "POLAR_SESSION_NOT_OBJECT",
            "POLAR_EXERCISE_NOT_ARRAY",
            "POLAR_EXERCISE_EMPTY",
            "POLAR_TARGET_ID_MISSING",
            "POLAR_START_TIME_NOT_OBJECT",
        }
        insufficient = code in insufficient_codes
        return _finalize(
            capture=capture,
            status=(
                PolarReconciliationStatus.INSUFFICIENT_PROVIDER_EVIDENCE
                if insufficient
                else PolarReconciliationStatus.UNSUPPORTED_OR_AMBIGUOUS_STRUCTURE
            ),
            future_support=FutureBaselineAdoptionSupport.NOT_SUPPORTED,
            current_orm_edit_detected=None,
            provider_candidate=False,
            compared_fields=(),
            differences=(),
            normalization_notes=(),
            blockers=(code,),
            timezone_context_name=athlete_timezone,
            timezone_context_source="CURRENT_USER_PROFILE",
        )

    if differences:
        return _finalize(
            capture=capture,
            status=PolarReconciliationStatus.MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION,
            future_support=FutureBaselineAdoptionSupport.CLARIFICATION_REQUIRED,
            current_orm_edit_detected=True,
            provider_candidate=False,
            compared_fields=compared,
            differences=differences,
            normalization_notes=notes,
            blockers=("CURRENT_ORM_DIFFERS_FROM_STORED_POLAR_SYNC_PROJECTION",),
            timezone_context_name=athlete_timezone,
            timezone_context_source="CURRENT_USER_PROFILE",
        )

    return _finalize(
        capture=capture,
        status=PolarReconciliationStatus.SYNC_PROJECTION_MATCH,
        future_support=FutureBaselineAdoptionSupport.SUPPORTED_BY_RECONCILIATION,
        current_orm_edit_detected=False,
        provider_candidate=True,
        compared_fields=compared,
        differences=(),
        normalization_notes=notes,
        blockers=(),
        timezone_context_name=athlete_timezone,
        timezone_context_source="CURRENT_USER_PROFILE",
    )
