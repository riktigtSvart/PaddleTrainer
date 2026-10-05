from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from app.integrations.eea_wise.client import (
    EEAWiseClient,
)


SOURCE_PROVIDER = "EEA_WISE_WFD"
SOURCE_PRODUCT = (
    "WFD2022_SURFACE_WATER_BODY_CENTRELINE"
)
SOURCE_TYPE = (
    "REPORTED_WFD_SURFACE_WATER_BODY_CENTRELINE"
)

SPATIAL_MATCH_METHOD = (
    "SEGMENT_MIDPOINT_TO_CENTRELINE_"
    "LOCAL_TANGENT_PLANE"
)

CANDIDATE_SCHEMA_VERSION = "0.2"

DEFAULT_SEARCH_RADIUS_M = 300.0

EARTH_MEAN_RADIUS_M = 6_371_008.8


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

    numeric = float(
        value
    )

    if not math.isfinite(
        numeric
    ):
        return None

    return numeric


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


def _string(
    value: Any,
) -> str | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    return text or None


def _coordinate_from_position(
    position: Any,
) -> tuple[
    float,
    float,
] | None:
    if not isinstance(
        position,
        dict,
    ):
        return None

    latitude = _finite_number(
        position.get(
            "latitude_deg"
        )
    )
    longitude = _finite_number(
        position.get(
            "longitude_deg"
        )
    )

    if (
        latitude is None
        or longitude is None
        or not -90.0
        <= latitude
        <= 90.0
        or not -180.0
        <= longitude
        <= 180.0
    ):
        return None

    return (
        latitude,
        longitude,
    )


def _segment_midpoint(
    segment: dict[str, Any],
) -> tuple[
    float,
    float,
] | None:
    start = _coordinate_from_position(
        segment.get(
            "start_position"
        )
    )
    end = _coordinate_from_position(
        segment.get(
            "end_position"
        )
    )

    if (
        start is None
        or end is None
    ):
        return None

    return (
        (
            start[0]
            + end[0]
        )
        / 2.0,
        (
            start[1]
            + end[1]
        )
        / 2.0,
    )


def _expanded_envelope(
    coordinates: list[
        tuple[
            float,
            float,
        ]
    ],
    *,
    padding_m: float,
) -> tuple[
    float,
    float,
    float,
    float,
] | None:
    if not coordinates:
        return None

    latitudes = [
        item[0]
        for item in coordinates
    ]
    longitudes = [
        item[1]
        for item in coordinates
    ]

    mean_latitude = sum(
        latitudes
    ) / len(
        latitudes
    )

    lat_padding_deg = (
        padding_m
        / 111_320.0
    )

    cosine = abs(
        math.cos(
            math.radians(
                mean_latitude
            )
        )
    )

    if cosine < 1e-6:
        cosine = 1e-6

    lon_padding_deg = (
        padding_m
        / (
            111_320.0
            * cosine
        )
    )

    return (
        min(
            longitudes
        )
        - lon_padding_deg,
        min(
            latitudes
        )
        - lat_padding_deg,
        max(
            longitudes
        )
        + lon_padding_deg,
        max(
            latitudes
        )
        + lat_padding_deg,
    )


def _paths_from_feature(
    feature: dict[str, Any],
) -> list[
    list[
        tuple[
            float,
            float,
        ]
    ]
]:
    geometry = feature.get(
        "geometry"
    )

    if not isinstance(
        geometry,
        dict,
    ):
        return []

    result = []

    for raw_path in (
        geometry.get(
            "paths"
        )
        or []
    ):
        if not isinstance(
            raw_path,
            list,
        ):
            continue

        path = []

        for raw_point in raw_path:
            if (
                not isinstance(
                    raw_point,
                    list,
                )
                or len(
                    raw_point
                )
                < 2
            ):
                continue

            longitude = (
                _finite_number(
                    raw_point[0]
                )
            )
            latitude = (
                _finite_number(
                    raw_point[1]
                )
            )

            if (
                latitude is None
                or longitude is None
            ):
                continue

            path.append(
                (
                    latitude,
                    longitude,
                )
            )

        if len(
            path
        ) >= 2:
            result.append(
                path
            )

    return result


