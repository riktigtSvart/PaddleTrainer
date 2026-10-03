from copy import deepcopy

from app.services.route_workload_input import (
    REASON_TRUSTED_MOTION_SEGMENTS_UNAVAILABLE,
    SOURCE_BRANCH,
    build_route_workload_input,
    build_route_workload_input_summary,
)


def _trusted_normalized():
    return {
        "provider": "POLAR",
        "route_count": 1,
        "routes": [
            {
                "exercise_index": 0,
                "route_start_time": (
                    "2026-09-30T17:35:18.663"
                ),
                "exercise_start_time": (
                    "2026-09-30T17:35:18"
                ),
                "route_start_offset_ms": 663,
                "waypoint_count": 3,
                "points": [
                    {
                        "waypoint_index": 46,
                        "exercise_elapsed_ms": 129_763,
                    },
                    {
                        "waypoint_index": 47,
                        "exercise_elapsed_ms": 130_763,
                    },
                    {
                        "waypoint_index": 48,
                        "exercise_elapsed_ms": 131_763,
                    },
                ],
            }
        ],
    }


def _trusted_motion(
    *,
    include_segments=True,
):
    segments = (
        [
            {
                "segment_index": 46,
                "start_waypoint_index": 46,
                "end_waypoint_index": 47,
                "start_exercise_elapsed_ms": 129_763,
                "end_exercise_elapsed_ms": 130_763,
                "interval_ms": 1000,
                "surface_distance_m": 2.5,
                "initial_bearing_deg": 12.0,
                "gps_ground_speed_mps": 2.5,
                "motion_available": True,
                "reason": None,
            },
            {
                "segment_index": 47,
                "start_waypoint_index": 47,
                "end_waypoint_index": 48,
                "start_exercise_elapsed_ms": 130_763,
                "end_exercise_elapsed_ms": 131_763,
                "interval_ms": 1000,
                "surface_distance_m": 2.7,
                "initial_bearing_deg": 12.5,
                "gps_ground_speed_mps": 2.7,
                "motion_available": True,
                "reason": None,
            },
        ]
        if include_segments
        else []
    )

    return {
        "provider": "POLAR",
        "available": bool(
            segments
        ),
        "route_count": 1,
        "routes": [
            {
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }


def _trusted_summary(
    *,
    segment_count=2,
):
    return {
        "provider": "POLAR",
        "available": (
            segment_count > 0
        ),
        "route_count": 1,
        "routes": [
            {
                "exercise_index": 0,
                "segment_count": segment_count,
                "motion_segment_count": segment_count,
                "bearing_segment_count": segment_count,
                "zero_distance_segment_count": 0,
                "first_motion_start_elapsed_ms": (
                    129_763
                    if segment_count
                    else None
                ),
                "last_motion_end_elapsed_ms": (
                    131_763
                    if segment_count
                    else None
                ),
                "motion_span_ms": (
                    2_000
                    if segment_count
                    else None
                ),
                "total_surface_distance_m": (
                    5.2
                    if segment_count
                    else 0.0
                ),
                "total_positive_interval_ms": (
                    2_000
                    if segment_count
                    else 0
                ),
                "distance_over_time_ground_speed_mps": (
                    2.6
                    if segment_count
                    else None
                ),
                "minimum_segment_ground_speed_mps": (
                    2.5
                    if segment_count
                    else None
                ),
                "median_segment_ground_speed_mps": (
                    2.6
                    if segment_count
                    else None
                ),
                "maximum_segment_ground_speed_mps": (
                    2.7
                    if segment_count
                    else None
                ),
            }
        ],
    }


def _raw_summary():
    return {
        "provider": "POLAR",
        "available": True,
        "route_count": 1,
        "routes": [
            {
                "exercise_index": 0,
                "motion_segment_count": 48,
                "total_surface_distance_m": 124.4,
            }
        ],
    }


def _trust_boundary():
    return {
        "provider": "POLAR",
        "evidence_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "status": (
                    "VALIDATED_FORWARD_ANCHOR_AVAILABLE"
                ),
                "geometry_supported_usable_from_exercise_elapsed_ms": (
                    129_763
                ),
                "time_to_validated_forward_anchor_ms": (
                    56_000
                ),
                "segments_to_validated_forward_anchor": 46,
            }
        ],
    }


def _policy(
    *,
    action="EXCLUDE",
):
    return {
        "provider": "POLAR",
        "policy_version": "0.4",
        "profile": "BALANCED",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "action": action,
                "reason": (
                    "MULTI_DIMENSION_MATERIAL_EVIDENCE_WITHOUT_REQUIRED_ANCHORS"
                ),
                "scope": {
                    "type": "FIRST_ROUTE_WINDOW",
                    "expected_segment_indices": [
                        0, 1, 2, 3, 4
                    ],
                    "directive_applies_to_entire_route": False,
                },
            }
        ],
    }


