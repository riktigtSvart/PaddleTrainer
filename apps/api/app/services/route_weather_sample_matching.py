from __future__ import annotations

import math
from datetime import datetime
from typing import Any

MATCHING_VERSION = "0.2"
DEFAULT_MAX_TIME_DELTA_SECONDS = 3600.0
DEFAULT_MAX_DISTANCE_M = 50_000.0
EARTH_MEAN_RADIUS_M = 6_371_008.8

STATUS_MATCHED = "MATCHED"
STATUS_SEGMENT_TIME_UNAVAILABLE = "SEGMENT_TIME_UNAVAILABLE"
STATUS_SEGMENT_POSITION_UNAVAILABLE = "SEGMENT_POSITION_UNAVAILABLE"
STATUS_NO_SAMPLE_WITHIN_TOLERANCES = "NO_SAMPLE_WITHIN_TOLERANCES"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _coordinate(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    lat = _finite_number(latitude)
    lon = _finite_number(longitude)
    if (
        lat is None or lon is None
        or lat < -90.0 or lat > 90.0
        or lon < -180.0 or lon > 180.0
    ):
        return None
    return lat, lon


def _surface_distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_lat = math.radians(first[0])
    first_lon = math.radians(first[1])
    second_lat = math.radians(second[0])
    second_lon = math.radians(second[1])

    delta_lat = second_lat - first_lat
    delta_lon = second_lon - first_lon

    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(first_lat)
        * math.cos(second_lat)
        * math.sin(delta_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_MEAN_RADIUS_M * c


def _normalized_sample(
    sample: dict[str, Any],
    fallback_index: int,
) -> dict[str, Any] | None:
    sampled_at = _parse_datetime(sample.get("sample_timestamp"))
    coordinate = _coordinate(
        sample.get("latitude_deg"),
        sample.get("longitude_deg"),
    )
    if sampled_at is None or coordinate is None:
        return None

    wind_speed_mps = _finite_number(sample.get("wind_speed_mps"))
    wind_direction_from_deg = _finite_number(
        sample.get("wind_direction_from_deg")
    )

    return {
        "sample_id": sample.get("sample_id") or str(fallback_index),
        "sample_timestamp": sampled_at.isoformat(),
        "latitude_deg": coordinate[0],
        "longitude_deg": coordinate[1],
        "wind_speed_mps": wind_speed_mps,
        "wind_direction_from_deg": (
            wind_direction_from_deg % 360.0
            if wind_direction_from_deg is not None
            else None
        ),
        "air_temperature_c": _finite_number(
            sample.get("air_temperature_c")
        ),
        "source": sample.get("source"),
        "source_reference": sample.get("source_reference"),
    }


def _segment_reference_coordinate(
    segment: dict[str, Any],
) -> tuple[float, float] | None:
    start_position = segment.get("start_position")
    if not isinstance(start_position, dict):
        return None
    return _coordinate(
        start_position.get("latitude_deg"),
        start_position.get("longitude_deg"),
    )


def _match_segment(
    segment: dict[str, Any],
    samples: list[dict[str, Any]],
    *,
    max_time_delta_seconds: float,
    max_distance_m: float,
) -> dict[str, Any]:
    midpoint = _parse_datetime(segment.get("midpoint_timestamp"))
    coordinate = _segment_reference_coordinate(segment)

    result = {
        "order_index": _integer(segment.get("order_index")),
        "segment_index": _integer(segment.get("segment_index")),
        "segment_midpoint_timestamp": segment.get("midpoint_timestamp"),
        "segment_location_reference": "START_POSITION",
        "segment_reference_position": segment.get("start_position"),
        "available": False,
        "status": None,
        "matched_sample_id": None,
        "absolute_time_delta_seconds": None,
        "surface_distance_to_sample_m": None,
        "matched_sample": None,
    }

    if midpoint is None:
        result["status"] = STATUS_SEGMENT_TIME_UNAVAILABLE
        return result

    if coordinate is None:
        result["status"] = STATUS_SEGMENT_POSITION_UNAVAILABLE
        return result

    candidates = []
    for sample in samples:
        sampled_at = _parse_datetime(sample.get("sample_timestamp"))
        sample_coordinate = _coordinate(
            sample.get("latitude_deg"),
            sample.get("longitude_deg"),
        )
        if sampled_at is None or sample_coordinate is None:
            continue

        time_delta_seconds = abs((midpoint - sampled_at).total_seconds())
        if time_delta_seconds > max_time_delta_seconds:
            continue

        distance_m = _surface_distance_m(coordinate, sample_coordinate)
        if distance_m > max_distance_m:
            continue

        candidates.append(
            (
                time_delta_seconds,
                distance_m,
                str(sample.get("sample_id")),
                sample,
            )
        )

    if not candidates:
        result["status"] = STATUS_NO_SAMPLE_WITHIN_TOLERANCES
        return result

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    time_delta_seconds, distance_m, _, matched = candidates[0]

    result.update(
        {
            "available": True,
            "status": STATUS_MATCHED,
            "matched_sample_id": matched.get("sample_id"),
            "absolute_time_delta_seconds": time_delta_seconds,
            "surface_distance_to_sample_m": distance_m,
            "matched_sample": matched,
        }
    )
    return result


def build_route_weather_sample_matching(
    route_environment_context_input: dict[str, Any],
    weather_samples: list[dict[str, Any]],
    *,
    max_time_delta_seconds: float = DEFAULT_MAX_TIME_DELTA_SECONDS,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
) -> dict[str, Any]:
    if max_time_delta_seconds < 0.0 or max_distance_m < 0.0:
        raise ValueError("Matching tolerances must be non-negative")

    normalized_samples = [
        normalized
        for index, sample in enumerate(weather_samples)
        if isinstance(sample, dict)
        and (
            normalized := _normalized_sample(
                sample,
                index,
            )
        )
        is not None
    ]

    route_results = []
    for route_position, route in enumerate(
        route_environment_context_input.get("routes") or []
    ):
        if not isinstance(route, dict):
            continue

        route_index = _integer(route.get("route_index"))
        if route_index is None:
            route_index = route_position
        exercise_index = _integer(route.get("exercise_index"))

        matches = [
            _match_segment(
                segment,
                normalized_samples,
                max_time_delta_seconds=max_time_delta_seconds,
                max_distance_m=max_distance_m,
            )
            for segment in (route.get("segments") or [])
            if isinstance(segment, dict)
        ]

        matched_count = sum(
            1 for match in matches if match.get("available") is True
        )

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": matched_count > 0,
                "usable_interval": route.get("usable_interval"),
                "matched_segment_count": matched_count,
                "unmatched_segment_count": len(matches) - matched_count,
                "matches": matches,
            }
        )

    return {
        "provider": route_environment_context_input.get("provider"),
        "matching_version": MATCHING_VERSION,
        "available": any(
            route.get("available") is True for route in route_results
        ),
        "sample_count": len(normalized_samples),
        "route_count": len(route_results),
        "matching_policy": {
            "maximum_time_delta_seconds": max_time_delta_seconds,
            "maximum_surface_distance_m": max_distance_m,
            "time_selection": "MINIMUM_ABSOLUTE_TIME_DELTA",
            "distance_tiebreaker": "MINIMUM_SURFACE_DISTANCE",
            "segment_location_reference": "START_POSITION",
            "interpolates_weather": False,
            "interpolates_route_position": False,
            "uses_composite_score": False,
        },
        "routes": route_results,
    }


def build_route_weather_sample_matching_summary(
    matching: dict[str, Any],
) -> dict[str, Any]:
    return {
        **matching,
        "routes": [
            {
                **{
                    key: value
                    for key, value in route.items()
                    if key != "matches"
                },
                "matches_included": False,
                "match_payload_count": len(route.get("matches") or []),
            }
            for route in (matching.get("routes") or [])
            if isinstance(route, dict)
        ],
    }
