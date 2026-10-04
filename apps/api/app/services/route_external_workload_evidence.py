from __future__ import annotations

import math
import statistics
from copy import deepcopy
from typing import Any


EVIDENCE_VERSION = "0.1"

SCOPE_ROUTE_GROUND_MOTION = (
    "ROUTE_GROUND_MOTION"
)

REASON_WORKLOAD_INPUT_UNAVAILABLE = (
    "ROUTE_WORKLOAD_INPUT_UNAVAILABLE"
)
REASON_MOTION_SEGMENTS_UNAVAILABLE = (
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

    result = float(value)

    if not math.isfinite(
        result
    ):
        return None

    return result


def _bearing_separation_deg(
    first: float | None,
    second: float | None,
) -> float | None:
    if (
        first is None
        or second is None
    ):
        return None

    delta = (
        second
        - first
    ) % 360.0

    if delta > 180.0:
        delta = 360.0 - delta

    return delta


def _segment_midpoint_ms(
    segment: dict[str, Any],
) -> float | None:
    start_ms = _integer(
        segment.get(
            "start_exercise_elapsed_ms"
        )
    )
    end_ms = _integer(
        segment.get(
            "end_exercise_elapsed_ms"
        )
    )

    if (
        start_ms is None
        or end_ms is None
        or end_ms < start_ms
    ):
        return None

    return (
        start_ms
        + end_ms
    ) / 2.0


def _segments_are_source_contiguous(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    previous_end_waypoint = _integer(
        previous.get(
            "end_waypoint_index"
        )
    )
    current_start_waypoint = _integer(
        current.get(
            "start_waypoint_index"
        )
    )

    previous_end_ms = _integer(
        previous.get(
            "end_exercise_elapsed_ms"
        )
    )
    current_start_ms = _integer(
        current.get(
            "start_exercise_elapsed_ms"
        )
    )

    return (
        previous_end_waypoint is not None
        and current_start_waypoint is not None
        and previous_end_waypoint
        == current_start_waypoint
        and previous_end_ms is not None
        and current_start_ms is not None
        and previous_end_ms
        == current_start_ms
    )


def _build_observations(
    motion_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observations = []
    cumulative_distance_m = 0.0
    previous_segment = None

    for order_index, segment in enumerate(
        motion_segments
    ):
        surface_distance_m = _finite_number(
            segment.get(
                "surface_distance_m"
            )
        )
        gps_ground_speed_mps = _finite_number(
            segment.get(
                "gps_ground_speed_mps"
            )
        )
        bearing_deg = _finite_number(
            segment.get(
                "initial_bearing_deg"
            )
        )
        interval_ms = _integer(
            segment.get(
                "interval_ms"
            )
        )

        if (
            surface_distance_m is not None
            and surface_distance_m >= 0.0
        ):
            cumulative_distance_m += (
                surface_distance_m
            )

        source_contiguous = False
        previous_speed = None
        previous_bearing = None
        speed_change_mps = None
        midpoint_separation_ms = None
        speed_change_rate_mps2 = None
        bearing_change_deg = None

        if previous_segment is not None:
            source_contiguous = (
                _segments_are_source_contiguous(
                    previous_segment,
                    segment,
                )
            )

            previous_speed = _finite_number(
                previous_segment.get(
                    "gps_ground_speed_mps"
                )
            )
            previous_bearing = _finite_number(
                previous_segment.get(
                    "initial_bearing_deg"
                )
            )

            previous_midpoint_ms = (
                _segment_midpoint_ms(
                    previous_segment
                )
            )
            current_midpoint_ms = (
                _segment_midpoint_ms(
                    segment
                )
            )

            if (
                source_contiguous
                and previous_speed is not None
                and gps_ground_speed_mps
                is not None
            ):
                speed_change_mps = (
                    gps_ground_speed_mps
                    - previous_speed
                )

                if (
                    previous_midpoint_ms
                    is not None
                    and current_midpoint_ms
                    is not None
                ):
                    midpoint_separation_ms = (
                        current_midpoint_ms
                        - previous_midpoint_ms
                    )

                    if (
                        midpoint_separation_ms
                        > 0.0
                    ):
                        speed_change_rate_mps2 = (
                            speed_change_mps
                            / (
                                midpoint_separation_ms
                                / 1000.0
                            )
                        )

            if source_contiguous:
                bearing_change_deg = (
                    _bearing_separation_deg(
                        previous_bearing,
                        bearing_deg,
                    )
                )

        observations.append(
            {
                "order_index": (
                    order_index
                ),
                "segment_index": (
                    _integer(
                        segment.get(
                            "segment_index"
                        )
                    )
                ),
                "start_waypoint_index": (
                    _integer(
                        segment.get(
                            "start_waypoint_index"
                        )
                    )
                ),
                "end_waypoint_index": (
                    _integer(
                        segment.get(
                            "end_waypoint_index"
                        )
                    )
                ),
                "start_exercise_elapsed_ms": (
                    _integer(
                        segment.get(
                            "start_exercise_elapsed_ms"
                        )
                    )
                ),
                "end_exercise_elapsed_ms": (
                    _integer(
                        segment.get(
                            "end_exercise_elapsed_ms"
                        )
                    )
                ),
                "segment_midpoint_exercise_elapsed_ms": (
                    _segment_midpoint_ms(
                        segment
                    )
                ),
                "interval_ms": (
                    interval_ms
                ),
                "surface_distance_m": (
                    surface_distance_m
                ),
                "cumulative_trusted_surface_distance_m": (
                    cumulative_distance_m
                ),
                "gps_ground_speed_mps": (
                    gps_ground_speed_mps
                ),
                "initial_bearing_deg": (
                    bearing_deg
                ),
                "motion_available": (
                    segment.get(
                        "motion_available"
                    )
                    is True
                ),
                "motion_reason": (
                    segment.get(
                        "reason"
                    )
                ),
                "source_contiguous_with_previous": (
                    source_contiguous
                ),
                "previous_segment_index": (
                    _integer(
                        previous_segment.get(
                            "segment_index"
                        )
                    )
                    if previous_segment
                    is not None
                    else None
                ),
                "previous_gps_ground_speed_mps": (
                    previous_speed
                    if source_contiguous
                    else None
                ),
                "ground_speed_change_from_previous_mps": (
                    speed_change_mps
                ),
                "segment_midpoint_separation_from_previous_ms": (
                    midpoint_separation_ms
                    if source_contiguous
                    else None
                ),
                "ground_speed_change_rate_mps2": (
                    speed_change_rate_mps2
                ),
                "absolute_bearing_change_from_previous_deg": (
                    bearing_change_deg
                ),
            }
        )

        previous_segment = segment

    return observations


def _build_summary(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    speeds = [
        value
        for observation in observations
        if (
            value := _finite_number(
                observation.get(
                    "gps_ground_speed_mps"
                )
            )
        )
        is not None
    ]

    speed_change_rates = [
        value
        for observation in observations
        if (
            value := _finite_number(
                observation.get(
                    "ground_speed_change_rate_mps2"
                )
            )
        )
        is not None
    ]

    bearing_changes = [
        value
        for observation in observations
        if (
            value := _finite_number(
                observation.get(
                    "absolute_bearing_change_from_previous_deg"
                )
            )
        )
        is not None
    ]

    positive_intervals = [
        interval_ms
        for observation in observations
        if (
            (interval_ms := _integer(
                observation.get(
                    "interval_ms"
                )
            ))
            is not None
            and interval_ms > 0
        )
    ]

    total_surface_distance_m = sum(
        value
        for observation in observations
        if (
            value := _finite_number(
                observation.get(
                    "surface_distance_m"
                )
            )
        )
        is not None
        and value >= 0.0
    )

    total_positive_interval_ms = sum(
        positive_intervals
    )

    return {
        "observation_count": (
            len(
                observations
            )
        ),
        "motion_available_observation_count": (
            sum(
                1
                for observation in observations
                if observation.get(
                    "motion_available"
                )
                is True
            )
        ),
        "source_contiguous_transition_count": (
            sum(
                1
                for observation in observations
                if observation.get(
                    "source_contiguous_with_previous"
                )
                is True
            )
        ),
        "ground_speed_change_rate_observation_count": (
            len(
                speed_change_rates
            )
        ),
        "bearing_change_observation_count": (
            len(
                bearing_changes
            )
        ),
        "first_start_exercise_elapsed_ms": (
            observations[0].get(
                "start_exercise_elapsed_ms"
            )
            if observations
            else None
        ),
        "last_end_exercise_elapsed_ms": (
            observations[-1].get(
                "end_exercise_elapsed_ms"
            )
            if observations
            else None
        ),
        "total_surface_distance_m": (
            total_surface_distance_m
        ),
        "total_positive_interval_ms": (
            total_positive_interval_ms
        ),
        "distance_over_positive_interval_mps": (
            total_surface_distance_m
            / (
                total_positive_interval_ms
                / 1000.0
            )
            if total_positive_interval_ms
            > 0
            else None
        ),
        "minimum_ground_speed_mps": (
            min(
                speeds
            )
            if speeds
            else None
        ),
        "median_ground_speed_mps": (
            statistics.median(
                speeds
            )
            if speeds
            else None
        ),
        "maximum_ground_speed_mps": (
            max(
                speeds
            )
            if speeds
            else None
        ),
        "minimum_ground_speed_change_rate_mps2": (
            min(
                speed_change_rates
            )
            if speed_change_rates
            else None
        ),
        "median_ground_speed_change_rate_mps2": (
            statistics.median(
                speed_change_rates
            )
            if speed_change_rates
            else None
        ),
        "maximum_ground_speed_change_rate_mps2": (
            max(
                speed_change_rates
            )
            if speed_change_rates
            else None
        ),
        "maximum_absolute_bearing_change_deg": (
            max(
                bearing_changes
            )
            if bearing_changes
            else None
        ),
    }


def build_route_external_workload_evidence(
    route_workload_input: dict[str, Any],
) -> dict[str, Any]:
    """Build descriptive route-derived external-motion evidence.

    The evidence is intentionally environment-unadjusted and is not a
    physiological load estimate. Ground speed is speed over ground, not
    boat-through-water speed, air-relative speed, metabolic demand, or
    athlete effort.
    """
    route_results = []

    for route_position, route in enumerate(
        route_workload_input.get(
            "routes"
        )
        or []
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

        workload_input_available = (
            route.get(
                "available"
            )
            is True
        )

        motion_segments = [
            deepcopy(segment)
            for segment in (
                route.get(
                    "motion_segments"
                )
                or []
            )
            if isinstance(
                segment,
                dict,
            )
        ]

        observations = (
            _build_observations(
                motion_segments
            )
            if workload_input_available
            else []
        )

        available = bool(
            observations
        )

        if not workload_input_available:
            reason = (
                REASON_WORKLOAD_INPUT_UNAVAILABLE
            )
        elif not motion_segments:
            reason = (
                REASON_MOTION_SEGMENTS_UNAVAILABLE
            )
        else:
            reason = None

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": available,
                "reason": reason,
                "usable_interval": deepcopy(
                    route.get(
                        "usable_interval"
                    )
                ),
                "distance_evidence": deepcopy(
                    route.get(
                        "distance_evidence"
                    )
                ),
                "quality_provenance": deepcopy(
                    route.get(
                        "quality_provenance"
                    )
                ),
                "input_provenance": {
                    "route_workload_input_schema_version": (
                        route_workload_input.get(
                            "schema_version"
                        )
                    ),
                    "route_workload_input_source_branch": (
                        route_workload_input.get(
                            "source_branch"
                        )
                    ),
                },
                "summary": (
                    _build_summary(
                        observations
                    )
                ),
                "observations": (
                    observations
                ),
            }
        )

    return {
        "provider": (
            route_workload_input.get(
                "provider"
            )
        ),
        "evidence_version": (
            EVIDENCE_VERSION
        ),
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
        "scope": {
            "domain": (
                SCOPE_ROUTE_GROUND_MOTION
            ),
            "environment_adjusted": False,
            "estimates_physiological_load": False,
            "estimates_energy_expenditure": False,
            "estimates_athlete_effort": False,
            "ground_speed_semantics": (
                "SPEED_OVER_GROUND"
            ),
            "ground_speed_change_rate_semantics": (
                "FINITE_DIFFERENCE_OF_ADJACENT_SEGMENT_AVERAGE_GROUND_SPEEDS"
            ),
            "raw_data_mutated": False,
        },
        "routes": (
            route_results
        ),
    }


def build_route_external_workload_evidence_summary(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Strip full observation payload for inspection/API responses."""
    return {
        **evidence,
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key
                    != "observations"
                },
                "observations_included": (
                    False
                ),
                "observation_payload_count": (
                    len(
                        route.get(
                            "observations"
                        )
                        or []
                    )
                ),
            }
            for route in (
                evidence.get(
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
