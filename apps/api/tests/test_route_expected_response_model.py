from copy import deepcopy
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.encoders import jsonable_encoder

from app.api.routes import polar
from app.services import route_expected_response_model as model_service
from app.services.athlete_state_temporal_binding import build_athlete_state_temporal_binding
from app.services.route_expected_response_input import (
    build_route_expected_response_input,
    build_route_expected_response_input_summary,
)
from app.services.route_expected_response_model import (
    MODEL_ID,
    MODEL_NOT_CONFIGURED,
    MODEL_VERSION,
    build_route_expected_response_model,
    build_route_expected_response_model_summary,
)


@pytest.fixture
def ready_input():
    """Use the production V22 binder and V21 input boundary, not readiness flags."""
    context = {
        "as_of_date": date(2026, 9, 29),
        "training_load": {"available": True},
        "capacity": {"items": [{"estimated_at": datetime(2026, 9, 29, tzinfo=UTC)}]},
        "evidence_inventory": {"gaps": ["HRV_REFERENCE_MISSING"]},
    }
    binding = build_athlete_state_temporal_binding(
        "2026-09-30T15:37:27.763+00:00",
        [
            {
                "state_timestamp": "2026-09-29T22:00:00+00:00",
                "snapshot_id": "prior-day-state",
                "context": context,
                "source": {"source_policy": "PRIOR_LOCAL_DAY_CLOSED_WINDOW"},
                "traceability_gaps": ["HRV_REFERENCE_MISSING"],
            }
        ],
    )
    workload = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "observations": [{"order_index": i, "gps_ground_speed_mps": 2.5} for i in range(2)],
            }
        ],
    }
    environment = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "TRUSTED_WITH_LIMITATIONS",
                "route_limitations": ["MODELLED_GRIDDED_WEATHER"],
                "segments": [
                    {
                        "order_index": i,
                        "status": "TRUSTED_WITH_LIMITATIONS",
                        "usable_for_downstream_environment_context": True,
                        "limitations": ["BOAT_THROUGH_WATER_SPEED_NOT_ESTABLISHED"],
                        "hydrology": {"status": "WITHHELD", "water_level": None},
                    }
                    for i in range(2)
                ],
            }
        ],
    }
    return build_route_expected_response_input(
        workload,
        environment,
        athlete_state_context=context,
        athlete_state_binding=binding,
    )


def test_production_bound_ready_input_is_not_a_physiological_prediction(ready_input):
    assert ready_input["model_ready_route_count"] == 1
    result = build_route_expected_response_model(ready_input)
    assert result["model"]["model_id"] == MODEL_ID
    assert result["model"]["model_version"] == MODEL_VERSION
    assert result["model"]["stage"] == "FOUNDATION_ONLY"
    assert result["status"] == "NOT_ESTIMATED"
    assert result["input_eligible_route_count"] == 1
    assert result["estimated_route_count"] == 0
    assert result["response_available"] is False
    response = result["routes"][0]["expected_response"]
    assert response["status"] == "WITHHELD"
    assert response["value"] is None
    assert response["unit"] is None
    assert response["withheld_reasons"] == [MODEL_NOT_CONFIGURED]
    assert response["uncertainty"] == {
        "status": "NOT_ESTABLISHED",
        "interval": None,
        "confidence_level": None,
    }


@pytest.mark.parametrize("source", [None, {}, build_route_expected_response_input(None, None)])
def test_no_routes_is_unavailable(source):
    result = build_route_expected_response_model(source)
    assert result["status"] == "UNAVAILABLE"
    assert result["input_eligible_route_count"] == 0
    assert result["response_available"] is False


@pytest.mark.parametrize("status", ["WITHHELD", "INCOMPLETE", "UNAVAILABLE", "UNKNOWN"])
def test_upstream_input_status_cannot_be_promoted(ready_input, status):
    ready_input["routes"][0]["status"] = status
    result = build_route_expected_response_model(ready_input)
    assert result["status"] == "WITHHELD"
    assert result["input_eligible_route_count"] == 0
    assert "EXPECTED_RESPONSE_INPUT_NOT_READY" in result["routes"][0]["input_blocking_reasons"]


def test_compact_input_summary_is_not_accepted_as_full_model_input(ready_input):
    result = build_route_expected_response_model(
        build_route_expected_response_input_summary(ready_input)
    )
    assert result["input_eligible_route_count"] == 0
    assert (
        "FULL_EXPECTED_RESPONSE_INPUT_SEGMENTS_REQUIRED"
        in result["routes"][0]["input_blocking_reasons"]
    )


