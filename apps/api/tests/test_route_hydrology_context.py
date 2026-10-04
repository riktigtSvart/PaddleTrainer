import pytest

from app.services.route_hydrology_context import (
    build_route_hydrology_context,
    build_route_hydrology_context_summary,
)


def _route_context():
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 46,
                        "midpoint_timestamp": (
                            "2026-09-30T17:40:00+02:00"
                        ),
                        "start_position": {
                            "latitude_deg": 47.52,
                            "longitude_deg": 19.04,
                        },
                    }
                ],
            }
        ],
    }


def _hydrology():
    return {
        "provider": "OVF_VRAQUERY",
        "station": {
            "station_registry_number": 1026,
            "station_name": "Budapest",
            "watercourse": "Duna",
            "latitude_deg": 47.50,
            "longitude_deg": 19.04,
            "river_km": 1646.5,
        },
        "measurements": [
            {
                "measurement_id": "level",
                "observed_at": (
                    "2026-09-30T15:30:00+00:00"
                ),
                "metric_key": "WATER_LEVEL",
                "value": 14.0,
                "unit": "cm",
                "data_type_code": 101,
            },
            {
                "measurement_id": "q",
                "observed_at": (
                    "2026-09-30T15:30:00+00:00"
                ),
                "metric_key": "DISCHARGE",
                "value": 754.0,
                "unit": "m3/s",
                "data_type_code": 101,
            },
            {
                "measurement_id": "temp",
                "observed_at": (
                    "2026-09-30T15:30:00+00:00"
                ),
                "metric_key": "WATER_TEMPERATURE",
                "value": 18.1,
                "unit": "degC",
                "data_type_code": 101,
            },
        ],
    }


def test_matches_each_hydrology_metric_by_time():
    result = build_route_hydrology_context(
        _route_context(),
        _hydrology(),
        max_time_delta_seconds=3600.0,
    )

    segment = result["routes"][0]["segments"][0]

    assert segment["water_level"]["available"] is True
    assert segment["water_level"]["value"] == 14.0
    assert segment["discharge"]["value"] == 754.0
    assert segment["water_temperature"]["value"] == 18.1
    assert (
        segment["water_level"][
            "absolute_time_delta_seconds"
        ]
        == pytest.approx(
            600.0
        )
    )


def test_station_distance_is_descriptive_and_current_is_not_inferred():
    result = build_route_hydrology_context(
        _route_context(),
        _hydrology(),
    )

    segment = result["routes"][0]["segments"][0]

    assert segment["station_surface_distance_m"] > 0
    assert segment["current_speed_estimate_mps"] is None
    assert segment["current_direction_deg"] is None
    assert (
        result["scope"][
            "derives_current_from_discharge"
        ]
        is False
    )
    assert (
        result["scope"][
            "derives_current_from_water_level"
        ]
        is False
    )


def test_outside_time_tolerance_stays_unavailable():
    result = build_route_hydrology_context(
        _route_context(),
        _hydrology(),
        max_time_delta_seconds=60.0,
    )

    segment = result["routes"][0]["segments"][0]

    assert segment["water_level"]["available"] is False
    assert segment["discharge"]["available"] is False


def test_route_waterbody_identity_is_not_silently_asserted():
    result = build_route_hydrology_context(
        _route_context(),
        _hydrology(),
    )

    assert (
        result["matching_policy"][
            "route_waterbody_identity_asserted"
        ]
        is False
    )
    assert (
        result["matching_policy"][
            "station_selection"
        ]
        == "EXPLICIT_CALLER_PROVIDED"
    )


def test_summary_strips_segment_payload():
    context = build_route_hydrology_context(
        _route_context(),
        _hydrology(),
    )

    summary = (
        build_route_hydrology_context_summary(
            context
        )
    )

    route = summary["routes"][0]

    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 1
