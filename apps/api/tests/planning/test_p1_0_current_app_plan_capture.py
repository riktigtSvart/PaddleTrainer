from copy import deepcopy

import pytest

from app.planning.infrastructure.adapters.current_app_plan_read import (
    CurrentAppPlanReadAdapterError,
    adapt_current_app_plan_read,
)
from app.services.plan_contract_read import build_plan_read


CAPTURE_A = "2026-10-17T06:00:00+00:00"
CAPTURE_B = "2026-10-17T06:01:00+00:00"
WORKOUT_ID = "00000000-0000-0000-0000-00000000a001"
BLOCK_ID = "00000000-0000-0000-0000-00000000b001"
ATHLETE_ID = "00000000-0000-0000-0000-00000000c001"


def manual_snapshot():
    return {
        "id": WORKOUT_ID,
        "user_id": ATHLETE_ID,
        "training_period_id": None,
        "date": "2026-10-17",
        "planned_start_time": None,
        "sport": "KAYAK",
        "title": "Synthetic integration plan",
        "description": None,
        "duration_sec": 1800,
        "distance_m": None,
        "intensity_type": None,
        "status": "PLANNED",
        "source": "MANUAL",
        "polar_target_id": None,
        "raw_data": None,
        "created_at": "2026-10-17T05:00:00+00:00",
        "updated_at": "2026-10-17T05:00:00+00:00",
        "blocks": [
            {
                "id": BLOCK_ID,
                "workout_id": WORKOUT_ID,
                "parent_block_id": None,
                "position": 0,
                "block_type": "WORK",
                "name": "Easy",
                "duration_sec": 1800,
                "distance_m": None,
                "intensity_type": "NONE",
                "intensity_min": 0,
                "intensity_max": 0,
                "repeat_count": 1,
            }
        ],
    }


def test_lossless_capture_round_trips_exact_current_read_result():
    read = build_plan_read(manual_snapshot(), captured_at=CAPTURE_A)
    capture = adapt_current_app_plan_read(read)

    import json

    assert json.loads(capture.source_read_json) == read
    assert capture.verify_source_read_hash()
    assert capture.verify_content_hash()
    assert capture.planning_logical_plan_id == f"planned-workout:{WORKOUT_ID}"
    assert capture.source_workout_id == WORKOUT_ID
    assert capture.athlete_id == ATHLETE_ID
    assert capture.authoritative_revision_promotion_allowed is False
    assert "STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION" in (
        capture.promotion_blockers
    )


def test_repeated_current_reads_keep_logical_binding_but_not_external_ids():
    first_read = build_plan_read(manual_snapshot(), captured_at=CAPTURE_A)
    second_read = build_plan_read(manual_snapshot(), captured_at=CAPTURE_B)
    first = adapt_current_app_plan_read(first_read)
    second = adapt_current_app_plan_read(second_read)

    assert first.source_content_sha256 == second.source_content_sha256
    assert first.planning_logical_plan_id == second.planning_logical_plan_id
    assert first.capture_id != second.capture_id
    assert first.external_contract_plan_id != second.external_contract_plan_id
    assert first.external_occurrence_ids != second.external_occurrence_ids
    assert first.contract_block_ids == second.contract_block_ids


def test_source_edit_changes_source_hash_without_changing_logical_binding():
    first = adapt_current_app_plan_read(
        build_plan_read(manual_snapshot(), captured_at=CAPTURE_A)
    )
    edited = manual_snapshot()
    edited["title"] = "Edited title"
    second = adapt_current_app_plan_read(
        build_plan_read(edited, captured_at=CAPTURE_A)
    )

    assert first.planning_logical_plan_id == second.planning_logical_plan_id
    assert first.source_content_sha256 != second.source_content_sha256
    assert first.external_contract_plan_id != second.external_contract_plan_id


def test_adapter_fails_closed_if_read_api_semantics_change():
    read = build_plan_read(manual_snapshot(), captured_at=CAPTURE_A)
    changed = deepcopy(read)
    changed["api_rules_version"] = "plan-contract-read-api-0.2"

    with pytest.raises(
        CurrentAppPlanReadAdapterError,
        match="PLAN_READ_API_RULES_VERSION_CHANGED",
    ):
        adapt_current_app_plan_read(changed)


def test_adapter_refuses_silent_promotion_of_historical_verification():
    read = build_plan_read(manual_snapshot(), captured_at=CAPTURE_A)
    changed = deepcopy(read)
    changed["historical_plan_content_verified"] = True

    with pytest.raises(
        CurrentAppPlanReadAdapterError,
        match="SOURCE_READ_HISTORICAL_VERIFICATION_CHANGED",
    ):
        adapt_current_app_plan_read(changed)


def test_adapter_refuses_numeric_authority_expansion():
    read = build_plan_read(manual_snapshot(), captured_at=CAPTURE_A)
    changed = deepcopy(read)
    changed["numeric_output_authorized"] = True

    with pytest.raises(
        CurrentAppPlanReadAdapterError,
        match="SOURCE_READ_NUMERIC_AUTHORITY_CHANGED",
    ):
        adapt_current_app_plan_read(changed)
