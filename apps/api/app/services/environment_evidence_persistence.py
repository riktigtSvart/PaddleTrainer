from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    RouteEnvironmentEvidenceSet,
    RouteEnvironmentHydrologyMeasurement,
    RouteEnvironmentRoute,
    RouteEnvironmentSegment,
    RouteEnvironmentWeatherSample,
    User,
    WorkoutSession,
)


EVIDENCE_HASH_SEMANTICS_VERSION = "1"


def _canonical_hash(
    payload: dict[str, Any],
) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(
        serialized
    ).hexdigest()


def _semantic_hash_payload(
    *,
    schema_version: str,
    provider: str | None,
    session_external_id: str | None,
    scope: dict[str, Any],
    weather_samples: list[dict[str, Any]],
    hydrology_measurements: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_routes = []

    for route in sorted(
        routes,
        key=lambda item: (
            item.get("route_key")
            or ""
        ),
    ):
        normalized_route = dict(
            route
        )

        normalized_route["segments"] = sorted(
            route.get("segments")
            or [],
            key=lambda segment: (
                (
                    segment.get("order_index")
                    if isinstance(
                        segment.get("order_index"),
                        int,
                    )
                    else 0
                ),
                segment.get("record_id")
                or "",
            ),
        )

        normalized_routes.append(
            normalized_route
        )

    return {
        "hash_semantics_version": (
            EVIDENCE_HASH_SEMANTICS_VERSION
        ),
        "schema_version": schema_version,
        "provider": provider,
        "session_external_id": (
            session_external_id
        ),
        "scope": scope,
        "weather_samples": sorted(
            weather_samples,
            key=lambda item: (
                item.get("source_provider")
                or "",
                item.get("source_sample_id")
                or "",
            ),
        ),
        "hydrology_measurements": sorted(
            hydrology_measurements,
            key=lambda item: (
                item.get("source_provider")
                or "",
                item.get("source_measurement_id")
                or "",
            ),
        ),
        "routes": normalized_routes,
    }


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(
        value,
        datetime,
    ):
        return (
            value
            if value.tzinfo is not None
            else value.replace(
                tzinfo=timezone.utc
            )
        )

    if not isinstance(
        value,
        str,
    ) or not value.strip():
        return None

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def _finite_float(
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


def _string_or_none(
    value: Any,
) -> str | None:
    if value is None:
        return None

    return str(
        value
    )


def _position_coordinate(
    position: Any,
    key: str,
) -> float | None:
    if not isinstance(
        position,
        dict,
    ):
        return None

    return _finite_float(
        position.get(
            key
        )
    )


def _route_key(
    route_index: int,
    exercise_index: int | None,
) -> str:
    exercise_key = (
        str(
            exercise_index
        )
        if exercise_index
        is not None
        else "UNKNOWN"
    )

    return (
        f"r{route_index}:"
        f"e{exercise_key}"
    )


def _catalog_source_summary(
    source_catalog: dict[str, Any],
) -> dict[str, Any]:
    return {
        "evidence_hash_semantics_version": (
            EVIDENCE_HASH_SEMANTICS_VERSION
        ),
        "weather_source": (
            source_catalog.get(
                "weather_source"
            )
        ),
        "hydrology_source": (
            source_catalog.get(
                "hydrology_source"
            )
        ),
    }


def _weather_row(
    sample: dict[str, Any],
) -> dict[str, Any]:
    sample_id = sample.get(
        "sample_id"
    )

    provider = (
        sample.get(
            "source_provider"
        )
        or "UNKNOWN"
    )

    if not isinstance(
        sample_id,
        str,
    ) or not sample_id:
        raise ValueError(
            "Weather sample is missing sample_id"
        )

    return {
        "source_provider": str(
            provider
        ),
        "source_product": (
            _string_or_none(
                sample.get(
                    "source_product"
                )
            )
        ),
        "source_type": (
            _string_or_none(
                sample.get(
                    "source_type"
                )
            )
        ),
        "source_sample_id": (
            sample_id
        ),
        "sampled_at": (
            _parse_datetime(
                sample.get(
                    "sample_timestamp"
                )
            )
        ),
        "latitude_deg": (
            _finite_float(
                sample.get(
                    "latitude_deg"
                )
            )
        ),
        "longitude_deg": (
            _finite_float(
                sample.get(
                    "longitude_deg"
                )
            )
        ),
        "elevation_m": (
            _finite_float(
                sample.get(
                    "elevation_m"
                )
            )
        ),
        "air_temperature_c": (
            _finite_float(
                sample.get(
                    "air_temperature_c"
                )
            )
        ),
        "wind_speed_mps": (
            _finite_float(
                sample.get(
                    "wind_speed_mps"
                )
            )
        ),
        "wind_direction_from_deg": (
            _finite_float(
                sample.get(
                    "wind_direction_from_deg"
                )
            )
        ),
        "wind_gust_mps": (
            _finite_float(
                sample.get(
                    "wind_gust_mps"
                )
            )
        ),
        "temporal_resolution_seconds": (
            _integer(
                sample.get(
                    "temporal_resolution_seconds"
                )
            )
        ),
        "spatial_support": (
            _string_or_none(
                sample.get(
                    "spatial_support"
                )
            )
        ),
        "source_reference": (
            _string_or_none(
                sample.get(
                    "source_reference"
                )
            )
        ),
        "extra_data": {
            key: value
            for key, value
            in sample.items()
            if key not in {
                "sample_id",
                "sample_timestamp",
                "latitude_deg",
                "longitude_deg",
                "elevation_m",
                "air_temperature_c",
                "wind_speed_mps",
                "wind_direction_from_deg",
                "wind_gust_mps",
                "temporal_resolution_seconds",
                "spatial_support",
                "source_reference",
                "source_provider",
                "source_product",
                "source_type",
            }
        },
    }


def _hydrology_row(
    measurement: dict[str, Any],
) -> dict[str, Any]:
    measurement_id = (
        measurement.get(
            "measurement_id"
        )
    )

    observed_at = _parse_datetime(
        measurement.get(
            "observed_at"
        )
    )

    value = _finite_float(
        measurement.get(
            "value"
        )
    )

    metric_key = measurement.get(
        "metric_key"
    )

    unit = measurement.get(
        "unit"
    )

    if not isinstance(
        measurement_id,
        str,
    ) or not measurement_id:
        raise ValueError(
            "Hydrology measurement is missing measurement_id"
        )

    if observed_at is None:
        raise ValueError(
            "Hydrology measurement is missing observed_at"
        )

    if value is None:
        raise ValueError(
            "Hydrology measurement is missing finite value"
        )

    if not isinstance(
        metric_key,
        str,
    ) or not metric_key:
        raise ValueError(
            "Hydrology measurement is missing metric_key"
        )

    if not isinstance(
        unit,
        str,
    ) or not unit:
        raise ValueError(
            "Hydrology measurement is missing unit"
        )

    station = (
        measurement.get(
            "station"
        )
        if isinstance(
            measurement.get(
                "station"
            ),
            dict,
        )
        else {}
    )

    provider = (
        measurement.get(
            "source_provider"
        )
        or "UNKNOWN"
    )

    return {
        "source_provider": str(
            provider
        ),
        "source_product": (
            _string_or_none(
                measurement.get(
                    "source_product"
                )
            )
        ),
        "source_type": (
            _string_or_none(
                measurement.get(
                    "source_type"
                )
            )
        ),
        "source_measurement_id": (
            measurement_id
        ),
        "observed_at": (
            observed_at
        ),
        "metric_key": (
            metric_key
        ),
        "metric_code": (
            _string_or_none(
                measurement.get(
                    "metric_code"
                )
            )
        ),
        "value": (
            value
        ),
        "unit": (
            unit
        ),
        "provider_data_type": (
            _string_or_none(
                measurement.get(
                    "data_type_code"
                )
            )
        ),
        "data_quality_code": (
            _string_or_none(
                measurement.get(
                    "data_quality_code"
                )
            )
        ),
        "field_quality_code": (
            _string_or_none(
                measurement.get(
                    "field_quality_code"
                )
            )
        ),
        "station_registry_id": (
            _string_or_none(
                station.get(
                    "station_registry_number"
                )
            )
        ),
        "station_name": (
            _string_or_none(
                station.get(
                    "station_name"
                )
            )
        ),
        "watercourse": (
            _string_or_none(
                station.get(
                    "watercourse"
                )
            )
        ),
        "municipality": (
            _string_or_none(
                station.get(
                    "municipality"
                )
            )
        ),
        "station_latitude_deg": (
            _finite_float(
                station.get(
                    "latitude_deg"
                )
            )
        ),
        "station_longitude_deg": (
            _finite_float(
                station.get(
                    "longitude_deg"
                )
            )
        ),
        "river_km": (
            _finite_float(
                station.get(
                    "river_km"
                )
            )
        ),
        "extra_data": {
            key: value
            for key, value
            in measurement.items()
            if key not in {
                "measurement_id",
                "observed_at",
                "metric_code",
                "metric_key",
                "value",
                "unit",
                "data_type_code",
                "data_quality_code",
                "field_quality_code",
                "source_provider",
                "source_product",
                "source_type",
                "station",
            }
        },
    }


def _metric_reference(
    metric: Any,
) -> tuple[
    str | None,
    str | None,
    float | None,
]:
    if not isinstance(
        metric,
        dict,
    ):
        return (
            None,
            None,
            None,
        )

    return (
        _string_or_none(
            metric.get(
                "measurement_id"
            )
        ),
        _string_or_none(
            metric.get(
                "status"
            )
        ),
        _finite_float(
            metric.get(
                "absolute_time_delta_seconds"
            )
        ),
    )


def _segment_row(
    segment: dict[str, Any],
    *,
    weather_ids: set[str],
    hydrology_ids: set[str],
) -> dict[str, Any]:
    record_id = segment.get(
        "record_id"
    )

    if not isinstance(
        record_id,
        str,
    ) or not record_id:
        raise ValueError(
            "Environment segment is missing record_id"
        )

    source_locator = (
        segment.get(
            "source_locator"
        )
        if isinstance(
            segment.get(
                "source_locator"
            ),
            dict,
        )
        else {}
    )

    path = (
        segment.get(
            "actual_path_evidence"
        )
        if isinstance(
            segment.get(
                "actual_path_evidence"
            ),
            dict,
        )
        else {}
    )

    motion = (
        segment.get(
            "external_motion"
        )
        if isinstance(
            segment.get(
                "external_motion"
            ),
            dict,
        )
        else {}
    )

    weather = (
        segment.get(
            "weather"
        )
        if isinstance(
            segment.get(
                "weather"
            ),
            dict,
        )
        else {}
    )

    wind = (
        segment.get(
            "wind_physics"
        )
        if isinstance(
            segment.get(
                "wind_physics"
            ),
            dict,
        )
        else {}
    )

    hydrology = (
        segment.get(
            "hydrology"
        )
        if isinstance(
            segment.get(
                "hydrology"
            ),
            dict,
        )
        else {}
    )

    waterbody = (
        segment.get(
            "waterbody_identity"
        )
        if isinstance(
            segment.get(
                "waterbody_identity"
            ),
            dict,
        )
        else {}
    )

    route_choice = (
        segment.get(
            "route_choice_context"
        )
        if isinstance(
            segment.get(
                "route_choice_context"
            ),
            dict,
        )
        else {}
    )

    weather_sample_key = (
        _string_or_none(
            weather.get(
                "sample_id"
            )
        )
    )

    if (
        weather_sample_key is not None
        and weather_sample_key
        not in weather_ids
    ):
        raise ValueError(
            "Segment references weather sample "
            f"not present in source catalog: "
            f"{weather_sample_key}"
        )

    (
        water_level_key,
        water_level_status,
        water_level_delta,
    ) = _metric_reference(
        hydrology.get(
            "water_level"
        )
    )

    (
        discharge_key,
        discharge_status,
        discharge_delta,
    ) = _metric_reference(
        hydrology.get(
            "discharge"
        )
    )

    (
        water_temperature_key,
        water_temperature_status,
        water_temperature_delta,
    ) = _metric_reference(
        hydrology.get(
            "water_temperature"
        )
    )

    for measurement_key in (
        water_level_key,
        discharge_key,
        water_temperature_key,
    ):
        if (
            measurement_key is not None
            and measurement_key
            not in hydrology_ids
        ):
            raise ValueError(
                "Segment references hydrology measurement "
                "not present in source catalog: "
                f"{measurement_key}"
            )

    start_position = path.get(
        "start_position"
    )
    end_position = path.get(
        "end_position"
    )

    return {
        "record_id": (
            record_id
        ),
        "order_index": (
            _integer(
                segment.get(
                    "order_index"
                )
            )
            or 0
        ),
        "view_segment_index": (
            _integer(
                source_locator.get(
                    "view_segment_index"
                )
            )
        ),
        "segment_index_scope": (
            _string_or_none(
                source_locator.get(
                    "segment_index_scope"
                )
            )
        ),
        "source_segment_index": (
            _integer(
                source_locator.get(
                    "source_segment_index"
                )
            )
        ),
        "source_segment_index_scope": (
            _string_or_none(
                source_locator.get(
                    "source_segment_index_scope"
                )
            )
        ),
        "source_segment_index_status": (
            _string_or_none(
                source_locator.get(
                    "source_segment_index_status"
                )
            )
        ),
        "source_waypoint_contiguous": (
            source_locator.get(
                "source_waypoint_contiguous"
            )
            is True
        ),
        "start_waypoint_index": (
            _integer(
                source_locator.get(
                    "start_waypoint_index"
                )
            )
        ),
        "end_waypoint_index": (
            _integer(
                source_locator.get(
                    "end_waypoint_index"
                )
            )
        ),
        "start_exercise_elapsed_ms": (
            _integer(
                source_locator.get(
                    "start_exercise_elapsed_ms"
                )
            )
        ),
        "end_exercise_elapsed_ms": (
            _integer(
                source_locator.get(
                    "end_exercise_elapsed_ms"
                )
            )
        ),
        "start_timestamp": (
            _parse_datetime(
                source_locator.get(
                    "start_timestamp"
                )
            )
        ),
        "midpoint_timestamp": (
            _parse_datetime(
                source_locator.get(
                    "midpoint_timestamp"
                )
            )
        ),
        "end_timestamp": (
            _parse_datetime(
                source_locator.get(
                    "end_timestamp"
                )
            )
        ),
        "start_latitude_deg": (
            _position_coordinate(
                start_position,
                "latitude_deg",
            )
        ),
        "start_longitude_deg": (
            _position_coordinate(
                start_position,
                "longitude_deg",
            )
        ),
        "end_latitude_deg": (
            _position_coordinate(
                end_position,
                "latitude_deg",
            )
        ),
        "end_longitude_deg": (
            _position_coordinate(
                end_position,
                "longitude_deg",
            )
        ),
        "surface_distance_m": (
            _finite_float(
                path.get(
                    "surface_distance_m"
                )
            )
        ),
        "movement_bearing_deg": (
            _finite_float(
                path.get(
                    "movement_bearing_deg"
                )
            )
        ),
        "position_status": (
            _string_or_none(
                path.get(
                    "position_status"
                )
            )
        ),
        "gps_ground_speed_mps": (
            _finite_float(
                motion.get(
                    "gps_ground_speed_mps"
                )
            )
        ),
        "ground_speed_change_rate_mps2": (
            _finite_float(
                motion.get(
                    "ground_speed_change_rate_mps2"
                )
            )
        ),
        "cumulative_trusted_surface_distance_m": (
            _finite_float(
                motion.get(
                    "cumulative_trusted_surface_distance_m"
                )
            )
        ),
        "weather_sample_key": (
            weather_sample_key
        ),
        "weather_match_status": (
            _string_or_none(
                weather.get(
                    "match_status"
                )
            )
        ),
        "weather_time_delta_seconds": (
            _finite_float(
                weather.get(
                    "absolute_time_delta_seconds"
                )
            )
        ),
        "weather_surface_distance_m": (
            _finite_float(
                weather.get(
                    "surface_distance_to_sample_m"
                )
            )
        ),
        "wind_status": (
            _string_or_none(
                wind.get(
                    "status"
                )
            )
        ),
        "headwind_component_mps": (
            _finite_float(
                wind.get(
                    "headwind_component_mps"
                )
            )
        ),
        "tailwind_component_mps": (
            _finite_float(
                wind.get(
                    "tailwind_component_mps"
                )
            )
        ),
        "crosswind_magnitude_mps": (
            _finite_float(
                wind.get(
                    "crosswind_magnitude_mps"
                )
            )
        ),
        "relative_air_velocity_along_course_mps": (
            _finite_float(
                wind.get(
                    "relative_air_velocity_along_course_mps"
                )
            )
        ),
        "relative_air_velocity_cross_course_mps": (
            _finite_float(
                wind.get(
                    "relative_air_velocity_cross_course_mps"
                )
            )
        ),
        "relative_air_speed_mps": (
            _finite_float(
                wind.get(
                    "relative_air_speed_mps"
                )
            )
        ),
        "water_level_measurement_key": (
            water_level_key
        ),
        "water_level_status": (
            water_level_status
        ),
        "water_level_time_delta_seconds": (
            water_level_delta
        ),
        "discharge_measurement_key": (
            discharge_key
        ),
        "discharge_status": (
            discharge_status
        ),
        "discharge_time_delta_seconds": (
            discharge_delta
        ),
        "water_temperature_measurement_key": (
            water_temperature_key
        ),
        "water_temperature_status": (
            water_temperature_status
        ),
        "water_temperature_time_delta_seconds": (
            water_temperature_delta
        ),
        "station_surface_distance_m": (
            _finite_float(
                hydrology.get(
                    "station_surface_distance_m"
                )
            )
        ),
        "current_speed_estimate_mps": (
            _finite_float(
                hydrology.get(
                    "current_speed_estimate_mps"
                )
            )
        ),
        "current_direction_deg": (
            _finite_float(
                hydrology.get(
                    "current_direction_deg"
                )
            )
        ),
        "waterbody_identity_status": (
            _string_or_none(
                waterbody.get(
                    "status"
                )
            )
        ),
        "waterbody_id": (
            _string_or_none(
                waterbody.get(
                    "waterbody_id"
                )
            )
        ),
        "river_reach_id": (
            _string_or_none(
                waterbody.get(
                    "river_reach_id"
                )
            )
        ),
        "flow_relation": (
            _string_or_none(
                waterbody.get(
                    "flow_relation"
                )
            )
        ),
        "route_corridor_id": (
            _string_or_none(
                waterbody.get(
                    "route_corridor_id"
                )
            )
        ),
        "route_choice_status": (
            _string_or_none(
                route_choice.get(
                    "status"
                )
            )
        ),
        "route_choice_intent": (
            _string_or_none(
                route_choice.get(
                    "route_choice_intent"
                )
            )
        ),
        "group_tactical_context": (
            _string_or_none(
                route_choice.get(
                    "group_tactical_context"
                )
            )
        ),
        "preferred_flow_line": (
            _string_or_none(
                route_choice.get(
                    "preferred_flow_line"
                )
            )
        ),
        "extra_data": {},
    }


def build_environment_persistence_plan(
    evidence_record: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        evidence_record,
        dict,
    ):
        raise ValueError(
            "evidence_record must be a dict"
        )

    schema_version = evidence_record.get(
        "schema_version"
    )

    if not isinstance(
        schema_version,
        str,
    ) or not schema_version:
        raise ValueError(
            "evidence_record is missing schema_version"
        )

    source_catalog = (
        evidence_record.get(
            "source_catalog"
        )
        if isinstance(
            evidence_record.get(
                "source_catalog"
            ),
            dict,
        )
        else {}
    )

    weather_rows_by_id = {}

    for sample in (
        source_catalog.get(
            "weather_samples"
        )
        or []
    ):
        if not isinstance(
            sample,
            dict,
        ):
            continue

        row = _weather_row(
            sample
        )

        weather_rows_by_id[
            row[
                "source_sample_id"
            ]
        ] = row

    hydrology_rows_by_id = {}

    for measurement in (
        source_catalog.get(
            "hydrology_measurements"
        )
        or []
    ):
        if not isinstance(
            measurement,
            dict,
        ):
            continue

        row = _hydrology_row(
            measurement
        )

        hydrology_rows_by_id[
            row[
                "source_measurement_id"
            ]
        ] = row

    routes = []

    for route_position, route in enumerate(
        evidence_record.get(
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

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

        segments = [
            _segment_row(
                segment,
                weather_ids=set(
                    weather_rows_by_id
                ),
                hydrology_ids=set(
                    hydrology_rows_by_id
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

        routes.append(
            {
                "route_key": (
                    _route_key(
                        route_index,
                        exercise_index,
                    )
                ),
                "route_index": (
                    route_index
                ),
                "exercise_index": (
                    exercise_index
                ),
                "segment_record_count": (
                    len(
                        segments
                    )
                ),
                "quality_provenance": (
                    route.get(
                        "quality_provenance"
                    )
                    if isinstance(
                        route.get(
                            "quality_provenance"
                        ),
                        dict,
                    )
                    else {}
                ),
                "time_context": (
                    route.get(
                        "time_context"
                    )
                    if isinstance(
                        route.get(
                            "time_context"
                        ),
                        dict,
                    )
                    else {}
                ),
                "route_semantics": (
                    route.get(
                        "route_semantics"
                    )
                    if isinstance(
                        route.get(
                            "route_semantics"
                        ),
                        dict,
                    )
                    else {}
                ),
                "segments": (
                    segments
                ),
            }
        )

    provider = _string_or_none(
        evidence_record.get(
            "provider"
        )
    )

    session_external_id = (
        _string_or_none(
            evidence_record.get(
                "session_external_id"
            )
        )
    )

    scope = (
        evidence_record.get(
            "scope"
        )
        if isinstance(
            evidence_record.get(
                "scope"
            ),
            dict,
        )
        else {}
    )

    weather_samples = list(
        weather_rows_by_id.values()
    )

    hydrology_measurements = list(
        hydrology_rows_by_id.values()
    )

    evidence_hash = _canonical_hash(
        _semantic_hash_payload(
            schema_version=schema_version,
            provider=provider,
            session_external_id=(
                session_external_id
            ),
            scope=scope,
            weather_samples=(
                weather_samples
            ),
            hydrology_measurements=(
                hydrology_measurements
            ),
            routes=routes,
        )
    )

    return {
        "evidence_hash": evidence_hash,
        "hash_semantics_version": (
            EVIDENCE_HASH_SEMANTICS_VERSION
        ),
        "schema_version": (
            schema_version
        ),
        "provider": provider,
        "session_external_id": (
            session_external_id
        ),
        "scope": scope,
        "source_summary": (
            _catalog_source_summary(
                source_catalog
            )
        ),
        "weather_samples": (
            weather_samples
        ),
        "hydrology_measurements": (
            hydrology_measurements
        ),
        "routes": routes,
    }


async def _count_rows_for_evidence_set(
    db: AsyncSession,
    model,
    evidence_set_id,
) -> int:
    value = await db.scalar(
        select(
            func.count()
        )
        .select_from(
            model
        )
        .where(
            model.evidence_set_id
            == evidence_set_id
        )
    )

    return int(
        value
        or 0
    )


async def _build_persistence_result(
    db: AsyncSession,
    *,
    status: str,
    evidence_set_id,
    evidence_hash: str,
    schema_version: str,
) -> dict[str, Any]:
    route_count = (
        await _count_rows_for_evidence_set(
            db,
            RouteEnvironmentRoute,
            evidence_set_id,
        )
    )

    weather_sample_count = (
        await _count_rows_for_evidence_set(
            db,
            RouteEnvironmentWeatherSample,
            evidence_set_id,
        )
    )

    hydrology_measurement_count = (
        await _count_rows_for_evidence_set(
            db,
            RouteEnvironmentHydrologyMeasurement,
            evidence_set_id,
        )
    )

    segment_count = (
        await _count_rows_for_evidence_set(
            db,
            RouteEnvironmentSegment,
            evidence_set_id,
        )
    )

    return {
        "status": status,
        "evidence_set_id": str(
            evidence_set_id
        ),
        "evidence_hash": evidence_hash,
        "schema_version": schema_version,
        "route_count": route_count,
        "weather_sample_count": (
            weather_sample_count
        ),
        "hydrology_measurement_count": (
            hydrology_measurement_count
        ),
        "segment_count": segment_count,
    }


async def persist_route_environment_evidence(
    db: AsyncSession,
    *,
    user: User,
    workout_session: WorkoutSession,
    evidence_record: dict[str, Any],
) -> dict[str, Any]:
    if workout_session.user_id != user.id:
        raise ValueError(
            "Workout session does not belong to user"
        )

    record_external_id = evidence_record.get(
        "session_external_id"
    )

    if (
        record_external_id is not None
        and str(
            record_external_id
        )
        != str(
            workout_session.external_id
        )
    ):
        raise ValueError(
            "Evidence session_external_id does not match workout session"
        )

    plan = build_environment_persistence_plan(
        evidence_record
    )

    existing = await db.scalar(
        select(
            RouteEnvironmentEvidenceSet
        ).where(
            RouteEnvironmentEvidenceSet.workout_session_id
            == workout_session.id,
            RouteEnvironmentEvidenceSet.evidence_hash
            == plan[
                "evidence_hash"
            ],
        )
    )

    now = datetime.now(
        timezone.utc
    )

    if existing is not None:
        if not existing.is_current:
            await db.execute(
                update(
                    RouteEnvironmentEvidenceSet
                )
                .where(
                    RouteEnvironmentEvidenceSet.workout_session_id
                    == workout_session.id,
                    RouteEnvironmentEvidenceSet.id
                    != existing.id,
                    RouteEnvironmentEvidenceSet.is_current
                    .is_(
                        True
                    ),
                )
                .values(
                    is_current=False,
                    replaced_at=now,
                )
            )

            existing.is_current = True
            existing.replaced_at = None

            await db.commit()

            status = "REACTIVATED_EXISTING"
        else:
            status = "ALREADY_CURRENT"

        return await _build_persistence_result(
            db,
            status=status,
            evidence_set_id=(
                existing.id
            ),
            evidence_hash=(
                existing.evidence_hash
            ),
            schema_version=(
                existing.schema_version
            ),
        )

    try:
        await db.execute(
            update(
                RouteEnvironmentEvidenceSet
            )
            .where(
                RouteEnvironmentEvidenceSet.workout_session_id
                == workout_session.id,
                RouteEnvironmentEvidenceSet.is_current
                .is_(
                    True
                ),
            )
            .values(
                is_current=False,
                replaced_at=now,
            )
        )

        evidence_set = (
            RouteEnvironmentEvidenceSet(
                user_id=user.id,
                workout_session_id=(
                    workout_session.id
                ),
                schema_version=(
                    plan[
                        "schema_version"
                    ]
                ),
                evidence_hash=(
                    plan[
                        "evidence_hash"
                    ]
                ),
                provider=(
                    plan[
                        "provider"
                    ]
                ),
                session_external_id=(
                    plan[
                        "session_external_id"
                    ]
                ),
                is_current=True,
                scope=(
                    plan[
                        "scope"
                    ]
                ),
                source_summary=(
                    plan[
                        "source_summary"
                    ]
                ),
            )
        )

        db.add(
            evidence_set
        )
        await db.flush()

        weather_by_source_id = {}

        for row in plan[
            "weather_samples"
        ]:
            weather = (
                RouteEnvironmentWeatherSample(
                    evidence_set_id=(
                        evidence_set.id
                    ),
                    **row,
                )
            )

            db.add(
                weather
            )
            weather_by_source_id[
                row[
                    "source_sample_id"
                ]
            ] = weather

        hydrology_by_source_id = {}

        for row in plan[
            "hydrology_measurements"
        ]:
            measurement = (
                RouteEnvironmentHydrologyMeasurement(
                    evidence_set_id=(
                        evidence_set.id
                    ),
                    **row,
                )
            )

            db.add(
                measurement
            )
            hydrology_by_source_id[
                row[
                    "source_measurement_id"
                ]
            ] = measurement

        await db.flush()

        segment_count = 0

        for route_plan in plan[
            "routes"
        ]:
            route = (
                RouteEnvironmentRoute(
                    evidence_set_id=(
                        evidence_set.id
                    ),
                    route_key=(
                        route_plan[
                            "route_key"
                        ]
                    ),
                    route_index=(
                        route_plan[
                            "route_index"
                        ]
                    ),
                    exercise_index=(
                        route_plan[
                            "exercise_index"
                        ]
                    ),
                    segment_record_count=(
                        route_plan[
                            "segment_record_count"
                        ]
                    ),
                    quality_provenance=(
                        route_plan[
                            "quality_provenance"
                        ]
                    ),
                    time_context=(
                        route_plan[
                            "time_context"
                        ]
                    ),
                    route_semantics=(
                        route_plan[
                            "route_semantics"
                        ]
                    ),
                )
            )

            db.add(
                route
            )
            await db.flush()

            for segment_plan in route_plan[
                "segments"
            ]:
                segment_data = dict(
                    segment_plan
                )

                weather_key = (
                    segment_data.pop(
                        "weather_sample_key"
                    )
                )

                water_level_key = (
                    segment_data.pop(
                        "water_level_measurement_key"
                    )
                )

                discharge_key = (
                    segment_data.pop(
                        "discharge_measurement_key"
                    )
                )

                water_temperature_key = (
                    segment_data.pop(
                        "water_temperature_measurement_key"
                    )
                )

                segment = (
                    RouteEnvironmentSegment(
                        evidence_set_id=(
                            evidence_set.id
                        ),
                        route_evidence_id=(
                            route.id
                        ),
                        weather_sample_id=(
                            weather_by_source_id[
                                weather_key
                            ].id
                            if weather_key
                            is not None
                            else None
                        ),
                        water_level_measurement_id=(
                            hydrology_by_source_id[
                                water_level_key
                            ].id
                            if water_level_key
                            is not None
                            else None
                        ),
                        discharge_measurement_id=(
                            hydrology_by_source_id[
                                discharge_key
                            ].id
                            if discharge_key
                            is not None
                            else None
                        ),
                        water_temperature_measurement_id=(
                            hydrology_by_source_id[
                                water_temperature_key
                            ].id
                            if water_temperature_key
                            is not None
                            else None
                        ),
                        **segment_data,
                    )
                )

                db.add(
                    segment
                )
                segment_count += 1

        await db.commit()

    except Exception:
        await db.rollback()
        raise

    return await _build_persistence_result(
        db,
        status="CREATED",
        evidence_set_id=(
            evidence_set.id
        ),
        evidence_hash=(
            evidence_set.evidence_hash
        ),
        schema_version=(
            evidence_set.schema_version
        ),
    )
