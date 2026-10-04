from copy import deepcopy

import pytest

from app.services.route_external_workload_evidence import (
    REASON_WORKLOAD_INPUT_UNAVAILABLE,
    SCOPE_ROUTE_GROUND_MOTION,
    build_route_external_workload_evidence,
    build_route_external_workload_evidence_summary,
)


def _workload_input(
    *,
    available=True,
):
    return {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": available,
        "source_branch": (
            "TRUSTED_ROUTE_VIEW"
        ),
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": available,
                "reason": None,
                "usable_interval": {
                    "start_exercise_elapsed_ms": (
                        129_763
                    ),
                    "end_exercise_elapsed_ms": (
                        133_763
                    ),
                    "span_ms": 4_000,
                },
                "distance_evidence": {
                    "provider_reported": {
                        "value_m": 8_045.7,
                    },
                    "raw_gps_surface_distance_m": (
                        8_060.8
                    ),
                    "trusted_gps_surface_distance_m": (
                        10.0
                    ),
                },
                "quality_provenance": {
                    "artifact_policy": {
                        "action": "EXCLUDE",
                    },
                    "trust_mask": {
                        "mode": (
                            "MASKED_BEFORE_TRUST_BOUNDARY"
                        ),
                    },
                },
                "motion_segments": (
                    [
                        {
                            "segment_index": 46,
                            "start_waypoint_index": 46,
                            "end_waypoint_index": 47,
                            "start_exercise_elapsed_ms": (
                                129_763
                            ),
                            "end_exercise_elapsed_ms": (
                                130_763
                            ),
                            "interval_ms": 1_000,
                            "surface_distance_m": 2.0,
                            "initial_bearing_deg": 350.0,
                            "gps_ground_speed_mps": 2.0,
                            "motion_available": True,
                            "reason": None,
                        },
                        {
                            "segment_index": 47,
                            "start_waypoint_index": 47,
                            "end_waypoint_index": 48,
                            "start_exercise_elapsed_ms": (
                                130_763
                            ),
                            "end_exercise_elapsed_ms": (
                                131_763
                            ),
                            "interval_ms": 1_000,
                            "surface_distance_m": 3.0,
                            "initial_bearing_deg": 10.0,
                            "gps_ground_speed_mps": 3.0,
                            "motion_available": True,
                            "reason": None,
                        },
                        {
                            "segment_index": 48,
                            "start_waypoint_index": 48,
                            "end_waypoint_index": 49,
                            "start_exercise_elapsed_ms": (
                                131_763
                            ),
                            "end_exercise_elapsed_ms": (
                                133_763
                            ),
                            "interval_ms": 2_000,
                            "surface_distance_m": 5.0,
                            "initial_bearing_deg": 20.0,
                            "gps_ground_speed_mps": 2.5,
                            "motion_available": True,
                            "reason": None,
                        },
                    ]
                    if available
                    else []
                ),
            }
        ],
    }


def test_builds_environment_unadjusted_ground_motion_evidence():
    result = (
        build_route_external_workload_evidence(
            _workload_input()
        )
    )

    assert result["available"] is True
    assert result["scope"] == {
        "domain": (
            SCOPE_ROUTE_GROUND_MOTION
        ),
        "environment_adjusted": False,
        "estimates_physiological_load": False,
        "estimates_energy_expenditure": False,
        "estimates_athlete_effort": False,
        "ground_speed_semantics": (
            "SPEED_OVER_GROUND"
        ),
        "ground_speed_change_rate_semantics": (
            "FINITE_DIFFERENCE_OF_ADJACENT_SEGMENT_AVERAGE_GROUND_SPEEDS"
        ),
        "raw_data_mutated": False,
    }


def test_preserves_trusted_segment_indices_and_timing():
    route = (
        build_route_external_workload_evidence(
            _workload_input()
        )["routes"][0]
    )

    observations = route["observations"]

    assert [
        item["segment_index"]
        for item in observations
    ] == [46, 47, 48]

    assert (
        observations[0][
            "start_exercise_elapsed_ms"
        ]
        == 129_763
    )


def test_calculates_speed_change_only_across_source_contiguous_segments():
    route = (
        build_route_external_workload_evidence(
            _workload_input()
        )["routes"][0]
    )

    observations = route["observations"]

    assert (
        observations[0][
            "ground_speed_change_from_previous_mps"
        ]
        is None
    )

    assert (
        observations[1][
            "source_contiguous_with_previous"
        ]
        is True
    )
    assert (
        observations[1][
            "ground_speed_change_from_previous_mps"
        ]
        == pytest.approx(
            1.0
        )
    )
    assert (
        observations[1][
            "ground_speed_change_rate_mps2"
        ]
        == pytest.approx(
            1.0
        )
    )

    # Segment-average speeds are separated by 1.5 s between
    # midpoints because the second interval is 1 s and the third 2 s.
    assert (
        observations[2][
            "segment_midpoint_separation_from_previous_ms"
        ]
        == pytest.approx(
            1_500.0
        )
    )
    assert (
        observations[2][
            "ground_speed_change_rate_mps2"
        ]
        == pytest.approx(
            -0.5 / 1.5
        )
    )


def test_bearing_change_uses_smallest_circular_separation():
    route = (
        build_route_external_workload_evidence(
            _workload_input()
        )["routes"][0]
    )

    observations = route["observations"]

    assert (
        observations[1][
            "absolute_bearing_change_from_previous_deg"
        ]
        == pytest.approx(
            20.0
        )
    )


def test_summary_is_descriptive_and_matches_trusted_segments():
    route = (
        build_route_external_workload_evidence(
            _workload_input()
        )["routes"][0]
    )

    summary = route["summary"]

    assert (
        summary[
            "observation_count"
        ]
        == 3
    )
    assert (
        summary[
            "source_contiguous_transition_count"
        ]
        == 2
    )
    assert (
        summary[
            "ground_speed_change_rate_observation_count"
        ]
        == 2
    )
    assert (
        summary[
            "total_surface_distance_m"
        ]
        == pytest.approx(
            10.0
        )
    )
    assert (
        summary[
            "total_positive_interval_ms"
        ]
        == 4_000
    )
    assert (
        summary[
            "distance_over_positive_interval_mps"
        ]
        == pytest.approx(
            2.5
        )
    )


def test_does_not_mutate_route_workload_input():
    source = _workload_input()
    original = deepcopy(
        source
    )

    result = (
        build_route_external_workload_evidence(
            source
        )
    )

    result["routes"][0][
        "observations"
    ][0][
        "gps_ground_speed_mps"
    ] = 999.0

    assert source == original


def test_unavailable_route_workload_input_is_explicit():
    result = (
        build_route_external_workload_evidence(
            _workload_input(
                available=False
            )
        )
    )

    route = result["routes"][0]

    assert result["available"] is False
    assert route["available"] is False
    assert (
        route["reason"]
        == REASON_WORKLOAD_INPUT_UNAVAILABLE
    )
    assert route["observations"] == []


def test_summary_strips_observation_payload():
    evidence = (
        build_route_external_workload_evidence(
            _workload_input()
        )
    )

    summary = (
        build_route_external_workload_evidence_summary(
            evidence
        )
    )

    route = summary["routes"][0]

    assert "observations" not in route
    assert (
        route[
            "observations_included"
        ]
        is False
    )
    assert (
        route[
            "observation_payload_count"
        ]
        == 3
    )
