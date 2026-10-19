from copy import deepcopy
from uuid import uuid4

import pytest

from app.planning.infrastructure.adapters.phase_occurrence_candidate import (
    PhaseOccurrenceCandidateAdapterError,
    capture_occurrence_execution_candidate,
)
from app.planning_contracts.phase_reconciliation import (
    RULES_VERSION,
    reconcile,
)


SESSION_ID = str(uuid4())
ATHLETE_ID = str(uuid4())

SESSION_HASH = "a" * 64
PLAN_HASH = "b" * 64
STABLE_OCCURRENCE_ID = (
    "phase-source-occurrence_" + "c" * 64
)
CAPTURED_OCCURRENCE_ID = "occ_capture_p1_6c_adapter"


def reconciliation_read():
    spec = {
        "schema_version": "0.1",
        "binding": {
            "session_id": SESSION_ID,
            "athlete_id": ATHLETE_ID,
            "source_sha256": SESSION_HASH,
            "plan_sha256": PLAN_HASH,
        },
        "input_kind": "PINNED_FULL_API_REPLAY",
        "sport": "RUNNING",
        "scope": "PHASED",
        "source_plan_link_status": "EXACT_PROVIDER_ID",
        "phase_blocking_reasons": [],
        "whole_session_target": None,
        "phases": [
            {
                "occurrence_id": STABLE_OCCURRENCE_ID,
                "captured_contract_occurrence_id": (
                    CAPTURED_OCCURRENCE_ID
                ),
                "block_id": "polar-block:e0.0",
                "source_pointer": (
                    "/exercise/0/phaseOrRepeat/0"
                ),
                "display_name": "Phase 1",
                "advance": "AUTOMATIC",
                "goal": {
                    "type": "DURATION",
                    "value": 60.0,
                    "unit": "SECOND",
                },
                "goal_authority": (
                    "STRUCTURED_PROVIDER_GOAL_NOT_DISPLAY_NAME"
                ),
            },
        ],
        "grid": {
            "slot_count": 180,
            "speed_kmh": None,
            "distance_m": None,
            "index_clock_assumption": (
                "ONE_SECOND_NATIVE_INDEX_CANDIDATE"
            ),
            "native_unit_policy": "TEST_ONLY",
            "native_units_independently_verified": False,
            "route_origin_candidate_s": None,
            "source_grid_issues": [],
        },
        "whole_session_observations": None,
    }

    result = reconcile(spec)
    hypothesis = result[
        "consistent_hypotheses_after_clarification"
    ][0]

    return {
        "status": (
            "PHASE_RECONCILIATION_READ_WITH_LIMITATIONS"
        ),
        "rules_version": RULES_VERSION,
        "session_id": SESSION_ID,
        "source_content_sha256": SESSION_HASH,
        "plan_source_content_sha256": PLAN_HASH,
        "stable_artifact_id": result["artifact_id"],
        "stable_normalized_motion_input_sha256": (
            result["normalized_input_sha256"]
        ),
        "source_capture_occurrence_mapping": [
            {
                "stable_source_occurrence_id": (
                    STABLE_OCCURRENCE_ID
                ),
                "captured_contract_occurrence_id": (
                    CAPTURED_OCCURRENCE_ID
                ),
                "source_pointer": (
                    "/exercise/0/phaseOrRepeat/0"
                ),
            },
        ],
        "result": result,
        "actual_phase_alignment_verified": False,
        "_hypothesis_id": hypothesis["hypothesis_id"],
    }


def capture(value):
    return capture_occurrence_execution_candidate(
        value,
        hypothesis_id=value["_hypothesis_id"],
        stable_source_occurrence_id=(
            STABLE_OCCURRENCE_ID
        ),
    )


def test_server_adapter_derives_candidate_evidence():
    value = reconciliation_read()
    before = deepcopy(value)

    result = capture(value)

    assert (
        result.phase_reconciliation_artifact_id
        == value["stable_artifact_id"]
    )
    assert (
        result.phase_reconciliation_rules_version
        == RULES_VERSION
    )
    assert (
        result.session_source_content_hash
        == SESSION_HASH
    )
    assert (
        result.plan_source_content_hash
        == PLAN_HASH
    )
    assert (
        result.stable_source_occurrence_id
        == STABLE_OCCURRENCE_ID
    )
    assert (
        result.captured_contract_occurrence_id
        == CAPTURED_OCCURRENCE_ID
    )

    assert result.candidate_start_window_s == (
        0.0,
        0.0,
    )
    assert result.candidate_completion_window_s == (
        60.0,
        60.0,
    )
    assert result.clock_domain == (
        "NATIVE_INDEX_CANDIDATE"
    )

    assert result.provider_event_verified is False
    assert result.clock_alignment_verified is False
    assert result.actual_boundary_verified is False

    # Extraction is read-only.
    assert value == before


def test_only_consistent_hypotheses_are_eligible():
    value = reconciliation_read()
    value["result"][
        "consistent_hypotheses_after_clarification"
    ] = []

    with pytest.raises(
        PhaseOccurrenceCandidateAdapterError,
        match="not uniquely eligible",
    ):
        capture(value)


def test_client_cannot_replace_source_hashes():
    value = reconciliation_read()
    value["source_content_sha256"] = "f" * 64

    with pytest.raises(
        PhaseOccurrenceCandidateAdapterError,
        match="Session source hash differs",
    ):
        capture(value)


def test_source_occurrence_mapping_must_be_unique():
    value = reconciliation_read()
    value["source_capture_occurrence_mapping"].append(
        deepcopy(
            value["source_capture_occurrence_mapping"][0]
        )
    )

    with pytest.raises(
        PhaseOccurrenceCandidateAdapterError,
        match="mapping is not unique",
    ):
        capture(value)


def test_unresolved_completion_window_is_not_eligible():
    value = reconciliation_read()
    hypothesis = value["result"][
        "consistent_hypotheses_after_clarification"
    ][0]
    hypothesis["phase_windows"][0][
        "goal_completion_window_s"
    ] = None

    with pytest.raises(
        PhaseOccurrenceCandidateAdapterError,
        match="goal_completion_window_s",
    ):
        capture(value)


def test_future_stronger_alignment_semantics_fail_closed():
    value = reconciliation_read()
    value["actual_phase_alignment_verified"] = True

    with pytest.raises(
        PhaseOccurrenceCandidateAdapterError,
        match="Unexpected phase-alignment authority",
    ):
        capture(value)


def test_unknown_rules_version_fails_closed():
    value = reconciliation_read()
    value["rules_version"] = "future-rules"

    with pytest.raises(
        PhaseOccurrenceCandidateAdapterError,
        match="Unsupported phase reconciliation rules",
    ):
        capture(value)
