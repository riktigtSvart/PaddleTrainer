from app.services.route_coverage import (
    build_route_coverage_evidence,
)


def test_describes_route_coverage_and_gaps():
    result = build_route_coverage_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 0,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.1,
                            "longitude_deg": 19.1,
                        },
                        {
                            "waypoint_index": 2,
                            "exercise_elapsed_ms": 2000,
                            "latitude_deg": 47.2,
                            "longitude_deg": 19.2,
                        },
                        {
                            "waypoint_index": 3,
                            "exercise_elapsed_ms": 5000,
                            "latitude_deg": 47.3,
                            "longitude_deg": 19.3,
                        },
                        {
                            "waypoint_index": 4,
                            "exercise_elapsed_ms": 6000,
                            "latitude_deg": 47.4,
                            "longitude_deg": 19.4,
                        },
                    ],
                }
            ],
        },
        session_duration_ms=7000,
    )

    assert result["available"] is True
    assert result["route_count"] == 1

    route = result["routes"][0]

    assert route["waypoint_count"] == 5
    assert (
        route["timestamped_waypoint_count"]
        == 5
    )
    assert (
        route["valid_coordinate_count"]
        == 5
    )
    assert (
        route["coordinate_fraction"]
        == 1.0
    )

    assert (
        route["first_exercise_elapsed_ms"]
        == 0
    )
    assert (
        route["last_exercise_elapsed_ms"]
        == 6000
    )
    assert route["route_span_ms"] == 6000

    assert (
        route[
            "adjacent_timestamp_interval_count"
        ]
        == 4
    )

    assert (
        route["nominal_interval_ms"]
        == 1000
    )
    assert (
        route[
            "minimum_positive_interval_ms"
        ]
        == 1000
    )
    assert (
        route[
            "maximum_positive_interval_ms"
        ]
        == 3000
    )

    assert (
        route["gap_threshold_ms"]
        == 1500.0
    )
    assert route["gap_count"] == 1
    assert route["maximum_gap_ms"] == 3000

    assert (
        route[
            "session_end_minus_last_waypoint_ms"
        ]
        == 1000
    )


def test_missing_timestamp_is_not_bridged():
    result = build_route_coverage_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 0,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": None,
                            "latitude_deg": 47.1,
                            "longitude_deg": None,
                        },
                        {
                            "waypoint_index": 2,
                            "exercise_elapsed_ms": 2000,
                            "latitude_deg": 47.2,
                            "longitude_deg": 19.2,
                        },
                    ],
                }
            ],
        }
    )

    route = result["routes"][0]

    assert (
        route["timestamped_waypoint_count"]
        == 2
    )

    assert (
        route[
            "adjacent_timestamp_interval_count"
        ]
        == 0
    )

    assert (
        route["valid_coordinate_count"]
        == 2
    )

    assert (
        route["coordinate_fraction"]
        == 2 / 3
    )

    assert route["gap_count"] == 0


def test_reports_non_increasing_timestamps():
    result = build_route_coverage_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 0,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 2,
                            "exercise_elapsed_ms": 1000,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 3,
                            "exercise_elapsed_ms": 500,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                    ],
                }
            ],
        }
    )

    route = result["routes"][0]

    assert (
        route[
            "adjacent_timestamp_interval_count"
        ]
        == 3
    )

    assert route["positive_interval_count"] == 1
    assert route["zero_interval_count"] == 1
    assert route["negative_interval_count"] == 1

    assert (
        route["nominal_interval_ms"]
        == 1000
    )


def test_accepts_integer_valued_float_elapsed_ms():
    result = build_route_coverage_evidence(
        {
            "provider": "POLAR",
            "routes": [
                {
                    "exercise_index": 0,
                    "points": [
                        {
                            "waypoint_index": 0,
                            "exercise_elapsed_ms": 73763.0,
                            "latitude_deg": 47.0,
                            "longitude_deg": 19.0,
                        },
                        {
                            "waypoint_index": 1,
                            "exercise_elapsed_ms": 74764.0,
                            "latitude_deg": 47.1,
                            "longitude_deg": 19.1,
                        },
                    ],
                }
            ],
        }
    )

    route = result["routes"][0]

    assert (
        route["timestamped_waypoint_count"]
        == 2
    )
    assert (
        route["first_exercise_elapsed_ms"]
        == 73763
    )
    assert (
        route["last_exercise_elapsed_ms"]
        == 74764
    )
    assert (
        route[
            "adjacent_timestamp_interval_count"
        ]
        == 1
    )
    assert (
        route["nominal_interval_ms"]
        == 1001
    )