def test_input_schema_is_explicitly_versioned(ready_input):
    ready_input["schema_version"] = "9.9"
    result = build_route_expected_response_model(ready_input)
    assert (
        "EXPECTED_RESPONSE_INPUT_SCHEMA_UNSUPPORTED"
        in result["routes"][0]["input_blocking_reasons"]
    )
    assert result["input_eligible_route_count"] == 0


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("model_ready", False, "UPSTREAM_MODEL_INPUT_NOT_READY"),
        ("athlete_state_status", "NOT_BOUND", "ROUTE_ATHLETE_STATE_NOT_BOUND"),
        ("environment_route_status", "WITHHELD", "ROUTE_ENVIRONMENT_NOT_USABLE"),
        ("segment_count", 99, "EXPECTED_RESPONSE_INPUT_SEGMENT_COUNTS_INCONSISTENT"),
        ("workload_segment_count", True, "EXPECTED_RESPONSE_INPUT_SEGMENT_COUNTS_INCONSISTENT"),
        ("aligned_usable_segment_count", 99, "EXPECTED_RESPONSE_INPUT_SEGMENT_COUNTS_INCONSISTENT"),
    ],
)
def test_route_flags_and_counts_are_verified(ready_input, field, value, reason):
    ready_input["routes"][0][field] = value
    result = build_route_expected_response_model(ready_input)
    assert reason in result["routes"][0]["input_blocking_reasons"]
    assert result["input_eligible_route_count"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment_status", "WITHHELD"),
        ("environment_context_withheld", True),
        ("environment_usable", False),
        ("external_workload", None),
        ("aligned_for_expected_response_input", False),
    ],
)
def test_one_bad_segment_blocks_whole_route_even_if_route_flags_claim_ready(
    ready_input, field, value
):
    ready_input["routes"][0]["segments"][1][field] = value
    result = build_route_expected_response_model(ready_input)
    assert result["input_eligible_route_count"] == 0
    assert result["routes"][0]["segments"][0]["input_eligible"] is True
    assert result["routes"][0]["segments"][1]["input_eligible"] is False
    assert result["estimated_route_count"] == 0


def test_nested_environment_withheld_cannot_be_overridden_by_wrapper_flags(ready_input):
    ready_input["routes"][0]["segments"][0]["environment_context"]["status"] = "WITHHELD"
    result = build_route_expected_response_model(ready_input)
    assert result["input_eligible_route_count"] == 0


def test_duplicate_route_identity_blocks_every_instance(ready_input):
    ready_input["routes"].append(deepcopy(ready_input["routes"][0]))
    result = build_route_expected_response_model(ready_input)
    assert result["input_eligible_route_count"] == 0
    assert all(
        "ROUTE_IDENTITY_AMBIGUOUS" in route["input_blocking_reasons"] for route in result["routes"]
    )


@pytest.mark.parametrize(
    "order,reason", [(0, "SEGMENT_IDENTITY_AMBIGUOUS"), (True, "SEGMENT_IDENTITY_INVALID")]
)
def test_segment_identity_is_not_silently_collapsed(ready_input, order, reason):
    ready_input["routes"][0]["segments"][1]["order_index"] = order
    result = build_route_expected_response_model(ready_input)
    assert reason in result["routes"][0]["input_blocking_reasons"]


def test_readiness_context_without_temporal_binding_is_not_athlete_state(ready_input):
    ready_input["athlete_state"]["status"] = "NOT_BOUND"
    ready_input["athlete_state"]["context"] = {"readiness": {"score": 0.8}}
    result = build_route_expected_response_model(ready_input)
    assert "ATHLETE_STATE_NOT_EXPLICITLY_BOUND" in result["routes"][0]["input_blocking_reasons"]


@pytest.mark.parametrize(
    "timestamp,reason",
    [
        ("2026-10-01T00:00:00+00:00", "ATHLETE_STATE_IS_FUTURE"),
        ("2026-09-28T22:00:00+00:00", "ATHLETE_STATE_OUTSIDE_CARRY_FORWARD_POLICY"),
        ("2026-09-29T22:00:00", "ATHLETE_STATE_TEMPORAL_BINDING_NOT_VERIFIABLE"),
    ],
)
def test_bound_flag_does_not_override_temporal_evidence(ready_input, timestamp, reason):
    ready_input["athlete_state"]["binding"]["selected_snapshot"]["state_timestamp"] = timestamp
    result = build_route_expected_response_model(ready_input)
    assert reason in result["routes"][0]["input_blocking_reasons"]


def test_age_is_recomputed_from_timestamps(ready_input):
    ready_input["athlete_state"]["binding"]["selected_snapshot"]["age_seconds"] = 0
    result = build_route_expected_response_model(ready_input)
    assert "ATHLETE_STATE_BINDING_AGE_INCONSISTENT" in result["routes"][0]["input_blocking_reasons"]