def _to_local_xy_m(
    coordinate: tuple[
        float,
        float,
    ],
    *,
    origin: tuple[
        float,
        float,
    ],
) -> tuple[
    float,
    float,
]:
    latitude, longitude = (
        coordinate
    )
    origin_latitude, origin_longitude = (
        origin
    )

    latitude_rad = (
        math.radians(
            latitude
        )
    )
    origin_latitude_rad = (
        math.radians(
            origin_latitude
        )
    )

    x = (
        math.radians(
            longitude
            - origin_longitude
        )
        * EARTH_MEAN_RADIUS_M
        * math.cos(
            (
                latitude_rad
                + origin_latitude_rad
            )
            / 2.0
        )
    )

    y = (
        math.radians(
            latitude
            - origin_latitude
        )
        * EARTH_MEAN_RADIUS_M
    )

    return (
        x,
        y,
    )


def _distance_origin_to_segment_m(
    start_xy: tuple[
        float,
        float,
    ],
    end_xy: tuple[
        float,
        float,
    ],
) -> float:
    x1, y1 = start_xy
    x2, y2 = end_xy

    dx = x2 - x1
    dy = y2 - y1

    denominator = (
        dx * dx
        + dy * dy
    )

    if denominator <= 0.0:
        return math.hypot(
            x1,
            y1,
        )

    t = -(
        x1 * dx
        + y1 * dy
    ) / denominator

    t = max(
        0.0,
        min(
            1.0,
            t,
        ),
    )

    nearest_x = (
        x1
        + t * dx
    )
    nearest_y = (
        y1
        + t * dy
    )

    return math.hypot(
        nearest_x,
        nearest_y,
    )


def _distance_to_paths_m(
    coordinate: tuple[
        float,
        float,
    ],
    paths: list[
        list[
            tuple[
                float,
                float,
            ]
        ]
    ],
) -> float | None:
    minimum = None

    for path in paths:
        for index in range(
            len(
                path
            )
            - 1
        ):
            start_xy = (
                _to_local_xy_m(
                    path[index],
                    origin=(
                        coordinate
                    ),
                )
            )
            end_xy = (
                _to_local_xy_m(
                    path[
                        index
                        + 1
                    ],
                    origin=(
                        coordinate
                    ),
                )
            )

            distance = (
                _distance_origin_to_segment_m(
                    start_xy,
                    end_xy,
                )
            )

            if (
                minimum is None
                or distance
                < minimum
            ):
                minimum = (
                    distance
                )

    return minimum


def _waterbody_type_from_attributes(
    attributes: dict[
        str,
        Any,
    ],
) -> str:
    values = [
        _string(
            attributes.get(
                "specialisedZoneType"
            )
        ),
        _string(
            attributes.get(
                "geometry"
            )
        ),
    ]

    text = " ".join(
        item.lower()
        for item in values
        if item is not None
    )

    if "river" in text:
        return "RIVER"

    if "lake" in text:
        return "LAKE"

    if "reservoir" in text:
        return "RESERVOIR"

    if "canal" in text:
        return "CANAL"

    if "transitional" in text:
        return "TRANSITIONAL"

    if "coastal" in text:
        return "COASTAL"

    return "UNKNOWN"


def _source_feature_id(
    attributes: dict[
        str,
        Any,
    ],
) -> str | None:
    namespace = _string(
        attributes.get(
            "hydroIdNamespace"
        )
    )
    local_id = _string(
        attributes.get(
            "hydroIdLocalId"
        )
    )

    if (
        namespace is not None
        and local_id is not None
    ):
        return (
            f"{namespace}:{local_id}"
        )

    provider_id = _integer(
        attributes.get(
            "id"
        )
    )

    if provider_id is not None:
        return (
            f"ID:{provider_id}"
        )

    object_id = _integer(
        attributes.get(
            "OBJECTID"
        )
    )

    if object_id is not None:
        return (
            f"OBJECTID:{object_id}"
        )

    thematic_id = _string(
        attributes.get(
            "thematicIdIdentifier"
        )
    )

    if thematic_id is not None:
        return (
            f"WATERBODY:{thematic_id}"
        )

    return None


