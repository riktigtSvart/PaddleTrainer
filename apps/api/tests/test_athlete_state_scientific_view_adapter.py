from copy import deepcopy

from app.services.athlete_state_scientific_view_adapter import (
    build_athlete_state_candidate_from_scientific_view,
    build_athlete_state_candidates_from_scientific_views,
    build_athlete_state_temporal_binding_from_scientific_views,
)
from app.services.athlete_state_temporal_binding import (
    STATUS_BOUND,
    STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE,
)
from app.services.route_expected_response_input import (
    STATUS_READY_WITH_LIMITATIONS,
    build_route_expected_response_input,
)


def _view(**overrides):
    value = {
        "schema_version": "0.1",
        "available": True,
        "state_timestamp": "2026-09-30T07:00:00+02:00",
        "training_load": {"available": True},
        "readiness_evidence": {"available": True},
        "capacity": [{"capacity_type": "GENERAL_AEROBIC", "value": 68.2}],
        "traceability_gaps": ["RESTING_HR_REFERENCE_MISSING"],
    }
    value.update(overrides)
    return value


def _workload():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "observations": [
                    {"order_index": 0, "gps_ground_speed_mps": 2.5}
                ],
            }
        ],
    }


def _environment():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "TRUSTED_WITH_LIMITATIONS",
                "route_limitations": ["MODELLED_GRIDDED_WEATHER"],
                "segments": [
                    {
                        "order_index": 0,
                        "status": "TRUSTED_WITH_LIMITATIONS",
                        "usable_for_downstream_environment_context": True,
                        "limitations": ["MODELLED_GRIDDED_WEATHER"],
                    }
                ],
            }
        ],
    }


def test_adapter_preserves_entire_scientific_view_as_context():
    view = _view()
    candidate = build_athlete_state_candidate_from_scientific_view(view)
    assert candidate["context"] == view
    assert candidate["context"] is not view
    assert candidate["available"] is True


def test_top_level_state_timestamp_is_used_without_component_timestamp_inference():
    candidate = build_athlete_state_candidate_from_scientific_view(_view())
    assert candidate["state_timestamp"] == "2026-09-30T07:00:00+02:00"
    assert candidate["source"]["timestamp_source"] == "state_timestamp"
    assert candidate["adapter_provenance"][
        "whole_view_timestamp_inferred_from_components"
    ] is False


def test_explicit_timestamp_can_anchor_view_when_top_level_anchor_missing():
    view = _view()
    view.pop("state_timestamp")
    candidate = build_athlete_state_candidate_from_scientific_view(
        view,
        state_timestamp="2026-09-30T07:00:00+02:00",
    )
    assert candidate["available"] is True
    assert candidate["source"]["timestamp_source"] == "EXPLICIT_ADAPTER_METADATA"


def test_missing_whole_view_temporal_anchor_is_not_promoted_to_available():
    view = _view()
    view.pop("state_timestamp")
    view["readiness_evidence"] = {
        "available": True,
        "observed_at": "2026-09-30T06:30:00+02:00",
    }
    candidate = build_athlete_state_candidate_from_scientific_view(view)
    assert candidate["available"] is False
    assert candidate["state_timestamp"] is None
    assert "ATHLETE_STATE_VIEW_TEMPORAL_ANCHOR_UNAVAILABLE" in candidate[
        "limitations"
    ]


def test_conflicting_explicit_and_source_timestamps_are_withheld():
    candidate = build_athlete_state_candidate_from_scientific_view(
        _view(),
        state_timestamp="2026-09-30T06:00:00+02:00",
    )
    assert candidate["available"] is False
    assert candidate["adapter_provenance"]["timestamp_conflict"] is True
    assert "ATHLETE_STATE_TIMESTAMP_CONFLICT" in candidate["limitations"]


def test_semantically_equal_timestamps_with_different_offsets_do_not_conflict():
    candidate = build_athlete_state_candidate_from_scientific_view(
        _view(state_timestamp="2026-09-30T05:00:00+00:00"),
        state_timestamp="2026-09-30T07:00:00+02:00",
    )
    assert candidate["available"] is True
    assert candidate["adapter_provenance"]["timestamp_conflict"] is False


def test_traceability_gaps_are_preserved_for_v22_limitations():
    binding = build_athlete_state_temporal_binding_from_scientific_views(
        "2026-09-30T08:00:00+02:00",
        [{"scientific_view": _view()}],
    )
    assert binding["status"] == STATUS_BOUND
    assert "RESTING_HR_REFERENCE_MISSING" in binding["limitations"]


