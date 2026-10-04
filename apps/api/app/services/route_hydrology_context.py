from __future__ import annotations

import math
from datetime import datetime
from typing import Any


CONTEXT_VERSION = "0.1"

DEFAULT_MAX_TIME_DELTA_SECONDS = (
    6.0
    * 3600.0
)

EARTH_MEAN_RADIUS_M = 6_371_008.8

METRIC_KEYS = (
    "WATER_LEVEL",
    "DISCHARGE",
    "WATER_TEMPERATURE",
)

STATUS_MATCHED = "MATCHED"
STATUS_MEASUREMENT_UNAVAILABLE = (
    "MEASUREMENT_UNAVAILABLE"
)
STATUS_SEGMENT_TIME_UNAVAILABLE = (
    "SEGMENT_TIME_UNAVAILABLE"
)


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    if not isinstance(
        value,
        (int, float),
    ):
        return None

    result = float(
        value
    )

    return (
        result
        if math.isfinite(
            result
        )
        else None
    )


def _integer(
    value: Any,
) -> int | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    if isinstance(
        value,
        int,
    ):
        return value

    if (
        isinstance(
            value,
            float,
        )
        and math.isfinite(
            value
        )
        and value.is_integer()
    ):
        return int(
            value
        )

    return None


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if not isinstance(
        value,
        str,
    ) or not value.strip():
        return None

    try:
        parsed = (
            datetime.fromisoformat(
                value.strip().replace(
                    "Z",
                    "+00:00",
                )
            )
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return None

    return parsed


def _coordinate(
    value: Any,
) -> tuple[
    float,
    float,
] | None:
    if not isinstance(
        value,
        dict,
    ):
        return None

    latitude = _finite_number(
        value.get(
            "latitude_deg"
        )
    )
    longitude = _finite_number(
        value.get(
            "longitude_deg"
        )
    )

    if (
        latitude is None
        or longitude is None
    ):
        return None

    return (
        latitude,
        longitude,
    )


def _distance_m(
    first: tuple[
        float,
        float,
    ],
    second: tuple[
        float,
        float,
    ],
) -> float:
    first_lat = math.radians(
        first[0]
    )
    first_lon = math.radians(
        first[1]
    )
    second_lat = math.radians(
        second[0]
    )
    second_lon = math.radians(
        second[1]
    )

    delta_lat = (
        second_lat
        - first_lat
    )
    delta_lon = (
        second_lon
        - first_lon
    )

    a = (
        math.sin(
            delta_lat / 2.0
        ) ** 2
        + math.cos(
            first_lat
        )
        * math.cos(
            second_lat
        )
        * math.sin(
            delta_lon / 2.0
        ) ** 2
    )

    c = 2.0 * math.atan2(
        math.sqrt(
            a
        ),
        math.sqrt(
            max(
                0.0,
                1.0 - a,
            )
        ),
    )

    return (
        EARTH_MEAN_RADIUS_M
        * c
    )


def _nearest_measurement(
    *,
    metric_key: str,
    midpoint: datetime,
    measurements: list[
        dict[
            str,
            Any,
        ]
    ],
    max_time_delta_seconds: float,
) -> dict[str, Any]:
    candidates = []

    for measurement in measurements:
        if not isinstance(
            measurement,
            dict,
        ):
            continue

        if (
            measurement.get(
                "metric_key"
            )
            != metric_key
        ):
            continue

        observed_at = _parse_datetime(
            measurement.get(
                "observed_at"
            )
        )

        if observed_at is None:
            continue

        delta = abs(
            (
                midpoint
                - observed_at
            ).total_seconds()
        )

        if (
            delta
            > max_time_delta_seconds
        ):
            continue

        candidates.append(
            (
                delta,
                str(
                    measurement.get(
                        "measurement_id"
                    )
                ),
                measurement,
            )
        )

    if not candidates:
        return {
            "available": False,
            "status": (
                STATUS_MEASUREMENT_UNAVAILABLE
            ),
            "measurement_id": None,
            "observed_at": None,
            "absolute_time_delta_seconds": (
                None
            ),
            "value": None,
            "unit": None,
            "data_type_code": None,
            "data_quality_code": None,
            "field_quality_code": None,
        }

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    delta, _, measurement = (
        candidates[0]
    )

    return {
        "available": True,
        "status": (
            STATUS_MATCHED
        ),
        "measurement_id": (
            measurement.get(
                "measurement_id"
            )
        ),
        "observed_at": (
            measurement.get(
                "observed_at"
            )
        ),
        "absolute_time_delta_seconds": (
            delta
        ),
        "value": (
            measurement.get(
                "value"
            )
        ),
        "unit": (
            measurement.get(
                "unit"
            )
        ),
        "data_type_code": (
            measurement.get(
                "data_type_code"
            )
        ),
        "data_quality_code": (
            measurement.get(
                "data_quality_code"
            )
        ),
        "field_quality_code": (
            measurement.get(
                "field_quality_code"
            )
        ),
    }


def build_route_hydrology_context(
    route_environment_context_input: dict[
        str,
        Any,
    ],
    hydrology_source: dict[
        str,
        Any,
    ],
    *,
    max_time_delta_seconds: float = (
        DEFAULT_MAX_TIME_DELTA_SECONDS
    ),
) -> dict[str, Any]:
    if max_time_delta_seconds < 0.0:
        raise ValueError(
            "max_time_delta_seconds must "
            "be non-negative"
        )

    measurements = [
        measurement
        for measurement in (
            hydrology_source.get(
                "measurements"
            )
            or []
        )
        if isinstance(
            measurement,
            dict,
        )
    ]

    station = (
        hydrology_source.get(
            "station"
        )
        if isinstance(
            hydrology_source.get(
                "station"
            ),
            dict,
        )
        else {}
    )

    station_coordinate = (
        _coordinate(
            station
        )
    )

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
            route_index = (
                route_position
            )

        segment_results = []

        for segment in (
            route.get(
                "segments"
            )
            or []
        ):
            if not isinstance(
                segment,
                dict,
            ):
                continue

            midpoint = _parse_datetime(
                segment.get(
                    "midpoint_timestamp"
                )
            )

            start_coordinate = (
                _coordinate(
                    segment.get(
                        "start_position"
                    )
                )
            )

            station_distance_m = (
                _distance_m(
                    start_coordinate,
                    station_coordinate,
                )
                if (
                    start_coordinate
                    is not None
                    and station_coordinate
                    is not None
                )
                else None
            )

            if midpoint is None:
                metric_context = {
                    metric_key: {
                        "available": (
                            False
                        ),
                        "status": (
                            STATUS_SEGMENT_TIME_UNAVAILABLE
                        ),
                        "measurement_id": (
                            None
                        ),
                        "observed_at": (
                            None
                        ),
                        "absolute_time_delta_seconds": (
                            None
                        ),
                        "value": None,
                        "unit": None,
                        "data_type_code": (
                            None
                        ),
                        "data_quality_code": (
                            None
                        ),
                        "field_quality_code": (
                            None
                        ),
                    }
                    for metric_key
                    in METRIC_KEYS
                }
            else:
                metric_context = {
                    metric_key: (
                        _nearest_measurement(
                            metric_key=(
                                metric_key
                            ),
                            midpoint=(
                                midpoint
                            ),
                            measurements=(
                                measurements
                            ),
                            max_time_delta_seconds=(
                                max_time_delta_seconds
                            ),
                        )
                    )
                    for metric_key
                    in METRIC_KEYS
                }

            segment_results.append(
                {
                    "order_index": (
                        _integer(
                            segment.get(
                                "order_index"
                            )
                        )
                    ),
                    "segment_index": (
                        _integer(
                            segment.get(
                                "segment_index"
                            )
                        )
                    ),
                    "midpoint_timestamp": (
                        segment.get(
                            "midpoint_timestamp"
                        )
                    ),
                    "station_surface_distance_m": (
                        station_distance_m
                    ),
                    "water_level": (
                        metric_context[
                            "WATER_LEVEL"
                        ]
                    ),
                    "discharge": (
                        metric_context[
                            "DISCHARGE"
                        ]
                    ),
                    "water_temperature": (
                        metric_context[
                            "WATER_TEMPERATURE"
                        ]
                    ),
                    "current_speed_estimate_mps": (
                        None
                    ),
                    "current_direction_deg": (
                        None
                    ),
                }
            )

        route_results.append(
            {
                "route_index": (
                    route_index
                ),
                "exercise_index": (
                    _integer(
                        route.get(
                            "exercise_index"
                        )
                    )
                ),
                "available": any(
                    (
                        segment[
                            metric_name
                        ][
                            "available"
                        ]
                        is True
                    )
                    for segment in (
                        segment_results
                    )
                    for metric_name in (
                        "water_level",
                        "discharge",
                        "water_temperature",
                    )
                ),
                "segment_count": (
                    len(
                        segment_results
                    )
                ),
                "water_level_matched_segment_count": (
                    sum(
                        1
                        for segment
                        in segment_results
                        if segment[
                            "water_level"
                        ][
                            "available"
                        ]
                        is True
                    )
                ),
                "discharge_matched_segment_count": (
                    sum(
                        1
                        for segment
                        in segment_results
                        if segment[
                            "discharge"
                        ][
                            "available"
                        ]
                        is True
                    )
                ),
                "water_temperature_matched_segment_count": (
                    sum(
                        1
                        for segment
                        in segment_results
                        if segment[
                            "water_temperature"
                        ][
                            "available"
                        ]
                        is True
                    )
                ),
                "segments": (
                    segment_results
                ),
            }
        )

    return {
        "provider": (
            hydrology_source.get(
                "provider"
            )
        ),
        "context_version": (
            CONTEXT_VERSION
        ),
        "available": any(
            route.get(
                "available"
            )
            is True
            for route in (
                route_results
            )
        ),
        "station": (
            station
        ),
        "matching_policy": {
            "maximum_time_delta_seconds": (
                max_time_delta_seconds
            ),
            "time_selection": (
                "MINIMUM_ABSOLUTE_TIME_DELTA_PER_METRIC"
            ),
            "interpolates_hydrology": (
                False
            ),
            "route_waterbody_identity_asserted": (
                False
            ),
            "station_selection": (
                "EXPLICIT_CALLER_PROVIDED"
            ),
        },
        "scope": {
            "contains_water_level": True,
            "contains_discharge": True,
            "contains_water_temperature": (
                True
            ),
            "estimates_current_velocity": (
                False
            ),
            "derives_current_from_water_level": (
                False
            ),
            "derives_current_from_discharge": (
                False
            ),
            "contains_physiological_interpretation": (
                False
            ),
            "raw_data_mutated": False,
        },
        "routes": (
            route_results
        ),
    }


def build_route_hydrology_context_summary(
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        **context,
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key != "segments"
                },
                "segments_included": (
                    False
                ),
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
                context.get(
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
