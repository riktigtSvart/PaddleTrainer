from copy import deepcopy

import pytest

from app.services.route_motion_artifact_policy import (
    ACTION_EXCLUDE,
    ACTION_OBSERVE,
    ACTION_RECONSTRUCT,
    ACTION_REVIEW,
    ACTION_SUPPRESS,
    build_route_motion_artifact_policy,
)


def _route(
    *,
    available=True,
    first_waypoint_ms=3_000,
    speed_range=0.5,
    peak_drop=0.0,
    sign_reversals=0,
    cross_track=0.05,
    path_minus_net=0.02,
    cancellation=0.2,
    cross_source_difference=0.5,
):
    return {
        "route_index": 0,
        "exercise_index": 0,
        "available": available,
        "first_route_waypoint_exercise_elapsed_ms": (
            first_waypoint_ms
        ),
        "trajectory_summary": {
            "gps_ground_speed_range_mps": speed_range,
            "peak_to_last_drop_fraction_of_speed_range": (
                peak_drop
            ),
            "speed_change_sign_reversal_count": (
                sign_reversals
            ),
        },
        "geometry": {
            "maximum_middle_point_cross_track_deviation_m": (
                cross_track
            ),
            "path_minus_net_displacement_sum_m": (
                path_minus_net
            ),
        },
        "temporal_residual": {
            "window_residual_cancellation_fraction": (
                cancellation
            ),
        },
        "cross_source_speed": {
            "maximum_absolute_gps_polar_speed_difference_mps": (
                cross_source_difference
            ),
        },
    }


def _evidence(route):
    return {
        "provider": "POLAR",
        "routes": [route],
    }


def test_clean_balanced_evidence_is_observe():
    result = build_route_motion_artifact_policy(
        _evidence(_route())
    )

    policy = result["routes"][0]

    assert policy["action"] == ACTION_OBSERVE
    assert policy["supporting_dimensions"] == []


def test_balanced_single_temporal_low_materiality_is_suppress():
    result = build_route_motion_artifact_policy(
        _evidence(
            _route(
                speed_range=1.2,
                peak_drop=0.65,
                sign_reversals=2,
                cancellation=0.94,
                cross_track=0.44,
                path_minus_net=0.28,
                cross_source_difference=1.76,
            )
        )
    )

    policy = result["routes"][0]

    assert policy["supporting_dimensions"] == [
        "TEMPORAL"
    ]
    assert policy["materiality"]["supported"] is False
    assert policy["action"] == ACTION_SUPPRESS


def test_two_dimensions_are_review():
    result = build_route_motion_artifact_policy(
        _evidence(
            _route(
                speed_range=3.0,
                peak_drop=1.0,
                sign_reversals=3,
                cancellation=0.90,
                cross_track=1.0,
                path_minus_net=0.6,
                cross_source_difference=1.0,
            )
        )
    )

    policy = result["routes"][0]

    assert set(policy["supporting_dimensions"]) == {
        "GEOMETRY",
        "TEMPORAL",
    }
    assert policy["action"] == ACTION_REVIEW


def test_three_material_dimensions_without_anchors_are_exclude():
    result = build_route_motion_artifact_policy(
        _evidence(
            _route(
                first_waypoint_ms=80_729,
                speed_range=3.52,
                peak_drop=1.0,
                sign_reversals=3,
                cross_track=1.135,
                path_minus_net=0.631,
                cancellation=0.878,
                cross_source_difference=4.092,
            )
        )
    )

    policy = result["routes"][0]

    assert policy["context"]["late_route_start"] is True
    assert set(policy["supporting_dimensions"]) == {
        "GEOMETRY",
        "TEMPORAL",
        "CROSS_SOURCE",
    }
    assert policy["action"] == ACTION_EXCLUDE
    assert (
        policy["reconstruction_eligibility"]["eligible"]
        is False
    )


def test_three_material_dimensions_with_anchors_are_reconstruct():
    result = build_route_motion_artifact_policy(
        _evidence(
            _route(
                speed_range=8.0,
                peak_drop=1.0,
                sign_reversals=3,
                cross_track=2.0,
                path_minus_net=2.0,
                cancellation=0.95,
                cross_source_difference=6.0,
            )
        ),
        reconstruction_context_by_route_index={
            0: {
                "backward_anchor_available": True,
                "forward_anchor_available": True,
            }
        },
    )

    assert (
        result["routes"][0]["action"]
        == ACTION_RECONSTRUCT
    )


def test_unavailable_evidence_is_observe():
    result = build_route_motion_artifact_policy(
        _evidence(
            _route(available=False)
        )
    )

    assert result["routes"][0]["action"] == ACTION_OBSERVE
    assert (
        result["routes"][0]["reason"]
        == "EVIDENCE_UNAVAILABLE"
    )


def test_custom_profile_can_change_thresholds():
    result = build_route_motion_artifact_policy(
        _evidence(
            _route(
                cross_track=0.2,
                path_minus_net=0.05,
            )
        ),
        profile="CUSTOM",
        custom_thresholds={
            "geometry_cross_track_m": 0.1,
            "material_cross_track_m": 0.1,
        },
    )

    policy = result["routes"][0]

    assert policy["supporting_dimensions"] == [
        "GEOMETRY"
    ]
    assert policy["action"] == ACTION_REVIEW


def test_unknown_profile_is_rejected():
    with pytest.raises(
        ValueError,
        match="profile must be one of",
    ):
        build_route_motion_artifact_policy(
            _evidence(_route()),
            profile="UNKNOWN",
        )


def test_policy_does_not_mutate_evidence():
    evidence = _evidence(
        _route(
            speed_range=3.0,
            peak_drop=1.0,
            sign_reversals=2,
        )
    )
    before = deepcopy(evidence)

    build_route_motion_artifact_policy(
        evidence
    )

    assert evidence == before


def test_policy_scope_is_first_route_window_not_entire_route():
    route = _route(
        first_waypoint_ms=80_729,
        speed_range=3.52,
        peak_drop=1.0,
        sign_reversals=3,
        cross_track=1.135,
        path_minus_net=0.631,
        cancellation=0.878,
        cross_source_difference=4.092,
    )
    route["expected_segment_indices"] = [0, 1, 2, 3, 4]
    route["startup_window_start_exercise_elapsed_ms"] = 80_729
    route["startup_window_end_exercise_elapsed_ms"] = 85_730

    result = build_route_motion_artifact_policy(
        _evidence(route),
        profile="BALANCED",
    )

    policy = result["routes"][0]

    assert policy["action"] == ACTION_EXCLUDE
    assert policy["scope"] == {
        "type": "FIRST_ROUTE_WINDOW",
        "expected_segment_indices": [0, 1, 2, 3, 4],
        "window_start_exercise_elapsed_ms": 80_729,
        "window_end_exercise_elapsed_ms": 85_730,
        "directive_applies_to_entire_route": False,
    }


def test_first_route_window_anchor_states_distinguish_false_from_unknown():
    route = _route(
        speed_range=3.52,
        peak_drop=1.0,
        sign_reversals=3,
        cross_track=1.135,
        path_minus_net=0.631,
        cancellation=0.878,
        cross_source_difference=4.092,
    )
    route["expected_segment_indices"] = [0, 1, 2, 3, 4]

    result = build_route_motion_artifact_policy(
        _evidence(route),
        profile="BALANCED",
    )

    eligibility = result["routes"][0][
        "reconstruction_eligibility"
    ]

    assert eligibility["backward_anchor_available"] is False
    assert eligibility["forward_anchor_available"] is None
    assert eligibility["eligible"] is False
