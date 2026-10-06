from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_TRUSTED = "TRUSTED"
STATUS_TRUSTED_WITH_LIMITATIONS = "TRUSTED_WITH_LIMITATIONS"
STATUS_WITHHELD = "WITHHELD"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_MIXED = "MIXED"

REPRESENTATIVENESS_REPRESENTATIVE = "REPRESENTATIVE"
REPRESENTATIVENESS_PARTIAL = "PARTIALLY_REPRESENTATIVE"
REPRESENTATIVENESS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
REPRESENTATIVENESS_NOT_REPRESENTATIVE = "NOT_REPRESENTATIVE"
REPRESENTATIVENESS_NOT_APPLICABLE = "NOT_APPLICABLE"


def build_trusted_route_hydrology_context(
    route_hydrology_context: Mapping[str, Any] | None,
    route_hydrology_representativeness: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project normalized hydrology context through representativeness gating.

    The source ``route_hydrology_context`` remains untouched and auditably
    available elsewhere.  This function only creates a downstream trust
    projection.  It never converts water level or discharge into local current
    velocity and never invents missing hydrology evidence.
    """
    context_routes = _sequence_of_mappings(
        route_hydrology_context.get("routes")
        if isinstance(route_hydrology_context, Mapping)
        else None
    )
    representativeness_routes = _sequence_of_mappings(
        route_hydrology_representativeness.get("routes")
        if isinstance(route_hydrology_representativeness, Mapping)
        else None
    )

    context_by_index = {
        _route_index(route, position): route
        for position, route in enumerate(context_routes)
    }
    representativeness_by_index = {
        _route_index(route, position): route
        for position, route in enumerate(representativeness_routes)
    }

    route_indices: list[int] = []
    for position, route in enumerate(representativeness_routes):
        index = _route_index(route, position)
        if index not in route_indices:
            route_indices.append(index)
    for position, route in enumerate(context_routes):
        index = _route_index(route, position)
        if index not in route_indices:
            route_indices.append(index)

    route_results: list[dict[str, Any]] = []
    counts = {
        STATUS_TRUSTED: 0,
        STATUS_TRUSTED_WITH_LIMITATIONS: 0,
        STATUS_WITHHELD: 0,
        STATUS_NOT_APPLICABLE: 0,
    }

    for route_index in route_indices:
        route_result = _build_route_result(
            route_index=route_index,
            source_context=context_by_index.get(route_index),
            representativeness=representativeness_by_index.get(route_index),
        )
        route_results.append(route_result)
        counts[route_result["trust_status"]] += 1

    return {
        "provider": _string(
            route_hydrology_context.get("provider")
            if isinstance(route_hydrology_context, Mapping)
            else None
        ),
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _overall_status(route_results),
        "route_count": len(route_results),
        "trusted_route_count": counts[STATUS_TRUSTED],
        "trusted_with_limitations_route_count": counts[
            STATUS_TRUSTED_WITH_LIMITATIONS
        ],
        "withheld_route_count": counts[STATUS_WITHHELD],
        "not_applicable_route_count": counts[STATUS_NOT_APPLICABLE],
        "input_provenance": {
            "route_hydrology_context_schema_version": (
                route_hydrology_context.get("schema_version")
                if isinstance(route_hydrology_context, Mapping)
                else None
            ),
            "route_hydrology_representativeness_schema_version": (
                route_hydrology_representativeness.get("schema_version")
                if isinstance(route_hydrology_representativeness, Mapping)
                else None
            ),
            "hydrology_provider": _string(
                route_hydrology_context.get("provider")
                if isinstance(route_hydrology_context, Mapping)
                else None
            ),
        },
        "policy": {
            "representative": STATUS_TRUSTED,
            "partially_representative": STATUS_TRUSTED_WITH_LIMITATIONS,
            "insufficient_evidence": STATUS_WITHHELD,
            "not_representative": STATUS_WITHHELD,
            "not_applicable": STATUS_NOT_APPLICABLE,
            "missing_source_context": STATUS_WITHHELD,
        },
        "scope": {
            "domain": "TRUSTED_ROUTE_HYDROLOGY_CONTEXT",
            "preserves_source_route_hydrology_context": True,
            "controls_downstream_hydrology_context_use": True,
            "requires_source_context_for_trusted_use": True,
            "propagates_representativeness_limitations": True,
            "requires_temporal_support_for_segment_inclusion": True,
            "mutates_source_hydrology_context": False,
            "estimates_hydrology_representativeness": False,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_trusted_route_hydrology_context_summary(
    trusted_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a compact projection without trusted per-segment payloads."""
    result = deepcopy(dict(trusted_context))
    result["routes"] = []
    for route in _sequence_of_mappings(trusted_context.get("routes")):
        compact = deepcopy(dict(route))
        source_context = compact.get("trusted_context")
        if isinstance(source_context, Mapping):
            source_context = deepcopy(dict(source_context))
            source_context.pop("segments", None)
            source_context["segments_included"] = False
            compact["trusted_context"] = source_context
        compact["segments_included"] = False
        result["routes"].append(compact)
    return result


def _build_route_result(
    *,
    route_index: int,
    source_context: Mapping[str, Any] | None,
    representativeness: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_context = (
        source_context if isinstance(source_context, Mapping) else None
    )
    representativeness = (
        representativeness
        if isinstance(representativeness, Mapping)
        else None
    )

    rep_status = _string(
        representativeness.get("status")
        if representativeness is not None
        else None
    )
    exercise_index = _integer(
        representativeness.get("exercise_index")
        if representativeness is not None
        else None
    )
    if exercise_index is None and source_context is not None:
        exercise_index = _integer(source_context.get("exercise_index"))

    source_segments = _sequence_of_mappings(
        source_context.get("segments") if source_context is not None else None
    )
    representativeness_segments = _sequence_of_mappings(
        representativeness.get("segments")
        if representativeness is not None
        else None
    )
    source_context_available = source_context is not None

    limitations = _string_list(
        representativeness.get("limitations")
        if representativeness is not None
        else None
    )
    rep_basis = _string_list(
        representativeness.get("resolution_basis")
        if representativeness is not None
        else None
    )

    trusted_projection = None
    trusted_segment_count = 0
    segment_alignment_available = bool(representativeness_segments) or not source_segments

    if rep_status == REPRESENTATIVENESS_NOT_APPLICABLE:
        trust_status = STATUS_NOT_APPLICABLE
        included = False
        usable_with_limitations = False
        trust_basis = [
            "HYDROLOGY_REPRESENTATIVENESS_NOT_APPLICABLE",
            "RIVER_HYDROLOGY_CONTEXT_NOT_APPLICABLE",
        ]
    elif not source_context_available:
        trust_status = STATUS_WITHHELD
        included = False
        usable_with_limitations = False
        trust_basis = [
            "SOURCE_ROUTE_HYDROLOGY_CONTEXT_MISSING",
            "TRUST_CANNOT_BE_CREATED_WITHOUT_SOURCE_EVIDENCE",
        ]
    elif rep_status in {
        REPRESENTATIVENESS_REPRESENTATIVE,
        REPRESENTATIVENESS_PARTIAL,
    } and not segment_alignment_available:
        trust_status = STATUS_WITHHELD
        included = False
        usable_with_limitations = False
        trust_basis = [
            "REPRESENTATIVENESS_SEGMENT_SUPPORT_UNAVAILABLE",
            "HYDROLOGY_CONTEXT_WITHHELD_TO_AVOID_UNSUPPORTED_SEGMENT_TRUST",
        ]
    elif rep_status == REPRESENTATIVENESS_REPRESENTATIVE:
        trusted_projection, trusted_segment_count = _trusted_segment_projection(
            source_context, representativeness_segments
        )
        included = trusted_projection is not None
        trust_status = STATUS_TRUSTED if included else STATUS_WITHHELD
        usable_with_limitations = False
        trust_basis = (
            [
                "HYDROLOGY_REPRESENTATIVENESS_ACCEPTED",
                "TEMPORALLY_SUPPORTED_SEGMENTS_INCLUDED",
                "SOURCE_ROUTE_HYDROLOGY_CONTEXT_INCLUDED",
            ]
            if included
            else [
                "HYDROLOGY_CONTEXT_SEGMENT_ALIGNMENT_FAILED",
                "HYDROLOGY_CONTEXT_WITHHELD_CONSERVATIVELY",
            ]
        )
    elif rep_status == REPRESENTATIVENESS_PARTIAL:
        trusted_projection, trusted_segment_count = _trusted_segment_projection(
            source_context, representativeness_segments
        )
        included = trusted_projection is not None
        trust_status = (
            STATUS_TRUSTED_WITH_LIMITATIONS if included else STATUS_WITHHELD
        )
        usable_with_limitations = included
        trust_basis = (
            [
                "PARTIAL_HYDROLOGY_REPRESENTATIVENESS_ACCEPTED_WITH_LIMITATIONS",
                "TEMPORALLY_SUPPORTED_SEGMENTS_INCLUDED",
                "REPRESENTATIVENESS_LIMITATIONS_MUST_PROPAGATE_DOWNSTREAM",
                "SOURCE_ROUTE_HYDROLOGY_CONTEXT_INCLUDED",
            ]
            if included
            else [
                "HYDROLOGY_CONTEXT_SEGMENT_ALIGNMENT_FAILED",
                "HYDROLOGY_CONTEXT_WITHHELD_CONSERVATIVELY",
            ]
        )
    elif rep_status == REPRESENTATIVENESS_NOT_REPRESENTATIVE:
        trust_status = STATUS_WITHHELD
        included = False
        usable_with_limitations = False
        trust_basis = [
            "HYDROLOGY_CONTEXT_WITHHELD_NOT_REPRESENTATIVE",
        ]
    elif rep_status == REPRESENTATIVENESS_INSUFFICIENT:
        trust_status = STATUS_WITHHELD
        included = False
        usable_with_limitations = False
        trust_basis = [
            "HYDROLOGY_CONTEXT_WITHHELD_INSUFFICIENT_REPRESENTATIVENESS_EVIDENCE",
        ]
    else:
        trust_status = STATUS_WITHHELD
        included = False
        usable_with_limitations = False
        trust_basis = [
            "HYDROLOGY_REPRESENTATIVENESS_STATUS_UNAVAILABLE_OR_UNKNOWN",
            "HYDROLOGY_CONTEXT_WITHHELD_CONSERVATIVELY",
        ]

    return {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "available": representativeness is not None or source_context_available,
        "applicable": (
            False
            if trust_status == STATUS_NOT_APPLICABLE
            else True
        ),
        "representativeness_status": rep_status,
        "trust_status": trust_status,
        "source_context_available": source_context_available,
        "hydrology_context_included": included,
        "usable_for_downstream_environment_context": included,
        "usable_with_limitations": usable_with_limitations,
        "source_context_segment_count": len(source_segments),
        "trusted_context_segment_count": trusted_segment_count if included else 0,
        "withheld_context_segment_count": (
            len(source_segments) - trusted_segment_count if included else len(source_segments)
        ),
        "segment_filter_applied": bool(source_segments) and included,
        "representativeness_resolution_basis": rep_basis,
        "representativeness_limitations": limitations,
        "trust_basis": trust_basis,
        "trusted_context": trusted_projection if included else None,
    }


def _trusted_segment_projection(
    source_context: Mapping[str, Any] | None,
    representativeness_segments: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, int]:
    if source_context is None:
        return None, 0

    source_segments = _sequence_of_mappings(source_context.get("segments"))
    if not source_segments:
        return deepcopy(dict(source_context)), 0

    supported_indices: set[int] = set()
    for position, segment in enumerate(representativeness_segments):
        if segment.get("temporally_supported") is not True:
            continue
        index = _integer(segment.get("segment_index"))
        supported_indices.add(index if index is not None else position)

    trusted_segments = []
    for position, segment in enumerate(source_segments):
        index = _integer(segment.get("segment_index"))
        index = index if index is not None else position
        if index in supported_indices:
            trusted_segments.append(deepcopy(dict(segment)))

    if not trusted_segments:
        return None, 0

    projection = deepcopy(dict(source_context))
    projection["segments"] = trusted_segments
    return projection, len(trusted_segments)


def _overall_status(routes: Sequence[Mapping[str, Any]]) -> str | None:
    statuses = {
        _string(route.get("trust_status"))
        for route in routes
        if _string(route.get("trust_status")) is not None
    }
    if not statuses:
        return None
    if len(statuses) == 1:
        return next(iter(statuses))
    return STATUS_MIXED


def _route_index(route: Mapping[str, Any], fallback: int) -> int:
    parsed = _integer(route.get("route_index"))
    return parsed if parsed is not None else fallback


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if item is not None]


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
