import math

import pytest

from app.services.route_motion_path_geometry import (
    build_route_motion_path_geometry_evidence,
    build_route_motion_path_geometry_summary,
)


def _point(index, latitude, longitude, elapsed_ms=None):
    return {
        "waypoint_index": index,
        "exercise_elapsed_ms": (
            index * 1000
            if elapsed_ms is None
            else elapsed_ms
        ),
        "latitude_deg": latitude,
        "longitude_deg": longitude,
    }


def _normalized(points):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "points": points,
            }
        ],
    }


def test_straight_window_path_and_net_are_nearly_equal():
    points = [
        _point(
            index,
            47.5,
            19.0 + index * 0.00001,
        )
        for index in range(6)
    ]

    result = (
        build_route_motion_path_geometry_evidence(
            _normalized(points)
        )
    )

    window = result["routes"][0]["first_window"]

    assert window["available"] is True
    assert (
        window[
            "net_displacement_fraction_of_path"
        ]
        == pytest.approx(
            1.0,
            abs=1e-9,
        )
    )
    assert (
        window[
            "path_minus_net_displacement_m"
        ]
        == pytest.approx(
            0.0,
            abs=1e-6,
        )
    )
    assert (
        window[
            "maximum_intermediate_point_cross_track_deviation_m"
        ]
        == pytest.approx(
            0.0,
            abs=1e-6,
        )
    )


def test_zigzag_has_path_excess_and_cross_track():
    points = [
        _point(0, 47.5, 19.00000),
        _point(1, 47.50003, 19.00002),
        _point(2, 47.49997, 19.00004),
        _point(3, 47.50003, 19.00006),
        _point(4, 47.49997, 19.00008),
        _point(5, 47.50000, 19.00010),
    ]

    result = (
        build_route_motion_path_geometry_evidence(
            _normalized(points)
        )
    )

    window = result["routes"][0]["first_window"]

    assert (
        window[
            "path_minus_net_displacement_m"
        ]
        > 0.0
    )
    assert (
        window[
            "net_displacement_fraction_of_path"
        ]
        < 1.0
    )
    assert (
        window[
            "maximum_intermediate_point_cross_track_deviation_m"
        ]
        > 0.0
    )


def test_rolling_windows_use_contiguous_segments():
    points = [
        _point(
            index,
            47.5,
            19.0 + index * 0.00001,
        )
        for index in range(8)
    ]

    result = (
        build_route_motion_path_geometry_evidence(
            _normalized(points),
            window_segment_count=5,
        )
    )

    windows = result["routes"][0]["windows"]

    assert len(windows) == 3
    assert [
        window[
            "start_segment_index"
        ]
        for window in windows
    ] == [0, 1, 2]
    assert [
        window[
            "end_segment_index"
        ]
        for window in windows
    ] == [4, 5, 6]


def test_missing_coordinate_marks_window_unavailable():
    points = [
        _point(
            index,
            47.5,
            19.0 + index * 0.00001,
        )
        for index in range(6)
    ]
    points[3]["latitude_deg"] = None

    result = (
        build_route_motion_path_geometry_evidence(
            _normalized(points)
        )
    )

    window = result["routes"][0]["first_window"]

    assert window["available"] is False
    assert (
        window["reason"]
        == "COORDINATES_UNAVAILABLE"
    )


def test_timestamp_gap_is_described_not_classified():
    points = [
        _point(
            index,
            47.5,
            19.0 + index * 0.00001,
        )
        for index in range(6)
    ]
    points[5]["exercise_elapsed_ms"] = 8000

    result = (
        build_route_motion_path_geometry_evidence(
            _normalized(points)
        )
    )

    window = result["routes"][0]["first_window"]

    assert (
        window[
            "maximum_adjacent_interval_ms"
        ]
        == 4000
    )
    assert (
        window[
            "all_adjacent_intervals_positive"
        ]
        is True
    )


def test_summary_omits_full_rolling_windows():
    points = [
        _point(
            index,
            47.5,
            19.0 + index * 0.00001,
        )
        for index in range(8)
    ]

    evidence = (
        build_route_motion_path_geometry_evidence(
            _normalized(points)
        )
    )

    summary = (
        build_route_motion_path_geometry_summary(
            evidence
        )
    )

    assert "windows" not in summary["routes"][0]
    assert (
        summary["routes"][0]["first_window"]
        is not None
    )


def test_positive_window_size_required():
    with pytest.raises(
        ValueError,
        match="window_segment_count",
    ):
        build_route_motion_path_geometry_evidence(
            _normalized([]),
            window_segment_count=0,
        )
