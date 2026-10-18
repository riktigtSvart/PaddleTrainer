from copy import deepcopy
from datetime import datetime, timezone

from app.planning.domain.common.serialization import canonical_json, compute_content_hash
from app.planning.domain.integration.models import finalize_existing_workout_plan_capture
from app.planning.domain.integration.polar_reconciliation import (
    FutureBaselineAdoptionSupport,
    PolarReconciliationStatus,
    reconcile_polar_source_capture,
)


NOW = datetime(2026, 10, 17, 17, 30, tzinfo=timezone.utc)
TZ = "Europe/Budapest"


def polar_raw(*, change_type="AUTOMATIC", duration_ms=1500.5):
    return {
        "session": {
            "id": "1450000123",
            "version": 2,
            "name": "6km fartlek",
            "description": "",
            "startTime": {
                "year": 2026,
                "month": 8,
                "day": 1,
                "hour": 10,
                "min": 0,
                "sec": 0,
            },
        },
        "exercise": [
            {
                "idx": 0,
                "sportId": "95",
                "type": "PHASED",
                "duration": duration_ms,
                "distance": None,
                "phaseOrRepeat": [
                    {
                        "name": "source phase",
                        "changeType": change_type,
                        "goal": {"type": "DURATION", "duration": duration_ms},
                        "phaseOrRepeat": [],
                        "intensity": {
                            "type": "HEART_RATE_ZONES",
                            "lowerZone": 1,
                            "upperZone": 4,
                        },
                    }
                ],
            }
        ],
    }


def orm_snapshot(raw=None):
    raw = deepcopy(raw or polar_raw())
    return {
        "id": "workout-1",
        "user_id": "athlete-1",
        "training_period_id": None,
        "date": "2026-08-01",
        "planned_start_time": "2026-08-01T10:00:00+02:00",
        "sport": "KAYAK",
        "title": "6km fartlek",
        "description": "",
        "duration_sec": 1,
        "distance_m": None,
        "intensity_type": "HEART_RATE_ZONES",
        "status": "PLANNED",
        "source": "POLAR",
        "polar_target_id": "1450000123",
        "raw_data": raw,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
        "blocks": [
            {
                "id": "ephemeral-block-id-a",
                "workout_id": "workout-1",
                "parent_block_id": None,
                "position": 0,
                "block_type": "WORK",
                "name": "source phase",
                "duration_sec": 1,
                "distance_m": None,
                "intensity_type": "HEART_RATE_ZONES",
                "intensity_min": 1,
                "intensity_max": 4,
                "repeat_count": 1,
            }
        ],
    }


def capture(*, snapshot=None, source_kind="STORED_POLAR_TARGET"):
    snapshot = deepcopy(snapshot or orm_snapshot())
    plan = {
        "contract_type": "WorkoutPlanContract",
        "schema_version": "0.1",
        "plan_id": "polar-target:1450000123:a01:hash",
        "plan_revision": 2,
        "athlete_id": "athlete-1",
        "planned_date": "2026-08-01",
        "planned_start_time": None,
        "sport": "KAYAK",
        "session_type": "FARTLEK",
        "title": "6km fartlek",
        "description": "",
        "blocks": [{"block_id": "polar-block:e0"}],
        "evidence": [],
    }
    source = {
        "status": "PLAN_CONTRACT_READ_WITH_LIMITATIONS",
        "source_snapshot": snapshot,
        "adapter_result": {"plan": plan},
    }
    source_json = canonical_json(source)
    source_hash = compute_content_hash(source, exclude_fields=frozenset())
    return finalize_existing_workout_plan_capture(
        api_rules_version="plan-contract-read-api-0.1-draft1",
        contract_release="DRAFT1",
        capture_id="capture-polar-1",
        captured_at=NOW,
        source_workout_id="workout-1",
        athlete_id="athlete-1",
        source_kind=source_kind,
        source_content_sha256="a" * 64,
        planning_logical_plan_id="planned-workout:workout-1",
        external_contract_plan_id=plan["plan_id"],
        external_contract_plan_revision=2,
        external_contract_schema_version="0.1",
        external_plan_content_hash="b" * 64,
        external_contract_snapshot_sha256="c" * 64,
        external_adapter_version="legacy-plan-adapter-0.1-draft1",
        contract_block_ids=("polar-block:e0",),
        external_occurrence_ids=("external-occurrence-1",),
        source_limitations=(
            "STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION",
            "HISTORICAL_PLAN_CONTENT_UNVERIFIED",
        ),
        provider_orm_basic_field_differences=(),
        source_read_json=source_json,
        source_read_content_hash=source_hash,
    )


def _reconcile(value):
    return reconcile_polar_source_capture(value, athlete_timezone=TZ)


