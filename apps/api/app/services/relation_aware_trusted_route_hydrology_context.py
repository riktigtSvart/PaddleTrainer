from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_TRUSTED = "TRUSTED"
STATUS_TRUSTED_WITH_LIMITATIONS = "TRUSTED_WITH_LIMITATIONS"
STATUS_WITHHELD = "WITHHELD"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_MIXED = "MIXED"

RELATION_STATUS_SUPPORTED_WITH_LIMITATIONS = "SUPPORTED_WITH_LIMITATIONS"
RELATION_STATUS_AMBIGUOUS = "AMBIGUOUS"
RELATION_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
METRIC_TRANSFER_SUPPORTED = "TRANSFER_SUPPORTED"

TRUST_MODE_DIRECT = "DIRECT_TRUST_PROJECTION"
TRUST_MODE_RELATION = "RELATION_DERIVED_METRIC_PROJECTION"
TRUST_MODE_WITHHELD = "WITHHELD"
TRUST_MODE_NOT_APPLICABLE = "NOT_APPLICABLE"

# Explicit metric-to-payload mapping. Unknown/future metric names are withheld until
# their payload semantics are added deliberately. This prevents accidental leakage
# of hydrology fields merely because they happen to be present on the source segment.
METRIC_PAYLOAD_FIELDS: dict[str, str] = {
    "WATER_LEVEL": "water_level",
    "DISCHARGE": "discharge",
    "WATER_TEMPERATURE": "water_temperature",
}

# Structural fields are safe to preserve because they identify/alignment-index the
# source segment; they are not hydrology measurements.
STRUCTURAL_SEGMENT_FIELDS = {
    "order_index",
    "segment_index",
    "source_segment_index",
    "source_route_index",
    "start_timestamp",
    "midpoint_timestamp",
    "end_timestamp",
}