def _waterbody_id(
    attributes: dict[
        str,
        Any,
    ],
) -> str | None:
    thematic_id = _string(
        attributes.get(
            "thematicIdIdentifier"
        )
    )

    if thematic_id is not None:
        return thematic_id

    namespace = _string(
        attributes.get(
            "hydroIdNamespace"
        )
    )
    local_id = _string(
        attributes.get(
            "hydroIdLocalId"
        )
    )

    if (
        namespace is not None
        and local_id is not None
    ):
        return (
            f"{namespace}:{local_id}"
        )

    return None


def _normalize_feature(
    feature: dict[str, Any],
) -> dict[str, Any] | None:
    attributes = feature.get(
        "attributes"
    )

    if not isinstance(
        attributes,
        dict,
    ):
        return None

    feature_id = (
        _source_feature_id(
            attributes
        )
    )
    waterbody_id = (
        _waterbody_id(
            attributes
        )
    )
    paths = _paths_from_feature(
        feature
    )

    if (
        feature_id is None
        or waterbody_id is None
        or not paths
    ):
        return None

    return {
        "source_feature_id": (
            feature_id
        ),
        "waterbody_id": (
            waterbody_id
        ),
        "source_feature_name": (
            _string(
                attributes.get(
                    "geographicalNameText"
                )
            )
        ),
        "waterbody_name": None,
        "waterbody_type": (
            _waterbody_type_from_attributes(
                attributes
            )
        ),
        "river_reach_id": None,
        "paths": paths,
        "source_properties": {
            key: deepcopy(
                attributes.get(
                    key
                )
            )
            for key in [
                "OBJECTID",
                "cYear",
                "continua",
                "geometry",
                "statusDate",
                "qcCheck",
                "countryCode",
                "thematicIdIdentifier",
                "thematicIdIdentifierScheme",
                "hydroIdLocalId",
                "hydroIdNamespace",
                "geographicalNameText",
                "geographicalNameLanguage",
                "specialisedZoneType",
                "id",
            ]
        },
    }


def normalize_eea_wise_features(
    payload: dict[
        str,
        Any,
    ],
) -> list[
    dict[str, Any]
]:
    result = []

    for feature in (
        payload.get(
            "features"
        )
        or []
    ):
        if not isinstance(
            feature,
            dict,
        ):
            continue

        normalized = (
            _normalize_feature(
                feature
            )
        )

        if normalized is not None:
            result.append(
                normalized
            )

    return result


def build_eea_wise_candidate_evidence_from_features(
    route_environment_context_input: dict[
        str,
        Any,
    ],
    *,
    normalized_features: list[
        dict[str, Any]
    ],
    search_radius_m: float = (
        DEFAULT_SEARCH_RADIUS_M
    ),
) -> dict[str, Any]:
    segment_candidates = []

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

        exercise_index = _integer(
            route.get(
                "exercise_index"
            )
        )

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

            midpoint = (
                _segment_midpoint(
                    segment
                )
            )

            candidates = []

            if midpoint is not None:
                for feature in (
                    normalized_features
                ):
                    distance_m = (
                        _distance_to_paths_m(
                            midpoint,
                            feature.get(
                                "paths"
                            )
                            or [],
                        )
                    )

                    if (
                        distance_m
                        is None
                        or distance_m
                        > search_radius_m
                    ):
                        continue

                    candidates.append(
                        {
                            "source_feature_id": (
                                feature.get(
                                    "source_feature_id"
                                )
                            ),
                            "waterbody_id": (
                                feature.get(
                                    "waterbody_id"
                                )
                            ),
                            "source_feature_name": (
                                feature.get(
                                    "source_feature_name"
                                )
                            ),
                            "waterbody_name": (
                                feature.get(
                                    "waterbody_name"
                                )
                            ),
                            "waterbody_type": (
                                feature.get(
                                    "waterbody_type"
                                )
                            ),
                            "river_reach_id": None,
                            "geometry_relation": (
                                "SEGMENT_MIDPOINT_WITHIN_"
                                "SEARCH_RADIUS_OF_REPORTED_"
                                "WATERBODY_CENTRELINE"
                            ),
                            "match_distance_m": (
                                distance_m
                            ),
                            "flow_direction_deg": None,
                            "source_reference": {
                                "provider": (
                                    SOURCE_PROVIDER
                                ),
                                "product": (
                                    SOURCE_PRODUCT
                                ),
                                "feature_id": (
                                    feature.get(
                                        "source_feature_id"
                                    )
                                ),
                            },
                            "source_properties": (
                                deepcopy(
                                    feature.get(
                                        "source_properties"
                                    )
                                    or {}
                                )
                            ),
                        }
                    )

            candidates.sort(
                key=lambda item: (
                    item.get(
                        "match_distance_m"
                    )
                    if item.get(
                        "match_distance_m"
                    )
                    is not None
                    else float(
                        "inf"
                    ),
                    str(
                        item.get(
                            "waterbody_id"
                        )
                        or ""
                    ),
                )
            )

            segment_candidates.append(
                {
                    "route_index": (
                        route_index
                    ),
                    "exercise_index": (
                        exercise_index
                    ),
                    "order_index": (
                        _integer(
                            segment.get(
                                "order_index"
                            )
                        )
                    ),
                    "candidates": (
                        candidates
                    ),
                }
            )

    return {
        "schema_version": (
            CANDIDATE_SCHEMA_VERSION
        ),
        "source_provider": (
            SOURCE_PROVIDER
        ),
        "source_product": (
            SOURCE_PRODUCT
        ),
        "source_type": (
            SOURCE_TYPE
        ),
        "spatial_match_method": (
            SPATIAL_MATCH_METHOD
        ),
        "search_radius_m": (
            search_radius_m
        ),
        "waterbody_id_semantics": (
            "EU_SURFACE_WATER_BODY_CODE_WHEN_REPORTED"
        ),
        "source_feature_id_semantics": (
            "REPORTED_HYDRO_FEATURE_ID_WHEN_AVAILABLE"
        ),
        "source_feature_name_semantics": (
            "REPORTED_GEOGRAPHICAL_NAME_OF_CENTRELINE_FEATURE"
        ),
        "river_reach_semantics": (
            "NOT_PROVIDED_BY_WFD_WATERBODY_CENTRELINE"
        ),
        "estimates_local_current_velocity": (
            False
        ),
        "derives_flow_direction_from_route_bearing": (
            False
        ),
        "segment_candidates": (
            segment_candidates
        ),
    }


