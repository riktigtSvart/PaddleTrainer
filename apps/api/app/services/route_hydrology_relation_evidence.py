from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_NOT_REQUIRED = "NOT_REQUIRED"
STATUS_SUPPORTED_WITH_LIMITATIONS = "SUPPORTED_WITH_LIMITATIONS"
STATUS_WITHHELD = "WITHHELD"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

METRIC_TRANSFER_SUPPORTED = "TRANSFER_SUPPORTED"
METRIC_TRANSFER_WITHHELD = "TRANSFER_WITHHELD"
METRIC_TRANSFER_AMBIGUOUS = "AMBIGUOUS"

RELATION_DIRECT_LOCAL_GAUGE = "DIRECT_LOCAL_GAUGE"
RELATION_AUTHORITATIVE_REACH_CROSSWALK = "AUTHORITATIVE_REACH_CROSSWALK"
RELATION_UNCONTROLLED_HYDRAULIC_CONNECTION = "UNCONTROLLED_HYDRAULIC_CONNECTION"
RELATION_STRUCTURE_CONTROLLED = "STRUCTURE_CONTROLLED"
RELATION_EMPIRICAL_PROXY = "EMPIRICAL_PROXY"
RELATION_HYDRAULIC_MODEL = "HYDRAULIC_MODEL"
RELATION_UNKNOWN = "UNKNOWN"

REPRESENTATIVENESS_REPRESENTATIVE = "REPRESENTATIVE"
REPRESENTATIVENESS_PARTIAL = "PARTIALLY_REPRESENTATIVE"
REPRESENTATIVENESS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
REPRESENTATIVENESS_NOT_REPRESENTATIVE = "NOT_REPRESENTATIVE"

DIRECT_SOURCE_STATUSES = {"IDENTITY_SUPPORTED", "DIRECT_RESOLVED"}