def test_sync_projection_match_supports_future_adoption_without_claiming_semantic_equivalence():
    artifact = _reconcile(capture())

    assert artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
    assert (
        artifact.future_baseline_adoption_support
        == FutureBaselineAdoptionSupport.SUPPORTED_BY_RECONCILIATION
    )
    assert artifact.current_orm_edit_detected is False
    assert artifact.provider_snapshot_selected_as_future_authority_candidate is True
    assert artifact.semantic_equivalence_claimed is False
    assert artifact.adoption_gate_integrated is False
    assert artifact.schema_version == "0.2"
    assert artifact.rules_version == "polar-source-reconciliation-0.2"
    assert artifact.timezone_context_name == TZ
    assert artifact.timezone_context_source == "CURRENT_USER_PROFILE"
    assert artifact.differences == ()
    assert artifact.blockers == ()
    assert artifact.verify_content_hash()


def test_fractional_provider_duration_and_change_type_are_recorded_as_known_normalization_limits():
    artifact = _reconcile(
        capture(snapshot=orm_snapshot(polar_raw(change_type="MANUAL", duration_ms=1500.5)))
    )

    assert artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
    assert "POLAR_DURATION_MILLISECONDS_TRUNCATED_TO_INTEGER_SECONDS_IN_ORM" in artifact.normalization_notes
    assert "POLAR_PHASE_CHANGE_TYPE_NOT_PERSISTED_IN_ORM_COLUMNS" in artifact.normalization_notes
    assert "POLAR_EXERCISE_WRAPPER_NOT_PERSISTED_AS_ORM_BLOCK" in artifact.normalization_notes


def test_ephemeral_orm_block_id_does_not_create_a_difference():
    snapshot = orm_snapshot()
    snapshot["blocks"][0]["id"] = "completely-different-uuid"
    artifact = _reconcile(capture(snapshot=snapshot))

    assert artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
    assert artifact.differences == ()
    assert "/blocks/*/id" in artifact.excluded_fields


def test_local_title_edit_requires_clarification():
    snapshot = orm_snapshot()
    snapshot["title"] = "Locally edited title"
    artifact = _reconcile(capture(snapshot=snapshot))

    assert artifact.status == PolarReconciliationStatus.MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION
    assert artifact.current_orm_edit_detected is True
    assert artifact.provider_snapshot_selected_as_future_authority_candidate is False
    assert artifact.future_baseline_adoption_support == FutureBaselineAdoptionSupport.CLARIFICATION_REQUIRED
    assert any(item.field_path == "/title" for item in artifact.differences)


def test_local_block_dose_edit_requires_clarification():
    snapshot = orm_snapshot()
    snapshot["blocks"][0]["duration_sec"] = 2
    artifact = _reconcile(capture(snapshot=snapshot))

    assert artifact.status == PolarReconciliationStatus.MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION
    assert any(
        item.field_path == "/blocks/0/duration_sec"
        for item in artifact.differences
    )


def test_start_time_compares_same_instant_using_current_profile_timezone():
    equivalent = orm_snapshot()
    # Polar 10:00 Europe/Budapest on 2026-08-01 is 08:00 UTC.
    equivalent["planned_start_time"] = "2026-08-01T08:00:00+00:00"
    artifact = _reconcile(capture(snapshot=equivalent))
    assert artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
    assert artifact.timezone_context_name == TZ
    assert artifact.timezone_context_source == "CURRENT_USER_PROFILE"
    assert "/planned_start_utc" in artifact.compared_fields

    changed = orm_snapshot()
    changed["planned_start_time"] = "2026-08-01T09:00:00+00:00"
    artifact = _reconcile(capture(snapshot=changed))
    assert artifact.status == PolarReconciliationStatus.MATERIAL_DIFFERENCE_REQUIRES_CLARIFICATION
    assert any(item.field_path == "/planned_start_utc" for item in artifact.differences)


def test_realistic_cest_storage_round_trip_does_not_look_like_a_local_edit():
    raw = polar_raw()
    raw["session"]["startTime"] = {
        "year": 2026, "month": 9, "day": 30, "hour": 17, "min": 45, "sec": 0
    }
    snapshot = orm_snapshot(raw)
    snapshot["date"] = "2026-09-30"
    snapshot["planned_start_time"] = "2026-09-30T15:45:00+00:00"
    artifact = _reconcile(capture(snapshot=snapshot))
    assert artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
    assert artifact.current_orm_edit_detected is False
    assert artifact.differences == ()


def test_missing_timezone_context_fails_closed_instead_of_comparing_wall_clocks():
    artifact = reconcile_polar_source_capture(capture(), athlete_timezone=None)
    assert artifact.status == PolarReconciliationStatus.UNSUPPORTED_OR_AMBIGUOUS_STRUCTURE
    assert artifact.future_baseline_adoption_support == FutureBaselineAdoptionSupport.NOT_SUPPORTED
    assert artifact.current_orm_edit_detected is None
    assert artifact.blockers == ("ATHLETE_TIMEZONE_CONTEXT_REQUIRED",)


def test_non_polar_capture_is_explicitly_not_applicable():
    artifact = _reconcile(capture(source_kind="STORED_ORM_WORKOUT"))

    assert artifact.status == PolarReconciliationStatus.NOT_APPLICABLE
    assert artifact.future_baseline_adoption_support == FutureBaselineAdoptionSupport.NOT_APPLICABLE
    assert artifact.current_orm_edit_detected is None
    assert artifact.provider_snapshot_selected_as_future_authority_candidate is False


