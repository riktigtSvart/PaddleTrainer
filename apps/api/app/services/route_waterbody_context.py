from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "0.3"

SCOPE_ROUTE_WATERBODY_CONTEXT = (
    "ROUTE_WATERBODY_CONTEXT"
)

STATUS_RESOLVED = "RESOLVED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_UNRESOLVED = "UNRESOLVED"

SEGMENT_MATCH_RESOLVED = "RESOLVED"
SEGMENT_MATCH_AMBIGUOUS = "AMBIGUOUS"
SEGMENT_MATCH_UNRESOLVED = "UNRESOLVED"
SEGMENT_MATCH_POSITION_UNAVAILABLE = (
    "POSITION_UNAVAILABLE"
)
SEGMENT_MATCH_WATERBODY_RESOLVED_FEATURE_AMBIGUOUS = (
    "WATERBODY_RESOLVED_FEATURE_AMBIGUOUS"
)

WATERBODY_TYPE_RIVER = "RIVER"
WATERBODY_TYPE_LAKE = "LAKE"
WATERBODY_TYPE_RESERVOIR = "RESERVOIR"
WATERBODY_TYPE_CANAL = "CANAL"
WATERBODY_TYPE_TRANSITIONAL = "TRANSITIONAL"
WATERBODY_TYPE_COASTAL = "COASTAL"
WATERBODY_TYPE_OTHER = "OTHER"
WATERBODY_TYPE_UNKNOWN = "UNKNOWN"

