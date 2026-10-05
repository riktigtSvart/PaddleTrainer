from __future__ import annotations

from copy import deepcopy
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_IDENTITY_SUPPORTED = "IDENTITY_SUPPORTED"
STATUS_DIRECT_RESOLVED = "DIRECT_RESOLVED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

CANDIDATE_IDENTITY_MATCH = "IDENTITY_MATCH"
CANDIDATE_IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
CANDIDATE_IDENTITY_UNKNOWN = "IDENTITY_UNKNOWN"

ENVIRONMENT_RIVER_INLAND = "RIVER_INLAND"
ENVIRONMENT_MARINE = "MARINE"


_NAME_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def build_route_hydrology_source_resolution(
    route_water_environment_identity: Mapping[str, Any] | None,
    hydrology_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve whether hydrology source identity is compatible with route water identity.

    This is deliberately an identity/provenance resolver, not a spatial-nearest
    selector and not a hydrodynamic model.  It consumes already trusted route
    water-environment identity plus provider-normalized hydrology station metadata.

    Exact normalized watercourse-name agreement is evidence of compatibility, but
    is not promoted to DIRECT_RESOLVED because no authoritative WFD-waterbody ↔
    hydrology-station crosswalk is asserted here.  A single compatible candidate is
    therefore IDENTITY_SUPPORTED.
    """
    candidates = build_hydrology_source_candidates(hydrology_source)
    routes = _sequence_of_mappings(
        route_water_environment_identity.get("routes")
        if isinstance(route_water_environment_identity, Mapping)
        else None
    )

    route_results: list[dict[str, Any]] = []
    global_counts = _empty_status_counts()

    for route_position, route in enumerate(routes):
        route_index = _integer(route.get("route_index"))
        if route_index is None:
            route_index = route_position
        exercise_index = _integer(route.get("exercise_index"))

        result = _resolve_route(
            route,
            candidates,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        route_results.append(result)
        global_counts[result["status"]] += 1

    if not route_results:
        overall_status = STATUS_UNRESOLVED
    elif global_counts[STATUS_AMBIGUOUS]:
        overall_status = STATUS_AMBIGUOUS
    elif global_counts[STATUS_UNRESOLVED]:
        overall_status = STATUS_UNRESOLVED
    elif global_counts[STATUS_IDENTITY_SUPPORTED]:
        overall_status = STATUS_IDENTITY_SUPPORTED
    elif global_counts[STATUS_DIRECT_RESOLVED]:
        overall_status = STATUS_DIRECT_RESOLVED
    else:
        overall_status = STATUS_NOT_APPLICABLE

    return {
        "provider": _provider(route_water_environment_identity, hydrology_source),
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": overall_status,
        "route_count": len(route_results),
        "candidate_source_count": len(candidates),
        "identity_supported_route_count": global_counts[
            STATUS_IDENTITY_SUPPORTED
        ],
        "direct_resolved_route_count": global_counts[STATUS_DIRECT_RESOLVED],
        "ambiguous_route_count": global_counts[STATUS_AMBIGUOUS],
        "unresolved_route_count": global_counts[STATUS_UNRESOLVED],
        "not_applicable_route_count": global_counts[STATUS_NOT_APPLICABLE],
        "input_provenance": {
            "route_water_environment_identity_schema_version": (
                route_water_environment_identity.get("schema_version")
                if isinstance(route_water_environment_identity, Mapping)
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
            "domain": "ROUTE_HYDROLOGY_SOURCE_RESOLUTION",
            "uses_trusted_water_environment_identity": True,
            "resolves_station_watercourse_compatibility": True,
            "uses_nearest_station_as_identity_proof": False,
            "claims_authoritative_waterbody_station_crosswalk": False,
            "controls_hydrology_context_inclusion": False,
            "estimates_hydrology_representativeness": False,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "raw_data_mutated": False,
        },
        "candidate_sources": candidates,
        "routes": route_results,
    }


def build_route_hydrology_source_resolution_summary(
    resolution: Mapping[str, Any],
) -> dict[str, Any]:
    """Compact summary; V14 has no per-segment resolution payload."""
    return deepcopy(dict(resolution))


def build_hydrology_source_candidates(
    hydrology_source: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract unique station candidates from normalized hydrology evidence."""
    if not isinstance(hydrology_source, Mapping):
        return []

    stations: list[Mapping[str, Any]] = []
    top_level_station = hydrology_source.get("station")
    if isinstance(top_level_station, Mapping):
        stations.append(top_level_station)

    measurements = _sequence_of_mappings(hydrology_source.get("measurements"))
    for measurement in measurements:
        station = measurement.get("station")
        if isinstance(station, Mapping):
            stations.append(station)

    source_provider = _string(hydrology_source.get("provider"))
    source_product = _string(hydrology_source.get("product"))
    source_type = _string(hydrology_source.get("source_type"))

    result_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for station in stations:
        registry_number = _station_registry_number(station)
        station_name = _string(station.get("station_name"))
        watercourse = _string(station.get("watercourse"))
        latitude = _finite_float(station.get("latitude_deg"))
        longitude = _finite_float(station.get("longitude_deg"))

        key = (
            registry_number,
            station_name,
            watercourse,
            latitude,
            longitude,
        )
        result_by_key[key] = {
            "source_provider": source_provider or _measurement_provider(
                measurements
            ),
            "source_product": source_product or _measurement_product(
                measurements
            ),
            "source_type": source_type or _measurement_source_type(
                measurements
            ),
            "station_registry_number": registry_number,
            "station_name": station_name,
            "watercourse": watercourse,
            "municipality": _string(station.get("municipality")),
            "latitude_deg": latitude,
            "longitude_deg": longitude,
            "river_km": _finite_float(station.get("river_km")),
        }

    return sorted(
        result_by_key.values(),
        key=lambda item: (
            item.get("source_provider") or "",
            item.get("station_registry_number") or "",
            item.get("station_name") or "",
        ),
    )


def _resolve_route(
    route: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    route_index: int,
    exercise_index: int | None,
) -> dict[str, Any]:
    river_segment_count = _nonnegative_integer(
        route.get("river_inland_segment_count")
    )
    marine_segment_count = _nonnegative_integer(route.get("marine_segment_count"))
    ambiguous_environment_segment_count = _nonnegative_integer(
        route.get("ambiguous_environment_segment_count")
    )
    mixed_environment_route = route.get("mixed_environment_route") is True

    river_identities = _sequence_of_mappings(route.get("river_inland_identities"))
    identity_records = [_river_identity_record(item) for item in river_identities]

    if marine_segment_count > 0 and river_segment_count == 0:
        return _route_result(
            route_index=route_index,
            exercise_index=exercise_index,
            status=STATUS_NOT_APPLICABLE,
            applicable=False,
            river_identities=identity_records,
            candidates=candidates,
            evaluated_candidates=[],
            resolved_source=None,
            basis=[
                "ROUTE_TRUSTED_AS_MARINE",
                "RIVER_HYDROLOGY_SOURCE_NOT_APPLICABLE",
            ],
        )

    if mixed_environment_route or ambiguous_environment_segment_count > 0:
        return _route_result(
            route_index=route_index,
            exercise_index=exercise_index,
            status=STATUS_AMBIGUOUS,
            applicable=True,
            river_identities=identity_records,
            candidates=candidates,
            evaluated_candidates=[],
            resolved_source=None,
            basis=[
                "ROUTE_WATER_ENVIRONMENT_IDENTITY_AMBIGUOUS_OR_MIXED",
                "HYDROLOGY_SOURCE_NOT_SELECTED",
            ],
        )

    if river_segment_count <= 0 or not identity_records:
        return _route_result(
            route_index=route_index,
            exercise_index=exercise_index,
            status=STATUS_UNRESOLVED,
            applicable=river_segment_count > 0,
            river_identities=identity_records,
            candidates=candidates,
            evaluated_candidates=[],
            resolved_source=None,
            basis=[
                "NO_TRUSTED_RIVER_INLAND_IDENTITY",
                "HYDROLOGY_SOURCE_NOT_SELECTED",
            ],
        )

    if len(identity_records) != 1:
        return _route_result(
            route_index=route_index,
            exercise_index=exercise_index,
            status=STATUS_AMBIGUOUS,
            applicable=True,
            river_identities=identity_records,
            candidates=candidates,
            evaluated_candidates=[],
            resolved_source=None,
            basis=[
                "MULTIPLE_TRUSTED_RIVER_INLAND_IDENTITIES",
                "HYDROLOGY_SOURCE_NOT_SELECTED",
            ],
        )

    identity = identity_records[0]
    identity_names = identity.get("identity_names") or []
    evaluated = [
        _evaluate_candidate(candidate, identity_names)
        for candidate in candidates
    ]
    matches = [
        item
        for item in evaluated
        if item.get("identity_compatibility") == CANDIDATE_IDENTITY_MATCH
    ]

    if len(matches) == 1:
        return _route_result(
            route_index=route_index,
            exercise_index=exercise_index,
            status=STATUS_IDENTITY_SUPPORTED,
            applicable=True,
            river_identities=identity_records,
            candidates=candidates,
            evaluated_candidates=evaluated,
            resolved_source=matches[0].get("candidate_source"),
            basis=[
                "SINGLE_TRUSTED_RIVER_INLAND_IDENTITY",
                "SINGLE_HYDROLOGY_STATION_WATERCOURSE_IDENTITY_MATCH",
                "NO_AUTHORITATIVE_WATERBODY_STATION_CROSSWALK_CLAIMED",
            ],
        )

    if len(matches) > 1:
        return _route_result(
            route_index=route_index,
            exercise_index=exercise_index,
            status=STATUS_AMBIGUOUS,
            applicable=True,
            river_identities=identity_records,
            candidates=candidates,
            evaluated_candidates=evaluated,
            resolved_source=None,
            basis=[
                "MULTIPLE_HYDROLOGY_STATIONS_MATCH_WATERCOURSE_IDENTITY",
                "NEAREST_STATION_NOT_USED_AS_TIE_BREAKER",
            ],
        )

    return _route_result(
        route_index=route_index,
        exercise_index=exercise_index,
        status=STATUS_UNRESOLVED,
        applicable=True,
        river_identities=identity_records,
        candidates=candidates,
        evaluated_candidates=evaluated,
        resolved_source=None,
        basis=[
            "NO_HYDROLOGY_STATION_WATERCOURSE_IDENTITY_MATCH",
            "NEAREST_STATION_NOT_ACCEPTED_AS_IDENTITY_PROOF",
        ],
    )


def _evaluate_candidate(
    candidate: Mapping[str, Any],
    identity_names: Sequence[str],
) -> dict[str, Any]:
    watercourse = _string(candidate.get("watercourse"))
    normalized_watercourse = _normalize_identity_name(watercourse)
    normalized_identity_names = sorted(
        {
            normalized
            for name in identity_names
            if (normalized := _normalize_identity_name(name)) is not None
        }
    )

    if normalized_watercourse is None or not normalized_identity_names:
        compatibility = CANDIDATE_IDENTITY_UNKNOWN
        basis = ["IDENTITY_NAME_EVIDENCE_INCOMPLETE"]
    elif normalized_watercourse in normalized_identity_names:
        compatibility = CANDIDATE_IDENTITY_MATCH
        basis = ["NORMALIZED_WATERCOURSE_NAME_EXACT_MATCH"]
    else:
        compatibility = CANDIDATE_IDENTITY_CONFLICT
        basis = ["NORMALIZED_WATERCOURSE_NAME_CONFLICT"]

    return {
        "candidate_source": deepcopy(dict(candidate)),
        "identity_compatibility": compatibility,
        "candidate_watercourse_normalized": normalized_watercourse,
        "trusted_waterbody_names_normalized": normalized_identity_names,
        "resolution_basis": basis,
    }


def _river_identity_record(identity: Mapping[str, Any]) -> dict[str, Any]:
    names: list[str] = []
    for key in (
        "waterbody_name",
        "geographical_name",
        "name",
    ):
        value = _string(identity.get(key))
        if value is not None:
            names.append(value)

    raw_source_names = identity.get("source_feature_names")
    if isinstance(raw_source_names, Sequence) and not isinstance(
        raw_source_names, (str, bytes)
    ):
        for item in raw_source_names:
            value = _string(item)
            if value is not None:
                names.append(value)

    unique_names = list(dict.fromkeys(names))
    return {
        "source_provider": _string(identity.get("source_provider")),
        "source_product": _string(identity.get("source_product")),
        "waterbody_id": _string(identity.get("waterbody_id")),
        "waterbody_type": _string(identity.get("waterbody_type")),
        "identity_names": unique_names,
        "source_feature_ids": deepcopy(identity.get("source_feature_ids")),
        "source_feature_names": deepcopy(identity.get("source_feature_names")),
    }


def _route_result(
    *,
    route_index: int,
    exercise_index: int | None,
    status: str,
    applicable: bool,
    river_identities: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    evaluated_candidates: Sequence[Mapping[str, Any]],
    resolved_source: Mapping[str, Any] | None,
    basis: Sequence[str],
) -> dict[str, Any]:
    return {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "available": True,
        "applicable": applicable,
        "status": status,
        "trusted_river_inland_identity_count": len(river_identities),
        "trusted_river_inland_identities": deepcopy(list(river_identities)),
        "candidate_source_count": len(candidates),
        "evaluated_candidate_count": len(evaluated_candidates),
        "evaluated_candidates": deepcopy(list(evaluated_candidates)),
        "resolved_hydrology_source": (
            deepcopy(dict(resolved_source))
            if isinstance(resolved_source, Mapping)
            else None
        ),
        "resolution_basis": list(basis),
    }


def _provider(
    water_identity: Mapping[str, Any] | None,
    hydrology_source: Mapping[str, Any] | None,
) -> str | None:
    if isinstance(hydrology_source, Mapping):
        provider = _string(hydrology_source.get("provider"))
        if provider is not None:
            return provider
    if isinstance(water_identity, Mapping):
        return _string(water_identity.get("provider"))
    return None


def _measurement_provider(
    measurements: Sequence[Mapping[str, Any]],
) -> str | None:
    return _first_measurement_string(measurements, "source_provider")


def _measurement_product(
    measurements: Sequence[Mapping[str, Any]],
) -> str | None:
    return _first_measurement_string(measurements, "source_product")


def _measurement_source_type(
    measurements: Sequence[Mapping[str, Any]],
) -> str | None:
    return _first_measurement_string(measurements, "source_type")


def _first_measurement_string(
    measurements: Sequence[Mapping[str, Any]],
    key: str,
) -> str | None:
    for measurement in measurements:
        value = _string(measurement.get(key))
        if value is not None:
            return value
    return None


def _station_registry_number(station: Mapping[str, Any]) -> str | None:
    value = station.get("station_registry_number")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _string(value)


def _normalize_identity_name(value: object) -> str | None:
    text = _string(value)
    if text is None:
        return None
    ascii_text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )
    normalized = _NAME_TOKEN_RE.sub(" ", ascii_text).strip()
    return normalized or None


def _sequence_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
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


def _nonnegative_integer(value: object) -> int:
    parsed = _integer(value)
    return parsed if parsed is not None and parsed >= 0 else 0


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _empty_status_counts() -> dict[str, int]:
    return {
        STATUS_IDENTITY_SUPPORTED: 0,
        STATUS_DIRECT_RESOLVED: 0,
        STATUS_AMBIGUOUS: 0,
        STATUS_UNRESOLVED: 0,
        STATUS_NOT_APPLICABLE: 0,
    }
