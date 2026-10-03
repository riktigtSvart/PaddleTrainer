import pytest

from app.services.route_motion_forward_anchor_evidence import (
    build_forward_anchor_reconstruction_context,
    build_route_motion_forward_anchor_evidence,
)


def _window(
    start,
    *,
    path=5.0,
    fraction=0.995,
    excess=0.02,
    cross_track=0.10,
    maximum_interval=1000,
    outside_count=0,
):
    return {
        "available": True,
        "start_segment_index": start,
        "end_segment_index": start + 4,
        "start_waypoint_index": start,
        "end_waypoint_index": start + 5,
        "start_exercise_elapsed_ms": (
            start * 1000
        ),
        "end_exercise_elapsed_ms": (
            (start + 5) * 1000
        ),
        "path_distance_m": path,
        "net_displacement_fraction_of_path": fraction,
        "path_minus_net_displacement_m": excess,
        "maximum_intermediate_point_cross_track_deviation_m": (
            cross_track
        ),
        "all_adjacent_intervals_positive": True,
        "maximum_adjacent_interval_ms": (
            maximum_interval
        ),
        "intermediate_point_along_track_outside_unit_interval_count": (
            outside_count
        ),
    }


def _path_geometry(windows):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "windows": windows,
            }
        ],
    }


def _startup():
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "expected_segment_indices": [
                    0, 1, 2, 3, 4
                ],
            }
        ],
    }


def test_three_consecutive_coherent_windows_validate_anchor():
    windows = [
        _window(start)
        for start in range(10)
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
        )
    )

    route = result["routes"][0]

    assert (
        route[
            "validated_forward_anchor_available"
        ]
        is True
    )
    assert (
        route["anchor"]["segment_index"]
        == 5
    )
    assert (
        route["anchor"][
            "confirmation_window_start_segment_indices"
        ]
        == [5, 6, 7]
    )


def test_startup_windows_are_not_used_as_forward_anchor():
    windows = [
        _window(start)
        for start in range(8)
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
        )
    )

    route = result["routes"][0]

    assert (
        route[
            "scan_start_segment_index"
        ]
        == 5
    )
    assert (
        route["anchor"]["segment_index"]
        == 5
    )


def test_two_coherent_windows_are_not_enough():
    windows = [
        _window(5),
        _window(6),
        _window(
            7,
            cross_track=0.8,
        ),
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
        )
    )

    assert (
        result["routes"][0][
            "validated_forward_anchor_available"
        ]
        is False
    )


def test_nonconsecutive_coherent_windows_do_not_form_run():
    windows = [
        _window(5),
        _window(7),
        _window(8),
        _window(10),
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
        )
    )

    assert (
        result["routes"][0][
            "validated_forward_anchor_available"
        ]
        is False
    )


def test_low_path_distance_is_not_anchor_support():
    windows = [
        _window(
            start,
            path=0.2,
        )
        for start in range(
            5,
            10,
        )
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
        )
    )

    inspection = (
        result["routes"][0][
            "inspection_windows"
        ]
    )

    assert (
        inspection[0]["coherent"]
        is False
    )
    assert (
        inspection[0]["gates"][
            "path_distance_passed"
        ]
        is False
    )


def test_interval_gap_blocks_anchor_window():
    windows = [
        _window(5),
        _window(
            6,
            maximum_interval=3000,
        ),
        _window(7),
        _window(8),
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
        )
    )

    assert (
        result["routes"][0][
            "validated_forward_anchor_available"
        ]
        is False
    )


def test_reconstruction_context_exports_forward_anchor_state():
    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(
                [
                    _window(start)
                    for start
                    in range(10)
                ]
            ),
            _startup(),
        )
    )

    context = (
        build_forward_anchor_reconstruction_context(
            result
        )
    )

    assert context == {
        0: {
            "forward_anchor_available": True
        }
    }


def test_custom_threshold_can_relax_cross_track_gate():
    windows = [
        _window(
            start,
            cross_track=0.4,
        )
        for start in range(
            5,
            8,
        )
    ]

    result = (
        build_route_motion_forward_anchor_evidence(
            _path_geometry(windows),
            _startup(),
            thresholds={
                "maximum_intermediate_cross_track_m": 0.5,
            },
        )
    )

    assert (
        result["routes"][0][
            "validated_forward_anchor_available"
        ]
        is True
    )
