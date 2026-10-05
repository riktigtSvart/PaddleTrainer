from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

ENVIRONMENT_RIVER_INLAND = "RIVER_INLAND"
ENVIRONMENT_MARINE = "MARINE"
ENVIRONMENT_AMBIGUOUS = "AMBIGUOUS"
ENVIRONMENT_UNRESOLVED = "UNRESOLVED"

STATUS_DIRECT_RESOLVED = "DIRECT_RESOLVED"
STATUS_CONTINUITY_SUPPORTED = "CONTINUITY_SUPPORTED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_TRANSITION_CANDIDATE = "TRANSITION_CANDIDATE"
STATUS_UNRESOLVED = "UNRESOLVED"

TRUSTED_RIVER_STATUSES = {
    STATUS_DIRECT_RESOLVED,
    STATUS_CONTINUITY_SUPPORTED,
}
TRUSTED_MARINE_STATUSES = {
    STATUS_DIRECT_RESOLVED,
}


def build_route_water_environment_identity(
    route_waterbody_trajectory_resolution: Mapping[str, Any] | None,
    route_marine_region_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Aggregate trusted river/inland and marine route identity evidence.

    This layer does not resolve new source evidence. It preserves each domain's
    trusted result and exposes one downstream environment type per segment.
    When both domains are trusted-resolved for the same segment, neither wins:
    the segment is retained as cross-domain AMBIGUOUS with both identities.
    """
    river_routes = _route_lookup(route_waterbody_trajectory_resolution)
    marine_routes = _route_lookup(route_marine_region_context)
    route_keys = _ordered_union_route_keys(river_routes, marine_routes)

    route_results: list[dict[str, Any]] = []
    global_status_counts = _empty_status_counts()
    global_environment_counts = _empty_environment_counts()
    global_cross_domain_conflicts = 0

    for route_key in route_keys:
        river_route = river_routes.get(route_key)
        marine_route = marine_routes.get(route_key)
        river_segments = _segment_lookup(river_route)
        marine_segments = _segment_lookup(marine_route)
        order_indices = _ordered_union_segment_indices(
            river_segments,
            marine_segments,
        )

        segment_results: list[dict[str, Any]] = []
        status_counts = _empty_status_counts()
        environment_counts = _empty_environment_counts()
        cross_domain_conflicts = 0
        resolved_environment_types: set[str] = set()

        river_identities: dict[tuple[Any, ...], dict[str, Any]] = {}
        marine_identities: dict[tuple[Any, ...], dict[str, Any]] = {}

        for order_index in order_indices:
            river_segment = river_segments.get(order_index)
            marine_segment = marine_segments.get(order_index)

            river_status = _string(
                river_segment.get("resolution_status")
                if isinstance(river_segment, Mapping)
                else None
            ) or STATUS_UNRESOLVED
            marine_status = _string(
                marine_segment.get("resolution_status")
                if isinstance(marine_segment, Mapping)
                else None
            ) or STATUS_UNRESOLVED

            river_identity = _trusted_river_identity(
                river_segment,
                river_status,
            )
            marine_identity = _trusted_marine_identity(
                marine_segment,
                marine_status,
            )

            river_resolved = river_identity is not None
            marine_resolved = marine_identity is not None

            if river_resolved and marine_resolved:
                environment_type = ENVIRONMENT_AMBIGUOUS
                unified_status = STATUS_AMBIGUOUS
                cross_domain_conflict = True
                resolution_basis = [
                    "TRUSTED_RIVER_INLAND_IDENTITY_AVAILABLE",
                    "TRUSTED_MARINE_REGION_IDENTITY_AVAILABLE",
                    "CROSS_DOMAIN_CONFLICT_RETAINED_AS_AMBIGUOUS",
                ]
            elif river_resolved:
                environment_type = ENVIRONMENT_RIVER_INLAND
                unified_status = river_status
                cross_domain_conflict = False
                resolved_environment_types.add(ENVIRONMENT_RIVER_INLAND)
                resolution_basis = [
                    "TRUSTED_RIVER_INLAND_IDENTITY_AVAILABLE",
                    "MARINE_DOMAIN_NOT_TRUSTED_RESOLVED",
                ]
            elif marine_resolved:
                environment_type = ENVIRONMENT_MARINE
                unified_status = marine_status
                cross_domain_conflict = False
                resolved_environment_types.add(ENVIRONMENT_MARINE)
                resolution_basis = [
                    "TRUSTED_MARINE_REGION_IDENTITY_AVAILABLE",
                    "RIVER_INLAND_DOMAIN_NOT_TRUSTED_RESOLVED",
                ]
            else:
                cross_domain_conflict = False
                if (
                    STATUS_TRANSITION_CANDIDATE
                    in {river_status, marine_status}
                ):
                    environment_type = ENVIRONMENT_AMBIGUOUS
                    unified_status = STATUS_TRANSITION_CANDIDATE
                    resolution_basis = [
                        "NO_TRUSTED_DOMAIN_IDENTITY",
                        "SOURCE_DOMAIN_TRANSITION_CANDIDATE_PRESENT",
                    ]
                elif STATUS_AMBIGUOUS in {river_status, marine_status}:
                    environment_type = ENVIRONMENT_AMBIGUOUS
                    unified_status = STATUS_AMBIGUOUS
                    resolution_basis = [
                        "NO_TRUSTED_DOMAIN_IDENTITY",
                        "SOURCE_DOMAIN_AMBIGUITY_PRESENT",
                    ]
                else:
                    environment_type = ENVIRONMENT_UNRESOLVED
                    unified_status = STATUS_UNRESOLVED
                    resolution_basis = [
                        "NO_TRUSTED_DOMAIN_IDENTITY",
                    ]

            if cross_domain_conflict:
                cross_domain_conflicts += 1

            status_counts[unified_status] += 1
            environment_counts[environment_type] += 1

            if river_identity is not None:
                river_identities[_river_identity_key(river_identity)] = deepcopy(
                    river_identity
                )
            if marine_identity is not None:
                marine_identities[_marine_identity_key(marine_identity)] = deepcopy(
                    marine_identity
                )

            segment_results.append(
                {
                    **_segment_provenance(
                        river_segment,
                        marine_segment,
                        order_index,
                    ),
                    "environment_type": environment_type,
                    "resolution_status": unified_status,
                    "cross_domain_conflict": cross_domain_conflict,
                    "resolved_river_inland_identity": deepcopy(river_identity),
                    "resolved_marine_region_identity": deepcopy(marine_identity),
                    "river_inland_evidence": _river_evidence_summary(
                        river_segment,
                        river_status,
                    ),
                    "marine_evidence": _marine_evidence_summary(
                        marine_segment,
                        marine_status,
                    ),
                    "resolution_basis": resolution_basis,
                }
            )

        for status, count in status_counts.items():
            global_status_counts[status] += count
        for environment_type, count in environment_counts.items():
            global_environment_counts[environment_type] += count
        global_cross_domain_conflicts += cross_domain_conflicts

        route_results.append(
            {
                "route_index": route_key[0],
                "exercise_index": route_key[1],
                "available": bool(segment_results),
                "status": _overall_status(status_counts),
                "segment_count": len(segment_results),
                "environment_types": sorted(resolved_environment_types),
                "mixed_environment_route": len(resolved_environment_types) > 1,
                "river_inland_segment_count": environment_counts[
                    ENVIRONMENT_RIVER_INLAND
                ],
                "marine_segment_count": environment_counts[ENVIRONMENT_MARINE],
                "ambiguous_environment_segment_count": environment_counts[
                    ENVIRONMENT_AMBIGUOUS
                ],
                "unresolved_environment_segment_count": environment_counts[
                    ENVIRONMENT_UNRESOLVED
                ],
                "direct_resolved_segment_count": status_counts[
                    STATUS_DIRECT_RESOLVED
                ],
                "continuity_supported_segment_count": status_counts[
                    STATUS_CONTINUITY_SUPPORTED
                ],
                "ambiguous_segment_count": status_counts[STATUS_AMBIGUOUS],
                "transition_candidate_segment_count": status_counts[
                    STATUS_TRANSITION_CANDIDATE
                ],
                "unresolved_segment_count": status_counts[STATUS_UNRESOLVED],
                "cross_domain_conflict_segment_count": cross_domain_conflicts,
                "river_inland_identity_count": len(river_identities),
                "river_inland_identities": list(river_identities.values()),
                "marine_region_identity_count": len(marine_identities),
                "marine_region_identities": list(marine_identities.values()),
                "segments": segment_results,
            }
        )

    return {
        "provider": _provider(
            route_waterbody_trajectory_resolution,
            route_marine_region_context,
        ),
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _overall_status(global_status_counts),
        "route_count": len(route_results),
        "river_inland_segment_count": global_environment_counts[
            ENVIRONMENT_RIVER_INLAND
        ],
        "marine_segment_count": global_environment_counts[ENVIRONMENT_MARINE],
        "ambiguous_environment_segment_count": global_environment_counts[
            ENVIRONMENT_AMBIGUOUS
        ],
        "unresolved_environment_segment_count": global_environment_counts[
            ENVIRONMENT_UNRESOLVED
        ],
        "direct_resolved_segment_count": global_status_counts[
            STATUS_DIRECT_RESOLVED
        ],
        "continuity_supported_segment_count": global_status_counts[
            STATUS_CONTINUITY_SUPPORTED
        ],
        "ambiguous_segment_count": global_status_counts[STATUS_AMBIGUOUS],
        "transition_candidate_segment_count": global_status_counts[
            STATUS_TRANSITION_CANDIDATE
        ],
        "unresolved_segment_count": global_status_counts[STATUS_UNRESOLVED],
        "cross_domain_conflict_segment_count": global_cross_domain_conflicts,
        "input_provenance": {
            "route_waterbody_trajectory_resolution_schema_version": (
                route_waterbody_trajectory_resolution.get("schema_version")
                if isinstance(route_waterbody_trajectory_resolution, Mapping)
                else None
            ),
            "route_marine_region_context_schema_version": (
                route_marine_region_context.get("schema_version")
                if isinstance(route_marine_region_context, Mapping)
                else None
            ),
            "river_inland_input_available": isinstance(
                route_waterbody_trajectory_resolution,
                Mapping,
            ),
            "marine_input_available": isinstance(
                route_marine_region_context,
                Mapping,
            ),
        },
        "scope": {
            "domain": "ROUTE_WATER_ENVIRONMENT_IDENTITY",
            "aggregates_existing_trusted_domain_resolutions": True,
            "resolves_new_provider_evidence": False,
            "preserves_river_inland_identity_semantics": True,
            "preserves_marine_region_identity_semantics": True,
            "claims_hydrographic_sea_identity": False,
            "prefers_river_over_marine_on_conflict": False,
            "prefers_marine_over_river_on_conflict": False,
            "retains_cross_domain_conflict_as_ambiguous": True,
            "infers_navigability": False,
            "estimates_local_current_velocity": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_route_water_environment_identity_summary(
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    raw_routes = identity.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )
    return {
        **{
            key: value
            for key, value in identity.items()
            if key != "routes"
        },
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
            for route in routes
            if isinstance(route, Mapping)
        ],
    }


def _provider(
    river: Mapping[str, Any] | None,
    marine: Mapping[str, Any] | None,
) -> str:
    for value in (river, marine):
        if isinstance(value, Mapping):
            provider = _string(value.get("provider"))
            if provider is not None:
                return provider
    return "POLAR"


def _route_lookup(
    context: Mapping[str, Any] | None,
) -> dict[tuple[int, int | None], Mapping[str, Any]]:
    if not isinstance(context, Mapping):
        return {}
    raw_routes = context.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )
    result: dict[tuple[int, int | None], Mapping[str, Any]] = {}
    for position, route in enumerate(routes):
        if not isinstance(route, Mapping):
            continue
        route_index = _integer(route.get("route_index"))
        if route_index is None:
            route_index = position
        result[(route_index, _integer(route.get("exercise_index")))] = route
    return result


def _ordered_union_route_keys(
    river_routes: Mapping[tuple[int, int | None], Mapping[str, Any]],
    marine_routes: Mapping[tuple[int, int | None], Mapping[str, Any]],
) -> list[tuple[int, int | None]]:
    keys = list(river_routes)
    keys.extend(key for key in marine_routes if key not in river_routes)
    return keys


def _segment_lookup(
    route: Mapping[str, Any] | None,
) -> dict[int, Mapping[str, Any]]:
    if not isinstance(route, Mapping):
        return {}
    raw_segments = route.get("segments")
    segments = (
        raw_segments
        if isinstance(raw_segments, Sequence)
        and not isinstance(raw_segments, (str, bytes))
        else []
    )
    result: dict[int, Mapping[str, Any]] = {}
    for position, segment in enumerate(segments):
        if not isinstance(segment, Mapping):
            continue
        order_index = _integer(segment.get("order_index"))
        if order_index is None:
            order_index = position
        result[order_index] = segment
    return result


def _ordered_union_segment_indices(
    river_segments: Mapping[int, Mapping[str, Any]],
    marine_segments: Mapping[int, Mapping[str, Any]],
) -> list[int]:
    return sorted(set(river_segments).union(marine_segments))


def _trusted_river_identity(
    segment: Mapping[str, Any] | None,
    status: str,
) -> dict[str, Any] | None:
    if status not in TRUSTED_RIVER_STATUSES or not isinstance(segment, Mapping):
        return None
    identity = segment.get("resolved_waterbody_identity")
    return deepcopy(identity) if isinstance(identity, Mapping) else None


def _trusted_marine_identity(
    segment: Mapping[str, Any] | None,
    status: str,
) -> dict[str, Any] | None:
    if status not in TRUSTED_MARINE_STATUSES or not isinstance(segment, Mapping):
        return None
    identity = segment.get("resolved_marine_region_identity")
    return deepcopy(identity) if isinstance(identity, Mapping) else None


def _river_evidence_summary(
    segment: Mapping[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    if not isinstance(segment, Mapping):
        return {
            "available": False,
            "resolution_status": STATUS_UNRESOLVED,
            "trusted_waterbody_identity": None,
            "source_direct_waterbody_identity": None,
            "direct_resolution_withheld_by_surface": False,
            "resolution_basis": [],
        }
    return {
        "available": True,
        "resolution_status": status,
        "trusted_waterbody_identity": deepcopy(
            segment.get("resolved_waterbody_identity")
        ),
        "source_direct_waterbody_identity": deepcopy(
            segment.get("direct_resolved_waterbody_identity")
        ),
        "direct_resolution_withheld_by_surface": bool(
            segment.get("direct_resolution_withheld_by_surface")
        ),
        "resolution_basis": list(segment.get("resolution_basis") or []),
    }


def _marine_evidence_summary(
    segment: Mapping[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    if not isinstance(segment, Mapping):
        return {
            "available": False,
            "resolution_status": STATUS_UNRESOLVED,
            "marine_region_identity": None,
        }
    return {
        "available": True,
        "resolution_status": status,
        "marine_region_identity": deepcopy(
            segment.get("resolved_marine_region_identity")
        ),
    }


def _segment_provenance(
    river_segment: Mapping[str, Any] | None,
    marine_segment: Mapping[str, Any] | None,
    order_index: int,
) -> dict[str, Any]:
    source = river_segment if isinstance(river_segment, Mapping) else marine_segment
    if not isinstance(source, Mapping):
        return {"order_index": order_index}
    return {
        "order_index": order_index,
        "segment_index": _integer(source.get("segment_index")),
        "source_segment_index": _integer(source.get("source_segment_index")),
        "start_exercise_elapsed_ms": _integer(
            source.get("start_exercise_elapsed_ms")
        ),
        "end_exercise_elapsed_ms": _integer(source.get("end_exercise_elapsed_ms")),
    }


def _river_identity_key(identity: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        identity.get("source_provider"),
        identity.get("source_product"),
        identity.get("waterbody_id"),
    )


def _marine_identity_key(identity: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        identity.get("source_provider"),
        identity.get("source_dataset"),
        identity.get("source_layer"),
        identity.get("source_feature_id"),
        identity.get("marine_subregion_id"),
        identity.get("marine_region_id"),
    )


def _empty_status_counts() -> dict[str, int]:
    return {
        STATUS_DIRECT_RESOLVED: 0,
        STATUS_CONTINUITY_SUPPORTED: 0,
        STATUS_AMBIGUOUS: 0,
        STATUS_TRANSITION_CANDIDATE: 0,
        STATUS_UNRESOLVED: 0,
    }


def _empty_environment_counts() -> dict[str, int]:
    return {
        ENVIRONMENT_RIVER_INLAND: 0,
        ENVIRONMENT_MARINE: 0,
        ENVIRONMENT_AMBIGUOUS: 0,
        ENVIRONMENT_UNRESOLVED: 0,
    }


def _overall_status(counts: Mapping[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return STATUS_UNRESOLVED
    if counts.get(STATUS_TRANSITION_CANDIDATE, 0):
        return STATUS_TRANSITION_CANDIDATE
    if counts.get(STATUS_AMBIGUOUS, 0):
        return STATUS_AMBIGUOUS
    if counts.get(STATUS_UNRESOLVED, 0):
        return STATUS_UNRESOLVED
    if counts.get(STATUS_CONTINUITY_SUPPORTED, 0):
        return STATUS_CONTINUITY_SUPPORTED
    return STATUS_DIRECT_RESOLVED


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
