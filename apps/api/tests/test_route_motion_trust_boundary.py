from app.services.route_motion_trust_boundary import (
    build_route_motion_trust_boundary_evidence,
    build_trust_boundary_policy_context,
)


def _startup(
    *,
    first_waypoint_ms=73_763,
    available=True,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": available,
                "first_route_waypoint_exercise_elapsed_ms": (
                    first_waypoint_ms
                ),
                "expected_segment_indices": [
                    0, 1, 2, 3, 4
                ],
            }
        ],
    }


def _forward(
    *,
    available=True,
    segment_index=46,
    waypoint_index=46,
    elapsed_ms=129_763,
):
    return {
        "provider": "POLAR",
        "criteria_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "criteria_version": "0.1",
                "validated_forward_anchor_available": (
                    available
                ),
                "anchor": (
                    {
                        "segment_index": segment_index,
                        "waypoint_index": waypoint_index,
                        "exercise_elapsed_ms": elapsed_ms,
                    }
                    if available
                    else None
                ),
            }
        ],
    }


def test_boundary_describes_unvalidated_prefix_to_anchor():
    result = (
        build_route_motion_trust_boundary_evidence(
            _startup(),
            _forward(),
        )
    )

    route = result["routes"][0]

    assert route["available"] is True
    assert (
        route[
            "geometry_supported_usable_from_exercise_elapsed_ms"
        ]
        == 129_763
    )
    assert (
        route[
            "time_to_validated_forward_anchor_ms"
        ]
        == 56_000
    )
    assert (
        route[
            "segments_to_validated_forward_anchor"
        ]
        == 46
    )
    assert route["unvalidated_prefix"] == {
        "start_exercise_elapsed_ms": 73_763,
        "end_exercise_elapsed_ms": 129_763,
        "end_semantics": "EXCLUSIVE",
        "duration_ms": 56_000,
        "classification": "UNVALIDATED_PREFIX",
        "does_not_assert_every_point_is_erroneous": True,
    }


def test_0927_like_boundary_has_11_second_prefix():
    result = (
        build_route_motion_trust_boundary_evidence(
            _startup(
                first_waypoint_ms=80_729
            ),
            _forward(
                segment_index=11,
                waypoint_index=11,
                elapsed_ms=91_729,
            ),
        )
    )

    route = result["routes"][0]

    assert (
        route[
            "time_to_validated_forward_anchor_ms"
        ]
        == 11_000
    )
    assert (
        route[
            "segments_to_validated_forward_anchor"
        ]
        == 11
    )


def test_no_forward_anchor_emits_no_usable_from_boundary():
    result = (
        build_route_motion_trust_boundary_evidence(
            _startup(),
            _forward(
                available=False
            ),
        )
    )

    route = result["routes"][0]

    assert route["available"] is False
    assert (
        route["status"]
        == "VALIDATED_FORWARD_ANCHOR_UNAVAILABLE"
    )
    assert (
        route[
            "geometry_supported_usable_from_exercise_elapsed_ms"
        ]
        is None
    )
    assert route["unvalidated_prefix"] is None


def test_anchor_before_first_waypoint_is_not_accepted():
    result = (
        build_route_motion_trust_boundary_evidence(
            _startup(
                first_waypoint_ms=10_000
            ),
            _forward(
                elapsed_ms=9_000
            ),
        )
    )

    route = result["routes"][0]

    assert route["available"] is False
    assert (
        route[
            "geometry_supported_usable_from_exercise_elapsed_ms"
        ]
        is None
    )


def test_unavailable_startup_evidence_is_explicit():
    result = (
        build_route_motion_trust_boundary_evidence(
            _startup(
                available=False
            ),
            _forward(),
        )
    )

    route = result["routes"][0]

    assert route["available"] is False
    assert (
        route["status"]
        == "STARTUP_EVIDENCE_UNAVAILABLE"
    )
    assert (
        route[
            "validated_forward_anchor_available"
        ]
        is None
    )


def test_scope_does_not_claim_physiological_validity():
    result = (
        build_route_motion_trust_boundary_evidence(
            _startup(),
            _forward(),
        )
    )

    assert result["scope"] == {
        "domain": "ROUTE_GEOMETRY",
        "does_not_assert_physiological_validity": True,
        "does_not_mutate_route_data": True,
    }


def test_policy_context_carries_boundary_metadata():
    evidence = (
        build_route_motion_trust_boundary_evidence(
            _startup(
                first_waypoint_ms=80_729
            ),
            _forward(
                segment_index=11,
                waypoint_index=11,
                elapsed_ms=91_729,
            ),
        )
    )

    context = (
        build_trust_boundary_policy_context(
            evidence
        )
    )

    assert context == {
        0: {
            "forward_anchor_available": True,
            "forward_anchor_exercise_elapsed_ms": 91_729,
            "geometry_supported_usable_from_exercise_elapsed_ms": 91_729,
            "time_to_validated_forward_anchor_ms": 11_000,
            "segments_to_validated_forward_anchor": 11,
            "trust_boundary_status": (
                "VALIDATED_FORWARD_ANCHOR_AVAILABLE"
            ),
        }
    }