def test_future_scientific_view_is_rejected_by_v22_policy():
    binding = build_athlete_state_temporal_binding_from_scientific_views(
        "2026-09-30T08:00:00+02:00",
        [
            {
                "scientific_view": _view(
                    state_timestamp="2026-09-30T09:00:00+02:00"
                )
            }
        ],
    )
    assert binding["status"] == STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE
    assert binding["bound"] is False


def test_multiple_views_use_latest_eligible_non_future_snapshot():
    binding = build_athlete_state_temporal_binding_from_scientific_views(
        "2026-09-30T08:00:00+02:00",
        [
            {
                "snapshot_id": "older",
                "scientific_view": _view(
                    state_timestamp="2026-09-29T20:00:00+02:00"
                ),
            },
            {
                "snapshot_id": "latest",
                "scientific_view": _view(
                    state_timestamp="2026-09-30T07:00:00+02:00"
                ),
            },
        ],
    )
    assert binding["status"] == STATUS_BOUND
    assert binding["selected_snapshot"]["snapshot_id"] == "latest"


def test_adapter_does_not_synthesize_readiness_into_athlete_state():
    candidate = build_athlete_state_candidate_from_scientific_view(_view())
    assert candidate["source"]["view"] == "ATHLETE_STATE_SCIENTIFIC_VIEW"
    assert "readiness_score" not in candidate
    assert candidate["context"]["readiness_evidence"] == {"available": True}


def test_adapter_does_not_mutate_source_view():
    view = _view()
    original = deepcopy(view)
    build_athlete_state_candidate_from_scientific_view(view)
    assert view == original


def test_non_mapping_scientific_views_are_ignored_in_batch_adapter():
    candidates = build_athlete_state_candidates_from_scientific_views(
        [
            {"scientific_view": _view()},
            {"scientific_view": None},
            "bad",
        ]
    )
    assert len(candidates) == 1


def test_bound_scientific_view_makes_v21_route_model_ready_with_limitations():
    binding = build_athlete_state_temporal_binding_from_scientific_views(
        "2026-09-30T08:00:00+02:00",
        [{"scientific_view": _view()}],
    )
    result = build_route_expected_response_input(
        _workload(),
        _environment(),
        athlete_state_context=binding["athlete_state_context"],
        athlete_state_binding=binding,
    )
    assert result["status"] == STATUS_READY_WITH_LIMITATIONS
    assert result["model_ready_route_count"] == 1
    assert result["athlete_state"]["status"] == "BOUND"


def test_source_adapter_metadata_is_exposed_on_binding():
    binding = build_athlete_state_temporal_binding_from_scientific_views(
        "2026-09-30T08:00:00+02:00",
        [{"scientific_view": _view()}],
    )
    assert binding["source_adapter"]["source_view"] == "ATHLETE_STATE_SCIENTIFIC_VIEW"
    assert binding["source_adapter"]["builds_athlete_state"] is False
    assert binding["source_adapter"][
        "synthesizes_readiness_into_athlete_state"
    ] is False


def test_actual_scientific_view_inventory_gaps_are_preserved():
    view = {
        "as_of_date": "2026-09-29",
        "training_load": {},
        "recovery_readiness": {},
        "evidence_inventory": {
            "gaps": ["ILLNESS_STATUS_UNKNOWN", "TRAVEL_STATUS_UNKNOWN"],
            "traceability": {"state": "METRIC_PROVENANCE_UNAVAILABLE"},
        },
        "capacity": {"available": False, "items": [], "evidence": []},
    }
    candidate = build_athlete_state_candidate_from_scientific_view(
        view,
        state_timestamp="2026-09-30T00:00:00+02:00",
    )
    assert candidate["traceability_gaps"] == [
        "ILLNESS_STATUS_UNKNOWN",
        "TRAVEL_STATUS_UNKNOWN",
    ]
    assert candidate["adapter_provenance"][
        "scientific_evidence_inventory_gaps_preserved"
    ] is True


def test_as_of_date_is_not_promoted_to_whole_state_timestamp():
    view = {
        "as_of_date": "2026-09-29",
        "evidence_inventory": {"gaps": []},
        "capacity": {"available": False, "items": [], "evidence": []},
    }
    candidate = build_athlete_state_candidate_from_scientific_view(view)
    assert candidate["state_timestamp"] is None
    assert candidate["available"] is False
    assert candidate["source"]["source_view_timestamp_field"] is None
