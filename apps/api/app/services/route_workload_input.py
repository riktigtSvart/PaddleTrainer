from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "0.1"

SOURCE_BRANCH = "TRUSTED_ROUTE_VIEW"

REASON_TRUSTED_MOTION_SEGMENTS_UNAVAILABLE = (
    "TRUSTED_MOTION_SEGMENTS_UNAVAILABLE"
)


def _integer(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
    ):
        return int(value)

    return None


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(
        value,
        (int, float),
    ):
        return None

    numeric = float(value)

    if not math.isfinite(
        numeric
    ):
        return None

    return numeric


def _route_lookup(
    evidence: dict[str, Any] | None,
) -> dict[
    tuple[int, int | None],
    dict[str, Any],
]:
    result = {}

    if not isinstance(
        evidence,
        dict,
    ):
        return result

    for route_position, route in enumerate(
        evidence.get("routes") or []
    ):
        if not isinstance(
            route,
            dict,
        ):
            continue

        route_index = _integer(
            route.get(
                "route_index"
            )
        )

        if route_index is None:
            route_index = route_position

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

        result[
            (
                route_index,
                exercise_index,
            )
        ] = route

    return result


def _match_route(
    lookup: dict[
        tuple[int, int | None],
        dict[str, Any],
    ],
    *,
    route_index: int,
    exercise_index: int | None,
) -> dict[str, Any] | None:
    exact = lookup.get(
        (
            route_index,
            exercise_index,
        )
    )

    if exact is not None:
        return exact

    matches = [
        route
        for (
            (
                _candidate_route_index,
                candidate_exercise_index,
            ),
            route,
        )
        in lookup.items()
        if candidate_exercise_index
        == exercise_index
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def _exercise_lookup(
    evidence: dict[str, Any] | None,
) -> dict[int | None, dict[str, Any]]:
    result = {}

    if not isinstance(
        evidence,
        dict,
    ):
        return result

    for exercise in (
        evidence.get(
            "exercises"
        )
        or []
    ):
        if not isinstance(
            exercise,
            dict,
        ):
            continue

        exercise_index = _integer(
            exercise.get(
                "exercise_index"
            )
        )

        result[
            exercise_index
        ] = exercise

    return result


def _motion_segments(
    route: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(
        route,
        dict,
    ):
        return []

    return [
        deepcopy(segment)
        for segment in (
            route.get(
                "segments"
            )
            or []
        )
        if isinstance(
            segment,
            dict,
        )
    ]


def _provider_distance(
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(
        evidence,
        dict,
    ):
        return {
            "value_m": None,
            "scope": None,
            "source": None,
        }

    return {
        "value_m": _finite_number(
            evidence.get(
                "value_m"
            )
        ),
        "scope": evidence.get(
            "scope"
        ),
        "source": evidence.get(
            "source"
        ),
    }


def build_route_workload_input(
    trusted_normalized_routes: dict[str, Any],
    trusted_motion: dict[str, Any],
    trusted_motion_summary: dict[str, Any],
    raw_motion_summary: dict[str, Any],
    trust_boundary_evidence: dict[str, Any],
    artifact_policy: dict[str, Any],
    trust_mask_summary: dict[str, Any],
    *,
    speed_gps_consistency: dict[str, Any] | None = None,
    provider_distance_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the official route-derived downstream workload input.

    This service does not detect artifacts, alter policy, smooth motion,
    reconstruct coordinates, or mutate provider/raw data. It packages
    already-trusted motion segments plus quality/provenance metadata for
    downstream workload, physiology, and environmental-context models.
    """
    normalized_lookup = _route_lookup(
        trusted_normalized_routes
    )
    trusted_motion_lookup = _route_lookup(
        trusted_motion
    )
    trusted_summary_lookup = _route_lookup(
        trusted_motion_summary
    )
    raw_summary_lookup = _route_lookup(
        raw_motion_summary
    )
    trust_lookup = _route_lookup(
        trust_boundary_evidence
    )
    policy_lookup = _route_lookup(
        artifact_policy
    )
    mask_lookup = _route_lookup(
        trust_mask_summary
    )
    speed_lookup = _exercise_lookup(
        speed_gps_consistency
    )

    provider_distance = _provider_distance(
        provider_distance_evidence
    )

    route_keys = []

    for route_position, route in enumerate(
        trusted_normalized_routes.get(
            "routes"
        )
        or []
    ):
        if not isinstance(
            route,
            dict,
        ):
            continue

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

        route_keys.append(
            (
                route_position,
                exercise_index,
            )
        )

    route_results = []

    for (
        route_index,
        exercise_index,
    ) in route_keys:
        normalized_route = _match_route(
            normalized_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        trusted_motion_route = _match_route(
            trusted_motion_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        trusted_summary_route = _match_route(
            trusted_summary_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        raw_summary_route = _match_route(
            raw_summary_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        trust_route = _match_route(
            trust_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        policy_route = _match_route(
            policy_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )
        mask_route = _match_route(
            mask_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )

        speed_exercise = speed_lookup.get(
            exercise_index
        )

        segments = _motion_segments(
            trusted_motion_route
        )

        available = bool(
            segments
        )

        reason = (
            None
            if available
            else REASON_TRUSTED_MOTION_SEGMENTS_UNAVAILABLE
        )

        trust_mask = (
            mask_route.get(
                "trust_mask"
            )
            if isinstance(
                mask_route,
                dict,
            )
            and isinstance(
                mask_route.get(
                    "trust_mask"
                ),
                dict,
            )
            else {}
        )

        raw_segment_count = _integer(
            (
                raw_summary_route
                or {}
            ).get(
                "motion_segment_count"
            )
        )

        trusted_segment_count = _integer(
            (
                trusted_summary_route
                or {}
            ).get(
                "motion_segment_count"
            )
        )

        excluded_segment_count = (
            raw_segment_count
            - trusted_segment_count
            if (
                raw_segment_count
                is not None
                and trusted_segment_count
                is not None
                and raw_segment_count
                >= trusted_segment_count
            )
            else None
        )

        usable_start_ms = _integer(
            (
                trusted_summary_route
                or {}
            ).get(
                "first_motion_start_elapsed_ms"
            )
        )

        usable_end_ms = _integer(
            (
                trusted_summary_route
                or {}
            ).get(
                "last_motion_end_elapsed_ms"
            )
        )

        usable_span_ms = _integer(
            (
                trusted_summary_route
                or {}
            ).get(
                "motion_span_ms"
            )
        )

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": available,
                "reason": reason,
                "source_branch": SOURCE_BRANCH,
                "usable_interval": {
                    "start_exercise_elapsed_ms": (
                        usable_start_ms
                    ),
                    "end_exercise_elapsed_ms": (
                        usable_end_ms
                    ),
                    "span_ms": usable_span_ms,
                },
                "distance_evidence": {
                    "provider_reported": (
                        deepcopy(
                            provider_distance
                        )
                    ),
                    "raw_gps_surface_distance_m": (
                        _finite_number(
                            (
                                raw_summary_route
                                or {}
                            ).get(
                                "total_surface_distance_m"
                            )
                        )
                    ),
                    "trusted_gps_surface_distance_m": (
                        _finite_number(
                            (
                                trusted_summary_route
                                or {}
                            ).get(
                                "total_surface_distance_m"
                            )
                        )
                    ),
                },
                "counts": {
                    "original_route_point_count": (
                        _integer(
                            trust_mask.get(
                                "original_point_count"
                            )
                        )
                    ),
                    "usable_route_point_count": (
                        _integer(
                            trust_mask.get(
                                "usable_point_count"
                            )
                        )
                    ),
                    "excluded_route_point_count": (
                        _integer(
                            trust_mask.get(
                                "excluded_point_count"
                            )
                        )
                    ),
                    "raw_motion_segment_count": (
                        raw_segment_count
                    ),
                    "trusted_motion_segment_count": (
                        trusted_segment_count
                    ),
                    "excluded_motion_segment_count": (
                        excluded_segment_count
                    ),
                },
                "ground_speed_evidence": {
                    "metric": (
                        "GPS_GROUND_SPEED"
                    ),
                    "unit": "m/s",
                    "distance_over_time_mps": (
                        _finite_number(
                            (
                                trusted_summary_route
                                or {}
                            ).get(
                                "distance_over_time_ground_speed_mps"
                            )
                        )
                    ),
                    "minimum_segment_mps": (
                        _finite_number(
                            (
                                trusted_summary_route
                                or {}
                            ).get(
                                "minimum_segment_ground_speed_mps"
                            )
                        )
                    ),
                    "median_segment_mps": (
                        _finite_number(
                            (
                                trusted_summary_route
                                or {}
                            ).get(
                                "median_segment_ground_speed_mps"
                            )
                        )
                    ),
                    "maximum_segment_mps": (
                        _finite_number(
                            (
                                trusted_summary_route
                                or {}
                            ).get(
                                "maximum_segment_ground_speed_mps"
                            )
                        )
                    ),
                },
                "cross_source_speed_consistency": (
                    {
                        key: deepcopy(value)
                        for key, value
                        in speed_exercise.items()
                        if key != "comparisons"
                    }
                    if isinstance(
                        speed_exercise,
                        dict,
                    )
                    else None
                ),
                "quality_provenance": {
                    "artifact_policy": {
                        "policy_version": (
                            artifact_policy.get(
                                "policy_version"
                            )
                        ),
                        "profile": (
                            artifact_policy.get(
                                "profile"
                            )
                        ),
                        "action": (
                            (
                                policy_route
                                or {}
                            ).get(
                                "action"
                            )
                        ),
                        "reason": (
                            (
                                policy_route
                                or {}
                            ).get(
                                "reason"
                            )
                        ),
                        "scope": deepcopy(
                            (
                                policy_route
                                or {}
                            ).get(
                                "scope"
                            )
                        ),
                    },
                    "trust_boundary": {
                        "evidence_version": (
                            trust_boundary_evidence.get(
                                "evidence_version"
                            )
                        ),
                        "status": (
                            (
                                trust_route
                                or {}
                            ).get(
                                "status"
                            )
                        ),
                        "geometry_supported_usable_from_exercise_elapsed_ms": (
                            (
                                trust_route
                                or {}
                            ).get(
                                "geometry_supported_usable_from_exercise_elapsed_ms"
                            )
                        ),
                        "time_to_validated_forward_anchor_ms": (
                            (
                                trust_route
                                or {}
                            ).get(
                                "time_to_validated_forward_anchor_ms"
                            )
                        ),
                        "segments_to_validated_forward_anchor": (
                            (
                                trust_route
                                or {}
                            ).get(
                                "segments_to_validated_forward_anchor"
                            )
                        ),
                    },
                    "trust_mask": {
                        "view_version": (
                            trust_mask.get(
                                "view_version"
                            )
                        ),
                        "mode": (
                            trust_mask.get(
                                "mode"
                            )
                        ),
                        "reason": (
                            trust_mask.get(
                                "reason"
                            )
                        ),
                        "applied_usable_from_exercise_elapsed_ms": (
                            trust_mask.get(
                                "applied_usable_from_exercise_elapsed_ms"
                            )
                        ),
                        "raw_data_mutated": (
                            trust_mask.get(
                                "raw_data_mutated"
                            )
                        ),
                    },
                },
                "route_context": {
                    "route_start_time": (
                        (
                            normalized_route
                            or {}
                        ).get(
                            "route_start_time"
                        )
                    ),
                    "exercise_start_time": (
                        (
                            normalized_route
                            or {}
                        ).get(
                            "exercise_start_time"
                        )
                    ),
                    "route_start_offset_ms": (
                        (
                            normalized_route
                            or {}
                        ).get(
                            "route_start_offset_ms"
                        )
                    ),
                },
                "motion_segments": segments,
            }
        )

    return {
        "provider": (
            trusted_motion.get(
                "provider"
            )
            or trusted_normalized_routes.get(
                "provider"
            )
        ),
        "schema_version": SCHEMA_VERSION,
        "available": any(
            route.get(
                "available"
            )
            is True
            for route in route_results
        ),
        "route_count": len(
            route_results
        ),
        "source_branch": (
            SOURCE_BRANCH
        ),
        "scope": {
            "purpose": (
                "ROUTE_DERIVED_EXTERNAL_WORKLOAD_INPUT"
            ),
            "raw_data_mutated": False,
            "performs_artifact_detection": False,
            "performs_reconstruction": False,
            "performs_smoothing": False,
        },
        "routes": route_results,
    }


def build_route_workload_input_summary(
    workload_input: dict[str, Any],
) -> dict[str, Any]:
    """Strip full segment payload for inspection/API summary responses."""
    return {
        **workload_input,
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key
                    != "motion_segments"
                },
                "motion_segments_included": (
                    False
                ),
                "motion_segment_payload_count": (
                    len(
                        route.get(
                            "motion_segments"
                        )
                        or []
                    )
                ),
            }
            for route in (
                workload_input.get(
                    "routes"
                )
                or []
            )
            if isinstance(
                route,
                dict,
            )
        ],
    }