def test_bound_context_cannot_be_replaced_after_binding(ready_input):
    ready_input["athlete_state"]["context"]["training_load"]["available"] = False
    result = build_route_expected_response_model(ready_input)
    assert "ATHLETE_STATE_BOUND_CONTEXT_MISMATCH" in result["routes"][0]["input_blocking_reasons"]


def test_hashes_are_deterministic_and_commit_full_evidence(ready_input):
    first = build_route_expected_response_model(ready_input)
    reordered = dict(reversed(list(ready_input.items())))
    second = build_route_expected_response_model(reordered)
    assert first["decision_hash"] == second["decision_hash"]
    assert len(first["decision_hash"]) == 64
    ready_input["routes"][0]["segments"][0]["external_workload"]["gps_ground_speed_mps"] += 0.1
    changed = build_route_expected_response_model(ready_input)
    assert (
        first["input_provenance"]["expected_response_input_hash"]
        != changed["input_provenance"]["expected_response_input_hash"]
    )
    assert first["decision_hash"] != changed["decision_hash"]


def test_interval_evidence_is_committed_without_scalar_conversion(ready_input):
    level = {"value": None, "unit": "cm", "value_interval": {"lower": 624, "upper": 638}}
    ready_input["routes"][0]["segments"][0]["environment_context"]["hydrology"] = {
        "status": "TRUSTED_WITH_LIMITATIONS",
        "water_level": level,
    }
    before = deepcopy(ready_input)
    first = build_route_expected_response_model(ready_input)
    assert ready_input == before
    assert first["routes"][0]["expected_response"]["value"] is None
    level["value_interval"]["upper"] = 639
    second = build_route_expected_response_model(ready_input)
    assert first["decision_hash"] != second["decision_hash"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()])
def test_noncanonical_evidence_is_withheld_without_an_invented_hash(ready_input, value):
    ready_input["routes"][0]["segments"][0]["external_workload"]["gps_ground_speed_mps"] = value
    result = build_route_expected_response_model(ready_input)
    assert result["input_provenance"]["expected_response_input_hash"] is None
    assert (
        "EXPECTED_RESPONSE_INPUT_NOT_CANONICAL_JSON"
        in result["routes"][0]["input_blocking_reasons"]
    )
    assert result["estimated_route_count"] == 0


def test_provenance_and_limitations_survive_without_repeating_state_payload(ready_input):
    result = build_route_expected_response_model(ready_input)
    binding = result["input_provenance"]["athlete_state_binding"]
    assert binding["selected_snapshot"]["snapshot_id"] == "prior-day-state"
    assert (
        binding["selected_snapshot"]["source"]["source_policy"] == "PRIOR_LOCAL_DAY_CLOSED_WINDOW"
    )
    assert "athlete_state_context" not in binding
    assert "evaluated_candidates" not in binding
    assert "HRV_REFERENCE_MISSING" in result["routes"][0]["limitations"]
    assert "MODELLED_GRIDDED_WEATHER" in result["routes"][0]["limitations"]
    assert (
        "BOAT_THROUGH_WATER_SPEED_NOT_ESTABLISHED"
        in result["routes"][0]["segments"][0]["limitations"]
    )


def test_summary_keeps_decision_hash_and_never_mutates_full_output(ready_input):
    before = deepcopy(ready_input)
    result = build_route_expected_response_model(ready_input)
    full_before = deepcopy(result)
    summary = build_route_expected_response_model_summary(result)
    assert "segments" not in summary["routes"][0]
    assert summary["routes"][0]["segments_included"] is False
    assert summary["decision_hash"] == result["decision_hash"]
    assert ready_input == before
    assert result == full_before


def test_foundation_has_no_physiology_current_or_training_dose_capability(ready_input):
    result = build_route_expected_response_model(ready_input)
    assert result["model"]["numeric_output_authorized"] is False
    assert all(value is False for key, value in result["scope"].items() if key != "domain")


def test_native_dates_and_api_serialized_dates_have_the_same_input_commitment(ready_input):
    native = build_route_expected_response_model(ready_input)
    serialized = build_route_expected_response_model(jsonable_encoder(ready_input))
    assert (
        native["input_provenance"]["expected_response_input_hash"]
        == serialized["input_provenance"]["expected_response_input_hash"]
    )
    assert native["decision_hash"] == serialized["decision_hash"]
    assert jsonable_encoder(native)["decision_hash"] == native["decision_hash"]


def test_model_version_is_part_of_decision_commitment(ready_input, monkeypatch):
    first = build_route_expected_response_model(ready_input)
    monkeypatch.setattr(model_service, "MODEL_VERSION", "0.1.1")
    second = build_route_expected_response_model(ready_input)
    assert (
        first["input_provenance"]["expected_response_input_hash"]
        == second["input_provenance"]["expected_response_input_hash"]
    )
    assert first["decision_hash"] != second["decision_hash"]