async def build_eea_wise_waterbody_candidate_evidence(
    route_environment_context_input: dict[
        str,
        Any,
    ],
    *,
    client: EEAWiseClient | None = None,
    search_radius_m: float = (
        DEFAULT_SEARCH_RADIUS_M
    ),
) -> dict[str, Any]:
    if (
        not math.isfinite(
            search_radius_m
        )
        or search_radius_m
        <= 0.0
    ):
        raise ValueError(
            "search_radius_m must be "
            "a positive finite number"
        )

    resolved_client = (
        client
        if client is not None
        else EEAWiseClient()
    )

    all_features = {}

    for route in (
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

        coordinates = []

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

            for key in [
                "start_position",
                "end_position",
            ]:
                coordinate = (
                    _coordinate_from_position(
                        segment.get(
                            key
                        )
                    )
                )

                if coordinate is not None:
                    coordinates.append(
                        coordinate
                    )

        envelope = _expanded_envelope(
            coordinates,
            padding_m=(
                search_radius_m
            ),
        )

        if envelope is None:
            continue

        (
            xmin_lon,
            ymin_lat,
            xmax_lon,
            ymax_lat,
        ) = envelope

        payload = (
            await resolved_client
            .query_surface_waterbody_centrelines(
                xmin_lon=xmin_lon,
                ymin_lat=ymin_lat,
                xmax_lon=xmax_lon,
                ymax_lat=ymax_lat,
            )
        )

        for feature in (
            normalize_eea_wise_features(
                payload
            )
        ):
            key = (
                feature.get(
                    "source_feature_id"
                ),
                feature.get(
                    "waterbody_id"
                ),
            )

            all_features[
                key
            ] = feature

    normalized_features = [
        all_features[key]
        for key in sorted(
            all_features,
            key=lambda item: (
                str(
                    item[0]
                    or ""
                ),
                str(
                    item[1]
                    or ""
                ),
            ),
        )
    ]

    result = (
        build_eea_wise_candidate_evidence_from_features(
            route_environment_context_input,
            normalized_features=(
                normalized_features
            ),
            search_radius_m=(
                search_radius_m
            ),
        )
    )

    result[
        "source_feature_count"
    ] = len(
        normalized_features
    )

    return result