SUPPORTED_WATERBODY_TYPES = {
    WATERBODY_TYPE_RIVER,
    WATERBODY_TYPE_LAKE,
    WATERBODY_TYPE_RESERVOIR,
    WATERBODY_TYPE_CANAL,
    WATERBODY_TYPE_TRANSITIONAL,
    WATERBODY_TYPE_COASTAL,
    WATERBODY_TYPE_OTHER,
    WATERBODY_TYPE_UNKNOWN,
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


def _string_or_none(
    value: Any,
) -> str | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    return text or None


def _waterbody_type(
    value: Any,
) -> str:
    normalized = (
        _string_or_none(
            value
        )
        or WATERBODY_TYPE_UNKNOWN
    ).upper()

    if normalized not in (
        SUPPORTED_WATERBODY_TYPES
    ):
        return WATERBODY_TYPE_OTHER

    return normalized


def _segment_key(
    *,
    route_index: int,
    exercise_index: int | None,
    order_index: int | None,
) -> tuple[
    int,
    int | None,
    int | None,
]:
    return (
        route_index,
        exercise_index,
        order_index,
    )


def _candidate_identity_key(
    candidate: dict[str, Any],
) -> tuple[
    str | None,
    str | None,
    str | None,
    str | None,
]:
    return (
        _string_or_none(
            candidate.get(
                "source_provider"
            )
        ),
        _string_or_none(
            candidate.get(
                "source_product"
            )
        ),
        _string_or_none(
            candidate.get(
                "source_feature_id"
            )
        ),
        _string_or_none(
            candidate.get(
                "waterbody_id"
            )
        ),
    )


def _waterbody_identity_key(
    candidate: dict[str, Any],
) -> tuple[
    str | None,
    str | None,
    str | None,
]:
    return (
        _string_or_none(
            candidate.get(
                "source_provider"
            )
        ),
        _string_or_none(
            candidate.get(
                "source_product"
            )
        ),
        _string_or_none(
            candidate.get(
                "waterbody_id"
            )
        ),
    )


def _normalized_candidate(
    candidate: dict[str, Any],
    *,
    source_provider: str | None,
    source_product: str | None,
) -> dict[str, Any] | None:
    if not isinstance(
        candidate,
        dict,
    ):
        return None

    resolved_provider = (
        _string_or_none(
            candidate.get(
                "source_provider"
            )
        )
        or source_provider
    )

    resolved_product = (
        _string_or_none(
            candidate.get(
                "source_product"
            )
        )
        or source_product
    )

    source_feature_id = (
        _string_or_none(
            candidate.get(
                "source_feature_id"
            )
        )
    )

    waterbody_id = (
        _string_or_none(
            candidate.get(
                "waterbody_id"
            )
        )
    )

    if (
        source_feature_id is None
        and waterbody_id is None
    ):
        return None

    return {
        "source_provider": (
            resolved_provider
        ),
        "source_product": (
            resolved_product
        ),
        "source_feature_id": (
            source_feature_id
        ),
        "source_feature_name": (
            _string_or_none(
                candidate.get(
                    "source_feature_name"
                )
            )
        ),
        "waterbody_id": (
            waterbody_id
        ),
        "waterbody_name": (
            _string_or_none(
                candidate.get(
                    "waterbody_name"
                )
            )
        ),
        "waterbody_type": (
            _waterbody_type(
                candidate.get(
                    "waterbody_type"
                )
            )
        ),
        "river_reach_id": (
            _string_or_none(
                candidate.get(
                    "river_reach_id"
                )
            )
        ),
        "geometry_relation": (
            _string_or_none(
                candidate.get(
                    "geometry_relation"
                )
            )
        ),
        "match_distance_m": (
            _finite_number(
                candidate.get(
                    "match_distance_m"
                )
            )
        ),
        "flow_direction_deg": (
            _finite_number(
                candidate.get(
                    "flow_direction_deg"
                )
            )
        ),
        "source_reference": (
            deepcopy(
                candidate.get(
                    "source_reference"
                )
            )
        ),
        "source_properties": (
            deepcopy(
                candidate.get(
                    "source_properties"
                )
            )
            if isinstance(
                candidate.get(
                    "source_properties"
                ),
                dict,
            )
            else {}
        ),
    }


def _candidate_lookup(
    candidate_evidence: dict[
        str,
        Any,
    ] | None,
) -> dict[
    tuple[
        int,
        int | None,
        int | None,
    ],
    list[dict[str, Any]],
]:
    result: dict[
        tuple[
            int,
            int | None,
            int | None,
        ],
        list[dict[str, Any]],
    ] = {}

    if not isinstance(
        candidate_evidence,
        dict,
    ):
        return result

    source_provider = (
        _string_or_none(
            candidate_evidence.get(
                "source_provider"
            )
        )
    )
    source_product = (
        _string_or_none(
            candidate_evidence.get(
                "source_product"
            )
        )
    )

    for item in (
        candidate_evidence.get(
            "segment_candidates"
        )
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        route_index = _integer(
            item.get(
                "route_index"
            )
        )
        order_index = _integer(
            item.get(
                "order_index"
            )
        )

        if route_index is None:
            continue

        exercise_index = _integer(
            item.get(
                "exercise_index"
            )
        )

        key = _segment_key(
            route_index=route_index,
            exercise_index=exercise_index,
            order_index=order_index,
        )

        unique = {}

        for raw_candidate in (
            item.get(
                "candidates"
            )
            or []
        ):
            normalized = (
                _normalized_candidate(
                    raw_candidate,
                    source_provider=(
                        source_provider
                    ),
                    source_product=(
                        source_product
                    ),
                )
            )

            if normalized is None:
                continue

            unique[
                _candidate_identity_key(
                    normalized
                )
            ] = normalized

        result[key] = [
            unique[
                identity_key
            ]
            for identity_key in sorted(
                unique,
                key=lambda item: tuple(
                    part or ""
                    for part in item
                ),
            )
        ]

    return result


def _resolved_waterbody_identity(
    candidates: list[
        dict[str, Any]
    ],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    keys = {
        _waterbody_identity_key(
            candidate
        )
        for candidate in candidates
        if _string_or_none(
            candidate.get(
                "waterbody_id"
            )
        )
        is not None
    }

    if len(keys) != 1:
        return None

    if any(
        _string_or_none(
            candidate.get(
                "waterbody_id"
            )
        )
        is None
        for candidate in candidates
    ):
        return None

    key = next(
        iter(
            keys
        )
    )

    names = sorted(
        {
            name
            for candidate in candidates
            for name in [
                _string_or_none(
                    candidate.get(
                        "waterbody_name"
                    )
                )
            ]
            if name is not None
        }
    )

    types = sorted(
        {
            _waterbody_type(
                candidate.get(
                    "waterbody_type"
                )
            )
            for candidate in candidates
        }
    )

    source_feature_ids = sorted(
        {
            feature_id
            for candidate in candidates
            for feature_id in [
                _string_or_none(
                    candidate.get(
                        "source_feature_id"
                    )
                )
            ]
            if feature_id is not None
        }
    )

    source_feature_names = sorted(
        {
            feature_name
            for candidate in candidates
            for feature_name in [
                _string_or_none(
                    candidate.get(
                        "source_feature_name"
                    )
                )
            ]
            if feature_name is not None
        }
    )

    river_reach_ids = sorted(
        {
            reach_id
            for candidate in candidates
            for reach_id in [
                _string_or_none(
                    candidate.get(
                        "river_reach_id"
                    )
                )
            ]
            if reach_id is not None
        }
    )

    return {
        "source_provider": key[0],
        "source_product": key[1],
        "waterbody_id": key[2],
        "waterbody_name": (
            names[0]
            if len(names) == 1
            else None
        ),
        "waterbody_type": (
            types[0]
            if len(types) == 1
            else WATERBODY_TYPE_UNKNOWN
        ),
        "source_feature_count": len(
            source_feature_ids
        ),
        "source_feature_ids": (
            source_feature_ids
        ),
        "source_feature_names": (
            source_feature_names
        ),
        "river_reach_ids": (
            river_reach_ids
        ),
    }


def _merge_waterbody_identity(
    target: dict[str, Any],
    incoming: dict[str, Any],
) -> None:
    for plural_key in (
        "source_feature_ids",
        "source_feature_names",
        "river_reach_ids",
    ):
        target[
            plural_key
        ] = sorted(
            set(
                target.get(
                    plural_key
                )
                or []
            )
            | set(
                incoming.get(
                    plural_key
                )
                or []
            )
        )

    target[
        "source_feature_count"
    ] = len(
        target.get(
            "source_feature_ids"
        )
        or []
    )

    if (
        target.get(
            "waterbody_name"
        )
        != incoming.get(
            "waterbody_name"
        )
    ):
        target[
            "waterbody_name"
        ] = None

    if (
        target.get(
            "waterbody_type"
        )
        != incoming.get(
            "waterbody_type"
        )
    ):
        target[
            "waterbody_type"
        ] = WATERBODY_TYPE_UNKNOWN


def _status_from_counts(
    *,
    total: int,
    resolved: int,
    ambiguous: int,
) -> str:
    if (
        total > 0
        and resolved == total
    ):
        return STATUS_RESOLVED

    if ambiguous > 0:
        return STATUS_AMBIGUOUS

    return STATUS_UNRESOLVED


def build_route_waterbody_candidate_evidence_summary(
    candidate_evidence: dict[
        str,
        Any,
    ] | None,
) -> dict[str, Any] | None:
    if not isinstance(
        candidate_evidence,
        dict,
    ):
        return None

    source_provider = (
        _string_or_none(
            candidate_evidence.get(
                "source_provider"
            )
        )
    )
    source_product = (
        _string_or_none(
            candidate_evidence.get(
                "source_product"
            )
        )
    )

    feature_stats = {}
    segment_record_count = 0
    segments_with_candidates = 0
    candidate_reference_count = 0
    candidate_count_histogram: dict[
        str,
        int,
    ] = {}

    for item in (
        candidate_evidence.get(
            "segment_candidates"
        )
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        segment_record_count += 1
        normalized_candidates = []

        for raw_candidate in (
            item.get(
                "candidates"
            )
            or []
        ):
            candidate = (
                _normalized_candidate(
                    raw_candidate,
                    source_provider=(
                        source_provider
                    ),
                    source_product=(
                        source_product
                    ),
                )
            )

            if candidate is not None:
                normalized_candidates.append(
                    candidate
                )

        unique = {
            _candidate_identity_key(
                candidate
            ): candidate
            for candidate in normalized_candidates
        }

        candidates = list(
            unique.values()
        )

        candidate_count = len(
            candidates
        )

        candidate_count_histogram[
            str(
                candidate_count
            )
        ] = (
            candidate_count_histogram.get(
                str(
                    candidate_count
                ),
                0,
            )
            + 1
        )

        if candidates:
            segments_with_candidates += 1

        candidate_reference_count += (
            candidate_count
        )

        for candidate in candidates:
            key = (
                _candidate_identity_key(
                    candidate
                )
            )

            stats = feature_stats.get(
                key
            )

            if stats is None:
                stats = {
                    "source_provider": (
                        candidate.get(
                            "source_provider"
                        )
                    ),
                    "source_product": (
                        candidate.get(
                            "source_product"
                        )
                    ),
                    "source_feature_id": (
                        candidate.get(
                            "source_feature_id"
                        )
                    ),
                    "source_feature_name": (
                        candidate.get(
                            "source_feature_name"
                        )
                    ),
                    "waterbody_id": (
                        candidate.get(
                            "waterbody_id"
                        )
                    ),
                    "waterbody_name": (
                        candidate.get(
                            "waterbody_name"
                        )
                    ),
                    "waterbody_type": (
                        candidate.get(
                            "waterbody_type"
                        )
                    ),
                    "segment_candidate_count": 0,
                    "minimum_match_distance_m": None,
                    "maximum_match_distance_m": None,
                }
                feature_stats[
                    key
                ] = stats

            stats[
                "segment_candidate_count"
            ] += 1

            distance = (
                _finite_number(
                    candidate.get(
                        "match_distance_m"
                    )
                )
            )

            if distance is not None:
                current_min = stats[
                    "minimum_match_distance_m"
                ]
                current_max = stats[
                    "maximum_match_distance_m"
                ]

                stats[
                    "minimum_match_distance_m"
                ] = (
                    distance
                    if current_min is None
                    else min(
                        current_min,
                        distance,
                    )
                )
                stats[
                    "maximum_match_distance_m"
                ] = (
                    distance
                    if current_max is None
                    else max(
                        current_max,
                        distance,
                    )
                )

    source_features = [
        feature_stats[key]
        for key in sorted(
            feature_stats,
            key=lambda item: tuple(
                part or ""
                for part in item
            ),
        )
    ]

    waterbody_keys = {
        (
            item.get(
                "source_provider"
            ),
            item.get(
                "source_product"
            ),
            item.get(
                "waterbody_id"
            ),
        )
        for item in source_features
        if item.get(
            "waterbody_id"
        )
        is not None
    }

    return {
        "schema_version": (
            candidate_evidence.get(
                "schema_version"
            )
        ),
        "source_provider": (
            source_provider
        ),
        "source_product": (
            source_product
        ),
        "source_type": (
            _string_or_none(
                candidate_evidence.get(
                    "source_type"
                )
            )
        ),
        "spatial_match_method": (
            candidate_evidence.get(
                "spatial_match_method"
            )
        ),
        "search_radius_m": (
            candidate_evidence.get(
                "search_radius_m"
            )
        ),
        "source_feature_count": len(
            source_features
        ),
        "waterbody_count": len(
            waterbody_keys
        ),
        "segment_candidate_record_count": (
            segment_record_count
        ),
        "segments_with_candidates": (
            segments_with_candidates
        ),
        "segments_without_candidates": (
            segment_record_count
            - segments_with_candidates
        ),
        "candidate_reference_count": (
            candidate_reference_count
        ),
        "candidate_count_histogram": (
            candidate_count_histogram
        ),
        "source_features": (
            source_features
        ),
    }


def build_route_waterbody_context(
    route_environment_context_input: dict[
        str,
        Any,
    ],
    *,
    waterbody_candidate_evidence: dict[
        str,
        Any,
    ] | None = None,
) -> dict[str, Any]:
    """Resolve route segments to provider-independent waterbody identities.

    Waterbody identity and concrete source-feature identity are separate:
    multiple source features can still resolve to one waterbody when they
    all carry the same provider waterbody identifier.

    The resolver deliberately does not:
    - select the nearest feature when different waterbodies are candidates;
    - derive flow direction from route bearing;
    - estimate local current velocity.
    """
    candidate_lookup = (
        _candidate_lookup(
            waterbody_candidate_evidence
        )
    )

    route_results = []
    global_resolved_features = {}
    global_resolved_waterbodies = {}

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

        segment_results = []
        route_resolved_features = {}
        route_resolved_waterbodies = {}

        feature_resolved_segment_count = 0
        feature_ambiguous_segment_count = 0
        feature_unresolved_segment_count = 0

        waterbody_resolved_segment_count = 0
        waterbody_ambiguous_segment_count = 0
        waterbody_unresolved_segment_count = 0

        position_unavailable_segment_count = 0

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

            order_index = _integer(
                segment.get(
                    "order_index"
                )
            )

            position_available = (
                segment.get(
                    "position_status"
                )
                == "ENDPOINT_POSITIONS_AVAILABLE"
            )

            candidates = (
                candidate_lookup.get(
                    _segment_key(
                        route_index=(
                            route_index
                        ),
                        exercise_index=(
                            exercise_index
                        ),
                        order_index=(
                            order_index
                        ),
                    ),
                    [],
                )
            )

            resolved_candidate = None
            resolved_waterbody = None

            if not position_available:
                match_status = (
                    SEGMENT_MATCH_POSITION_UNAVAILABLE
                )
                source_feature_match_status = (
                    SEGMENT_MATCH_POSITION_UNAVAILABLE
                )
                waterbody_match_status = (
                    SEGMENT_MATCH_POSITION_UNAVAILABLE
                )
                position_unavailable_segment_count += 1

            else:
                if len(
                    candidates
                ) == 1:
                    source_feature_match_status = (
                        SEGMENT_MATCH_RESOLVED
                    )
                    resolved_candidate = (
                        candidates[0]
                    )
                    feature_resolved_segment_count += 1

                elif len(
                    candidates
                ) > 1:
                    source_feature_match_status = (
                        SEGMENT_MATCH_AMBIGUOUS
                    )
                    feature_ambiguous_segment_count += 1

                else:
                    source_feature_match_status = (
                        SEGMENT_MATCH_UNRESOLVED
                    )
                    feature_unresolved_segment_count += 1

                resolved_waterbody = (
                    _resolved_waterbody_identity(
                        candidates
                    )
                )

                if resolved_waterbody is not None:
                    waterbody_match_status = (
                        SEGMENT_MATCH_RESOLVED
                    )
                    waterbody_resolved_segment_count += 1

                elif candidates:
                    waterbody_match_status = (
                        SEGMENT_MATCH_AMBIGUOUS
                    )
                    waterbody_ambiguous_segment_count += 1

                else:
                    waterbody_match_status = (
                        SEGMENT_MATCH_UNRESOLVED
                    )
                    waterbody_unresolved_segment_count += 1

                if (
                    source_feature_match_status
                    == SEGMENT_MATCH_RESOLVED
                    and waterbody_match_status
                    == SEGMENT_MATCH_RESOLVED
                ):
                    match_status = (
                        SEGMENT_MATCH_RESOLVED
                    )

                elif (
                    source_feature_match_status
                    == SEGMENT_MATCH_AMBIGUOUS
                    and waterbody_match_status
                    == SEGMENT_MATCH_RESOLVED
                ):
                    match_status = (
                        SEGMENT_MATCH_WATERBODY_RESOLVED_FEATURE_AMBIGUOUS
                    )

                elif (
                    candidates
                ):
                    match_status = (
                        SEGMENT_MATCH_AMBIGUOUS
                    )

                else:
                    match_status = (
                        SEGMENT_MATCH_UNRESOLVED
                    )

            if resolved_candidate is not None:
                feature_key = (
                    _candidate_identity_key(
                        resolved_candidate
                    )
                )
                route_resolved_features[
                    feature_key
                ] = deepcopy(
                    resolved_candidate
                )
                global_resolved_features[
                    feature_key
                ] = deepcopy(
                    resolved_candidate
                )

            if resolved_waterbody is not None:
                waterbody_key = (
                    (
                        resolved_waterbody.get(
                            "source_provider"
                        )
                    ),
                    (
                        resolved_waterbody.get(
                            "source_product"
                        )
                    ),
                    (
                        resolved_waterbody.get(
                            "waterbody_id"
                        )
                    ),
                )

                existing_route_waterbody = (
                    route_resolved_waterbodies.get(
                        waterbody_key
                    )
                )

                if existing_route_waterbody is None:
                    route_resolved_waterbodies[
                        waterbody_key
                    ] = deepcopy(
                        resolved_waterbody
                    )
                else:
                    _merge_waterbody_identity(
                        existing_route_waterbody,
                        resolved_waterbody,
                    )

                existing_global_waterbody = (
                    global_resolved_waterbodies.get(
                        waterbody_key
                    )
                )

                if existing_global_waterbody is None:
                    global_resolved_waterbodies[
                        waterbody_key
                    ] = deepcopy(
                        resolved_waterbody
                    )
                else:
                    _merge_waterbody_identity(
                        existing_global_waterbody,
                        resolved_waterbody,
                    )

            segment_results.append(
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
                    "segment_index_scope": (
                        segment.get(
                            "segment_index_scope"
                        )
                    ),
                    "source_segment_index": (
                        _integer(
                            segment.get(
                                "source_segment_index"
                            )
                        )
                    ),
                    "source_segment_index_scope": (
                        segment.get(
                            "source_segment_index_scope"
                        )
                    ),
                    "source_segment_index_status": (
                        segment.get(
                            "source_segment_index_status"
                        )
                    ),
                    "source_waypoint_contiguous": (
                        segment.get(
                            "source_waypoint_contiguous"
                        )
                        is True
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
                    "start_position": deepcopy(
                        segment.get(
                            "start_position"
                        )
                    ),
                    "end_position": deepcopy(
                        segment.get(
                            "end_position"
                        )
                    ),
                    "movement_bearing_deg": (
                        _finite_number(
                            segment.get(
                                "movement_bearing_deg"
                            )
                        )
                    ),
                    "match_status": (
                        match_status
                    ),
                    "waterbody_match_status": (
                        waterbody_match_status
                    ),
                    "source_feature_match_status": (
                        source_feature_match_status
                    ),
                    "candidate_count": len(
                        candidates
                    ),
                    "resolved_waterbody_identity": (
                        deepcopy(
                            resolved_waterbody
                        )
                        if resolved_waterbody
                        is not None
                        else None
                    ),
                    "resolved_identity": (
                        deepcopy(
                            resolved_candidate
                        )
                        if resolved_candidate
                        is not None
                        else None
                    ),
                    "candidates": deepcopy(
                        candidates
                    ),
                    "flow_relation": (
                        "UNRESOLVED"
                    ),
                }
            )

        route_feature_catalog = [
            route_resolved_features[key]
            for key in sorted(
                route_resolved_features,
                key=lambda item: tuple(
                    part or ""
                    for part in item
                ),
            )
        ]

        route_waterbody_catalog = [
            route_resolved_waterbodies[key]
            for key in sorted(
                route_resolved_waterbodies,
                key=lambda item: tuple(
                    part or ""
                    for part in item
                ),
            )
        ]

        segment_count = len(
            segment_results
        )

        route_status = (
            _status_from_counts(
                total=segment_count,
                resolved=(
                    waterbody_resolved_segment_count
                ),
                ambiguous=(
                    waterbody_ambiguous_segment_count
                ),
            )
        )

        source_feature_status = (
            _status_from_counts(
                total=segment_count,
                resolved=(
                    feature_resolved_segment_count
                ),
                ambiguous=(
                    feature_ambiguous_segment_count
                ),
            )
        )

        route_results.append(
            {
                "route_index": (
                    route_index
                ),
                "exercise_index": (
                    exercise_index
                ),
                "status": (
                    route_status
                ),
                "waterbody_status": (
                    route_status
                ),
                "source_feature_status": (
                    source_feature_status
                ),
                "segment_count": (
                    segment_count
                ),
                "resolved_segment_count": (
                    feature_resolved_segment_count
                ),
                "ambiguous_segment_count": (
                    feature_ambiguous_segment_count
                ),
                "unresolved_segment_count": (
                    feature_unresolved_segment_count
                ),
                "waterbody_resolved_segment_count": (
                    waterbody_resolved_segment_count
                ),
                "waterbody_ambiguous_segment_count": (
                    waterbody_ambiguous_segment_count
                ),
                "waterbody_unresolved_segment_count": (
                    waterbody_unresolved_segment_count
                ),
                "position_unavailable_segment_count": (
                    position_unavailable_segment_count
                ),
                "source_feature_count": len(
                    route_feature_catalog
                ),
                "waterbody_count": len(
                    route_waterbody_catalog
                ),
                "river_reach_count": len(
                    {
                        reach_id
                        for waterbody
                        in route_waterbody_catalog
                        for reach_id in (
                            waterbody.get(
                                "river_reach_ids"
                            )
                            or []
                        )
                    }
                ),
                "waterbodies": (
                    route_waterbody_catalog
                ),
                "resolved_features": (
                    route_feature_catalog
                ),
                "segments": (
                    segment_results
                ),
            }
        )

    resolved_feature_catalog = [
        global_resolved_features[key]
        for key in sorted(
            global_resolved_features,
            key=lambda item: tuple(
                part or ""
                for part in item
            ),
        )
    ]

    waterbody_catalog = [
        global_resolved_waterbodies[key]
        for key in sorted(
            global_resolved_waterbodies,
            key=lambda item: tuple(
                part or ""
                for part in item
            ),
        )
    ]

    route_count = len(
        route_results
    )

    waterbody_resolved_total = sum(
        route.get(
            "waterbody_resolved_segment_count",
            0,
        )
        for route in route_results
    )

    waterbody_ambiguous_total = sum(
        route.get(
            "waterbody_ambiguous_segment_count",
            0,
        )
        for route in route_results
    )

    waterbody_unresolved_total = sum(
        route.get(
            "waterbody_unresolved_segment_count",
            0,
        )
        for route in route_results
    )

    feature_resolved_total = sum(
        route.get(
            "resolved_segment_count",
            0,
        )
        for route in route_results
    )

    feature_ambiguous_total = sum(
        route.get(
            "ambiguous_segment_count",
            0,
        )
        for route in route_results
    )

    feature_unresolved_total = sum(
        route.get(
            "unresolved_segment_count",
            0,
        )
        for route in route_results
    )

    if (
        route_results
        and all(
            route.get(
                "waterbody_status"
            )
            == STATUS_RESOLVED
            for route in route_results
        )
    ):
        overall_status = (
            STATUS_RESOLVED
        )
    elif any(
        route.get(
            "waterbody_status"
        )
        == STATUS_AMBIGUOUS
        for route in route_results
    ):
        overall_status = (
            STATUS_AMBIGUOUS
        )
    else:
        overall_status = (
            STATUS_UNRESOLVED
        )

    return {
        "provider": (
            route_environment_context_input.get(
                "provider"
            )
        ),
        "schema_version": (
            SCHEMA_VERSION
        ),
        "available": bool(
            route_results
        ),
        "status": (
            overall_status
        ),
        "waterbody_status": (
            overall_status
        ),
        "route_count": (
            route_count
        ),
        "resolved_segment_count": (
            feature_resolved_total
        ),
        "ambiguous_segment_count": (
            feature_ambiguous_total
        ),
        "unresolved_segment_count": (
            feature_unresolved_total
        ),
        "waterbody_resolved_segment_count": (
            waterbody_resolved_total
        ),
        "waterbody_ambiguous_segment_count": (
            waterbody_ambiguous_total
        ),
        "waterbody_unresolved_segment_count": (
            waterbody_unresolved_total
        ),
        "source_feature_count": len(
            resolved_feature_catalog
        ),
        "waterbody_count": len(
            waterbody_catalog
        ),
        "waterbody_catalog": (
            waterbody_catalog
        ),
        "resolved_feature_catalog": (
            resolved_feature_catalog
        ),
        "candidate_source": (
            {
                "source_provider": (
                    _string_or_none(
                        (
                            waterbody_candidate_evidence
                            or {}
                        ).get(
                            "source_provider"
                        )
                    )
                ),
                "source_product": (
                    _string_or_none(
                        (
                            waterbody_candidate_evidence
                            or {}
                        ).get(
                            "source_product"
                        )
                    )
                ),
                "source_type": (
                    _string_or_none(
                        (
                            waterbody_candidate_evidence
                            or {}
                        ).get(
                            "source_type"
                        )
                    )
                ),
            }
        ),
        "scope": {
            "domain": (
                SCOPE_ROUTE_WATERBODY_CONTEXT
            ),
            "identifies_waterbody": True,
            "separates_waterbody_identity_from_source_feature_identity": (
                True
            ),
            "identifies_river_reach_when_source_provides_it": (
                True
            ),
            "selects_nearest_candidate_when_ambiguous": (
                False
            ),
            "selects_nearest_candidate_when_waterbodies_are_ambiguous": (
                False
            ),
            "derives_flow_direction_from_route_bearing": (
                False
            ),
            "estimates_local_current_velocity": (
                False
            ),
            "derives_current_from_water_level_or_discharge": (
                False
            ),
            "infers_route_choice_intent": (
                False
            ),
            "infers_group_tactics": (
                False
            ),
            "raw_data_mutated": (
                False
            ),
        },
        "routes": (
            route_results
        ),
    }


def build_route_waterbody_context_summary(
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        **{
            key: value
            for key, value
            in context.items()
            if key != "resolved_feature_catalog"
        },
        "resolved_feature_catalog_included": (
            False
        ),
        "resolved_feature_catalog_count": len(
            context.get(
                "resolved_feature_catalog"
            )
            or []
        ),
        "routes": [
            {
                **{
                    key: value
                    for key, value
                    in route.items()
                    if key not in {
                        "segments",
                        "resolved_features",
                    }
                },
                "segments_included": (
                    False
                ),
                "resolved_features_included": (
                    False
                ),
                "resolved_feature_payload_count": len(
                    route.get(
                        "resolved_features"
                    )
                    or []
                ),
                "segment_payload_count": len(
                    route.get(
                        "segments"
                    )
                    or []
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