def build_relation_aware_trusted_route_hydrology_context(
    route_hydrology_context: Mapping[str, Any] | None,
    trusted_route_hydrology_context: Mapping[str, Any] | None,
    route_hydrology_relation_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project trusted hydrology with metric-specific relation gating.

    Existing direct/identity-supported V17 trust remains authoritative and is
    passed through unchanged in measurement content.  Cross-waterbody relation
    evidence is only considered when the direct projection is WITHHELD.

    Relation-derived trust is strictly metric-aware: only explicitly supported
    metric payloads are copied from raw route hydrology context.  A supported
    WATER_LEVEL relation therefore never authorizes DISCHARGE, temperature, or
    local-current fields.  Unknown metric payload mappings are withheld.
    """
    source_routes = _sequence_of_mappings(
        route_hydrology_context.get("routes")
        if isinstance(route_hydrology_context, Mapping)
        else None
    )
    direct_routes = _sequence_of_mappings(
        trusted_route_hydrology_context.get("routes")
        if isinstance(trusted_route_hydrology_context, Mapping)
        else None
    )
    relation_routes = _sequence_of_mappings(
        route_hydrology_relation_evidence.get("routes")
        if isinstance(route_hydrology_relation_evidence, Mapping)
        else None
    )

    source_by_key = {
        _route_key(route, position): route
        for position, route in enumerate(source_routes)
    }
    direct_by_key = {
        _route_key(route, position): route
        for position, route in enumerate(direct_routes)
    }
    relation_by_key = {
        _route_key(route, position): route
        for position, route in enumerate(relation_routes)
    }

    route_keys: list[tuple[int, int | None]] = []
    for collection in (direct_routes, source_routes, relation_routes):
        for position, route in enumerate(collection):
            key = _route_key(route, position)
            if key not in route_keys:
                route_keys.append(key)

    results: list[dict[str, Any]] = []
    counts = {
        STATUS_TRUSTED: 0,
        STATUS_TRUSTED_WITH_LIMITATIONS: 0,
        STATUS_WITHHELD: 0,
        STATUS_NOT_APPLICABLE: 0,
    }

    for key in route_keys:
        result = _build_route_result(
            route_key=key,
            source_context=source_by_key.get(key),
            direct_trust=direct_by_key.get(key),
            relation_evidence=relation_by_key.get(key),
        )
        results.append(result)
        counts[result["trust_status"]] += 1

    return {
        "provider": _string(
            route_hydrology_context.get("provider")
            if isinstance(route_hydrology_context, Mapping)
            else None
        ),
        "schema_version": SCHEMA_VERSION,
        "available": bool(results),
        "status": _overall_status(results),
        "route_count": len(results),
        "trusted_route_count": counts[STATUS_TRUSTED],
        "trusted_with_limitations_route_count": counts[
            STATUS_TRUSTED_WITH_LIMITATIONS
        ],
        "withheld_route_count": counts[STATUS_WITHHELD],
        "not_applicable_route_count": counts[STATUS_NOT_APPLICABLE],
        "input_provenance": {
            "route_hydrology_context_schema_version": _schema_version(
                route_hydrology_context
            ),
            "trusted_route_hydrology_context_schema_version": _schema_version(
                trusted_route_hydrology_context
            ),
            "route_hydrology_relation_evidence_schema_version": _schema_version(
                route_hydrology_relation_evidence
            ),
        },
        "policy": {
            "direct_trust_precedence": True,
            "relation_considered_only_when_direct_trust_withheld": True,
            "relation_derived_trust_ceiling": STATUS_TRUSTED_WITH_LIMITATIONS,
            "metric_transfer_must_be_explicitly_supported": True,
            "unknown_metric_payload_mapping": STATUS_WITHHELD,
            "segment_included_when_at_least_one_authorized_metric_payload_available": True,
        },
        "scope": {
            "domain": "RELATION_AWARE_TRUSTED_ROUTE_HYDROLOGY_CONTEXT",
            "preserves_existing_direct_trust": True,
            "supports_cross_waterbody_relation_transfer": True,
            "controls_relation_derived_metric_inclusion": True,
            "metric_specific_transfer_required": True,
            "copies_unapproved_hydrology_metrics": False,
            "estimates_local_current_velocity": False,
            "infers_current_from_water_level": False,
            "infers_current_from_discharge": False,
            "mutates_source_hydrology_context": False,
            "mutates_direct_trust_projection": False,
            "mutates_relation_evidence": False,
            "raw_data_mutated": False,
        },
        "routes": results,
    }



def build_relation_aware_trusted_route_hydrology_context_summary(
    trusted_context: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(trusted_context))
    result["routes"] = []
    for route in _sequence_of_mappings(trusted_context.get("routes")):
        compact = deepcopy(dict(route))
        context = compact.get("trusted_context")
        if isinstance(context, Mapping):
            context = deepcopy(dict(context))
            context.pop("segments", None)
            context["segments_included"] = False
            compact["trusted_context"] = context
        compact["segments_included"] = False
        result["routes"].append(compact)
    return result



def _build_route_result(
    *,
    route_key: tuple[int, int | None],
    source_context: Mapping[str, Any] | None,
    direct_trust: Mapping[str, Any] | None,
    relation_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    route_index, exercise_index = route_key
    direct_status = _string(
        direct_trust.get("trust_status")
        if isinstance(direct_trust, Mapping)
        else None
    )

    if direct_status in {STATUS_TRUSTED, STATUS_TRUSTED_WITH_LIMITATIONS}:
        result = deepcopy(dict(direct_trust))
        result["route_index"] = route_index
        if result.get("exercise_index") is None:
            result["exercise_index"] = exercise_index
        result["trust_mode"] = TRUST_MODE_DIRECT
        result["direct_trust_status"] = direct_status
        result["relation_evidence_status"] = _string(
            relation_evidence.get("status")
            if isinstance(relation_evidence, Mapping)
            else None
        )
        result["relation_metric_projection_applied"] = False
        result["authorized_metric_keys"] = []
        result["withheld_metric_keys"] = []
        result["unsupported_metric_payload_keys"] = []
        result["relation_metric_trust"] = []
        return result

    if direct_status == STATUS_NOT_APPLICABLE:
        result = deepcopy(dict(direct_trust))
        result["route_index"] = route_index
        if result.get("exercise_index") is None:
            result["exercise_index"] = exercise_index
        result["trust_mode"] = TRUST_MODE_NOT_APPLICABLE
        result["direct_trust_status"] = direct_status
        result["relation_evidence_status"] = _string(
            relation_evidence.get("status")
            if isinstance(relation_evidence, Mapping)
            else None
        )
        result["relation_metric_projection_applied"] = False
        result["authorized_metric_keys"] = []
        result["withheld_metric_keys"] = []
        result["unsupported_metric_payload_keys"] = []
        result["relation_metric_trust"] = []
        return result

    relation_status = _string(
        relation_evidence.get("status")
        if isinstance(relation_evidence, Mapping)
        else None
    )
    source_segments = _sequence_of_mappings(
        source_context.get("segments") if isinstance(source_context, Mapping) else None
    )

    base = {
        "route_index": route_index,
        "exercise_index": exercise_index,
        "available": (
            isinstance(source_context, Mapping)
            or isinstance(direct_trust, Mapping)
            or isinstance(relation_evidence, Mapping)
        ),
        "applicable": relation_status != RELATION_STATUS_NOT_APPLICABLE,
        "direct_trust_status": direct_status,
        "relation_evidence_status": relation_status,
        "trust_mode": TRUST_MODE_WITHHELD,
        "source_context_available": isinstance(source_context, Mapping),
        "source_context_segment_count": len(source_segments),
        "relation_metric_projection_applied": False,
        "authorized_metric_keys": [],
        "withheld_metric_keys": [],
        "unsupported_metric_payload_keys": [],
        "relation_metric_trust": [],
    }

    if relation_status == RELATION_STATUS_NOT_APPLICABLE:
        return {
            **base,
            "trust_status": STATUS_NOT_APPLICABLE,
            "trust_mode": TRUST_MODE_NOT_APPLICABLE,
            "hydrology_context_included": False,
            "usable_for_downstream_environment_context": False,
            "usable_with_limitations": False,
            "trusted_context_segment_count": 0,
            "withheld_context_segment_count": len(source_segments),
            "segment_filter_applied": False,
            "representativeness_status": None,
            "representativeness_resolution_basis": [],
            "representativeness_limitations": [],
            "trust_basis": [
                "HYDROLOGY_RELATION_NOT_APPLICABLE",
                "RIVER_HYDROLOGY_CONTEXT_NOT_APPLICABLE",
            ],
            "trusted_context": None,
        }

    if relation_status == RELATION_STATUS_AMBIGUOUS:
        return _withheld_result(
            base,
            source_segments,
            basis=[
                "HYDROLOGY_RELATION_AMBIGUOUS",
                "RELATION_DERIVED_HYDROLOGY_WITHHELD",
            ],
            limitations=["HYDROLOGY_RELATION_AMBIGUOUS"],
        )

    if relation_status != RELATION_STATUS_SUPPORTED_WITH_LIMITATIONS:
        return _withheld_result(
            base,
            source_segments,
            basis=[
                "NO_SINGLE_SUPPORTED_HYDROLOGY_RELATION_AVAILABLE",
                "RELATION_DERIVED_HYDROLOGY_WITHHELD",
            ],
            limitations=["METRIC_SPECIFIC_HYDROLOGY_TRANSFER_NOT_ESTABLISHED"],
        )

    if not isinstance(source_context, Mapping):
        return _withheld_result(
            base,
            source_segments,
            basis=[
                "SOURCE_ROUTE_HYDROLOGY_CONTEXT_MISSING",
                "RELATION_CANNOT_CREATE_MEASUREMENT_EVIDENCE",
            ],
            limitations=["SOURCE_HYDROLOGY_MEASUREMENT_EVIDENCE_UNAVAILABLE"],
        )

    metric_relations = _sequence_of_mappings(relation_evidence.get("metric_relations"))
    supported_rows = [
        row
        for row in metric_relations
        if _string(row.get("decision")) == METRIC_TRANSFER_SUPPORTED
    ]
    authorized_keys = _unique_strings(
        _string(row.get("metric_key"))
        for row in supported_rows
        if _string(row.get("metric_key")) is not None
    )
    withheld_keys = _unique_strings(
        _string(row.get("metric_key"))
        for row in metric_relations
        if _string(row.get("decision")) != METRIC_TRANSFER_SUPPORTED
        and _string(row.get("metric_key")) is not None
    )
    supported_payload_fields = {
        key: METRIC_PAYLOAD_FIELDS[key]
        for key in authorized_keys
        if key in METRIC_PAYLOAD_FIELDS
    }
    unsupported_payload_keys = [
        key for key in authorized_keys if key not in METRIC_PAYLOAD_FIELDS
    ]

    metric_trust = []
    for row in metric_relations:
        item = deepcopy(dict(row))
        metric_key = _string(item.get("metric_key"))
        item["payload_field"] = METRIC_PAYLOAD_FIELDS.get(metric_key)
        item["payload_projection_supported"] = (
            metric_key in supported_payload_fields
            if metric_key is not None
            else False
        )
        if (
            _string(item.get("decision")) == METRIC_TRANSFER_SUPPORTED
            and metric_key in unsupported_payload_keys
        ):
            item["limitations"] = _append_unique(
                _string_list(item.get("limitations")),
                "METRIC_PAYLOAD_MAPPING_NOT_IMPLEMENTED",
            )
        metric_trust.append(item)

    if not supported_payload_fields:
        return _withheld_result(
            {
                **base,
                "authorized_metric_keys": authorized_keys,
                "withheld_metric_keys": withheld_keys,
                "unsupported_metric_payload_keys": unsupported_payload_keys,
                "relation_metric_trust": metric_trust,
            },
            source_segments,
            basis=[
                "NO_SUPPORTED_RELATION_METRIC_HAS_AN_IMPLEMENTED_PAYLOAD_MAPPING",
                "RELATION_DERIVED_HYDROLOGY_WITHHELD",
            ],
            limitations=[
                "METRIC_PAYLOAD_MAPPING_REQUIRED_BEFORE_TRUSTED_TRANSFER",
            ],
        )

    projected_segments = []
    for position, segment in enumerate(source_segments):
        projected = _project_relation_segment(
            segment,
            position=position,
            supported_payload_fields=supported_payload_fields,
        )
        if projected is not None:
            projected_segments.append(projected)

    if not projected_segments:
        return _withheld_result(
            {
                **base,
                "authorized_metric_keys": authorized_keys,
                "withheld_metric_keys": withheld_keys,
                "unsupported_metric_payload_keys": unsupported_payload_keys,
                "relation_metric_trust": metric_trust,
            },
            source_segments,
            basis=[
                "AUTHORIZED_RELATION_METRICS_HAVE_NO_SOURCE_SEGMENT_PAYLOAD",
                "RELATION_DERIVED_HYDROLOGY_WITHHELD",
            ],
            limitations=["AUTHORIZED_HYDROLOGY_METRIC_PAYLOAD_UNAVAILABLE"],
        )

    projection = deepcopy(dict(source_context))
    projection["segments"] = projected_segments
    projection["relation_derived"] = True
    projection["authorized_metric_keys"] = list(authorized_keys)
    projection["withheld_metric_keys"] = list(withheld_keys)

    relation_limitations = _unique_strings(
        item
        for row in metric_trust
        for item in _string_list(row.get("limitations"))
    )
    limitations = _unique_strings(
        [
            "CROSS_WATERBODY_HYDROLOGY_RELATION_DERIVED_CONTEXT",
            "RELATION_DERIVED_TRUST_REQUIRES_METRIC_SPECIFIC_INTERPRETATION",
            *relation_limitations,
            *(
                ["SOME_SUPPORTED_RELATION_METRICS_HAVE_NO_PAYLOAD_MAPPING"]
                if unsupported_payload_keys
                else []
            ),
        ]
    )

    return {
        **base,
        "trust_status": STATUS_TRUSTED_WITH_LIMITATIONS,
        "trust_mode": TRUST_MODE_RELATION,
        "hydrology_context_included": True,
        "usable_for_downstream_environment_context": True,
        "usable_with_limitations": True,
        "trusted_context_segment_count": len(projected_segments),
        "withheld_context_segment_count": len(source_segments) - len(projected_segments),
        "segment_filter_applied": bool(source_segments),
        "representativeness_status": "METRIC_SPECIFIC_RELATION",
        "representativeness_resolution_basis": [
            "EXPLICIT_CROSS_WATERBODY_RELATION_EVIDENCE_MATCHED",
            "METRIC_SPECIFIC_TRANSFER_APPLIED",
        ],
        "representativeness_limitations": limitations,
        "trust_basis": [
            "DIRECT_HYDROLOGY_TRUST_WAS_WITHHELD",
            "EXPLICIT_METRIC_SPECIFIC_HYDROLOGY_RELATION_ACCEPTED_WITH_LIMITATIONS",
            "ONLY_AUTHORIZED_METRIC_PAYLOADS_INCLUDED",
            "RELATION_DERIVED_TRUST_CEILING_IS_TRUSTED_WITH_LIMITATIONS",
        ],
        "relation_metric_projection_applied": True,
        "authorized_metric_keys": authorized_keys,
        "withheld_metric_keys": withheld_keys,
        "unsupported_metric_payload_keys": unsupported_payload_keys,
        "relation_metric_trust": metric_trust,
        "trusted_context": projection,
    }



def _project_relation_segment(
    segment: Mapping[str, Any],
    *,
    position: int,
    supported_payload_fields: Mapping[str, str],
) -> dict[str, Any] | None:
    projected: dict[str, Any] = {}
    for key in STRUCTURAL_SEGMENT_FIELDS:
        if key in segment:
            projected[key] = deepcopy(segment.get(key))
    if "segment_index" not in projected:
        projected["segment_index"] = position

    included_metric_keys: list[str] = []
    for metric_key, payload_field in supported_payload_fields.items():
        if payload_field not in segment:
            continue
        payload = segment.get(payload_field)
        if payload is None:
            continue
        projected[payload_field] = deepcopy(payload)
        included_metric_keys.append(metric_key)

    # These fields are intentionally never copied, even if present upstream:
    # current_speed_estimate_mps, current_direction_deg, or any unknown metric.
    if not included_metric_keys:
        return None

    projected["relation_authorized_metric_keys"] = included_metric_keys
    projected["relation_derived"] = True
    return projected



def _withheld_result(
    base: Mapping[str, Any],
    source_segments: Sequence[Mapping[str, Any]],
    *,
    basis: Sequence[str],
    limitations: Sequence[str],
) -> dict[str, Any]:
    return {
        **deepcopy(dict(base)),
        "trust_status": STATUS_WITHHELD,
        "trust_mode": TRUST_MODE_WITHHELD,
        "hydrology_context_included": False,
        "usable_for_downstream_environment_context": False,
        "usable_with_limitations": False,
        "trusted_context_segment_count": 0,
        "withheld_context_segment_count": len(source_segments),
        "segment_filter_applied": False,
        "representativeness_status": None,
        "representativeness_resolution_basis": [],
        "representativeness_limitations": list(limitations),
        "trust_basis": list(basis),
        "trusted_context": None,
    }



def _route_key(route: Mapping[str, Any], position: int) -> tuple[int, int | None]:
    route_index = _integer(route.get("route_index"))
    exercise_index = _integer(route.get("exercise_index"))
    return (route_index if route_index is not None else position, exercise_index)



def _overall_status(routes: Sequence[Mapping[str, Any]]) -> str:
    statuses = {_string(route.get("trust_status")) for route in routes}
    statuses.discard(None)
    if not statuses:
        return STATUS_WITHHELD
    if len(statuses) == 1:
        return next(iter(statuses))
    return STATUS_MIXED



def _schema_version(value: Mapping[str, Any] | None) -> str | None:
    if not isinstance(value, Mapping):
        return None
    return _string(value.get("schema_version")) or _string(value.get("evidence_version"))



def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]



def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None



def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None



def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [text for item in value if (text := _string(item)) is not None]



def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _string(value)
        if text is not None and text not in result:
            result.append(text)
    return result



def _append_unique(values: Sequence[str], value: str) -> list[str]:
    result = list(values)
    if value not in result:
        result.append(value)
    return result
