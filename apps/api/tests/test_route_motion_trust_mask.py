from copy import deepcopy

from app.services.route_motion_trust_mask import (
    MODE_MASKED_BEFORE_TRUST_BOUNDARY,
    MODE_UNAVAILABLE_NO_TRUST_BOUNDARY,
    MODE_UNCHANGED,
    build_route_motion_trust_mask,
    build_route_motion_trust_mask_summary,
)


def _normalized():
    return {
        "provider": "POLAR",
        "exercise_count": 1,
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
                "waypoint_count": 6,
                "points": [
                    {
                        "waypoint_index": index,
                        "source_elapsed_ms": (
                            1000 + index * 1000
                        ),
                        "exercise_elapsed_ms": (
                            10_000
                            + index * 1000
                        ),
                        "latitude_deg": (
                            47.5
                            + index * 0.00001
                        ),
                        "longitude_deg": 19.0,
                        "altitude_m": 100.0,
                    }
                    for index in range(6)
                ],
            }
        ],
    }


def _trust_boundary(
    *,
    available=True,
    usable_from_ms=13_000,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": available,
                "geometry_supported_usable_from_exercise_elapsed_ms": (
                    usable_from_ms
                    if available
                    else None
                ),
            }
        ],
    }


def _policy(action):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "action": action,
            }
        ],
    }


def test_observe_keeps_complete_route_even_when_boundary_exists():
    normalized = _normalized()
    original = deepcopy(
        normalized
    )

    result = build_route_motion_trust_mask(
        normalized,
        _trust_boundary(),
        _policy("OBSERVE"),
    )

    route = result["routes"][0]
    mask = route["trust_mask"]

    assert mask["mode"] == MODE_UNCHANGED
    assert mask["original_point_count"] == 6
    assert mask["usable_point_count"] == 6
    assert mask["excluded_point_count"] == 0
    assert (
        mask[
            "applied_usable_from_exercise_elapsed_ms"
        ]
        is None
    )
    assert normalized == original


def test_review_does_not_automatically_mask():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(),
        _policy("REVIEW"),
    )

    route = result["routes"][0]

    assert (
        route["trust_mask"]["mode"]
        == MODE_UNCHANGED
    )
    assert len(
        route["points"]
    ) == 6


def test_exclude_masks_points_before_boundary_and_keeps_boundary_point():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(
            usable_from_ms=13_000
        ),
        _policy("EXCLUDE"),
    )

    route = result["routes"][0]
    mask = route["trust_mask"]

    assert (
        mask["mode"]
        == MODE_MASKED_BEFORE_TRUST_BOUNDARY
    )
    assert [
        point[
            "exercise_elapsed_ms"
        ]
        for point in route["points"]
    ] == [
        13_000,
        14_000,
        15_000,
    ]
    assert mask["original_point_count"] == 6
    assert mask["usable_point_count"] == 3
    assert mask["excluded_point_count"] == 3
    assert (
        mask[
            "usable_first_exercise_elapsed_ms"
        ]
        == 13_000
    )
    assert route["waypoint_count"] == 3


def test_reconstruct_uses_same_safe_mask_until_reconstruction_exists():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(
            usable_from_ms=14_000
        ),
        _policy("RECONSTRUCT"),
    )

    route = result["routes"][0]

    assert (
        route["trust_mask"]["mode"]
        == MODE_MASKED_BEFORE_TRUST_BOUNDARY
    )
    assert [
        point["waypoint_index"]
        for point in route["points"]
    ] == [4, 5]


def test_exclude_without_boundary_exposes_no_automatically_usable_points():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(
            available=False
        ),
        _policy("EXCLUDE"),
    )

    route = result["routes"][0]
    mask = route["trust_mask"]

    assert (
        mask["mode"]
        == MODE_UNAVAILABLE_NO_TRUST_BOUNDARY
    )
    assert route["points"] == []
    assert route["waypoint_count"] == 0
    assert mask["usable_point_count"] == 0
    assert mask["excluded_point_count"] == 6


def test_original_waypoint_indices_are_not_renumbered():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(
            usable_from_ms=13_000
        ),
        _policy("EXCLUDE"),
    )

    assert [
        point["waypoint_index"]
        for point
        in result["routes"][0]["points"]
    ] == [3, 4, 5]


def test_summary_omits_usable_points_but_preserves_mask_metadata():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(
            usable_from_ms=13_000
        ),
        _policy("EXCLUDE"),
    )

    summary = (
        build_route_motion_trust_mask_summary(
            result
        )
    )

    route = summary["routes"][0]

    assert "points" not in route
    assert route["points_included"] is False
    assert (
        route["trust_mask"][
            "excluded_point_count"
        ]
        == 3
    )


def test_raw_data_mutated_is_explicitly_false():
    result = build_route_motion_trust_mask(
        _normalized(),
        _trust_boundary(),
        _policy("EXCLUDE"),
    )

    assert (
        result["scope"][
            "raw_data_mutated"
        ]
        is False
    )
    assert (
        result["routes"][0][
            "trust_mask"
        ][
            "raw_data_mutated"
        ]
        is False
    )