def test_missing_provider_snapshot_fails_closed_as_insufficient_evidence():
    snapshot = orm_snapshot()
    snapshot["raw_data"] = None
    artifact = _reconcile(capture(snapshot=snapshot))

    assert artifact.status == PolarReconciliationStatus.INSUFFICIENT_PROVIDER_EVIDENCE
    assert artifact.future_baseline_adoption_support == FutureBaselineAdoptionSupport.NOT_SUPPORTED
    assert artifact.current_orm_edit_detected is None
    assert artifact.blockers == ("POLAR_RAW_DATA_NOT_OBJECT",)


def test_unsupported_multisport_provider_structure_fails_closed():
    raw = polar_raw()
    raw["exercise"].append(
        {
            "idx": 1,
            "sportId": "1",
            "type": "VOLUME",
            "duration": 60000,
            "phaseOrRepeat": [],
        }
    )
    snapshot = orm_snapshot(raw)
    artifact = _reconcile(capture(snapshot=snapshot))

    assert artifact.status == PolarReconciliationStatus.UNSUPPORTED_OR_AMBIGUOUS_STRUCTURE
    assert artifact.future_baseline_adoption_support == FutureBaselineAdoptionSupport.NOT_SUPPORTED
    assert artifact.blockers == ("POLAR_MULTI_SPORT_TARGET_UNSUPPORTED",)


def test_same_capture_reconciles_to_same_content_hash():
    one = _reconcile(capture())
    two = _reconcile(capture())

    assert one == two
    assert one.content_hash == two.content_hash


def test_reconciliation_projection_matches_current_production_polar_sync_normalizer():
    from app.services.polar_targets import normalize_phase_tree, normalize_training_target

    raw = polar_raw(duration_ms=120000)
    raw["exercise"][0]["phaseOrRepeat"] = [
        {
            "name": "repeat container",
            "changeType": "AUTOMATIC",
            "repeatCount": 2,
            "phaseOrRepeat": [
                {
                    "name": "warmup",
                    "changeType": "AUTOMATIC",
                    "goal": {"type": "DURATION", "duration": 60000},
                    "phaseOrRepeat": [],
                    "intensity": {
                        "type": "HEART_RATE_ZONES",
                        "lowerZone": 1,
                        "upperZone": 2,
                    },
                },
                {
                    "name": "recovery",
                    "changeType": "AUTOMATIC",
                    "goal": {"type": "DURATION", "duration": 30000},
                    "phaseOrRepeat": [],
                    "intensity": {
                        "type": "HEART_RATE_ZONES",
                        "lowerZone": 1,
                        "upperZone": 1,
                    },
                },
            ],
        }
    ]
    normalized_top = normalize_training_target(raw)
    normalized_blocks = []
    for exercise_index, exercise in enumerate(raw["exercise"]):
        for item in normalize_phase_tree(exercise.get("phaseOrRepeat") or []):
            copied = dict(item)
            copied["key"] = f"e{exercise_index}:" + copied["key"]
            if copied["parent_key"] is not None:
                copied["parent_key"] = f"e{exercise_index}:" + copied["parent_key"]
            normalized_blocks.append(copied)

    ids = {item["key"]: f"orm-{index}" for index, item in enumerate(normalized_blocks)}
    orm_blocks = []
    for flat_position, item in enumerate(normalized_blocks):
        orm_blocks.append(
            {
                "id": ids[item["key"]],
                "workout_id": "workout-1",
                "parent_block_id": (
                    None if item["parent_key"] is None else ids[item["parent_key"]]
                ),
                "position": flat_position,
                "block_type": item["block_type"],
                "name": item["name"],
                "duration_sec": item["duration_sec"],
                "distance_m": item["distance_m"],
                "intensity_type": item["intensity_type"],
                "intensity_min": item["intensity_min"],
                "intensity_max": item["intensity_max"],
                "repeat_count": item["repeat_count"],
            }
        )

    intensity_types = {
        item["intensity_type"]
        for item in normalized_blocks
        if item["intensity_type"] is not None
    }
    if len(intensity_types) == 1:
        intensity_type = next(iter(intensity_types))
    elif len(intensity_types) > 1:
        intensity_type = "MIXED"
    else:
        intensity_type = None

    snapshot = orm_snapshot(raw)
    snapshot.update(
        {
            "date": normalized_top["date"],
            "planned_start_time": normalized_top["planned_start_time"] + "+02:00",
            "sport": normalized_top["sport"],
            "title": normalized_top["title"],
            "description": normalized_top["description"],
            "duration_sec": normalized_top["duration_sec"],
            "distance_m": normalized_top["distance_m"],
            "intensity_type": intensity_type,
            "source": "POLAR",
            "polar_target_id": normalized_top["polar_target_id"],
            "blocks": orm_blocks,
        }
    )

    artifact = _reconcile(capture(snapshot=snapshot))
    assert artifact.status == PolarReconciliationStatus.SYNC_PROJECTION_MATCH
    assert artifact.differences == ()