_NAME_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def build_route_hydrology_relation_evidence(
    route_environment_context_input: Mapping[str, Any] | None,
    route_hydrology_source_resolution: Mapping[str, Any] | None,
    relation_catalog: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate explicit hydrology relations between a route waterbody and source.

    V23 is a representation/evidence layer.  It can express that a station on a
    different watercourse is related to the route waterbody for a specific
    metric, but it does **not** itself promote that relation into trusted route
    hydrology context.

    The relation catalog must make transfer semantics explicit per metric.  Mere
    topological connection, physical proximity, or navigability never implies a
    usable transfer.
    """
    route_inputs = _sequence_of_mappings(
        route_environment_context_input.get("routes")
        if isinstance(route_environment_context_input, Mapping)
        else None
    )
    source_routes = _sequence_of_mappings(
        route_hydrology_source_resolution.get("routes")
        if isinstance(route_hydrology_source_resolution, Mapping)
        else None
    )
    relations = _sequence_of_mappings(
        relation_catalog.get("relations")
        if isinstance(relation_catalog, Mapping)
        else None
    )

    route_input_by_key = {
        _route_key(route, position): route
        for position, route in enumerate(route_inputs)
    }

    route_results: list[dict[str, Any]] = []
    counts = _empty_status_counts()

    for position, source_route in enumerate(source_routes):
        key = _route_key(source_route, position)
        result = _build_route_result(
            source_route=source_route,
            route_input=route_input_by_key.get(key),
            relations=relations,
            catalog_available=isinstance(relation_catalog, Mapping),
        )
        route_results.append(result)
        counts[result["status"]] += 1

    return {
        "provider": _string(
            relation_catalog.get("provider")
            if isinstance(relation_catalog, Mapping)
            else None
        ),
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _overall_status(route_results),
        "route_count": len(route_results),
        "not_required_route_count": counts[STATUS_NOT_REQUIRED],
        "supported_with_limitations_route_count": counts[
            STATUS_SUPPORTED_WITH_LIMITATIONS
        ],
        "withheld_route_count": counts[STATUS_WITHHELD],
        "ambiguous_route_count": counts[STATUS_AMBIGUOUS],
        "unavailable_route_count": counts[STATUS_UNAVAILABLE],
        "not_applicable_route_count": counts[STATUS_NOT_APPLICABLE],
        "input_provenance": {
            "route_environment_context_input_schema_version": _schema_version(
                route_environment_context_input
            ),
            "route_hydrology_source_resolution_schema_version": _schema_version(
                route_hydrology_source_resolution
            ),
            "relation_catalog_schema_version": _schema_version(relation_catalog),
            "relation_catalog_provider": _string(
                relation_catalog.get("provider")
                if isinstance(relation_catalog, Mapping)
                else None
            ),
            "relation_catalog_product": _string(
                relation_catalog.get("product")
                if isinstance(relation_catalog, Mapping)
                else None
            ),
        },
        "scope": {
            "domain": "ROUTE_HYDROLOGY_RELATION_EVIDENCE",
            "represents_cross_waterbody_hydraulic_relations": True,
            "metric_specific_transfer_required": True,
            "supports_structure_controlled_branches": True,
            "supports_uncontrolled_hydraulic_connections": True,
            "supports_empirical_or_model_relations": True,
            "uses_nearest_station_as_relation_proof": False,
            "uses_navigability_as_relation_proof": False,
            "uses_topological_connection_alone_as_transfer_proof": False,
            "promotes_relation_to_trusted_hydrology": False,
            "controls_hydrology_context_inclusion": False,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_route_hydrology_relation_evidence_summary(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(evidence))
    result["routes"] = []
    for route in _sequence_of_mappings(evidence.get("routes")):
        compact = deepcopy(dict(route))
        compact.pop("evaluated_relations", None)
        compact["evaluated_relations_included"] = False
        result["routes"].append(compact)
    return result


def _build_route_result(
    *,
    source_route: Mapping[str, Any],
    route_input: Mapping[str, Any] | None,
    relations: Sequence[Mapping[str, Any]],
    catalog_available: bool,
) -> dict[str, Any]:
    route_index, exercise_index = _route_key(source_route, 0)
    source_status = _string(source_route.get("status")) or "UNRESOLVED"
    applicable = source_route.get("applicable") is not False
    target_identities = _sequence_of_mappings(
        source_route.get("trusted_river_inland_identities")
    )
    route_interval = _route_interval(route_input)

    base = {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "available": True,
        "applicable": applicable,
        "source_resolution_status": source_status,
        "route_interval": route_interval,
        "trusted_river_inland_identities": deepcopy(target_identities),
    }

    if not applicable or source_status == "NOT_APPLICABLE":
        return {
            **base,
            "status": STATUS_NOT_APPLICABLE,
            "metric_relations": [],
            "selected_source_by_metric": {},
            "evaluated_relations": [],
            "resolution_basis": ["RIVER_HYDROLOGY_RELATION_NOT_APPLICABLE"],
            "limitations": ["NO_RIVER_HYDROLOGY_RELATION_CLAIM"],
        }

    if source_status in DIRECT_SOURCE_STATUSES and isinstance(
        source_route.get("resolved_hydrology_source"), Mapping
    ):
        return {
            **base,
            "status": STATUS_NOT_REQUIRED,
            "metric_relations": [],
            "selected_source_by_metric": {},
            "evaluated_relations": [],
            "resolution_basis": [
                "DIRECT_OR_IDENTITY_SUPPORTED_HYDROLOGY_SOURCE_ALREADY_AVAILABLE",
                "CROSS_WATERBODY_RELATION_NOT_REQUIRED",
            ],
            "limitations": [],
        }

    if not catalog_available:
        return {
            **base,
            "status": STATUS_UNAVAILABLE,
            "metric_relations": [],
            "selected_source_by_metric": {},
            "evaluated_relations": [],
            "resolution_basis": ["HYDROLOGY_RELATION_CATALOG_UNAVAILABLE"],
            "limitations": ["CROSS_WATERBODY_RELATION_EVIDENCE_UNAVAILABLE"],
        }

    candidates = _candidate_sources(source_route)
    evaluated_relations: list[dict[str, Any]] = []
    metric_rows: dict[str, list[dict[str, Any]]] = {}

    for relation_position, relation in enumerate(relations):
        target_match, target_basis = _target_matches(relation, target_identities)
        temporal_match, temporal_basis = _temporal_relation_matches(
            relation,
            route_interval,
        )

        matching_sources = [
            candidate
            for candidate in candidates
            if _source_matches(relation, candidate)[0]
        ]

        relation_match = target_match and temporal_match and bool(matching_sources)
        evaluated = {
            "relation_position": relation_position,
            "relation_id": _scalar_id(relation.get("relation_id")),
            "relation_type": _relation_type(relation),
            "target_match": target_match,
            "temporal_match": temporal_match,
            "matching_source_count": len(matching_sources),
            "relation_match": relation_match,
            "target_basis": target_basis,
            "temporal_basis": temporal_basis,
            "matching_sources": deepcopy(matching_sources),
        }
        evaluated_relations.append(evaluated)

        if not relation_match:
            continue

        for metric in _sequence_of_mappings(relation.get("metrics")):
            metric_key = _string(metric.get("metric_key"))
            if metric_key is None:
                continue
            for source in matching_sources:
                metric_rows.setdefault(metric_key, []).append(
                    _evaluate_metric_relation(
                        relation=relation,
                        metric=metric,
                        source=source,
                    )
                )

    metric_relations: list[dict[str, Any]] = []
    selected_source_by_metric: dict[str, Any] = {}
    any_supported = False
    any_ambiguous = False

    for metric_key in sorted(metric_rows):
        rows = metric_rows[metric_key]
        supported = [
            row for row in rows if row["decision"] == METRIC_TRANSFER_SUPPORTED
        ]

        unique_supported = _unique_metric_rows(supported)
        if len(unique_supported) > 1:
            any_ambiguous = True
            metric_relations.append(
                {
                    "metric_key": metric_key,
                    "decision": METRIC_TRANSFER_AMBIGUOUS,
                    "representativeness_ceiling": REPRESENTATIVENESS_INSUFFICIENT,
                    "relation_type": None,
                    "relation_id": None,
                    "source": None,
                    "limitations": [
                        "MULTIPLE_DISTINCT_SUPPORTED_RELATIONS_FOR_METRIC"
                    ],
                    "candidate_relation_count": len(unique_supported),
                }
            )
            continue

        if len(unique_supported) == 1:
            row = unique_supported[0]
            any_supported = True
            metric_relations.append(deepcopy(row))
            selected_source_by_metric[metric_key] = deepcopy(row["source"])
            continue

        withheld = rows[0] if rows else None
        if withheld is not None:
            metric_relations.append(deepcopy(withheld))

    if any_ambiguous:
        status = STATUS_AMBIGUOUS
        basis = [
            "MULTIPLE_SUPPORTED_HYDROLOGY_RELATIONS_OVERLAP_FOR_AT_LEAST_ONE_METRIC",
            "RELATION_TRANSFER_WITHHELD_PENDING_DISAMBIGUATION",
        ]
        limitations = ["HYDROLOGY_RELATION_AMBIGUOUS"]
    elif any_supported:
        status = STATUS_SUPPORTED_WITH_LIMITATIONS
        basis = [
            "EXPLICIT_CROSS_WATERBODY_RELATION_EVIDENCE_MATCHED",
            "METRIC_SPECIFIC_TRANSFER_SUPPORTED",
            "RELATION_DOES_NOT_BYPASS_REPRESENTATIVENESS_OR_TRUST_GATING",
        ]
        limitations = _unique_strings(
            [
                "CROSS_WATERBODY_HYDROLOGY_RELATION_REQUIRES_METRIC_LEVEL_GATING",
                *[
                    item
                    for row in metric_relations
                    for item in _string_list(row.get("limitations"))
                ],
            ]
        )
    else:
        status = STATUS_WITHHELD
        basis = [
            "NO_METRIC_HAS_A_SINGLE_SUPPORTED_CROSS_WATERBODY_TRANSFER",
            "HYDROLOGY_RELATION_TRANSFER_WITHHELD",
        ]
        limitations = _unique_strings(
            [
                "CROSS_WATERBODY_HYDROLOGY_TRANSFER_NOT_ESTABLISHED",
                *[
                    item
                    for row in metric_relations
                    for item in _string_list(row.get("limitations"))
                ],
            ]
        )

    return {
        **base,
        "status": status,
        "metric_relations": metric_relations,
        "selected_source_by_metric": selected_source_by_metric,
        "evaluated_relations": evaluated_relations,
        "resolution_basis": basis,
        "limitations": limitations,
    }


def _evaluate_metric_relation(
    *,
    relation: Mapping[str, Any],
    metric: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    relation_type = _relation_type(relation)
    authority = relation.get("authority")
    authority = authority if isinstance(authority, Mapping) else {}
    authority_ok = bool(
        _string(authority.get("provider"))
        and (_string(authority.get("reference")) or _string(authority.get("product")))
    )

    transfer_allowed = metric.get("transfer_allowed") is True
    control_required = relation.get("control_structure_state_required")
    if control_required is None:
        control_required = relation_type == RELATION_STRUCTURE_CONTROLLED
    control_state = relation.get("control_state_evidence")
    control_state = control_state if isinstance(control_state, Mapping) else {}
    control_ok = not control_required or control_state.get("available") is True

    calibration_required = relation_type in {
        RELATION_EMPIRICAL_PROXY,
        RELATION_HYDRAULIC_MODEL,
    }
    calibration = relation.get("calibration_evidence")
    calibration = calibration if isinstance(calibration, Mapping) else {}
    calibration_ok = (
        not calibration_required
        or calibration.get("available") is True
        or _string(calibration.get("status")) in {"CALIBRATED", "VALIDATED", "AUTHORITATIVE"}
    )

    limitations = _unique_strings(
        [
            *_string_list(relation.get("limitations")),
            *_string_list(metric.get("limitations")),
        ]
    )

    if not authority_ok:
        limitations = _append_unique(
            limitations,
            "AUTHORITATIVE_RELATION_PROVENANCE_MISSING",
        )
    if not transfer_allowed:
        limitations = _append_unique(
            limitations,
            "METRIC_TRANSFER_NOT_EXPLICITLY_ALLOWED",
        )
    if not control_ok:
        limitations = _append_unique(
            limitations,
            "CONTROL_STRUCTURE_STATE_EVIDENCE_REQUIRED",
        )
    if not calibration_ok:
        limitations = _append_unique(
            limitations,
            "CALIBRATION_EVIDENCE_REQUIRED_FOR_PROXY_OR_MODEL_TRANSFER",
        )

    supported = authority_ok and transfer_allowed and control_ok and calibration_ok
    ceiling = _representativeness_ceiling(metric.get("representativeness_ceiling"))
    if not supported:
        ceiling = REPRESENTATIVENESS_INSUFFICIENT

    return {
        "metric_key": _string(metric.get("metric_key")),
        "decision": (
            METRIC_TRANSFER_SUPPORTED if supported else METRIC_TRANSFER_WITHHELD
        ),
        "representativeness_ceiling": ceiling,
        "relation_type": relation_type,
        "relation_id": _scalar_id(relation.get("relation_id")),
        "source": deepcopy(dict(source)),
        "authority": deepcopy(dict(authority)),
        "control_structure_state_required": bool(control_required),
        "control_structure_state_available": control_state.get("available") is True,
        "calibration_evidence_required": calibration_required,
        "calibration_evidence_available": calibration_ok if calibration_required else None,
        "uncertainty": deepcopy(metric.get("uncertainty")),
        "limitations": limitations,
    }


def _target_matches(
    relation: Mapping[str, Any],
    identities: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    target = relation.get("target")
    target = target if isinstance(target, Mapping) else {}
    wanted_ids = set(_string_list(target.get("waterbody_ids")))
    wanted_names = {
        normalized
        for value in _string_list(target.get("waterbody_names"))
        if (normalized := _normalize_name(value)) is not None
    }

    route_ids = {
        value
        for identity in identities
        if (value := _string(identity.get("waterbody_id"))) is not None
    }
    route_names: set[str] = set()
    for identity in identities:
        for value in _string_list(identity.get("identity_names")):
            normalized = _normalize_name(value)
            if normalized is not None:
                route_names.add(normalized)

    if wanted_ids:
        if route_ids & wanted_ids:
            return True, ["TARGET_WATERBODY_ID_MATCH"]
        return False, ["TARGET_WATERBODY_ID_MISMATCH"]

    if wanted_names:
        if route_names & wanted_names:
            return True, ["TARGET_WATERBODY_NAME_MATCH"]
        return False, ["TARGET_WATERBODY_NAME_MISMATCH"]

    return False, ["TARGET_WATERBODY_SELECTOR_MISSING"]


def _source_matches(
    relation: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    source = relation.get("source")
    source = source if isinstance(source, Mapping) else {}

    wanted_station_ids = {
        _station_registry_number_value(value)
        for value in _sequence(source.get("station_registry_numbers"))
    }
    wanted_station_ids.discard(None)

    wanted_watercourses = {
        normalized
        for value in _string_list(source.get("watercourse_names"))
        if (normalized := _normalize_name(value)) is not None
    }

    candidate_station = _station_registry_number(candidate)
    candidate_watercourse = _normalize_name(candidate.get("watercourse"))

    if wanted_station_ids:
        if candidate_station in wanted_station_ids:
            return True, ["SOURCE_STATION_REGISTRY_MATCH"]
        return False, ["SOURCE_STATION_REGISTRY_MISMATCH"]

    if wanted_watercourses:
        if candidate_watercourse in wanted_watercourses:
            return True, ["SOURCE_WATERCOURSE_NAME_MATCH"]
        return False, ["SOURCE_WATERCOURSE_NAME_MISMATCH"]

    return False, ["SOURCE_SELECTOR_MISSING"]


def _temporal_relation_matches(
    relation: Mapping[str, Any],
    route_interval: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    valid_from_raw = relation.get("valid_from")
    valid_to_raw = relation.get("valid_to")
    if valid_from_raw is None and valid_to_raw is None:
        return True, ["RELATION_HAS_NO_DECLARED_VALIDITY_WINDOW"]

    valid_from = _parse_aware_datetime(valid_from_raw)
    valid_to = _parse_aware_datetime(valid_to_raw)
    route_start = _parse_aware_datetime(route_interval.get("start_timestamp"))
    route_end = _parse_aware_datetime(route_interval.get("end_timestamp"))

    if route_start is None or route_end is None:
        return False, ["ROUTE_TIME_UNAVAILABLE_FOR_RELATION_VALIDITY_CHECK"]
    if valid_from_raw is not None and valid_from is None:
        return False, ["RELATION_VALID_FROM_INVALID_OR_TIMEZONE_UNAWARE"]
    if valid_to_raw is not None and valid_to is None:
        return False, ["RELATION_VALID_TO_INVALID_OR_TIMEZONE_UNAWARE"]
    if valid_from is not None and route_end < valid_from:
        return False, ["ROUTE_PRECEDES_RELATION_VALIDITY"]
    if valid_to is not None and route_start > valid_to:
        return False, ["ROUTE_FOLLOWS_RELATION_VALIDITY"]
    return True, ["ROUTE_OVERLAPS_RELATION_VALIDITY_WINDOW"]


def _candidate_sources(source_route: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    resolved = source_route.get("resolved_hydrology_source")
    if isinstance(resolved, Mapping):
        _append_candidate(result, seen, resolved)

    for evaluated in _sequence_of_mappings(source_route.get("evaluated_candidates")):
        candidate = evaluated.get("candidate_source")
        if isinstance(candidate, Mapping):
            _append_candidate(result, seen, candidate)

    return result


def _append_candidate(
    result: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
    candidate: Mapping[str, Any],
) -> None:
    key = (
        _station_registry_number(candidate),
        _string(candidate.get("station_name")),
        _normalize_name(candidate.get("watercourse")),
        candidate.get("latitude_deg"),
        candidate.get("longitude_deg"),
    )
    if key in seen:
        return
    seen.add(key)
    result.append(deepcopy(dict(candidate)))


def _route_interval(route_input: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(route_input, Mapping):
        return {"start_timestamp": None, "end_timestamp": None}
    timestamps: list[datetime] = []
    for segment in _sequence_of_mappings(route_input.get("segments")):
        for key in ("start_timestamp", "midpoint_timestamp", "end_timestamp"):
            parsed = _parse_aware_datetime(segment.get(key))
            if parsed is not None:
                timestamps.append(parsed)
    if not timestamps:
        return {"start_timestamp": None, "end_timestamp": None}
    return {
        "start_timestamp": min(timestamps).isoformat(),
        "end_timestamp": max(timestamps).isoformat(),
    }


def _unique_metric_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        source = row.get("source")
        source = source if isinstance(source, Mapping) else {}
        key = (
            row.get("metric_key"),
            row.get("relation_id"),
            row.get("relation_type"),
            _station_registry_number(source),
            row.get("representativeness_ceiling"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(deepcopy(dict(row)))
    return result


def _representativeness_ceiling(value: Any) -> str:
    text = _string(value)
    if text in {
        REPRESENTATIVENESS_REPRESENTATIVE,
        REPRESENTATIVENESS_PARTIAL,
        REPRESENTATIVENESS_INSUFFICIENT,
        REPRESENTATIVENESS_NOT_REPRESENTATIVE,
    }:
        return text
    return REPRESENTATIVENESS_INSUFFICIENT


def _relation_type(relation: Mapping[str, Any]) -> str:
    value = _string(relation.get("relation_type"))
    if value in {
        RELATION_DIRECT_LOCAL_GAUGE,
        RELATION_AUTHORITATIVE_REACH_CROSSWALK,
        RELATION_UNCONTROLLED_HYDRAULIC_CONNECTION,
        RELATION_STRUCTURE_CONTROLLED,
        RELATION_EMPIRICAL_PROXY,
        RELATION_HYDRAULIC_MODEL,
    }:
        return value
    return RELATION_UNKNOWN


def _route_key(route: Mapping[str, Any], fallback: int) -> tuple[int, int | None]:
    route_index = _integer(route.get("route_index"))
    if route_index is None:
        route_index = fallback
    return route_index, _integer(route.get("exercise_index"))


def _station_registry_number(source: Mapping[str, Any]) -> str | None:
    return _station_registry_number_value(source.get("station_registry_number"))


def _station_registry_number_value(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _string(value)


def _normalize_name(value: Any) -> str | None:
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


def _parse_aware_datetime(value: Any) -> datetime | None:
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
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _overall_status(routes: Sequence[Mapping[str, Any]]) -> str:
    if not routes:
        return STATUS_UNAVAILABLE
    statuses = {_string(route.get("status")) for route in routes}
    statuses.discard(None)
    for status in (
        STATUS_AMBIGUOUS,
        STATUS_WITHHELD,
        STATUS_SUPPORTED_WITH_LIMITATIONS,
        STATUS_NOT_REQUIRED,
        STATUS_UNAVAILABLE,
        STATUS_NOT_APPLICABLE,
    ):
        if status in statuses:
            return status
    return STATUS_UNAVAILABLE


def _schema_version(source: Mapping[str, Any] | None) -> str | None:
    if not isinstance(source, Mapping):
        return None
    return _string(source.get("schema_version"))


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _sequence(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return list(value)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in value:
        text = _string(item)
        if text is not None:
            result.append(text)
    return result


def _scalar_id(value: Any) -> str | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int)):
        return value
    return str(value)


def _unique_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _string(value)
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _append_unique(values: list[str], value: str) -> list[str]:
    if value in values:
        return values
    return [*values, value]


def _empty_status_counts() -> dict[str, int]:
    return {
        STATUS_NOT_REQUIRED: 0,
        STATUS_SUPPORTED_WITH_LIMITATIONS: 0,
        STATUS_WITHHELD: 0,
        STATUS_AMBIGUOUS: 0,
        STATUS_UNAVAILABLE: 0,
        STATUS_NOT_APPLICABLE: 0,
    }
