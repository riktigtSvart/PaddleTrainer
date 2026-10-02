from app.services.polar_training_routes import (
    normalize_polar_training_routes,
)


def test_normalizes_route_time_to_exercise_time():
    result = normalize_polar_training_routes(
        {
            "exercises": [
                {
                    "startTime": (
                        "2026-09-30T17:35:18"
                    ),
                    "routes": {
                        "route": {
                            "startTime": (
                                "2026-09-30T17:35:18.663"
                            ),
                            "wayPoints": [
                                {
                                    "longitude": 19.04678333,
                                    "latitude": 47.52013167,
                                    "altitude": 90.0,
                                    "elapsedMillis": 73100,
                                }
                            ],
                        }
                    },
                }
            ]
        }
    )

    assert result["provider"] == "POLAR"
    assert result["exercise_count"] == 1
    assert result["route_count"] == 1

    route = result["routes"][0]

    assert (
        route["route_start_offset_ms"]
        == 663
    )

    point = route["points"][0]

    assert point["source_elapsed_ms"] == 73100
    assert (
        point["exercise_elapsed_ms"]
        == 73763
    )
    assert isinstance(
        route["route_start_offset_ms"],
        int,
    )

    assert isinstance(
        point["exercise_elapsed_ms"],
        int,
    )


def test_preserves_waypoint_order_and_coordinates():
    result = normalize_polar_training_routes(
        {
            "exercises": [
                {
                    "startTime": (
                        "2026-09-30T17:35:18"
                    ),
                    "routes": {
                        "route": {
                            "startTime": (
                                "2026-09-30T17:35:18"
                            ),
                            "wayPoints": [
                                {
                                    "longitude": 19.0,
                                    "latitude": 47.0,
                                    "altitude": 90.0,
                                    "elapsedMillis": 1000,
                                },
                                {
                                    "longitude": 19.1,
                                    "latitude": 47.1,
                                    "altitude": 91.0,
                                    "elapsedMillis": 2000,
                                },
                            ],
                        }
                    },
                }
            ]
        }
    )

    points = result["routes"][0]["points"]

    assert len(points) == 2

    assert points[0] == {
        "waypoint_index": 0,
        "source_elapsed_ms": 1000,
        "exercise_elapsed_ms": 1000,
        "latitude_deg": 47.0,
        "longitude_deg": 19.0,
        "altitude_m": 90.0,
    }

    assert points[1] == {
        "waypoint_index": 1,
        "source_elapsed_ms": 2000,
        "exercise_elapsed_ms": 2000,
        "latitude_deg": 47.1,
        "longitude_deg": 19.1,
        "altitude_m": 91.0,
    }


def test_missing_route_start_does_not_invent_alignment():
    result = normalize_polar_training_routes(
        {
            "exercises": [
                {
                    "startTime": (
                        "2026-09-30T17:35:18"
                    ),
                    "routes": {
                        "route": {
                            "wayPoints": [
                                {
                                    "longitude": 19.0,
                                    "latitude": 47.0,
                                    "altitude": 90.0,
                                    "elapsedMillis": 73100,
                                }
                            ]
                        }
                    },
                }
            ]
        }
    )

    route = result["routes"][0]
    point = route["points"][0]

    assert (
        route["route_start_offset_ms"]
        is None
    )

    assert point["source_elapsed_ms"] == 73100

    assert (
        point["exercise_elapsed_ms"]
        is None
    )