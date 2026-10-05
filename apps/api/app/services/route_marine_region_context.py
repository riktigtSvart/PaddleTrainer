from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "0.1"

STATUS_DIRECT_RESOLVED = "DIRECT_RESOLVED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_TRANSITION_CANDIDATE = "TRANSITION_CANDIDATE"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"


def build_route_marine_region_context(
    route_marine_surface_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve reported MSFD region/subregion identity from marine polygons.

    Resolution is direct polygon-containment evidence only. This does not claim
    a hydrographic sea-area identity, perform trajectory smoothing, infer
    coastal access, or merge with river/inland waterbody identity.
    """
    catalog = _feature_catalog(route_marine_surface_evidence)
    catalog_by_id = {
        feature["source_feature_id"]: feature
        for feature in catalog
        if feature.get("source_feature_id") is not None
    }

    route_results: list[dict[str, Any]] = []
    total_direct = 0
    total_ambiguous = 0
    total_transition = 0
    total_unresolved = 0

    raw_routes = route_marine_surface_evidence.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )

    for route_position, raw_route in enumerate(routes):
        if not isinstance(raw_route, Mapping):
            continue

        route_index = _integer(raw_route.get("route_index"))
        if route_index is None:
            route_index = route_position
        exercise_index = _integer(raw_route.get("exercise_index"))

        segment_results: list[dict[str, Any]] = []
        counts = {
            STATUS_DIRECT_RESOLVED: 0,
            STATUS_AMBIGUOUS: 0,
            STATUS_TRANSITION_CANDIDATE: 0,
            STATUS_UNRESOLVED: 0,
        }
        seen_identity_keys: dict[tuple[str | None, str | None], dict[str, Any]] = {}

        raw_segments = raw_route.get("segments")
        segments = (
            raw_segments
            if isinstance(raw_segments, Sequence)
            and not isinstance(raw_segments, (str, bytes))
            else []
        )

        for order_position, raw_segment in enumerate(segments):
            if not isinstance(raw_segment, Mapping):
                continue

            order_index = _integer(raw_segment.get("order_index"))
            if order_index is None:
                order_index = order_position

            start_ids = _inside_feature_ids(
                raw_segment.get("start_surface_evidence")
            )
            end_ids = _inside_feature_ids(
                raw_segment.get("end_surface_evidence")
            )
            common_ids = tuple(sorted(set(start_ids).intersection(end_ids)))

            common_candidates = _dedupe_identities(
                catalog_by_id.get(feature_id)
                for feature_id in common_ids
            )
            start_candidates = _dedupe_identities(
                catalog_by_id.get(feature_id)
                for feature_id in start_ids
            )
            end_candidates = _dedupe_identities(
                catalog_by_id.get(feature_id)
                for feature_id in end_ids
            )

            resolved_identity: dict[str, Any] | None = None
            if len(common_candidates) == 1:
                status = STATUS_DIRECT_RESOLVED
                resolved_identity = common_candidates[0]
                key = _identity_key(resolved_identity)
                seen_identity_keys[key] = resolved_identity
            elif len(common_candidates) > 1:
                status = STATUS_AMBIGUOUS
            elif start_candidates and end_candidates:
                status = STATUS_TRANSITION_CANDIDATE
            else:
                status = STATUS_UNRESOLVED

            counts[status] += 1
            segment_results.append(
                {
                    "order_index": order_index,
                    "segment_index": _integer(raw_segment.get("segment_index")),
                    "source_segment_index": _integer(
                        raw_segment.get("source_segment_index")
                    ),
                    "start_exercise_elapsed_ms": _integer(
                        raw_segment.get("start_exercise_elapsed_ms")
                    ),
                    "end_exercise_elapsed_ms": _integer(
                        raw_segment.get("end_exercise_elapsed_ms")
                    ),
                    "resolution_status": status,
                    "resolved_marine_region_identity": resolved_identity,
                    "candidate_count": len(common_candidates),
                    "candidates": common_candidates,
                    "start_candidates": start_candidates,
                    "end_candidates": end_candidates,
                }
            )

        route_status = _overall_status(counts)
        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "status": route_status,
                "segment_count": len(segment_results),
                "direct_resolved_segment_count": counts[STATUS_DIRECT_RESOLVED],
                "ambiguous_segment_count": counts[STATUS_AMBIGUOUS],
                "transition_candidate_segment_count": counts[
                    STATUS_TRANSITION_CANDIDATE
                ],
                "unresolved_segment_count": counts[STATUS_UNRESOLVED],
                "marine_region_identity_count": len(seen_identity_keys),
                "marine_region_identities": list(seen_identity_keys.values()),
                "segments": segment_results,
            }
        )

        total_direct += counts[STATUS_DIRECT_RESOLVED]
        total_ambiguous += counts[STATUS_AMBIGUOUS]
        total_transition += counts[STATUS_TRANSITION_CANDIDATE]
        total_unresolved += counts[STATUS_UNRESOLVED]

    totals = {
        STATUS_DIRECT_RESOLVED: total_direct,
        STATUS_AMBIGUOUS: total_ambiguous,
        STATUS_TRANSITION_CANDIDATE: total_transition,
        STATUS_UNRESOLVED: total_unresolved,
    }

    return {
        "provider": route_marine_surface_evidence.get("provider"),
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _overall_status(totals),
        "route_count": len(route_results),
        "direct_resolved_segment_count": total_direct,
        "ambiguous_segment_count": total_ambiguous,
        "transition_candidate_segment_count": total_transition,
        "unresolved_segment_count": total_unresolved,
        "input_provenance": {
            "route_marine_surface_evidence_schema_version": (
                route_marine_surface_evidence.get("schema_version")
            ),
            "source_query": route_marine_surface_evidence.get("source_query"),
        },
        "scope": {
            "domain": "ROUTE_MARINE_REGION_CONTEXT",
            "identity_type": "EEA_MSFD_REGION_SUBREGION",
            "uses_direct_polygon_containment": True,
            "uses_trajectory_continuity": False,
            "claims_hydrographic_sea_identity": False,
            "merges_with_river_inland_identity": False,
            "infers_navigability": False,
            "infers_coastal_access": False,
            "raw_data_mutated": False,
        },
        "marine_region_catalog": catalog,
        "routes": route_results,
    }


def build_route_marine_region_context_summary(
    context: Mapping[str, Any],
) -> dict[str, Any]:
    catalog = context.get("marine_region_catalog")
    catalog_count = (
        len(catalog)
        if isinstance(catalog, Sequence)
        and not isinstance(catalog, (str, bytes))
        else 0
    )
    routes = context.get("routes")
    raw_routes = (
        routes
        if isinstance(routes, Sequence)
        and not isinstance(routes, (str, bytes))
        else []
    )
    return {
        **{
            key: value
            for key, value in context.items()
            if key not in {"routes", "marine_region_catalog"}
        },
        "marine_region_catalog_included": False,
        "marine_region_catalog_count": catalog_count,
        "routes": [
            {
                **{
                    key: value
                    for key, value in route.items()
                    if key != "segments"
                },
                "segments_included": False,
                "segment_payload_count": len(route.get("segments") or []),
            }
            for route in raw_routes
            if isinstance(route, Mapping)
        ],
    }


def _feature_catalog(
    evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw_catalog = evidence.get("source_feature_catalog")
    if not isinstance(raw_catalog, Sequence) or isinstance(
        raw_catalog, (str, bytes)
    ):
        return []

    catalog: list[dict[str, Any]] = []
    for raw_feature in raw_catalog:
        if not isinstance(raw_feature, Mapping):
            continue
        source_feature_id = _string(raw_feature.get("source_feature_id"))
        attributes = raw_feature.get("source_attributes")
        if source_feature_id is None or not isinstance(attributes, Mapping):
            continue
        catalog.append(
            {
                "source_provider": _string(raw_feature.get("source_provider")),
                "source_dataset": _string(raw_feature.get("source_dataset")),
                "source_layer": _string(raw_feature.get("source_layer")),
                "source_feature_id": source_feature_id,
                "marine_subregion_id": _string(attributes.get("subregion")),
                "marine_subregion_name": _string(
                    attributes.get("subregionName")
                ),
                "marine_region_id": _string(attributes.get("region")),
                "marine_region_name": _string(attributes.get("regionName")),
                "zone_type": _string(attributes.get("zoneType")),
                "spatial_zone_type": _string(attributes.get("spZoneType")),
                "environment_domain": _string(attributes.get("envDomain")),
            }
        )
    return catalog


def _inside_feature_ids(point: object) -> tuple[str, ...]:
    if not isinstance(point, Mapping):
        return ()
    if point.get("containment") != "INSIDE":
        return ()
    raw_ids = point.get("containing_source_feature_ids")
    if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
        return ()
    return tuple(
        value
        for value in (_string(raw_id) for raw_id in raw_ids)
        if value is not None
    )


def _dedupe_identities(
    features: Any,
) -> list[dict[str, Any]]:
    found: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        feature_dict = dict(feature)
        key = _identity_key(feature_dict)
        found.setdefault(key, feature_dict)
    return list(found.values())


def _identity_key(
    identity: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    subregion = _string(identity.get("marine_subregion_id"))
    region = _string(identity.get("marine_region_id"))
    return (subregion, region)


def _overall_status(counts: Mapping[str, int]) -> str:
    direct = counts.get(STATUS_DIRECT_RESOLVED, 0)
    ambiguous = counts.get(STATUS_AMBIGUOUS, 0)
    transition = counts.get(STATUS_TRANSITION_CANDIDATE, 0)
    unresolved = counts.get(STATUS_UNRESOLVED, 0)
    total = direct + ambiguous + transition + unresolved
    if total == 0:
        return STATUS_UNRESOLVED
    if direct == total:
        return STATUS_DIRECT_RESOLVED
    if transition > 0:
        return STATUS_TRANSITION_CANDIDATE
    if ambiguous > 0:
        return STATUS_AMBIGUOUS
    if direct > 0 and unresolved > 0:
        return STATUS_PARTIALLY_RESOLVED
    return STATUS_UNRESOLVED


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