def test_exact_carry_forward_boundary_is_eligible(ready_input):
    binding = ready_input["athlete_state"]["binding"]
    binding["target_timestamp"] = "2026-09-30T22:00:00+00:00"
    binding["selected_snapshot"]["age_seconds"] = 86400
    result = build_route_expected_response_model(ready_input)
    assert result["input_eligible_route_count"] == 1
    assert result["estimated_route_count"] == 0


def test_caller_bound_flag_without_temporal_contract_does_not_authorize_model_input(ready_input):
    ready_input["athlete_state"]["binding"] = {
        "status": "BOUND",
        "binding_basis": ["EXPLICIT_CALLER_BINDING"],
    }
    result = build_route_expected_response_model(ready_input)
    assert (
        "ATHLETE_STATE_TEMPORAL_BINDING_NOT_VERIFIABLE"
        in result["routes"][0]["input_blocking_reasons"]
    )


def test_non_mapping_segment_is_retained_as_a_blocking_diagnostic(ready_input):
    ready_input["routes"][0]["segments"][1] = None
    result = build_route_expected_response_model(ready_input)
    assert result["input_eligible_route_count"] == 0
    assert result["routes"][0]["segment_count"] == 2
    assert result["routes"][0]["segments"][1]["input_eligible"] is False


def test_multiple_routes_keep_their_own_input_eligibility(ready_input):
    second = deepcopy(ready_input["routes"][0])
    second["route_index"] = 1
    second["status"] = "WITHHELD"
    ready_input["routes"].append(second)
    result = build_route_expected_response_model(ready_input)
    assert result["input_eligible_route_count"] == 1
    assert result["input_blocked_route_count"] == 1
    assert result["response_withheld_route_count"] == 2
    assert result["estimated_route_count"] == 0


@pytest.mark.parametrize("mode", ["EMPTY", "ELIGIBLE", "WITHHELD"])
@pytest.mark.asyncio
async def test_real_inspection_wires_full_model_input_and_compact_output(
    monkeypatch, ready_input, mode
):
    # Run real route orchestration. Stub external I/O, and provide a prepared
    # V21 input at its assembly seam for positive and withheld wiring controls.
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"]))
    )
    monkeypatch.setattr(
        polar, "get_or_create_demo_user", AsyncMock(return_value=SimpleNamespace(id="test-user"))
    )
    monkeypatch.setattr(polar, "get_valid_access_token", AsyncMock(return_value="test-token"))
    monkeypatch.setattr(
        polar.PolarClient,
        "list_training_sessions",
        AsyncMock(
            return_value={
                "trainingSessions": [{"identifier": {"id": "wiring-control"}, "exercises": []}],
            }
        ),
    )
    monkeypatch.setattr(
        polar,
        "load_and_bind_athlete_state_scientific_views",
        AsyncMock(
            return_value={
                "status": "NOT_BOUND",
                "athlete_state_context": None,
            }
        ),
    )
    if mode != "EMPTY":
        if mode == "WITHHELD":
            ready_input["routes"][0]["status"] = "WITHHELD"
            ready_input["routes"][0]["model_ready"] = False
        monkeypatch.setattr(
            polar, "build_route_expected_response_input", lambda *args, **kwargs: ready_input
        )
    writes = AsyncMock(side_effect=AssertionError("inspect must remain read-only"))
    monkeypatch.setattr(polar, "persist_route_environment_evidence", writes)

    result = await polar._build_training_session_route_inspection(
        route_date=date(2026, 9, 30),
        artifact_policy_profile="BALANCED",
        wind_speed_mps=None,
        wind_direction_from_deg=None,
        weather_provider=None,
        hydrology_provider=None,
        hydrology_station_registry_number=None,
        hydrology_relation_provider=None,
        hydrology_relation_validation_mode=False,
        persist_environment_evidence=False,
        db=db,
    )
    session = result["route_sessions"][0]
    model = session["route_expected_response_model"]
    assert (
        model["status"]
        == {"EMPTY": "UNAVAILABLE", "ELIGIBLE": "NOT_ESTIMATED", "WITHHELD": "WITHHELD"}[mode]
    )
    assert model["input_eligible_route_count"] == (1 if mode == "ELIGIBLE" else 0)
    assert model["model"]["stage"] == "FOUNDATION_ONLY"
    assert model["response_available"] is False
    assert model["estimated_route_count"] == 0
    assert len(model["decision_hash"]) == 64
    for route in model["routes"]:
        assert "segments" not in route
        assert route["segments_included"] is False
    writes.assert_not_awaited()
