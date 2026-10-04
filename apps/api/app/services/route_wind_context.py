from __future__ import annotations

import math
import statistics
from typing import Any


EVIDENCE_VERSION = "0.1"

DIRECTION_SEMANTICS = (
    "METEOROLOGICAL_FROM_TRUE_NORTH_CLOCKWISE"
)

STATUS_AVAILABLE = "AVAILABLE"
STATUS_WEATHER_SAMPLE_UNAVAILABLE = "WEATHER_SAMPLE_UNAVAILABLE"
STATUS_MOVEMENT_BEARING_UNAVAILABLE = (
    "MOVEMENT_BEARING_UNAVAILABLE"
)
STATUS_GROUND_SPEED_UNAVAILABLE = (
    "GROUND_SPEED_UNAVAILABLE"
)


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


def _normalize_degrees(
    value: float,
) -> float:
    return value % 360.0


def _unit_vector_from_heading(
    heading_deg: float,
) -> tuple[float, float]:
    """Return east,north unit vector for heading degrees.

    Heading is clockwise from true north.
    """
    radians = math.radians(
        _normalize_degrees(
            heading_deg
        )
    )

    east = math.sin(
        radians
    )
    north = math.cos(
        radians
    )

    return (
        east,
        north,
    )


def _wind_vector_from_meteorological_direction(
    wind_speed_mps: float,
    wind_direction_from_deg: float,
) -> tuple[
    float,
    float,
    float,
]:
    """Return east,north velocity of air and the direction it moves toward."""
    wind_to_deg = _normalize_degrees(
        wind_direction_from_deg
        + 180.0
    )

    east_unit, north_unit = (
        _unit_vector_from_heading(
            wind_to_deg
        )
    )

    return (
        wind_speed_mps
        * east_unit,
        wind_speed_mps
        * north_unit,
        wind_to_deg,
    )


def _course_components(
    east_mps: float,
    north_mps: float,
    movement_bearing_deg: float,
) -> tuple[
    float,
    float,
]:
    """Project vector onto along-course and right-of-course axes.

    Positive along-course means air motion aids movement direction.
    Positive cross-course means air motion is toward the athlete's/boat's
    right side relative to the current movement heading.
    """
    course_east, course_north = (
        _unit_vector_from_heading(
            movement_bearing_deg
        )
    )

    right_east = course_north
    right_north = -course_east

    along = (
        east_mps
        * course_east
        + north_mps
        * course_north
    )

    cross = (
        east_mps
        * right_east
        + north_mps
        * right_north
    )

    return (
        along,
        cross,
    )


def _apparent_air_from_direction_deg(
    apparent_east_mps: float,
    apparent_north_mps: float,
) -> float | None:
    magnitude = math.hypot(
        apparent_east_mps,
        apparent_north_mps,
    )

    if magnitude == 0.0:
        return None

    to_direction_rad = math.atan2(
        apparent_east_mps,
        apparent_north_mps,
    )

    to_direction_deg = (
        math.degrees(
            to_direction_rad
        )
        % 360.0
    )

    return _normalize_degrees(
        to_direction_deg
        + 180.0
    )


