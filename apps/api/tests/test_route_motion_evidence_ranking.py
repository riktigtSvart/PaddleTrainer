import pytest

from app.services.route_motion_evidence_ranking import (
    build_route_motion_evidence_ranking,
)


def _region(
    dimension,
    rank,
    start,
    end,
    center,
):
    return {
        "rank": rank,
        "dimension_key": dimension,
        "metric_field": (
            f"{dimension}_metric"
        ),
        "metric_value": float(
            100 - rank
        ),
        "region_start_segment_index": (
            start
        ),
        "region_end_segment_index": (
            end
        ),
        "representative_center_segment_index": (
            center
        ),
        "representative_window": {
            "center_segment_index": (
                center
            ),
        },
    }


def _window(
    center,
    start,
    end,
    minimum_speed,
    maximum_speed,
):
    return {
        "center_segment_index": center,
        "window_start_segment_index": (
            start
        ),
        "window_end_segment_index": (
            end
        ),
        "minimum_gps_ground_speed_mps": (
            minimum_speed
        ),
        "maximum_gps_ground_speed_mps": (
            maximum_speed
        ),
    }


def _regions(
    dimensions,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "dimensions": dimensions,
            }
        ],
    }


def _windows(
    windows,
):
    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "windows": windows,
            }
        ],
    }


def test_geometry_family_prefers_multi_dimension_support():
    dimensions = {
        "cross_track_deviation": [
            _region(
                "cross_track_deviation",
                1,
                0,
                4,
                2,
            ),
            _region(
                "cross_track_deviation",
                2,
                20,
                24,
                22,
            ),
        ],
        "heading_change_rate": [
            _region(
                "heading_change_rate",
                1,
                0,
                4,
                2,
            ),
        ],
    }

    result = (
        build_route_motion_evidence_ranking(
            _windows([]),
            _regions(dimensions),
        )
    )

    geometry = (
        result["routes"][0]
        ["families"]
        ["geometry"]
    )

    assert (
        geometry[0]
        ["representative_center_segment_index"]
        == 2
    )

    assert (
        geometry[0]
        ["support_dimension_count"]
        == 2
    )


def test_overlapping_family_candidates_are_not_repeated():
    dimensions = {
        "absolute_speed_residual": [
            _region(
                "absolute_speed_residual",
                1,
                0,
                4,
                2,
            ),
        ],
        "compensating_residual_distance": [
            _region(
                "compensating_residual_distance",
                1,
                1,
                5,
                3,
            ),
        ],
    }

    result = (
        build_route_motion_evidence_ranking(
            _windows([]),
            _regions(dimensions),
        )
    )

    temporal = (
        result["routes"][0]
        ["families"]
        ["temporal"]
    )

    assert len(temporal) == 1


def test_speed_transition_ranking_uses_speed_range():
    windows = [
        _window(
            2,
            0,
            4,
            0.2,
            5.2,
        ),
        _window(
            10,
            8,
            12,
            2.0,
            4.0,
        ),
    ]

    result = (
        build_route_motion_evidence_ranking(
            _windows(windows),
            _regions({}),
        )
    )

    transitions = (
        result["routes"][0]
        ["speed_transition"]
    )

    assert (
        transitions[0]
        ["gps_ground_speed_range_mps"]
        == pytest.approx(5.0)
    )

    assert (
        transitions[0]
        ["center_segment_index"]
        == 2
    )


def test_overlapping_speed_transition_windows_are_suppressed():
    windows = [
        _window(
            2,
            0,
            4,
            0.0,
            6.0,
        ),
        _window(
            3,
            1,
            5,
            0.0,
            5.5,
        ),
        _window(
            20,
            18,
            22,
            0.0,
            4.0,
        ),
    ]

    result = (
        build_route_motion_evidence_ranking(
            _windows(windows),
            _regions({}),
        )
    )

    transitions = (
        result["routes"][0]
        ["speed_transition"]
    )

    assert len(transitions) == 2

    assert (
        transitions[0]
        ["center_segment_index"]
        == 2
    )

    assert (
        transitions[1]
        ["center_segment_index"]
        == 20
    )


def test_ranking_has_no_anomaly_decision():
    result = (
        build_route_motion_evidence_ranking(
            _windows(
                [
                    _window(
                        2,
                        0,
                        4,
                        0.0,
                        5.0,
                    )
                ]
            ),
            _regions({}),
        )
    )

    transition = (
        result["routes"][0]
        ["speed_transition"][0]
    )

    assert "score" not in transition
    assert "classification" not in transition
    assert "is_anomaly" not in transition


def test_ranking_limit_must_be_positive():
    with pytest.raises(
        ValueError,
        match="ranking_limit must be >= 1",
    ):
        build_route_motion_evidence_ranking(
            _windows([]),
            _regions({}),
            ranking_limit=0,
        )