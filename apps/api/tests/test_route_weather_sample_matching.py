import pytest

from app.services.route_weather_sample_matching import (
    STATUS_MATCHED,
    STATUS_NO_SAMPLE_WITHIN_TOLERANCES,
    build_route_weather_sample_matching,
    build_route_weather_sample_matching_summary,
)


def _context():
    return {
        "provider": "POLAR",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "usable_interval": {
                    "start_exercise_elapsed_ms": 1000,
                    "end_exercise_elapsed_ms": 2000,
                },
                "segments": [
                    {
                        "order_index": 0,
                        "segment_index": 10,
                        "midpoint_timestamp": "2026-09-30T17:40:00+02:00",
                        "start_position": {
                            "latitude_deg": 47.52,
                            "longitude_deg": 19.04,
                        },
                    }
                ],
            }
        ],
    }


def _sample(sample_id, timestamp, lat, lon):
    return {
        "sample_id": sample_id,
        "sample_timestamp": timestamp,
        "latitude_deg": lat,
        "longitude_deg": lon,
        "wind_speed_mps": 5.0,
        "wind_direction_from_deg": 0.0,
        "air_temperature_c": 16.0,
        "source": "TEST",
    }


def test_matches_nearest_time_sample_within_both_tolerances():
    result = build_route_weather_sample_matching(
        _context(),
        [
            _sample("later", "2026-09-30T17:45:00+02:00", 47.52, 19.04),
            _sample("nearer", "2026-09-30T17:41:00+02:00", 47.53, 19.04),
        ],
        max_time_delta_seconds=600.0,
        max_distance_m=5000.0,
    )
    match = result["routes"][0]["matches"][0]
    assert match["status"] == STATUS_MATCHED
    assert match["matched_sample_id"] == "nearer"
    assert match["absolute_time_delta_seconds"] == pytest.approx(60.0)


def test_distance_breaks_equal_time_tie():
    result = build_route_weather_sample_matching(
        _context(),
        [
            _sample("far", "2026-09-30T17:41:00+02:00", 47.55, 19.04),
            _sample("near", "2026-09-30T17:39:00+02:00", 47.5201, 19.04),
        ],
        max_time_delta_seconds=600.0,
        max_distance_m=10_000.0,
    )
    assert result["routes"][0]["matches"][0]["matched_sample_id"] == "near"


def test_rejects_sample_outside_time_tolerance():
    result = build_route_weather_sample_matching(
        _context(),
        [_sample("old", "2026-09-30T16:00:00+02:00", 47.52, 19.04)],
        max_time_delta_seconds=300.0,
        max_distance_m=10_000.0,
    )
    assert (
        result["routes"][0]["matches"][0]["status"]
        == STATUS_NO_SAMPLE_WITHIN_TOLERANCES
    )


def test_rejects_sample_outside_distance_tolerance():
    result = build_route_weather_sample_matching(
        _context(),
        [_sample("distant", "2026-09-30T17:40:00+02:00", 48.0, 19.04)],
        max_time_delta_seconds=300.0,
        max_distance_m=1000.0,
    )
    assert (
        result["routes"][0]["matches"][0]["status"]
        == STATUS_NO_SAMPLE_WITHIN_TOLERANCES
    )


def test_normalizes_direction_but_does_not_interpolate():
    result = build_route_weather_sample_matching(
        _context(),
        [
            {
                **_sample(
                    "obs",
                    "2026-09-30T17:40:00+02:00",
                    47.52,
                    19.04,
                ),
                "wind_direction_from_deg": 370.0,
            }
        ],
    )
    matched = result["routes"][0]["matches"][0]["matched_sample"]
    assert matched["wind_direction_from_deg"] == pytest.approx(10.0)
    assert result["matching_policy"]["interpolates_weather"] is False
    assert result["matching_policy"]["uses_composite_score"] is False


def test_summary_strips_matches():
    result = build_route_weather_sample_matching(
        _context(),
        [_sample("obs", "2026-09-30T17:40:00+02:00", 47.52, 19.04)],
    )
    summary = build_route_weather_sample_matching_summary(result)
    route = summary["routes"][0]
    assert "matches" not in route
    assert route["matches_included"] is False
    assert route["match_payload_count"] == 1
