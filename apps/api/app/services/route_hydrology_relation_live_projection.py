from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from app.services.route_hydrology_relation_evidence import (
    build_route_hydrology_relation_evidence,
    build_route_hydrology_relation_evidence_summary,
)
from app.services.relation_aware_trusted_route_hydrology_context import (
    TRUST_MODE_RELATION,
    build_relation_aware_trusted_route_hydrology_context,
    build_relation_aware_trusted_route_hydrology_context_summary,
)


SCHEMA_VERSION = "0.1"


def build_route_hydrology_relation_live_projection(
    *,
    route_environment_context_input: Mapping[str, Any] | None,
    route_hydrology_source_resolution: Mapping[str, Any] | None,
    route_hydrology_context: Mapping[str, Any] | None,
    trusted_route_hydrology_context: Mapping[str, Any] | None,
    relation_catalog: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compose V23 catalog evaluation with V23.1 metric-aware trust.

    With no relation catalog this is a semantic no-op: the existing direct V17
    trusted hydrology context remains the effective downstream input.
    """
    if not isinstance(relation_catalog, Mapping):
        return {
            "schema_version": SCHEMA_VERSION,
            "enabled": False,
            "status": "DISABLED",
            "relation_catalog_provider": None,
            "route_hydrology_relation_evidence": None,
            "route_hydrology_relation_evidence_summary": None,
            "relation_aware_trusted_route_hydrology_context": None,
            "relation_aware_trusted_route_hydrology_context_summary": None,
            "effective_trusted_route_hydrology_context": (
                trusted_route_hydrology_context
            ),
            "relation_derived_hydrology_in_use": False,
            "persistence_requires_relation_lineage": False,
        }

    relation_evidence = build_route_hydrology_relation_evidence(
        route_environment_context_input,
        route_hydrology_source_resolution,
        relation_catalog,
    )
    relation_aware = build_relation_aware_trusted_route_hydrology_context(
        route_hydrology_context,
        trusted_route_hydrology_context,
        relation_evidence,
    )

    relation_derived = any(
        _text(route.get("trust_mode")) == TRUST_MODE_RELATION
        and route.get("hydrology_context_included") is True
        for route in _mapping_sequence(relation_aware.get("routes"))
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": True,
        "status": _text(relation_evidence.get("status")) or "UNAVAILABLE",
        "relation_catalog_provider": _text(relation_catalog.get("provider")),
        "route_hydrology_relation_evidence": relation_evidence,
        "route_hydrology_relation_evidence_summary": (
            build_route_hydrology_relation_evidence_summary(relation_evidence)
        ),
        "relation_aware_trusted_route_hydrology_context": relation_aware,
        "relation_aware_trusted_route_hydrology_context_summary": (
            build_relation_aware_trusted_route_hydrology_context_summary(
                relation_aware
            )
        ),
        "effective_trusted_route_hydrology_context": relation_aware,
        "relation_derived_hydrology_in_use": relation_derived,
        "persistence_requires_relation_lineage": relation_derived,
        "scope": {
            "direct_trust_precedence": True,
            "relation_catalog_is_measurement_source": False,
            "relation_can_create_measurements_without_source_context": False,
            "metric_specific_projection_required": True,
            "relation_derived_current_velocity_allowed": False,
            "raw_inputs_mutated": False,
        },
    }


def build_route_hydrology_relation_live_projection_summary(
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(projection))
    result.pop("route_hydrology_relation_evidence", None)
    result.pop("relation_aware_trusted_route_hydrology_context", None)
    result.pop("effective_trusted_route_hydrology_context", None)
    result["full_relation_evidence_included"] = False
    result["full_relation_aware_trusted_context_included"] = False
    result["effective_trusted_route_hydrology_context_included"] = False
    return result


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