def _normalized_weather_sample(
    weather_sample: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(
        weather_sample,
        dict,
    ):
        return None

    speed = _finite_number(
        weather_sample.get(
            "wind_speed_mps"
        )
    )
    direction_from = _finite_number(
        weather_sample.get(
            "wind_direction_from_deg"
        )
    )

    if (
        speed is None
        or speed < 0.0
        or direction_from is None
    ):
        return None

    return {
        "wind_speed_mps": speed,
        "wind_direction_from_deg": (
            _normalize_degrees(
                direction_from
            )
        ),
        "direction_semantics": (
            DIRECTION_SEMANTICS
        ),
        "source": weather_sample.get(
            "source"
        ),
        "observation_timestamp": (
            weather_sample.get(
                "observation_timestamp"
            )
        ),
        "observation_location": (
            weather_sample.get(
                "observation_location"
            )
        ),
    }


def _segment_weather_sample(
    segment_index: int | None,
    default_weather_sample: dict[str, Any] | None,
    wind_by_segment_index: dict[
        int,
        dict[str, Any],
    ] | None,
    matched_weather_sample: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if isinstance(
        matched_weather_sample,
        dict,
    ):
        return _normalized_weather_sample(
            matched_weather_sample
        )

    if (
        segment_index is not None
        and isinstance(
            wind_by_segment_index,
            dict,
        )
        and segment_index
        in wind_by_segment_index
    ):
        return _normalized_weather_sample(
            wind_by_segment_index[
                segment_index
            ]
        )

    return _normalized_weather_sample(
        default_weather_sample
    )


def _build_segment_wind_context(
    segment: dict[str, Any],
    *,
    default_weather_sample: dict[str, Any] | None,
    wind_by_segment_index: dict[
        int,
        dict[str, Any],
    ] | None,
    matched_weather_sample: dict[str, Any] | None = None,
) -> dict[str, Any]:
    segment_index = _integer(
        segment.get(
            "segment_index"
        )
    )

    movement_bearing_deg = (
        _finite_number(
            segment.get(
                "movement_bearing_deg"
            )
        )
    )

    ground_speed_mps = (
        _finite_number(
            segment.get(
                "gps_ground_speed_mps"
            )
        )
    )

    wind = _segment_weather_sample(
        segment_index,
        default_weather_sample,
        wind_by_segment_index,
        matched_weather_sample,
    )

    result = {
        "order_index": (
            _integer(
                segment.get(
                    "order_index"
                )
            )
        ),
        "segment_index": (
            segment_index
        ),
        "start_exercise_elapsed_ms": (
            _integer(
                segment.get(
                    "start_exercise_elapsed_ms"
                )
            )
        ),
        "segment_midpoint_exercise_elapsed_ms": (
            segment.get(
                "segment_midpoint_exercise_elapsed_ms"
            )
        ),
        "end_exercise_elapsed_ms": (
            _integer(
                segment.get(
                    "end_exercise_elapsed_ms"
                )
            )
        ),
        "midpoint_timestamp": (
            segment.get(
                "midpoint_timestamp"
            )
        ),
        "start_position": (
            segment.get(
                "start_position"
            )
        ),
        "end_position": (
            segment.get(
                "end_position"
            )
        ),
        "movement_bearing_deg": (
            movement_bearing_deg
        ),
        "gps_ground_speed_mps": (
            ground_speed_mps
        ),
        "weather_sample": (
            wind
        ),
        "available": False,
        "status": None,
        "wind_to_direction_deg": None,
        "wind_east_mps": None,
        "wind_north_mps": None,
        "wind_along_course_mps": None,
        "wind_cross_course_mps": None,
        "headwind_component_mps": None,
        "tailwind_component_mps": None,
        "crosswind_magnitude_mps": None,
        "relative_air_velocity_along_course_mps": None,
        "relative_air_velocity_cross_course_mps": None,
        "relative_air_speed_mps": None,
        "apparent_wind_direction_from_deg": None,
    }

    if wind is None:
        result[
            "status"
        ] = STATUS_WEATHER_SAMPLE_UNAVAILABLE
        return result

    if movement_bearing_deg is None:
        result[
            "status"
        ] = STATUS_MOVEMENT_BEARING_UNAVAILABLE
        return result

    if ground_speed_mps is None:
        result[
            "status"
        ] = STATUS_GROUND_SPEED_UNAVAILABLE
        return result

    (
        wind_east_mps,
        wind_north_mps,
        wind_to_direction_deg,
    ) = _wind_vector_from_meteorological_direction(
        wind["wind_speed_mps"],
        wind[
            "wind_direction_from_deg"
        ],
    )

    (
        wind_along_course_mps,
        wind_cross_course_mps,
    ) = _course_components(
        wind_east_mps,
        wind_north_mps,
        movement_bearing_deg,
    )

    movement_east_unit, movement_north_unit = (
        _unit_vector_from_heading(
            movement_bearing_deg
        )
    )

    boat_east_mps = (
        ground_speed_mps
        * movement_east_unit
    )
    boat_north_mps = (
        ground_speed_mps
        * movement_north_unit
    )

    apparent_east_mps = (
        wind_east_mps
        - boat_east_mps
    )
    apparent_north_mps = (
        wind_north_mps
        - boat_north_mps
    )

    (
        relative_along_mps,
        relative_cross_mps,
    ) = _course_components(
        apparent_east_mps,
        apparent_north_mps,
        movement_bearing_deg,
    )

    relative_air_speed_mps = math.hypot(
        apparent_east_mps,
        apparent_north_mps,
    )

    result.update(
        {
            "available": True,
            "status": (
                STATUS_AVAILABLE
            ),
            "wind_to_direction_deg": (
                wind_to_direction_deg
            ),
            "wind_east_mps": (
                wind_east_mps
            ),
            "wind_north_mps": (
                wind_north_mps
            ),
            "wind_along_course_mps": (
                wind_along_course_mps
            ),
            "wind_cross_course_mps": (
                wind_cross_course_mps
            ),
            "headwind_component_mps": (
                max(
                    0.0,
                    -wind_along_course_mps,
                )
            ),
            "tailwind_component_mps": (
                max(
                    0.0,
                    wind_along_course_mps,
                )
            ),
            "crosswind_magnitude_mps": (
                abs(
                    wind_cross_course_mps
                )
            ),
            "relative_air_velocity_along_course_mps": (
                relative_along_mps
            ),
            "relative_air_velocity_cross_course_mps": (
                relative_cross_mps
            ),
            "relative_air_speed_mps": (
                relative_air_speed_mps
            ),
            "apparent_wind_direction_from_deg": (
                _apparent_air_from_direction_deg(
                    apparent_east_mps,
                    apparent_north_mps,
                )
            ),
        }
    )

    return result


def _summary(
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    available_segments = [
        segment
        for segment in segments
        if segment.get(
            "available"
        )
        is True
    ]

    def values(
        key: str,
    ) -> list[float]:
        return [
            value
            for segment in available_segments
            if (
                value := _finite_number(
                    segment.get(
                        key
                    )
                )
            )
            is not None
        ]

    headwinds = values(
        "headwind_component_mps"
    )
    tailwinds = values(
        "tailwind_component_mps"
    )
    crosswinds = values(
        "crosswind_magnitude_mps"
    )
    relative_speeds = values(
        "relative_air_speed_mps"
    )

    return {
        "segment_count": (
            len(
                segments
            )
        ),
        "available_segment_count": (
            len(
                available_segments
            )
        ),
        "wind_unavailable_segment_count": (
            sum(
                1
                for segment in segments
                if segment.get(
                    "status"
                )
                == STATUS_WEATHER_SAMPLE_UNAVAILABLE
            )
        ),
        "movement_bearing_unavailable_segment_count": (
            sum(
                1
                for segment in segments
                if segment.get(
                    "status"
                )
                == STATUS_MOVEMENT_BEARING_UNAVAILABLE
            )
        ),
        "ground_speed_unavailable_segment_count": (
            sum(
                1
                for segment in segments
                if segment.get(
                    "status"
                )
                == STATUS_GROUND_SPEED_UNAVAILABLE
            )
        ),
        "maximum_headwind_component_mps": (
            max(
                headwinds
            )
            if headwinds
            else None
        ),
        "maximum_tailwind_component_mps": (
            max(
                tailwinds
            )
            if tailwinds
            else None
        ),
        "maximum_crosswind_magnitude_mps": (
            max(
                crosswinds
            )
            if crosswinds
            else None
        ),
        "minimum_relative_air_speed_mps": (
            min(
                relative_speeds
            )
            if relative_speeds
            else None
        ),
        "median_relative_air_speed_mps": (
            statistics.median(
                relative_speeds
            )
            if relative_speeds
            else None
        ),
        "maximum_relative_air_speed_mps": (
            max(
                relative_speeds
            )
            if relative_speeds
            else None
        ),
    }


def build_route_wind_context(
    route_environment_context_input: dict[str, Any],
    *,
    default_weather_sample: dict[str, Any] | None = None,
    wind_by_segment_index: dict[
        int,
        dict[str, Any],
    ] | None = None,
    weather_sample_matching: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project wind onto trusted route motion without physiology inference.

    Wind direction uses meteorological convention: degrees clockwise from
    true north indicating the direction FROM which the wind is blowing.

    Relative air velocity is air velocity minus athlete/boat ground
    velocity. It is still an external physical quantity; it is not a
    metabolic or physiological load estimate.
    """
    route_results = []

    for route_position, route in enumerate(
        route_environment_context_input.get(
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

        matched_samples_by_segment_index = {}

        if isinstance(
            weather_sample_matching,
            dict,
        ):
            matching_routes = [
                matching_route
                for matching_route in (
                    weather_sample_matching.get(
                        "routes"
                    )
                    or []
                )
                if isinstance(
                    matching_route,
                    dict,
                )
                and _integer(
                    matching_route.get(
                        "route_index"
                    )
                )
                == route_index
                and _integer(
                    matching_route.get(
                        "exercise_index"
                    )
                )
                == exercise_index
            ]

            if len(matching_routes) == 1:
                for match in (
                    matching_routes[0].get(
                        "matches"
                    )
                    or []
                ):
                    if not isinstance(
                        match,
                        dict,
                    ):
                        continue

                    match_segment_index = _integer(
                        match.get(
                            "segment_index"
                        )
                    )
                    matched_sample = (
                        match.get(
                            "matched_sample"
                        )
                    )

                    if (
                        match_segment_index
                        is not None
                        and isinstance(
                            matched_sample,
                            dict,
                        )
                    ):
                        matched_samples_by_segment_index[
                            match_segment_index
                        ] = matched_sample

        segments = [
            _build_segment_wind_context(
                segment,
                default_weather_sample=(
                    default_weather_sample
                ),
                wind_by_segment_index=(
                    wind_by_segment_index
                ),
                matched_weather_sample=(
                    matched_samples_by_segment_index.get(
                        _integer(
                            segment.get(
                                "segment_index"
                            )
                        )
                    )
                ),
            )
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

        summary = _summary(
            segments
        )

        route_results.append(
            {
                "route_index": (
                    route_index
                ),
                "exercise_index": (
                    exercise_index
                ),
                "available": (
                    summary[
                        "available_segment_count"
                    ]
                    > 0
                ),
                "usable_interval": (
                    route.get(
                        "usable_interval"
                    )
                ),
                "quality_provenance": (
                    route.get(
                        "quality_provenance"
                    )
                ),
                "time_context": (
                    route.get(
                        "time_context"
                    )
                ),
                "summary": summary,
                "segments": segments,
            }
        )

    return {
        "provider": (
            route_environment_context_input.get(
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
        "route_count": (
            len(
                route_results
            )
        ),
        "scope": {
            "wind_direction_semantics": (
                DIRECTION_SEMANTICS
            ),
            "wind_is_environmental_input": True,
            "uses_speed_over_ground": True,
            "estimates_relative_air_velocity": True,
            "estimates_boat_through_water_speed": False,
            "contains_hydrology": False,
            "estimates_physiological_load": False,
            "estimates_athlete_effort": False,
            "raw_data_mutated": False,
        },
        "routes": route_results,
    }


def build_route_wind_context_summary(
    wind_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        **wind_context,
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key != "segments"
                },
                "segments_included": False,
                "segment_payload_count": (
                    len(
                        route.get(
                            "segments"
                        )
                        or []
                    )
                ),
            }
            for route in (
                wind_context.get(
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
