from copy import deepcopy

from app.services.route_expected_response_input import (
    ATHLETE_STATE_BOUND,
    STATUS_INCOMPLETE,
    STATUS_READY,
    STATUS_READY_WITH_LIMITATIONS,
    STATUS_UNAVAILABLE,
    STATUS_WITHHELD,
    build_route_expected_response_input,
    build_route_expected_response_input_summary,
)


def _workload(segment_count=2):
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "observations": [
                    {
                        "order_index": index,
                        "gps_ground_speed_mps": 2.5 + index * 0.1,
                    }
                    for index in range(segment_count)
                ],
            }
        ],
    }


def _environment(
    segment_count=2,
    *,
    route_status="TRUSTED",
    segment_status="TRUSTED",
    limitations=None,
):
    limitations = list(limitations or [])
    return {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": route_status,
                "route_limitations": limitations,
                "segments": [
                    {
                        "order_index": index,
                        "status": segment_status,
                        "usable_for_downstream_environment_context": (
                            segment_status in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"}
                        ),
                        "limitations": limitations,
                        "weather": {"status": "TRUSTED_WITH_LIMITATIONS"},
                    }
                    for index in range(segment_count)
                ],
            }
        ],
    }


def _state(*, traceability_gaps=None):
    return {
        "schema_version": "0.1",
        "date": "2026-09-30",
        "training_load": {"available": True},
        "traceability_gaps": list(traceability_gaps or []),
    }


def _binding():
    return {
        "schema_version": "0.1",
        "status": ATHLETE_STATE_BOUND,
        "effective_date": "2026-09-30",
        "binding_basis": ["EXPLICIT_CALLER_BINDING"],
    }


def test_no_inputs_is_unavailable():
    result = build_route_expected_response_input(None, None)
    assert result["status"] == STATUS_UNAVAILABLE
    assert result["route_count"] == 0
    assert result["model_ready_route_count"] == 0


def test_route_inputs_without_athlete_state_are_incomplete():
    result = build_route_expected_response_input(_workload(), _environment())
    route = result["routes"][0]
    assert result["status"] == STATUS_INCOMPLETE
    assert route["status"] == STATUS_INCOMPLETE
    assert route["model_ready"] is False
    assert route["athlete_state_status"] == "NOT_BOUND"
    assert "ATHLETE_STATE_NOT_EXPLICITLY_BOUND" in route["limitations"]


def test_athlete_state_context_without_explicit_binding_is_not_bound():
    result = build_route_expected_response_input(
        _workload(),
        _environment(),
        athlete_state_context=_state(),
    )
    assert result["athlete_state"]["available"] is True
    assert result["athlete_state"]["explicitly_bound"] is False
    assert result["routes"][0]["model_ready"] is False


