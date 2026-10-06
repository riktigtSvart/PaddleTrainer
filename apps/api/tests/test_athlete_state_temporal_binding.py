from copy import deepcopy

from app.services.athlete_state_temporal_binding import (
    CANDIDATE_FUTURE,
    CANDIDATE_INVALID_TIMESTAMP,
    CANDIDATE_TOO_OLD,
    STATUS_AMBIGUOUS,
    STATUS_BOUND,
    STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE,
    STATUS_NOT_BOUND,
    athlete_state_context_from_binding,
    build_athlete_state_temporal_binding,
    build_athlete_state_temporal_binding_summary,
)
from app.services.route_expected_response_input import (
    STATUS_READY_WITH_LIMITATIONS,
    build_route_expected_response_input,
)


def _candidate(
    timestamp="2026-09-30T06:00:00+02:00",
    *,
    snapshot_id="state-1",
    context=None,
    traceability_gaps=None,
):
    return {
        "snapshot_id": snapshot_id,
        "schema_version": "0.1",
        "state_timestamp": timestamp,
        "available": True,
        "source": {"provider": "PADDLETRAINER", "view": "SCIENTIFIC_ATHLETE_STATE"},
        "traceability_gaps": list(traceability_gaps or []),
        "context": context
        or {
            "schema_version": "0.1",
            "training_load": {"available": True},
            "traceability_gaps": list(traceability_gaps or []),
        },
    }


def _workload():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "observations": [{"order_index": 0, "gps_ground_speed_mps": 2.5}],
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


def test_no_candidates_is_not_bound():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [],
    )
    assert result["status"] == STATUS_NOT_BOUND
    assert result["bound"] is False


def test_latest_non_future_candidate_within_policy_is_bound():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [
            _candidate("2026-09-29T20:00:00+02:00", snapshot_id="older"),
            _candidate("2026-09-30T07:00:00+02:00", snapshot_id="latest"),
        ],
    )
    assert result["status"] == STATUS_BOUND
    assert result["selected_snapshot"]["snapshot_id"] == "latest"
    assert result["selected_snapshot"]["age_seconds"] == 3600.0
    assert result["selected_snapshot"]["carried_forward"] is True


def test_future_candidate_is_rejected():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [_candidate("2026-09-30T09:00:00+02:00")],
    )
    assert result["status"] == STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE
    assert result["evaluated_candidates"][0]["eligibility_status"] == CANDIDATE_FUTURE


def test_candidate_older_than_policy_is_rejected():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [_candidate("2026-09-28T08:00:00+02:00")],
        max_carry_forward_seconds=24 * 60 * 60,
    )
    assert result["status"] == STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE
    assert result["evaluated_candidates"][0]["eligibility_status"] == CANDIDATE_TOO_OLD


def test_timezone_unaware_candidate_is_rejected_instead_of_assuming_timezone():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [_candidate("2026-09-30T07:00:00")],
    )
    assert result["status"] == STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE
    assert (
        result["evaluated_candidates"][0]["eligibility_status"]
        == CANDIDATE_INVALID_TIMESTAMP
    )


def test_timezone_unaware_target_is_insufficient_temporal_evidence():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00",
        [_candidate()],
    )
    assert result["status"] == STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE
    assert result["target_timestamp"] is None


def test_distinct_candidates_at_same_latest_timestamp_are_ambiguous():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [
            _candidate(
                "2026-09-30T07:00:00+02:00",
                snapshot_id="a",
                context={"schema_version": "0.1", "training_load": {"value": 1}},
            ),
            _candidate(
                "2026-09-30T07:00:00+02:00",
                snapshot_id="b",
                context={"schema_version": "0.1", "training_load": {"value": 2}},
            ),
        ],
    )
    assert result["status"] == STATUS_AMBIGUOUS
    assert result["bound"] is False


def test_semantic_duplicate_at_same_timestamp_is_collapsed():
    a = _candidate("2026-09-30T07:00:00+02:00", snapshot_id="a")
    b = deepcopy(a)
    b["snapshot_id"] = "b"
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [a, b],
    )
    assert result["status"] == STATUS_BOUND


def test_traceability_gaps_and_carry_forward_are_preserved_as_limitations():
    result = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [_candidate(traceability_gaps=["HRV_REFERENCE_MISSING"])],
    )
    assert "HRV_REFERENCE_MISSING" in result["limitations"]
    assert "ATHLETE_STATE_CARRIED_FORWARD_WITHIN_BINDING_POLICY" in result[
        "limitations"
    ]
    assert "ATHLETE_STATE_COMPONENT_SPECIFIC_RECENCY_NOT_ESTABLISHED" in result[
        "limitations"
    ]


def test_bound_context_integrates_with_v21_expected_response_contract():
    binding = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [_candidate()],
    )
    state = athlete_state_context_from_binding(binding)

    result = build_route_expected_response_input(
        _workload(),
        _environment(),
        athlete_state_context=state,
        athlete_state_binding=binding,
    )

    assert result["status"] == STATUS_READY_WITH_LIMITATIONS
    assert result["model_ready_route_count"] == 1
    assert result["athlete_state"]["status"] == "BOUND"
    assert "ATHLETE_STATE_CARRIED_FORWARD_WITHIN_BINDING_POLICY" in result[
        "routes"
    ][0]["limitations"]


def test_summary_omits_bound_athlete_state_context():
    binding = build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        [_candidate()],
    )
    summary = build_athlete_state_temporal_binding_summary(binding)
    assert "athlete_state_context" not in summary
    assert summary["athlete_state_context_included"] is False


def test_builder_does_not_mutate_candidate_input():
    candidates = [_candidate()]
    original = deepcopy(candidates)
    build_athlete_state_temporal_binding(
        "2026-09-30T08:00:00+02:00",
        candidates,
    )
    assert candidates == original