def _trust_mask(
    *,
    mode="MASKED_BEFORE_TRUST_BOUNDARY",
):
    return {
        "provider": "POLAR",
        "view_version": "0.1",
        "routes": [
            {
                "exercise_index": 0,
                "trust_mask": {
                    "view_version": "0.1",
                    "action": "EXCLUDE",
                    "mode": mode,
                    "reason": (
                        "POLICY_ACTION_REQUIRES_MASKING_AND_TRUST_BOUNDARY_IS_AVAILABLE"
                    ),
                    "raw_data_mutated": False,
                    "original_point_count": 49,
                    "usable_point_count": 3,
                    "excluded_point_count": 46,
                    "applied_usable_from_exercise_elapsed_ms": (
                        129_763
                    ),
                },
            }
        ],
    }


def _speed_consistency():
    return {
        "provider": "POLAR",
        "available": True,
        "exercises": [
            {
                "exercise_index": 0,
                "available": True,
                "reason": None,
                "paired_segment_count": 2,
                "paired_fraction": 1.0,
                "first_paired_start_elapsed_ms": 129_763,
                "maximum_absolute_difference_mps": 0.2,
                "comparisons": [
                    {
                        "segment_index": 46,
                    }
                ],
            }
        ],
    }


def _build(
    *,
    include_segments=True,
    trusted_segment_count=2,
    action="EXCLUDE",
):
    return build_route_workload_input(
        _trusted_normalized(),
        _trusted_motion(
            include_segments=include_segments
        ),
        _trusted_summary(
            segment_count=trusted_segment_count
        ),
        _raw_summary(),
        _trust_boundary(),
        _policy(
            action=action
        ),
        _trust_mask(),
        speed_gps_consistency=(
            _speed_consistency()
        ),
        provider_distance_evidence={
            "value_m": 8_045.7,
            "scope": "TRAINING_SESSION",
            "source": (
                "PROVIDER_SESSION_SUMMARY"
            ),
        },
    )


def test_builds_official_trusted_route_workload_input():
    result = _build()

    route = result["routes"][0]

    assert result["source_branch"] == SOURCE_BRANCH
    assert result["available"] is True
    assert route["available"] is True
    assert route["usable_interval"] == {
        "start_exercise_elapsed_ms": 129_763,
        "end_exercise_elapsed_ms": 131_763,
        "span_ms": 2_000,
    }
    assert (
        route["counts"][
            "excluded_motion_segment_count"
        ]
        == 46
    )
    assert (
        route[
            "quality_provenance"
        ][
            "trust_mask"
        ][
            "applied_usable_from_exercise_elapsed_ms"
        ]
        == 129_763
    )


def test_keeps_provider_raw_and_trusted_distance_separate():
    route = _build()["routes"][0]

    assert route["distance_evidence"] == {
        "provider_reported": {
            "value_m": 8_045.7,
            "scope": "TRAINING_SESSION",
            "source": (
                "PROVIDER_SESSION_SUMMARY"
            ),
        },
        "raw_gps_surface_distance_m": 124.4,
        "trusted_gps_surface_distance_m": 5.2,
    }


def test_motion_segments_are_copied_without_recomputation():
    trusted_motion = _trusted_motion()
    original = deepcopy(
        trusted_motion
    )

    result = build_route_workload_input(
        _trusted_normalized(),
        trusted_motion,
        _trusted_summary(),
        _raw_summary(),
        _trust_boundary(),
        _policy(),
        _trust_mask(),
    )

    assert (
        result["routes"][0][
            "motion_segments"
        ]
        == original["routes"][0][
            "segments"
        ]
    )

    result["routes"][0][
        "motion_segments"
    ][0][
        "gps_ground_speed_mps"
    ] = 999.0

    assert trusted_motion == original


def test_cross_source_consistency_is_summary_only():
    route = _build()["routes"][0]

    consistency = route[
        "cross_source_speed_consistency"
    ]

    assert consistency[
        "paired_segment_count"
    ] == 2
    assert "comparisons" not in consistency


def test_no_trusted_segments_is_explicitly_unavailable():
    result = _build(
        include_segments=False,
        trusted_segment_count=0,
    )

    route = result["routes"][0]

    assert result["available"] is False
    assert route["available"] is False
    assert (
        route["reason"]
        == REASON_TRUSTED_MOTION_SEGMENTS_UNAVAILABLE
    )
    assert route["motion_segments"] == []


def test_policy_action_is_provenance_not_redecided():
    route = _build(
        action="REVIEW"
    )["routes"][0]

    assert (
        route[
            "quality_provenance"
        ][
            "artifact_policy"
        ][
            "action"
        ]
        == "REVIEW"
    )

    assert (
        route[
            "quality_provenance"
        ][
            "artifact_policy"
        ][
            "policy_version"
        ]
        == "0.4"
    )


def test_scope_explicitly_performs_no_detection_smoothing_or_reconstruction():
    result = _build()

    assert result["scope"] == {
        "purpose": (
            "ROUTE_DERIVED_EXTERNAL_WORKLOAD_INPUT"
        ),
        "raw_data_mutated": False,
        "performs_artifact_detection": False,
        "performs_reconstruction": False,
        "performs_smoothing": False,
    }


def test_summary_strips_motion_segment_payload():
    result = _build()

    summary = (
        build_route_workload_input_summary(
            result
        )
    )

    route = summary["routes"][0]

    assert "motion_segments" not in route
    assert (
        route[
            "motion_segments_included"
        ]
        is False
    )
    assert (
        route[
            "motion_segment_payload_count"
        ]
        == 2
    )