def test_explicit_bound_state_with_trusted_inputs_is_ready():
    result = build_route_expected_response_input(
        _workload(),
        _environment(),
        athlete_state_context=_state(),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_READY
    assert route["status"] == STATUS_READY
    assert route["model_ready"] is True
    assert route["aligned_usable_segment_count"] == 2


def test_environment_limitations_make_ready_with_limitations():
    result = build_route_expected_response_input(
        _workload(),
        _environment(
            route_status="TRUSTED_WITH_LIMITATIONS",
            segment_status="TRUSTED_WITH_LIMITATIONS",
            limitations=["MODELLED_GRIDDED_WEATHER"],
        ),
        athlete_state_context=_state(),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_READY_WITH_LIMITATIONS
    assert route["model_ready"] is True
    assert "MODELLED_GRIDDED_WEATHER" in route["limitations"]


def test_withheld_environment_blocks_model_readiness():
    result = build_route_expected_response_input(
        _workload(),
        _environment(route_status="WITHHELD", segment_status="WITHHELD"),
        athlete_state_context=_state(),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_WITHHELD
    assert route["status"] == STATUS_WITHHELD
    assert route["model_ready"] is False


def test_missing_workload_is_unavailable_even_with_environment_and_state():
    result = build_route_expected_response_input(
        None,
        _environment(),
        athlete_state_context=_state(),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_UNAVAILABLE
    assert "TRUSTED_EXTERNAL_WORKLOAD_UNAVAILABLE" in route["limitations"]


def test_missing_environment_is_incomplete():
    result = build_route_expected_response_input(
        _workload(),
        None,
        athlete_state_context=_state(),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_INCOMPLETE
    assert route["model_ready"] is False
    assert "TRUSTED_ENVIRONMENT_CONTEXT_UNAVAILABLE" in route["limitations"]


def test_environment_segment_gap_blocks_model_readiness():
    result = build_route_expected_response_input(
        _workload(segment_count=2),
        _environment(segment_count=1),
        athlete_state_context=_state(),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_INCOMPLETE
    assert route["workload_segment_count"] == 2
    assert route["aligned_usable_segment_count"] == 1
    assert "TRUSTED_ENVIRONMENT_CONTEXT_INCOMPLETE_FOR_WORKLOAD_SEGMENTS" in route[
        "limitations"
    ]


def test_withheld_environment_segment_payload_is_not_forwarded():
    environment = _environment()
    environment["routes"][0]["segments"][1]["status"] = "WITHHELD"
    environment["routes"][0]["segments"][1][
        "usable_for_downstream_environment_context"
    ] = False
    result = build_route_expected_response_input(_workload(), environment)
    segment = result["routes"][0]["segments"][1]
    assert segment["environment_context"] is None
    assert segment["environment_context_withheld"] is True
    assert segment["aligned_for_expected_response_input"] is False


def test_usable_environment_segment_payload_is_forwarded():
    result = build_route_expected_response_input(_workload(), _environment())
    segment = result["routes"][0]["segments"][0]
    assert segment["environment_context"] is not None
    assert segment["environment_usable"] is True
    assert segment["aligned_for_expected_response_input"] is True


def test_readiness_named_payload_does_not_implicitly_bind_athlete_state():
    readiness_like = {
        "schema_version": "0.1",
        "readiness": {"score": 0.8},
    }
    result = build_route_expected_response_input(
        _workload(),
        _environment(),
        athlete_state_context=readiness_like,
    )
    assert result["policy"]["readiness_projection_is_not_athlete_state"] is True
    assert result["athlete_state"]["status"] == "NOT_BOUND"
    assert result["model_ready_route_count"] == 0


def test_athlete_state_traceability_gaps_are_preserved_as_limitations():
    result = build_route_expected_response_input(
        _workload(),
        _environment(),
        athlete_state_context=_state(traceability_gaps=["HRV_REFERENCE_MISSING"]),
        athlete_state_binding=_binding(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_READY_WITH_LIMITATIONS
    assert "HRV_REFERENCE_MISSING" in route["limitations"]


def test_summary_removes_segment_payloads():
    result = build_route_expected_response_input(_workload(), _environment())
    summary = build_route_expected_response_input_summary(result)
    assert "segments" not in summary["routes"][0]
    assert summary["routes"][0]["segments_included"] is False
    assert result["routes"][0]["segments"]


def test_legacy_segments_alias_remains_supported():
    workload = _workload()
    route = workload["routes"][0]
    route["segments"] = route.pop("observations")

    result = build_route_expected_response_input(workload, _environment())

    assert result["routes"][0]["workload_segment_count"] == 2
    assert result["routes"][0]["aligned_usable_segment_count"] == 2


def test_production_observations_shape_is_used_for_workload_alignment():
    workload = _workload(segment_count=3)
    result = build_route_expected_response_input(
        workload,
        _environment(segment_count=3),
    )

    route = result["routes"][0]
    assert route["workload_segment_count"] == 3
    assert route["environment_usable_segment_count"] == 3
    assert route["aligned_usable_segment_count"] == 3
    assert route["status"] == STATUS_INCOMPLETE
    assert route["segments"][0]["external_workload"]["gps_ground_speed_mps"] == 2.5


def test_builder_does_not_mutate_inputs():
    workload = _workload()
    environment = _environment(
        route_status="TRUSTED_WITH_LIMITATIONS",
        segment_status="TRUSTED_WITH_LIMITATIONS",
        limitations=["MODELLED_GRIDDED_WEATHER"],
    )
    state = _state(traceability_gaps=["SLEEP_REFERENCE_MISSING"])
    binding = _binding()
    originals = tuple(deepcopy(item) for item in (workload, environment, state, binding))

    build_route_expected_response_input(
        workload,
        environment,
        athlete_state_context=state,
        athlete_state_binding=binding,
    )

    assert (workload, environment, state, binding) == originals
