from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.2"

STATUS_REPRESENTATIVE = "REPRESENTATIVE"
STATUS_PARTIALLY_REPRESENTATIVE = "PARTIALLY_REPRESENTATIVE"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUS_NOT_REPRESENTATIVE = "NOT_REPRESENTATIVE"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

SOURCE_STATUS_DIRECT_RESOLVED = "DIRECT_RESOLVED"
SOURCE_STATUS_IDENTITY_SUPPORTED = "IDENTITY_SUPPORTED"
SOURCE_STATUS_AMBIGUOUS = "AMBIGUOUS"
SOURCE_STATUS_UNRESOLVED = "UNRESOLVED"
SOURCE_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

IDENTITY_CONFLICT = "IDENTITY_CONFLICT"

DEFAULT_MAX_TEMPORAL_GAP_SECONDS = 3 * 60 * 60
DEFAULT_MIN_TEMPORAL_COVERAGE_FRACTION = 0.80

_AUTHORITATIVE_REACH_BASIS = {
    "AUTHORITATIVE_WATERBODY_STATION_CROSSWALK",
    "AUTHORITATIVE_RIVER_REACH_STATION_CROSSWALK",
    "AUTHORITATIVE_REACH_STATION_CROSSWALK",
}


def build_route_hydrology_representativeness(
    route_environment_context_input: Mapping[str, Any] | None,
    route_hydrology_source_resolution: Mapping[str, Any] | None,
    hydrology_source: Mapping[str, Any] | None,
    *,
    max_temporal_gap_seconds: int = DEFAULT_MAX_TEMPORAL_GAP_SECONDS,
    min_temporal_coverage_fraction: float = DEFAULT_MIN_TEMPORAL_COVERAGE_FRACTION,
) -> dict[str, Any]:
    """Evaluate route-level hydrology-source representativeness evidence.

    The result is conservative by design.  Identity compatibility plus temporal
    overlap can support PARTIALLY_REPRESENTATIVE, but cannot become fully
    REPRESENTATIVE without authoritative reach/station linkage.  Straight-line
    station distance is reported only as context and is never identity or reach
    proof.  No local current velocity is estimated here.
    """
    if isinstance(max_temporal_gap_seconds, bool) or max_temporal_gap_seconds <= 0:
        raise ValueError("max_temporal_gap_seconds must be positive")
    if not 0.0 <= float(min_temporal_coverage_fraction) <= 1.0:
        raise ValueError("min_temporal_coverage_fraction must be between 0 and 1")

    route_inputs = _sequence_of_mappings(
        route_environment_context_input.get("routes")
        if isinstance(route_environment_context_input, Mapping)
        else None
    )
    resolution_routes = _sequence_of_mappings(
        route_hydrology_source_resolution.get("routes")
        if isinstance(route_hydrology_source_resolution, Mapping)
        else None
    )
    measurements = _sequence_of_mappings(
        hydrology_source.get("measurements")
        if isinstance(hydrology_source, Mapping)
        else None
    )

    route_input_by_index = {
        _route_index(route, position): route
        for position, route in enumerate(route_inputs)
    }

    route_results: list[dict[str, Any]] = []
    counts = _empty_status_counts()

    for position, source_resolution in enumerate(resolution_routes):
        route_index = _route_index(source_resolution, position)
        route_input = route_input_by_index.get(route_index, {})
        route_result = _build_route_result(
            route_input,
            source_resolution,
            measurements,
            route_index=route_index,
            max_temporal_gap_seconds=int(max_temporal_gap_seconds),
            min_temporal_coverage_fraction=float(
                min_temporal_coverage_fraction
            ),
        )
        route_results.append(route_result)
        counts[route_result["status"]] += 1

    overall_status = _overall_status(route_results, counts)

    return {
        "provider": _string(
            hydrology_source.get("provider")
            if isinstance(hydrology_source, Mapping)
            else None
        ),
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": overall_status,
        "route_count": len(route_results),
        "representative_route_count": counts[STATUS_REPRESENTATIVE],
        "partially_representative_route_count": counts[
            STATUS_PARTIALLY_REPRESENTATIVE
        ],
        "insufficient_evidence_route_count": counts[
            STATUS_INSUFFICIENT_EVIDENCE
        ],
        "not_representative_route_count": counts[STATUS_NOT_REPRESENTATIVE],
        "not_applicable_route_count": counts[STATUS_NOT_APPLICABLE],
        "policy": {
            "max_temporal_gap_seconds": int(max_temporal_gap_seconds),
            "min_temporal_coverage_fraction": float(
                min_temporal_coverage_fraction
            ),
        },
        "input_provenance": {
            "route_environment_context_input_schema_version": (
                route_environment_context_input.get("schema_version")
                if isinstance(route_environment_context_input, Mapping)
                else None
            ),
            "route_hydrology_source_resolution_schema_version": (
                route_hydrology_source_resolution.get("schema_version")
                if isinstance(route_hydrology_source_resolution, Mapping)
                else None
            ),
            "hydrology_source_provider": _string(
                hydrology_source.get("provider")
                if isinstance(hydrology_source, Mapping)
                else None
            ),
            "hydrology_source_product": _string(
                hydrology_source.get("product")
                if isinstance(hydrology_source, Mapping)
                else None
            ),
        },
        "scope": {
            "domain": "ROUTE_HYDROLOGY_REPRESENTATIVENESS",
            "uses_hydrology_source_resolution": True,
            "uses_temporal_measurement_support": True,
            "reports_station_to_route_geodesic_distance": True,
            "uses_geodesic_distance_as_identity_proof": False,
            "uses_geodesic_distance_as_reach_proof": False,
            "requires_authoritative_reach_crosswalk_for_full_representativeness": True,
            "controls_hydrology_context_inclusion": False,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_route_hydrology_representativeness_summary(
    representativeness: Mapping[str, Any],
) -> dict[str, Any]:
    """Return compact route summaries while omitting per-segment support rows."""
    result = deepcopy(dict(representativeness))
    result["routes"] = []
    for route in _sequence_of_mappings(representativeness.get("routes")):
        compact = deepcopy(dict(route))
        compact.pop("segments", None)
        compact["segments_included"] = False
        result["routes"].append(compact)
    return result


def _build_route_result(
    route_input: Mapping[str, Any],
    source_resolution: Mapping[str, Any],
    measurements: Sequence[Mapping[str, Any]],
    *,
    route_index: int,
    max_temporal_gap_seconds: int,
    min_temporal_coverage_fraction: float,
) -> dict[str, Any]:
    source_status = _string(source_resolution.get("status")) or SOURCE_STATUS_UNRESOLVED
    exercise_index = _integer(source_resolution.get("exercise_index"))
    resolved_source = source_resolution.get("resolved_hydrology_source")
    resolved_source = (
        dict(resolved_source) if isinstance(resolved_source, Mapping) else None
    )

    base = {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "source_resolution_status": source_status,
        "resolved_hydrology_source": deepcopy(resolved_source),
        "station_identity_supported": source_status
        in {SOURCE_STATUS_IDENTITY_SUPPORTED, SOURCE_STATUS_DIRECT_RESOLVED},
        "authoritative_reach_crosswalk_available": _has_authoritative_reach_basis(
            source_resolution
        ),
    }

    if source_status == SOURCE_STATUS_NOT_APPLICABLE or source_resolution.get(
        "applicable"
    ) is False:
        return {
            **base,
            "available": True,
            "applicable": False,
            "status": STATUS_NOT_APPLICABLE,
            "temporal_evidence": _empty_temporal_evidence(route_input),
            "spatial_evidence": _spatial_evidence(route_input, resolved_source),
            "resolution_basis": [
                "HYDROLOGY_SOURCE_RESOLUTION_NOT_APPLICABLE",
                "RIVER_HYDROLOGY_REPRESENTATIVENESS_NOT_APPLICABLE",
            ],
            "limitations": [
                "NO_RIVER_HYDROLOGY_REPRESENTATIVENESS_CLAIM"
            ],
            "segments": [],
        }

    if _has_identity_conflict(source_resolution):
        return {
            **base,
            "available": True,
            "applicable": True,
            "status": STATUS_NOT_REPRESENTATIVE,
            "temporal_evidence": _empty_temporal_evidence(route_input),
            "spatial_evidence": _spatial_evidence(route_input, resolved_source),
            "resolution_basis": [
                "HYDROLOGY_SOURCE_IDENTITY_CONFLICT",
                "SOURCE_NOT_ACCEPTED_AS_ROUTE_HYDROLOGY_REPRESENTATIVE",
            ],
            "limitations": [
                "WATERCOURSE_IDENTITY_CONFLICT_PRECLUDES_REPRESENTATIVENESS"
            ],
            "segments": [],
        }

    if source_status not in {
        SOURCE_STATUS_IDENTITY_SUPPORTED,
        SOURCE_STATUS_DIRECT_RESOLVED,
    } or resolved_source is None:
        return {
            **base,
            "available": True,
            "applicable": True,
            "status": STATUS_INSUFFICIENT_EVIDENCE,
            "temporal_evidence": _empty_temporal_evidence(route_input),
            "spatial_evidence": _spatial_evidence(route_input, resolved_source),
            "resolution_basis": [
                "HYDROLOGY_SOURCE_NOT_UNIQUELY_RESOLVED",
                "REPRESENTATIVENESS_WITHHELD",
            ],
            "limitations": [
                "SOURCE_IDENTITY_EVIDENCE_INSUFFICIENT"
            ],
            "segments": [],
        }

    relevant_measurements = _measurements_for_source(measurements, resolved_source)
    route_segments = _sequence_of_mappings(route_input.get("segments"))
    temporal_evidence, segment_support = _temporal_evidence(
        route_segments,
        relevant_measurements,
        max_temporal_gap_seconds=max_temporal_gap_seconds,
    )
    spatial_evidence = _spatial_evidence(route_input, resolved_source)

    coverage_fraction = temporal_evidence["temporally_supported_segment_fraction"]
    has_sufficient_temporal_coverage = (
        temporal_evidence["timestamped_segment_count"] > 0
        and temporal_evidence["matching_measurement_count"] > 0
        and coverage_fraction >= min_temporal_coverage_fraction
    )

    if not has_sufficient_temporal_coverage:
        return {
            **base,
            "available": True,
            "applicable": True,
            "status": STATUS_INSUFFICIENT_EVIDENCE,
            "temporal_evidence": temporal_evidence,
            "spatial_evidence": spatial_evidence,
            "resolution_basis": [
                "HYDROLOGY_SOURCE_IDENTITY_SUPPORTED",
                "TEMPORAL_MEASUREMENT_SUPPORT_INSUFFICIENT",
                "REPRESENTATIVENESS_WITHHELD",
            ],
            "limitations": [
                "TEMPORAL_COVERAGE_BELOW_POLICY_THRESHOLD"
            ],
            "segments": segment_support,
        }

    authoritative_reach = _has_authoritative_reach_basis(source_resolution)
    if source_status == SOURCE_STATUS_DIRECT_RESOLVED and authoritative_reach:
        status = STATUS_REPRESENTATIVE
        basis = [
            "HYDROLOGY_SOURCE_DIRECT_RESOLVED",
            "AUTHORITATIVE_REACH_STATION_LINK_AVAILABLE",
            "TEMPORAL_MEASUREMENT_SUPPORT_SUFFICIENT",
        ]
        limitations: list[str] = []
    else:
        status = STATUS_PARTIALLY_REPRESENTATIVE
        basis = [
            "HYDROLOGY_SOURCE_IDENTITY_SUPPORTED",
            "TEMPORAL_MEASUREMENT_SUPPORT_SUFFICIENT",
            "FULL_REPRESENTATIVENESS_WITHHELD_WITHOUT_AUTHORITATIVE_REACH_LINK",
        ]
        limitations = [
            "NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK",
            "STATION_TO_ROUTE_GEODESIC_DISTANCE_IS_CONTEXT_ONLY",
            "ALONG_RIVER_DISTANCE_NOT_ESTABLISHED",
        ]

    return {
        **base,
        "available": True,
        "applicable": True,
        "status": status,
        "temporal_evidence": temporal_evidence,
        "spatial_evidence": spatial_evidence,
        "resolution_basis": basis,
        "limitations": limitations,
        "segments": segment_support,
    }


def _temporal_evidence(
    route_segments: Sequence[Mapping[str, Any]],
    measurements: Sequence[Mapping[str, Any]],
    *,
    max_temporal_gap_seconds: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    measurement_times_by_metric: dict[str, list[datetime]] = {}
    parsed_measurement_count = 0
    for measurement in measurements:
        observed_at = _parse_datetime(measurement.get("observed_at"))
        metric_key = _string(measurement.get("metric_key"))
        if observed_at is None or metric_key is None:
            continue
        measurement_times_by_metric.setdefault(metric_key, []).append(observed_at)
        parsed_measurement_count += 1

    for times in measurement_times_by_metric.values():
        times.sort()

    timestamped_segment_count = 0
    supported_segment_count = 0
    segment_rows: list[dict[str, Any]] = []
    supported_by_metric: dict[str, int] = {
        metric: 0 for metric in sorted(measurement_times_by_metric)
    }

    for position, segment in enumerate(route_segments):
        midpoint = _segment_midpoint_timestamp(segment)
        segment_index = _integer(segment.get("segment_index"))
        if segment_index is None:
            segment_index = position

        if midpoint is None:
            segment_rows.append(
                {
                    "segment_index": segment_index,
                    "midpoint_timestamp": None,
                    "temporally_supported": False,
                    "supported_metric_keys": [],
                    "nearest_measurement_delta_seconds_by_metric": {},
                    "reason": "SEGMENT_TIMESTAMP_UNAVAILABLE",
                }
            )
            continue

        timestamped_segment_count += 1
        deltas: dict[str, float] = {}
        supported_metrics: list[str] = []
        for metric, times in measurement_times_by_metric.items():
            delta = _nearest_delta_seconds(midpoint, times)
            if delta is None:
                continue
            deltas[metric] = delta
            if delta <= max_temporal_gap_seconds:
                supported_metrics.append(metric)
                supported_by_metric[metric] += 1

        supported = bool(supported_metrics)
        if supported:
            supported_segment_count += 1

        segment_rows.append(
            {
                "segment_index": segment_index,
                "midpoint_timestamp": midpoint.isoformat(),
                "temporally_supported": supported,
                "supported_metric_keys": sorted(supported_metrics),
                "nearest_measurement_delta_seconds_by_metric": {
                    key: deltas[key] for key in sorted(deltas)
                },
                "reason": (
                    "MEASUREMENT_WITHIN_TEMPORAL_POLICY"
                    if supported
                    else "NO_MEASUREMENT_WITHIN_TEMPORAL_POLICY"
                ),
            }
        )

    coverage_fraction = (
        supported_segment_count / timestamped_segment_count
        if timestamped_segment_count
        else 0.0
    )

    metric_coverage = []
    for metric in sorted(measurement_times_by_metric):
        supported_count = supported_by_metric.get(metric, 0)
        metric_coverage.append(
            {
                "metric_key": metric,
                "measurement_count": len(measurement_times_by_metric[metric]),
                "temporally_supported_segment_count": supported_count,
                "temporally_supported_segment_fraction": (
                    supported_count / timestamped_segment_count
                    if timestamped_segment_count
                    else 0.0
                ),
            }
        )

    return (
        {
            "route_segment_count": len(route_segments),
            "timestamped_segment_count": timestamped_segment_count,
            "matching_measurement_count": parsed_measurement_count,
            "temporally_supported_segment_count": supported_segment_count,
            "temporally_supported_segment_fraction": coverage_fraction,
            "metric_coverage": metric_coverage,
        },
        segment_rows,
    )


def _spatial_evidence(
    route_input: Mapping[str, Any],
    resolved_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    station_lat = _finite_float(
        resolved_source.get("latitude_deg")
        if isinstance(resolved_source, Mapping)
        else None
    )
    station_lon = _finite_float(
        resolved_source.get("longitude_deg")
        if isinstance(resolved_source, Mapping)
        else None
    )

    route_positions = _route_positions(route_input)
    distances: list[float] = []
    if station_lat is not None and station_lon is not None:
        for lat, lon in route_positions:
            distances.append(_haversine_m(station_lat, station_lon, lat, lon))

    return {
        "station_registry_number": (
            resolved_source.get("station_registry_number")
            if isinstance(resolved_source, Mapping)
            else None
        ),
        "station_river_km": (
            _finite_float(resolved_source.get("river_km"))
            if isinstance(resolved_source, Mapping)
            else None
        ),
        "route_position_count": len(route_positions),
        "station_to_route_min_geodesic_m": min(distances) if distances else None,
        "station_to_route_max_geodesic_m": max(distances) if distances else None,
        "route_river_km_available": False,
        "along_river_distance_available": False,
        "reach_crosswalk_available": False,
        "geodesic_distance_used_as_representativeness_proof": False,
    }


def _measurements_for_source(
    measurements: Sequence[Mapping[str, Any]],
    resolved_source: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    target_registry = _station_registry_number(resolved_source)
    if target_registry is None:
        return []

    result: list[Mapping[str, Any]] = []
    for measurement in measurements:
        station = measurement.get("station")
        station = station if isinstance(station, Mapping) else {}
        registry = _station_registry_number(station)
        if registry == target_registry:
            result.append(measurement)
    return result


def _has_identity_conflict(source_resolution: Mapping[str, Any]) -> bool:
    evaluated = _sequence_of_mappings(source_resolution.get("evaluated_candidates"))
    if not evaluated:
        return False
    compatibilities = {
        _string(item.get("identity_compatibility")) for item in evaluated
    }
    compatibilities.discard(None)
    return bool(compatibilities) and compatibilities == {IDENTITY_CONFLICT}


def _has_authoritative_reach_basis(source_resolution: Mapping[str, Any]) -> bool:
    basis = source_resolution.get("resolution_basis")
    if not isinstance(basis, Sequence) or isinstance(basis, (str, bytes)):
        return False
    return any(str(item) in _AUTHORITATIVE_REACH_BASIS for item in basis)


def _route_positions(route_input: Mapping[str, Any]) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    for segment in _sequence_of_mappings(route_input.get("segments")):
        for key in ("start_position", "end_position"):
            position = segment.get(key)
            if not isinstance(position, Mapping):
                continue
            lat = _finite_float(position.get("latitude_deg"))
            lon = _finite_float(position.get("longitude_deg"))
            if lat is None or lon is None:
                continue
            positions.append((lat, lon))
    return positions


def _segment_midpoint_timestamp(segment: Mapping[str, Any]) -> datetime | None:
    midpoint = _parse_datetime(segment.get("midpoint_timestamp"))
    if midpoint is not None:
        return midpoint
    source_locator = segment.get("source_locator")
    if isinstance(source_locator, Mapping):
        return _parse_datetime(source_locator.get("midpoint_timestamp"))
    return None


def _nearest_delta_seconds(target: datetime, times: Sequence[datetime]) -> float | None:
    if not times:
        return None
    index = bisect_left(times, target)
    candidates: list[datetime] = []
    if index < len(times):
        candidates.append(times[index])
    if index > 0:
        candidates.append(times[index - 1])
    return min(abs((candidate - target).total_seconds()) for candidate in candidates)


def _overall_status(
    route_results: Sequence[Mapping[str, Any]],
    counts: Mapping[str, int],
) -> str:
    if not route_results:
        return STATUS_INSUFFICIENT_EVIDENCE
    for status in (
        STATUS_NOT_REPRESENTATIVE,
        STATUS_INSUFFICIENT_EVIDENCE,
        STATUS_PARTIALLY_REPRESENTATIVE,
        STATUS_REPRESENTATIVE,
    ):
        if counts.get(status, 0):
            return status
    return STATUS_NOT_APPLICABLE


def _empty_temporal_evidence(
    route_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe route temporal structure without claiming hydrology support.

    Negative/non-applicable representativeness branches still describe the
    route that was evaluated.  A zero support count means "no accepted
    hydrology temporal support", not "the route has no segments".
    """
    route_segments = _sequence_of_mappings(
        route_input.get("segments")
        if isinstance(route_input, Mapping)
        else None
    )
    timestamped_segment_count = sum(
        1
        for segment in route_segments
        if _segment_midpoint_timestamp(segment) is not None
    )
    return {
        "route_segment_count": len(route_segments),
        "timestamped_segment_count": timestamped_segment_count,
        "matching_measurement_count": 0,
        "temporally_supported_segment_count": 0,
        "temporally_supported_segment_fraction": 0.0,
        "metric_coverage": [],
    }


def _route_index(route: Mapping[str, Any], fallback: int) -> int:
    parsed = _integer(route.get("route_index"))
    return parsed if parsed is not None else fallback


def _station_registry_number(source: Mapping[str, Any]) -> str | None:
    value = source.get("station_registry_number")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _string(value)


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * radius_m * math.asin(min(1.0, math.sqrt(a)))


def _sequence_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _empty_status_counts() -> dict[str, int]:
    return {
        STATUS_REPRESENTATIVE: 0,
        STATUS_PARTIALLY_REPRESENTATIVE: 0,
        STATUS_INSUFFICIENT_EVIDENCE: 0,
        STATUS_NOT_REPRESENTATIVE: 0,
        STATUS_NOT_APPLICABLE: 0,
    }
