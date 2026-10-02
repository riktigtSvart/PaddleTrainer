from __future__ import annotations

import math
from datetime import datetime
from typing import Any


PROVIDER = "POLAR"


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(value, (int, float)):
        return None

    numeric = float(value)

    if not math.isfinite(numeric):
        return None

    return numeric


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def normalize_polar_training_routes(
    training_session: dict[str, Any] | None,
) -> dict[str, Any]:
    training_session = training_session or {}

    exercises = (
        training_session.get("exercises")
        or []
    )

    if not isinstance(exercises, list):
        exercises = []

    routes: list[dict[str, Any]] = []

    for exercise_index, exercise in enumerate(
        exercises
    ):
        if not isinstance(exercise, dict):
            continue

        exercise_start = _parse_datetime(
            exercise.get("startTime")
        )

        route_container = (
            exercise.get("routes")
            or {}
        )

        if not isinstance(
            route_container,
            dict,
        ):
            continue

        route = (
            route_container.get("route")
            or {}
        )

        if not isinstance(route, dict):
            continue

        route_start = _parse_datetime(
            route.get("startTime")
        )

        route_start_offset_ms = None

        if (
            exercise_start is not None
            and route_start is not None
        ):
            route_start_offset_ms = (
                (
                    route_start
                    - exercise_start
                ).total_seconds()
                * 1000
            )

        raw_waypoints = (
            route.get("wayPoints")
            or []
        )

        if not isinstance(
            raw_waypoints,
            list,
        ):
            raw_waypoints = []

        points: list[dict[str, Any]] = []

        for waypoint_index, waypoint in enumerate(
            raw_waypoints
        ):
            if not isinstance(
                waypoint,
                dict,
            ):
                continue

            source_elapsed_ms = (
                waypoint.get(
                    "elapsedMillis"
                )
            )

            if not isinstance(
                source_elapsed_ms,
                int,
            ):
                source_elapsed_ms = None

            exercise_elapsed_ms = None

            if (
                source_elapsed_ms is not None
                and route_start_offset_ms
                is not None
            ):
                exercise_elapsed_ms = (
                    route_start_offset_ms
                    + source_elapsed_ms
                )

            points.append(
                {
                    "waypoint_index": (
                        waypoint_index
                    ),
                    "source_elapsed_ms": (
                        source_elapsed_ms
                    ),
                    "exercise_elapsed_ms": (
                        exercise_elapsed_ms
                    ),
                    "latitude_deg": (
                        _finite_number(
                            waypoint.get(
                                "latitude"
                            )
                        )
                    ),
                    "longitude_deg": (
                        _finite_number(
                            waypoint.get(
                                "longitude"
                            )
                        )
                    ),
                    "altitude_m": (
                        _finite_number(
                            waypoint.get(
                                "altitude"
                            )
                        )
                    ),
                }
            )

        routes.append(
            {
                "exercise_index": (
                    exercise_index
                ),
                "route_start_time": (
                    route.get("startTime")
                ),
                "exercise_start_time": (
                    exercise.get(
                        "startTime"
                    )
                ),
                "route_start_offset_ms": (
                    route_start_offset_ms
                ),
                "waypoint_count": len(
                    points
                ),
                "points": points,
            }
        )

    return {
        "provider": PROVIDER,
        "exercise_count": len(exercises),
        "route_count": len(routes),
        "routes": routes,
    }