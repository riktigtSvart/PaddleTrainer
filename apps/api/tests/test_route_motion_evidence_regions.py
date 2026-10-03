import pytest

from app.services.route_motion_evidence_regions import (
    build_route_motion_evidence_regions,
)


def _window(
    center,
    start,
    end,
    *,
    cross_track=0.0,
    residual=0.0,
):
    return {
        "center_segment_index": center,
        "window_start_segment_index": (
            start
        ),
        "window_end_segment_index": (
            end
        ),
        "maximum_middle_point_cross_track_deviation_m": (
            cross_track
        ),
        "maximum_absolute_speed_residual_mps": (
            residual
        ),
    }


def _evidence(
    windows,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "observation_count": 100,
                "window_radius_segments": 2,
                "target_window_size_segments": 5,
                "windows": windows,
            }
        ],
    }


def test_overlapping_windows_become_one_distinct_region():
    windows = [
        _window(
            2,
            0,
            4,
            cross_track=10.0,
        ),
        _window(
            3,
            1,
            5,
            cross_track=9.0,
        ),
        _window(
            4,
            2,
            6,
            cross_track=8.0,
        ),
        _window(
            20,
            18,
            22,
            cross_track=5.0,
        ),
    ]

    result = (
        build_route_motion_evidence_regions(
            _evidence(windows)
        )
    )

    regions = (
        result["routes"][0]
        ["dimensions"]
        ["cross_track_deviation"]
    )

    assert len(regions) == 2

    assert (
        regions[0]
        ["representative_center_segment_index"]
        == 2
    )

    assert (
        regions[0]
        ["metric_value"]
        == pytest.approx(10.0)
    )

    assert (
        regions[0]
        ["suppressed_overlapping_window_count"]
        == 2
    )

    assert (
        regions[1]
        ["representative_center_segment_index"]
        == 20
    )


def test_dimensions_are_ranked_independently():
    windows = [
        _window(
            2,
            0,
            4,
            cross_track=10.0,
            residual=1.0,
        ),
        _window(
            20,
            18,
            22,
            cross_track=1.0,
            residual=20.0,
        ),
    ]

    result = (
        build_route_motion_evidence_regions(
            _evidence(windows)
        )
    )

    dimensions = (
        result["routes"][0]
        ["dimensions"]
    )

    assert (
        dimensions[
            "cross_track_deviation"
        ][0][
            "representative_center_segment_index"
        ]
        == 2
    )

    assert (
        dimensions[
            "absolute_speed_residual"
        ][0][
            "representative_center_segment_index"
        ]
        == 20
    )


def test_touching_but_non_overlapping_windows_remain_distinct():
    windows = [
        _window(
            2,
            0,
            4,
            cross_track=10.0,
        ),
        _window(
            7,
            5,
            9,
            cross_track=9.0,
        ),
    ]

    result = (
        build_route_motion_evidence_regions(
            _evidence(windows)
        )
    )

    regions = (
        result["routes"][0]
        ["dimensions"]
        ["cross_track_deviation"]
    )

    assert len(regions) == 2


def test_region_output_contains_no_decision_layer():
    windows = [
        _window(
            2,
            0,
            4,
            cross_track=10.0,
        )
    ]

    result = (
        build_route_motion_evidence_regions(
            _evidence(windows)
        )
    )

    region = (
        result["routes"][0]
        ["dimensions"]
        ["cross_track_deviation"]
        [0]
    )

    assert "score" not in region
    assert "classification" not in region
    assert "is_anomaly" not in region
    assert "reconstruction" not in region


def test_region_limit_must_be_positive():
    with pytest.raises(
        ValueError,
        match="region_limit must be >= 1",
    ):
        build_route_motion_evidence_regions(
            _evidence([]),
            region_limit=0,
        )