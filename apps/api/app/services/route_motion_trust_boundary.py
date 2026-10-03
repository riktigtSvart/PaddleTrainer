from __future__ import annotations

import math
from typing import Any


EVIDENCE_VERSION = "0.1"

STATUS_BOUNDARY_AVAILABLE = (
    "VALIDATED_FORWARD_ANCHOR_AVAILABLE"
)
STATUS_BOUNDARY_UNAVAILABLE = (
    "VALIDATED_FORWARD_ANCHOR_UNAVAILABLE"
)
STATUS_STARTUP_EVIDENCE_UNAVAILABLE = (
    "STARTUP_EVIDENCE_UNAVAILABLE"
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


def _route_lookup(
    evidence: dict[str, Any],
) -> dict[
    tuple[int, int | None],
    dict[str, Any],
]:
    result = {}

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
            (_candidate_route_index, candidate_exercise_index),
            route,
        )
        in lookup.items()
        if candidate_exercise_index
        == exercise_index
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def build_route_motion_trust_boundary_evidence(
    startup_evidence: dict[str, Any],
    forward_anchor_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Describe a geometry-supported usable-from boundary.

    The prefix before the validated forward anchor is UNVALIDATED, not
    automatically erroneous. This service does not mutate route data.
    """
    forward_lookup = _route_lookup(
        forward_anchor_evidence
    )

    route_results = []

    for route_position, startup_route in enumerate(
        startup_evidence.get(
            "routes"
        )
        or []
    ):
        if not isinstance(
            startup_route,
            dict,
        ):
            continue

        route_index = _integer(
            startup_route.get(
                "route_index"
            )
        )
        if route_index is None:
            route_index = route_position

        exercise_index = _integer(
            startup_route.get(
                "exercise_index"
            )
        )

        first_waypoint_elapsed_ms = _integer(
            startup_route.get(
                "first_route_waypoint_exercise_elapsed_ms"
            )
        )

        expected_segment_indices = [
            value
            for raw_value
            in (
                startup_route.get(
                    "expected_segment_indices"
                )
                or []
            )
            if (
                value := _integer(
                    raw_value
                )
            )
            is not None
        ]

        forward_route = _match_route(
            forward_lookup,
            route_index=route_index,
            exercise_index=exercise_index,
        )

        startup_available = (
            startup_route.get(
                "available"
            )
            is True
        )

        if not startup_available:
            route_results.append(
                {
                    "route_index": route_index,
                    "exercise_index": exercise_index,
                    "available": False,
                    "status": (
                        STATUS_STARTUP_EVIDENCE_UNAVAILABLE
                    ),
                    "first_route_waypoint_exercise_elapsed_ms": (
                        first_waypoint_elapsed_ms
                    ),
                    "validated_forward_anchor_available": None,
                    "validated_forward_anchor_segment_index": None,
                    "validated_forward_anchor_waypoint_index": None,
                    "validated_forward_anchor_exercise_elapsed_ms": None,
                    "segments_to_validated_forward_anchor": None,
                    "time_to_validated_forward_anchor_ms": None,
                    "unvalidated_prefix": None,
                    "geometry_supported_usable_from_exercise_elapsed_ms": None,
                    "geometry_supported_usable_from_segment_index": None,
                    "geometry_supported_usable_from_waypoint_index": None,
                    "basis": {
                        "forward_anchor_criteria_version": None,
                        "description": (
                            "No trust boundary is emitted when "
                            "startup evidence is unavailable."
                        ),
                    },
                }
            )
            continue

        validated_forward_anchor_available = (
            isinstance(
                forward_route,
                dict,
            )
            and forward_route.get(
                "validated_forward_anchor_available"
            )
            is True
        )

        anchor = (
            forward_route.get(
                "anchor"
            )
            if (
                validated_forward_anchor_available
                and isinstance(
                    forward_route,
                    dict,
                )
            )
            else None
        )

        if not isinstance(
            anchor,
            dict,
        ):
            anchor = {}

        anchor_segment_index = _integer(
            anchor.get(
                "segment_index"
            )
        )
        anchor_waypoint_index = _integer(
            anchor.get(
                "waypoint_index"
            )
        )
        anchor_elapsed_ms = _integer(
            anchor.get(
                "exercise_elapsed_ms"
            )
        )

        boundary_available = (
            validated_forward_anchor_available
            and first_waypoint_elapsed_ms is not None
            and anchor_elapsed_ms is not None
            and anchor_elapsed_ms
            >= first_waypoint_elapsed_ms
        )

        time_to_anchor_ms = (
            anchor_elapsed_ms
            - first_waypoint_elapsed_ms
            if boundary_available
            else None
        )

        first_expected_segment_index = (
            min(
                expected_segment_indices
            )
            if expected_segment_indices
            else 0
        )

        segments_to_anchor = (
            anchor_segment_index
            - first_expected_segment_index
            if (
                boundary_available
                and anchor_segment_index
                is not None
            )
            else None
        )

        unvalidated_prefix = (
            {
                "start_exercise_elapsed_ms": (
                    first_waypoint_elapsed_ms
                ),
                "end_exercise_elapsed_ms": (
                    anchor_elapsed_ms
                ),
                "end_semantics": "EXCLUSIVE",
                "duration_ms": (
                    time_to_anchor_ms
                ),
                "classification": (
                    "UNVALIDATED_PREFIX"
                ),
                "does_not_assert_every_point_is_erroneous": (
                    True
                ),
            }
            if boundary_available
            else None
        )

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": (
                    boundary_available
                ),
                "status": (
                    STATUS_BOUNDARY_AVAILABLE
                    if boundary_available
                    else STATUS_BOUNDARY_UNAVAILABLE
                ),
                "first_route_waypoint_exercise_elapsed_ms": (
                    first_waypoint_elapsed_ms
                ),
                "validated_forward_anchor_available": (
                    validated_forward_anchor_available
                ),
                "validated_forward_anchor_segment_index": (
                    anchor_segment_index
                    if boundary_available
                    else None
                ),
                "validated_forward_anchor_waypoint_index": (
                    anchor_waypoint_index
                    if boundary_available
                    else None
                ),
                "validated_forward_anchor_exercise_elapsed_ms": (
                    anchor_elapsed_ms
                    if boundary_available
                    else None
                ),
                "segments_to_validated_forward_anchor": (
                    segments_to_anchor
                ),
                "time_to_validated_forward_anchor_ms": (
                    time_to_anchor_ms
                ),
                "unvalidated_prefix": (
                    unvalidated_prefix
                ),
                "geometry_supported_usable_from_exercise_elapsed_ms": (
                    anchor_elapsed_ms
                    if boundary_available
                    else None
                ),
                "geometry_supported_usable_from_segment_index": (
                    anchor_segment_index
                    if boundary_available
                    else None
                ),
                "geometry_supported_usable_from_waypoint_index": (
                    anchor_waypoint_index
                    if boundary_available
                    else None
                ),
                "basis": {
                    "forward_anchor_criteria_version": (
                        forward_route.get(
                            "criteria_version"
                        )
                        if isinstance(
                            forward_route,
                            dict,
                        )
                        else None
                    ),
                    "description": (
                        "Usable-from boundary is supported by "
                        "validated forward-anchor route geometry "
                        "and timestamp continuity only."
                    ),
                },
            }
        )

    return {
        "provider": startup_evidence.get(
            "provider"
        ),
        "evidence_version": (
            EVIDENCE_VERSION
        ),
        "available": bool(
            route_results
        ),
        "route_count": len(
            route_results
        ),
        "scope": {
            "domain": "ROUTE_GEOMETRY",
            "does_not_assert_physiological_validity": (
                True
            ),
            "does_not_mutate_route_data": (
                True
            ),
        },
        "routes": route_results,
    }


def build_trust_boundary_policy_context(
    evidence: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    result = {}

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

        validated_forward_anchor_available = (
            route.get(
                "validated_forward_anchor_available"
            )
        )

        result[
            route_index
        ] = {
            "forward_anchor_available": (
                validated_forward_anchor_available
                if isinstance(
                    validated_forward_anchor_available,
                    bool,
                )
                else None
            ),
            "forward_anchor_exercise_elapsed_ms": (
                route.get(
                    "validated_forward_anchor_exercise_elapsed_ms"
                )
            ),
            "geometry_supported_usable_from_exercise_elapsed_ms": (
                route.get(
                    "geometry_supported_usable_from_exercise_elapsed_ms"
                )
            ),
            "time_to_validated_forward_anchor_ms": (
                route.get(
                    "time_to_validated_forward_anchor_ms"
                )
            ),
            "segments_to_validated_forward_anchor": (
                route.get(
                    "segments_to_validated_forward_anchor"
                )
            ),
            "trust_boundary_status": (
                route.get(
                    "status"
                )
            ),
        }

    return result
