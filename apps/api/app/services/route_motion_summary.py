from __future__ import annotations

import math
import statistics
from typing import Any


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


def build_route_motion_summary_evidence(
    motion_evidence: dict[str, Any],
) -> dict[str, Any]:
    raw_routes = (
        motion_evidence.get("routes")
        or []
    )

    if not isinstance(raw_routes, list):
        raw_routes = []

    routes: list[dict[str, Any]] = []

    for route in raw_routes:
        if not isinstance(route, dict):
            continue

        segments = (
            route.get("segments")
            or []
        )

        if not isinstance(segments, list):
            segments = []

        motion_segments = [
            segment
            for segment in segments
            if (
                isinstance(segment, dict)
                and segment.get(
                    "motion_available"
                )
                is True
            )
        ]

        distances: list[float] = []
        speeds: list[float] = []
        intervals_ms: list[int] = []

        bearing_segment_count = 0
        zero_distance_segment_count = 0

        first_motion_start_ms = None
        last_motion_end_ms = None

        for segment in motion_segments:
            distance = _finite_number(
                segment.get(
                    "surface_distance_m"
                )
            )

            speed = _finite_number(
                segment.get(
                    "gps_ground_speed_mps"
                )
            )

            interval_ms = segment.get(
                "interval_ms"
            )

            bearing = _finite_number(
                segment.get(
                    "initial_bearing_deg"
                )
            )

            if distance is not None:
                distances.append(distance)

                if distance == 0.0:
                    zero_distance_segment_count += 1

            if speed is not None:
                speeds.append(speed)

            if (
                isinstance(interval_ms, int)
                and not isinstance(
                    interval_ms,
                    bool,
                )
                and interval_ms > 0
            ):
                intervals_ms.append(
                    interval_ms
                )

            if bearing is not None:
                bearing_segment_count += 1

        if motion_segments:
            first_motion_start_ms = (
                motion_segments[0].get(
                    "start_exercise_elapsed_ms"
                )
            )

            last_motion_end_ms = (
                motion_segments[-1].get(
                    "end_exercise_elapsed_ms"
                )
            )

        total_surface_distance_m = (
            sum(distances)
            if distances
            else None
        )

        total_positive_interval_ms = (
            sum(intervals_ms)
            if intervals_ms
            else None
        )

        distance_over_time_ground_speed_mps = None

        if (
            total_surface_distance_m
            is not None
            and total_positive_interval_ms
            is not None
            and total_positive_interval_ms > 0
        ):
            distance_over_time_ground_speed_mps = (
                total_surface_distance_m
                / (
                    total_positive_interval_ms
                    / 1000.0
                )
            )

        motion_span_ms = None

        if (
            isinstance(
                first_motion_start_ms,
                int,
            )
            and isinstance(
                last_motion_end_ms,
                int,
            )
        ):
            motion_span_ms = (
                last_motion_end_ms
                - first_motion_start_ms
            )

        routes.append(
            {
                "exercise_index": (
                    route.get(
                        "exercise_index"
                    )
                ),
                "segment_count": (
                    len(segments)
                ),
                "motion_segment_count": (
                    len(motion_segments)
                ),
                "bearing_segment_count": (
                    bearing_segment_count
                ),
                "zero_distance_segment_count": (
                    zero_distance_segment_count
                ),
                "first_motion_start_elapsed_ms": (
                    first_motion_start_ms
                ),
                "last_motion_end_elapsed_ms": (
                    last_motion_end_ms
                ),
                "motion_span_ms": (
                    motion_span_ms
                ),
                "total_surface_distance_m": (
                    total_surface_distance_m
                ),
                "total_positive_interval_ms": (
                    total_positive_interval_ms
                ),
                "distance_over_time_ground_speed_mps": (
                    distance_over_time_ground_speed_mps
                ),
                "minimum_segment_ground_speed_mps": (
                    min(speeds)
                    if speeds
                    else None
                ),
                "median_segment_ground_speed_mps": (
                    statistics.median(
                        speeds
                    )
                    if speeds
                    else None
                ),
                "maximum_segment_ground_speed_mps": (
                    max(speeds)
                    if speeds
                    else None
                ),
            }
        )

    return {
        "provider": (
            motion_evidence.get(
                "provider"
            )
        ),
        "available": any(
            route[
                "motion_segment_count"
            ] > 0
            for route in routes
        ),
        "route_count": len(routes),
        "routes": routes,
    }