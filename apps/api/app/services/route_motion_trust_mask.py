from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


VIEW_VERSION = "0.1"

MODE_UNCHANGED = "UNCHANGED"
MODE_MASKED_BEFORE_TRUST_BOUNDARY = (
    "MASKED_BEFORE_TRUST_BOUNDARY"
)
MODE_UNAVAILABLE_NO_TRUST_BOUNDARY = (
    "UNAVAILABLE_NO_TRUST_BOUNDARY"
)

AUTO_MASK_ACTIONS = {
    "EXCLUDE",
    "RECONSTRUCT",
}


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


def _elapsed_ms(
    point: dict[str, Any],
) -> int | None:
    return _integer(
        point.get(
            "exercise_elapsed_ms"
        )
    )


def build_route_motion_trust_mask(
    normalized_routes: dict[str, Any],
    trust_boundary_evidence: dict[str, Any],
    artifact_policy: dict[str, Any],
) -> dict[str, Any]:
    """Build a downstream-usable route view without mutating raw data.

    OBSERVE, SUPPRESS and REVIEW preserve the complete normalized route.
    EXCLUDE and RECONSTRUCT mask the prefix before the validated
    geometry-supported usable-from boundary. If such a boundary is not
    available, no route points are exposed as automatically usable.
    """
    trust_lookup = _route_lookup(
        trust_boundary_evidence
    )
    policy_lookup = _route_lookup(
        artifact_policy
    )

    output_routes = []

    for route_index, route in enumerate(
        normalized_routes.get("routes") or []
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

        action = (
            policy_route.get("action")
            if isinstance(
                policy_route,
                dict,
            )
            else None
        )

        points = [
            deepcopy(point)
            for point
            in (
                route.get("points")
                or []
            )
            if isinstance(
                point,
                dict,
            )
        ]

        original_point_count = len(
            points
        )

        original_first_elapsed_ms = (
            _elapsed_ms(points[0])
            if points
            else None
        )
        original_last_elapsed_ms = (
            _elapsed_ms(points[-1])
            if points
            else None
        )

        should_mask = (
            action in AUTO_MASK_ACTIONS
        )

        usable_from_ms = (
            _integer(
                trust_route.get(
                    "geometry_supported_usable_from_exercise_elapsed_ms"
                )
            )
            if isinstance(
                trust_route,
                dict,
            )
            else None
        )

        boundary_available = (
            isinstance(
                trust_route,
                dict,
            )
            and trust_route.get(
                "available"
            )
            is True
            and usable_from_ms is not None
        )

        if not should_mask:
            usable_points = points
            mode = MODE_UNCHANGED
            reason = (
                "POLICY_ACTION_DOES_NOT_REQUIRE_AUTOMATIC_MASKING"
            )
            applied_usable_from_ms = None
        elif boundary_available:
            usable_points = [
                point
                for point in points
                if (
                    (elapsed := _elapsed_ms(point))
                    is not None
                    and elapsed >= usable_from_ms
                )
            ]
            mode = (
                MODE_MASKED_BEFORE_TRUST_BOUNDARY
            )
            reason = (
                "POLICY_ACTION_REQUIRES_MASKING_AND_TRUST_BOUNDARY_IS_AVAILABLE"
            )
            applied_usable_from_ms = (
                usable_from_ms
            )
        else:
            usable_points = []
            mode = (
                MODE_UNAVAILABLE_NO_TRUST_BOUNDARY
            )
            reason = (
                "POLICY_ACTION_REQUIRES_MASKING_BUT_TRUST_BOUNDARY_IS_UNAVAILABLE"
            )
            applied_usable_from_ms = None

        usable_point_count = len(
            usable_points
        )
        excluded_point_count = (
            original_point_count
            - usable_point_count
        )

        usable_first_elapsed_ms = (
            _elapsed_ms(
                usable_points[0]
            )
            if usable_points
            else None
        )
        usable_last_elapsed_ms = (
            _elapsed_ms(
                usable_points[-1]
            )
            if usable_points
            else None
        )

        output_route = {
            key: deepcopy(value)
            for key, value in route.items()
            if key not in {
                "points",
                "waypoint_count",
            }
        }

        output_route.update(
            {
                "waypoint_count": (
                    usable_point_count
                ),
                "points": usable_points,
                "trust_mask": {
                    "view_version": (
                        VIEW_VERSION
                    ),
                    "action": action,
                    "mode": mode,
                    "reason": reason,
                    "raw_data_mutated": False,
                    "original_point_count": (
                        original_point_count
                    ),
                    "usable_point_count": (
                        usable_point_count
                    ),
                    "excluded_point_count": (
                        excluded_point_count
                    ),
                    "original_first_exercise_elapsed_ms": (
                        original_first_elapsed_ms
                    ),
                    "original_last_exercise_elapsed_ms": (
                        original_last_elapsed_ms
                    ),
                    "geometry_supported_usable_from_exercise_elapsed_ms": (
                        usable_from_ms
                    ),
                    "applied_usable_from_exercise_elapsed_ms": (
                        applied_usable_from_ms
                    ),
                    "usable_first_exercise_elapsed_ms": (
                        usable_first_elapsed_ms
                    ),
                    "usable_last_exercise_elapsed_ms": (
                        usable_last_elapsed_ms
                    ),
                },
            }
        )

        output_routes.append(
            output_route
        )

    return {
        "provider": normalized_routes.get(
            "provider"
        ),
        "view_version": VIEW_VERSION,
        "available": bool(
            output_routes
        ),
        "exercise_count": (
            normalized_routes.get(
                "exercise_count"
            )
        ),
        "route_count": len(
            output_routes
        ),
        "scope": {
            "purpose": (
                "DOWNSTREAM_ROUTE_AND_WORKLOAD_PROCESSING"
            ),
            "raw_data_mutated": False,
            "auto_mask_actions": sorted(
                AUTO_MASK_ACTIONS
            ),
        },
        "routes": output_routes,
    }


def build_route_motion_trust_mask_summary(
    trusted_view: dict[str, Any],
) -> dict[str, Any]:
    return {
        **trusted_view,
        "routes": [
            {
                **{
                    key: value
                    for key, value in route.items()
                    if key != "points"
                },
                "points_included": False,
            }
            for route in (
                trusted_view.get(
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
