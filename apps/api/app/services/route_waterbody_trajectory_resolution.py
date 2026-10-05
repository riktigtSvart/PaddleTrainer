from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "0.4"

STATUS_DIRECT_RESOLVED = "DIRECT_RESOLVED"
STATUS_CONTINUITY_SUPPORTED = "CONTINUITY_SUPPORTED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_TRANSITION_CANDIDATE = "TRANSITION_CANDIDATE"
STATUS_UNRESOLVED = "UNRESOLVED"

SURFACE_SUPPORT_SUPPORTED = "SUPPORTED"
SURFACE_SUPPORT_EXPLICIT_OUTSIDE = "EXPLICIT_OUTSIDE"
SURFACE_SUPPORT_INCONCLUSIVE = "INCONCLUSIVE"
SURFACE_SUPPORT_UNAVAILABLE = "UNAVAILABLE"

DEFAULT_MAX_AMBIGUOUS_GAP_SEGMENTS = 30
DEFAULT_MAX_AMBIGUOUS_GAP_MS = 30_000
DEFAULT_MIN_ANCHOR_SEGMENTS = 5


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None




def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _axial_heading_error_deg(movement_bearing_deg: object, flow_direction_deg: object) -> float | None:
    movement = _finite_number(movement_bearing_deg)
    flow = _finite_number(flow_direction_deg)
    if movement is None or flow is None:
        return None
    difference = abs((movement - flow) % 360.0)
    if difference > 180.0:
        difference = 360.0 - difference
    return min(difference, abs(180.0 - difference))


def _run_candidate_diagnostics(
    segments: Sequence[Mapping[str, object]],
    start: int,
    end: int,
) -> list[dict[str, object]]:
    run_segment_count = end - start + 1
    stats: dict[tuple[str | None, str | None, str], dict[str, object]] = {}

    for index in range(start, end + 1):
        segment = segments[index]
        movement_bearing = segment.get("movement_bearing_deg")
        raw_candidates = segment.get("candidates")
        candidates = (
            raw_candidates
            if isinstance(raw_candidates, Sequence)
            and not isinstance(raw_candidates, (str, bytes))
            else []
        )

        per_segment: dict[tuple[str | None, str | None, str], dict[str, object]] = {}
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            key = _waterbody_key(candidate)
            if key is None:
                continue
            item = per_segment.setdefault(
                key,
                {
                    "identity": _waterbody_identity_from_candidate(candidate),
                    "distances": [],
                    "heading_errors": [],
                },
            )
            distance = _finite_number(candidate.get("match_distance_m"))
            if distance is not None:
                item["distances"].append(distance)
            heading_error = _axial_heading_error_deg(
                movement_bearing, candidate.get("flow_direction_deg")
            )
            if heading_error is not None:
                item["heading_errors"].append(heading_error)

        segment_min_distances: dict[tuple[str | None, str | None, str], float] = {}
        segment_min_heading_errors: dict[tuple[str | None, str | None, str], float] = {}

        for key, item in per_segment.items():
            aggregate = stats.setdefault(
                key,
                {
                    "identity": deepcopy(item.get("identity")),
                    "segment_presence_count": 0,
                    "distances": [],
                    "heading_errors": [],
                    "nearest_by_distance_segment_count": 0,
                    "best_heading_alignment_segment_count": 0,
                },
            )
            aggregate["segment_presence_count"] += 1

            distances = item.get("distances") or []
            if distances:
                minimum_distance = min(distances)
                aggregate["distances"].append(minimum_distance)
                segment_min_distances[key] = minimum_distance

            heading_errors = item.get("heading_errors") or []
            if heading_errors:
                minimum_heading_error = min(heading_errors)
                aggregate["heading_errors"].append(minimum_heading_error)
                segment_min_heading_errors[key] = minimum_heading_error

        if segment_min_distances:
            best_distance = min(segment_min_distances.values())
            for key, distance in segment_min_distances.items():
                if abs(distance - best_distance) <= 1e-9:
                    stats[key]["nearest_by_distance_segment_count"] += 1

        if segment_min_heading_errors:
            best_heading_error = min(segment_min_heading_errors.values())
            for key, error in segment_min_heading_errors.items():
                if abs(error - best_heading_error) <= 1e-9:
                    stats[key]["best_heading_alignment_segment_count"] += 1

    result: list[dict[str, object]] = []
    for key in sorted(stats, key=lambda value: tuple(part or "" for part in value)):
        aggregate = stats[key]
        distances = [float(value) for value in aggregate.get("distances") or []]
        heading_errors = [float(value) for value in aggregate.get("heading_errors") or []]
        presence = int(aggregate.get("segment_presence_count") or 0)
        identity = aggregate.get("identity")
        result.append(
            {
                "source_provider": key[0],
                "source_product": key[1],
                "waterbody_id": key[2],
                "waterbody_name": (
                    identity.get("waterbody_name")
                    if isinstance(identity, Mapping)
                    else None
                ),
                "waterbody_type": (
                    identity.get("waterbody_type")
                    if isinstance(identity, Mapping)
                    else None
                ),
                "segment_presence_count": presence,
                "segment_presence_fraction": (
                    presence / run_segment_count if run_segment_count else 0.0
                ),
                "distance_evidence_available_segment_count": len(distances),
                "minimum_match_distance_m": min(distances) if distances else None,
                "median_match_distance_m": _median(distances),
                "maximum_match_distance_m": max(distances) if distances else None,
                "nearest_by_distance_segment_count": int(
                    aggregate.get("nearest_by_distance_segment_count") or 0
                ),
                "heading_alignment_available_segment_count": len(heading_errors),
                "minimum_axial_heading_error_deg": (
                    min(heading_errors) if heading_errors else None
                ),
                "median_axial_heading_error_deg": _median(heading_errors),
                "maximum_axial_heading_error_deg": (
                    max(heading_errors) if heading_errors else None
                ),
                "best_heading_alignment_segment_count": int(
                    aggregate.get("best_heading_alignment_segment_count") or 0
                ),
            }
        )
    return result


def _distance_corroborates_common_anchor(
    diagnostics: Sequence[Mapping[str, object]],
    common_anchor_key: tuple[str | None, str | None, str] | None,
    run_segment_count: int,
) -> tuple[bool, bool]:
    """Return (distance_evidence_complete, anchor_dominates_every_segment).

    Nearest-distance evidence is only corroborative. It can never resolve a run
    by itself; callers must also require stable same-waterbody anchors, candidate
    compatibility, and continuous EU-Hydro surface evidence.
    """
    if common_anchor_key is None or run_segment_count < 1:
        return False, False

    anchor = None
    evidence_complete = True
    for item in diagnostics:
        if not isinstance(item, Mapping):
            continue
        key = _waterbody_key(item)
        if key is None:
            continue
        presence = _integer(item.get("segment_presence_count")) or 0
        distance_count = (
            _integer(item.get("distance_evidence_available_segment_count")) or 0
        )
        if presence > 0 and distance_count != presence:
            evidence_complete = False
        if key == common_anchor_key:
            anchor = item

    if anchor is None:
        return False, False

    anchor_presence = _integer(anchor.get("segment_presence_count")) or 0
    anchor_distance_count = (
        _integer(anchor.get("distance_evidence_available_segment_count")) or 0
    )
    anchor_nearest_count = (
        _integer(anchor.get("nearest_by_distance_segment_count")) or 0
    )

    if anchor_presence != run_segment_count:
        evidence_complete = False
    if anchor_distance_count != run_segment_count:
        evidence_complete = False

    competitors_never_nearest = all(
        (_integer(item.get("nearest_by_distance_segment_count")) or 0) == 0
        for item in diagnostics
        if isinstance(item, Mapping)
        and _waterbody_key(item) not in {None, common_anchor_key}
    )

    anchor_dominates = (
        evidence_complete
        and anchor_nearest_count == run_segment_count
        and competitors_never_nearest
    )
    return evidence_complete, anchor_dominates


def _route_key(route: Mapping[str, object], fallback: int) -> tuple[int, int | None]:
    route_index = _integer(route.get("route_index"))
    if route_index is None:
        route_index = fallback
    return route_index, _integer(route.get("exercise_index"))


def _waterbody_key(identity: object) -> tuple[str | None, str | None, str] | None:
    if not isinstance(identity, Mapping):
        return None
    waterbody_id = _string(identity.get("waterbody_id"))
    if waterbody_id is None:
        return None
    return (
        _string(identity.get("source_provider")),
        _string(identity.get("source_product")),
        waterbody_id,
    )


def _waterbody_identity_from_candidate(candidate: object) -> dict[str, object] | None:
    if not isinstance(candidate, Mapping):
        return None
    key = _waterbody_key(candidate)
    if key is None:
        return None
    return {
        "source_provider": key[0],
        "source_product": key[1],
        "waterbody_id": key[2],
        "waterbody_name": _string(candidate.get("waterbody_name")),
        "waterbody_type": _string(candidate.get("waterbody_type")),
    }


def _candidate_waterbody_keys(segment: Mapping[str, object]) -> set[tuple[str | None, str | None, str]]:
    result: set[tuple[str | None, str | None, str]] = set()
    raw_candidates = segment.get("candidates")
    candidates = (
        raw_candidates
        if isinstance(raw_candidates, Sequence)
        and not isinstance(raw_candidates, (str, bytes))
        else []
    )
    for candidate in candidates:
        key = _waterbody_key(candidate)
        if key is not None:
            result.add(key)
    return result


def _surface_route_lookup(route_water_surface_evidence: Mapping[str, object]) -> dict[tuple[int, int | None], Mapping[str, object]]:
    lookup: dict[tuple[int, int | None], Mapping[str, object]] = {}
    raw_routes = route_water_surface_evidence.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )
    for position, route in enumerate(routes):
        if isinstance(route, Mapping):
            lookup[_route_key(route, position)] = route
    return lookup


def _surface_segment_lookup(route: Mapping[str, object] | None) -> dict[int, Mapping[str, object]]:
    if route is None:
        return {}
    lookup: dict[int, Mapping[str, object]] = {}
    raw_segments = route.get("segments")
    segments = (
        raw_segments
        if isinstance(raw_segments, Sequence)
        and not isinstance(raw_segments, (str, bytes))
        else []
    )
    for position, segment in enumerate(segments):
        if not isinstance(segment, Mapping):
            continue
        order_index = _integer(segment.get("order_index"))
        if order_index is None:
            order_index = position
        lookup[order_index] = segment
    return lookup


def _endpoint_surface_continuous(endpoint: object) -> bool:
    return (
        isinstance(endpoint, Mapping)
        and endpoint.get("containment") == "INSIDE"
        and endpoint.get("relation") in {"INSIDE", "BOUNDARY_NEAR"}
    )


def _endpoint_surface_explicit_outside(endpoint: object) -> bool:
    return (
        isinstance(endpoint, Mapping)
        and endpoint.get("containment") == "OUTSIDE"
        and endpoint.get("relation") == "OUTSIDE"
    )


def _segment_surface_continuity(surface_segment: Mapping[str, object] | None) -> tuple[bool, bool]:
    if surface_segment is None:
        return False, False
    start = surface_segment.get("start_surface_evidence")
    end = surface_segment.get("end_surface_evidence")
    available = isinstance(start, Mapping) and isinstance(end, Mapping)
    continuous = (
        available
        and _endpoint_surface_continuous(start)
        and _endpoint_surface_continuous(end)
    )
    boundary_near = False
    for endpoint in (start, end):
        if (
            isinstance(endpoint, Mapping)
            and endpoint.get("relation") == "BOUNDARY_NEAR"
            and endpoint.get("containment") == "INSIDE"
        ):
            boundary_near = True
    return bool(continuous), boundary_near


def _segment_surface_support_status(
    surface_segment: Mapping[str, object] | None,
) -> str:
    """Classify structural surface evidence without inferring waterbody identity.

    EXPLICIT_OUTSIDE is intentionally strict: both segment endpoints must carry
    explicit OUTSIDE containment and OUTSIDE relation. Missing, mixed, or
    boundary evidence is INCONCLUSIVE rather than negative evidence.
    """
    if surface_segment is None:
        return SURFACE_SUPPORT_UNAVAILABLE
    start = surface_segment.get("start_surface_evidence")
    end = surface_segment.get("end_surface_evidence")
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        return SURFACE_SUPPORT_INCONCLUSIVE
    if _endpoint_surface_continuous(start) and _endpoint_surface_continuous(end):
        return SURFACE_SUPPORT_SUPPORTED
    if _endpoint_surface_explicit_outside(start) and _endpoint_surface_explicit_outside(end):
        return SURFACE_SUPPORT_EXPLICIT_OUTSIDE
    return SURFACE_SUPPORT_INCONCLUSIVE


def _direct_identity(segment: Mapping[str, object]) -> dict[str, object] | None:
    if segment.get("waterbody_match_status") != "RESOLVED":
        return None
    identity = segment.get("resolved_waterbody_identity")
    if _waterbody_key(identity) is None:
        return None
    return deepcopy(dict(identity)) if isinstance(identity, Mapping) else None


def _run_duration_ms(segments: Sequence[Mapping[str, object]], start: int, end: int) -> int | None:
    start_ms = _integer(segments[start].get("start_exercise_elapsed_ms"))
    end_ms = _integer(segments[end].get("end_exercise_elapsed_ms"))
    if start_ms is None or end_ms is None or end_ms < start_ms:
        return None
    return end_ms - start_ms


def _anchor_span_left(
    trusted_direct_identities: Sequence[Mapping[str, object] | None],
    index: int,
    key: tuple[str | None, str | None, str],
) -> int:
    count = 0
    position = index
    while position >= 0:
        if _waterbody_key(trusted_direct_identities[position]) != key:
            break
        count += 1
        position -= 1
    return count


def _anchor_span_right(
    trusted_direct_identities: Sequence[Mapping[str, object] | None],
    index: int,
    key: tuple[str | None, str | None, str],
) -> int:
    count = 0
    position = index
    while position < len(trusted_direct_identities):
        if _waterbody_key(trusted_direct_identities[position]) != key:
            break
        count += 1
        position += 1
    return count


def _copy_segment_provenance(segment: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "order_index",
        "segment_index",
        "segment_index_scope",
        "source_segment_index",
        "source_segment_index_scope",
        "source_segment_index_status",
        "source_waypoint_contiguous",
        "start_waypoint_index",
        "end_waypoint_index",
        "start_exercise_elapsed_ms",
        "end_exercise_elapsed_ms",
        "start_position",
        "end_position",
        "movement_bearing_deg",
    )
    return {key: deepcopy(segment.get(key)) for key in keys}


def _route_status(counts: Mapping[str, int]) -> str:
    if counts.get(STATUS_TRANSITION_CANDIDATE, 0):
        return STATUS_TRANSITION_CANDIDATE
    if counts.get(STATUS_AMBIGUOUS, 0):
        return STATUS_AMBIGUOUS
    if counts.get(STATUS_UNRESOLVED, 0):
        return STATUS_UNRESOLVED
    if counts.get(STATUS_CONTINUITY_SUPPORTED, 0):
        return STATUS_CONTINUITY_SUPPORTED
    return STATUS_DIRECT_RESOLVED


def build_route_waterbody_trajectory_resolution(
    route_waterbody_context: Mapping[str, object],
    route_water_surface_evidence: Mapping[str, object],
    *,
    max_ambiguous_gap_segments: int = DEFAULT_MAX_AMBIGUOUS_GAP_SEGMENTS,
    max_ambiguous_gap_ms: int = DEFAULT_MAX_AMBIGUOUS_GAP_MS,
    min_anchor_segments: int = DEFAULT_MIN_ANCHOR_SEGMENTS,
) -> dict[str, object]:
    """Resolve short WISE waterbody ambiguity using trajectory continuity.

    The function is intentionally conservative. It never mutates the direct
    WISE context or EU-Hydro surface evidence. Direct WISE identity remains source
    evidence, but trusted direct resolution is withheld when both segment endpoints
    are explicitly OUTSIDE EU-Hydro structural water-surface geometry. Missing or
    mixed surface evidence never negates WISE by itself. Ambiguous segments may be
    continuity-supported through two evidence paths. Short ambiguous runs use the
    original bounded-gap rule. Longer runs require the same stable trusted-direct
    waterbody on both sides, candidate compatibility, continuous EU-Hydro surface
    evidence, complete candidate distance evidence, and common-anchor distance
    dominance in every ambiguous segment. Nearest distance is corroborative only,
    never sufficient by itself.
    """
    if max_ambiguous_gap_segments < 1:
        raise ValueError("max_ambiguous_gap_segments must be >= 1")
    if max_ambiguous_gap_ms < 1:
        raise ValueError("max_ambiguous_gap_ms must be >= 1")
    if min_anchor_segments < 1:
        raise ValueError("min_anchor_segments must be >= 1")

    surface_routes = _surface_route_lookup(route_water_surface_evidence)
    raw_routes = route_waterbody_context.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )

    route_results: list[dict[str, object]] = []
    global_counts = {
        STATUS_DIRECT_RESOLVED: 0,
        STATUS_CONTINUITY_SUPPORTED: 0,
        STATUS_AMBIGUOUS: 0,
        STATUS_TRANSITION_CANDIDATE: 0,
        STATUS_UNRESOLVED: 0,
    }
    global_source_direct_resolved_count = 0
    global_direct_withheld_by_surface_count = 0

    for route_position, raw_route in enumerate(routes):
        if not isinstance(raw_route, Mapping):
            continue
        route_index, exercise_index = _route_key(raw_route, route_position)
        surface_segment_by_order = _surface_segment_lookup(
            surface_routes.get((route_index, exercise_index))
        )

        raw_segments = raw_route.get("segments")
        source_segments = [
            segment
            for segment in (
                raw_segments
                if isinstance(raw_segments, Sequence)
                and not isinstance(raw_segments, (str, bytes))
                else []
            )
            if isinstance(segment, Mapping)
        ]

        segment_results: list[dict[str, object]] = []
        base_statuses: list[str] = []
        trusted_direct_identities: list[dict[str, object] | None] = []
        source_direct_resolved_count = 0
        direct_withheld_by_surface_count = 0
        for position, segment in enumerate(source_segments):
            order_index = _integer(segment.get("order_index"))
            if order_index is None:
                order_index = position
            source_direct_identity = _direct_identity(segment)
            source_direct_key = _waterbody_key(source_direct_identity)

            surface_segment = surface_segment_by_order.get(order_index)
            surface_continuous, boundary_near_inside = _segment_surface_continuity(
                surface_segment
            )
            surface_support_status = _segment_surface_support_status(surface_segment)
            direct_withheld_by_surface = (
                source_direct_key is not None
                and surface_support_status == SURFACE_SUPPORT_EXPLICIT_OUTSIDE
            )

            if source_direct_key is not None:
                source_direct_resolved_count += 1
            if direct_withheld_by_surface:
                direct_withheld_by_surface_count += 1

            trusted_direct_identity = (
                None if direct_withheld_by_surface else source_direct_identity
            )
            trusted_direct_key = _waterbody_key(trusted_direct_identity)

            if trusted_direct_key is not None:
                status = STATUS_DIRECT_RESOLVED
            elif source_direct_key is not None and direct_withheld_by_surface:
                status = STATUS_UNRESOLVED
            elif segment.get("waterbody_match_status") == "AMBIGUOUS":
                status = STATUS_AMBIGUOUS
            else:
                status = STATUS_UNRESOLVED

            candidate_keys = _candidate_waterbody_keys(segment)

            if direct_withheld_by_surface:
                resolution_basis = [
                    "DIRECT_WATERBODY_EVIDENCE_PRESERVED_AS_SOURCE",
                    "EU_HYDRO_EXPLICIT_OUTSIDE_BOTH_ENDPOINTS",
                    "TRUSTED_DIRECT_RESOLUTION_WITHHELD",
                ]
            elif status == STATUS_DIRECT_RESOLVED:
                resolution_basis = ["DIRECT_WATERBODY_RESOLUTION"]
                if surface_support_status == SURFACE_SUPPORT_SUPPORTED:
                    resolution_basis.append("EU_HYDRO_SURFACE_SUPPORT")
            else:
                resolution_basis = []

            result = _copy_segment_provenance(segment)
            result.update(
                {
                    "direct_match_status": segment.get("match_status"),
                    "direct_waterbody_match_status": segment.get("waterbody_match_status"),
                    "direct_source_feature_match_status": segment.get("source_feature_match_status"),
                    "direct_resolved_waterbody_identity": deepcopy(source_direct_identity),
                    "candidate_waterbody_ids": sorted({key[2] for key in candidate_keys}),
                    "surface_continuity_available": order_index in surface_segment_by_order,
                    "surface_continuous": surface_continuous,
                    "surface_boundary_near_inside": boundary_near_inside,
                    "direct_surface_evidence_status": surface_support_status,
                    "direct_resolution_withheld_by_surface": direct_withheld_by_surface,
                    "resolution_status": status,
                    "resolved_waterbody_identity": deepcopy(trusted_direct_identity),
                    "resolution_basis": resolution_basis,
                    "continuity_run_index": None,
                }
            )
            segment_results.append(result)
            base_statuses.append(status)
            trusted_direct_identities.append(
                deepcopy(trusted_direct_identity)
                if trusted_direct_identity is not None
                else None
            )

        runs: list[dict[str, object]] = []
        run_index = 0
        cursor = 0
        while cursor < len(source_segments):
            if base_statuses[cursor] != STATUS_AMBIGUOUS:
                cursor += 1
                continue
            start = cursor
            while cursor + 1 < len(source_segments) and base_statuses[cursor + 1] == STATUS_AMBIGUOUS:
                cursor += 1
            end = cursor

            left_index = start - 1
            right_index = end + 1
            left_identity = (
                trusted_direct_identities[left_index]
                if left_index >= 0
                else None
            )
            right_identity = (
                trusted_direct_identities[right_index]
                if right_index < len(trusted_direct_identities)
                else None
            )
            left_key = _waterbody_key(left_identity)
            right_key = _waterbody_key(right_identity)

            left_anchor_segments = (
                _anchor_span_left(trusted_direct_identities, left_index, left_key)
                if left_key is not None
                else 0
            )
            right_anchor_segments = (
                _anchor_span_right(trusted_direct_identities, right_index, right_key)
                if right_key is not None
                else 0
            )
            stable_anchors = (
                left_anchor_segments >= min_anchor_segments
                and right_anchor_segments >= min_anchor_segments
            )

            segment_count = end - start + 1
            duration_ms = _run_duration_ms(source_segments, start, end)
            within_gap_limit = (
                segment_count <= max_ambiguous_gap_segments
                and (
                    duration_ms is None
                    or duration_ms <= max_ambiguous_gap_ms
                )
            )
            surface_continuous = all(
                bool(segment_results[index].get("surface_continuous"))
                for index in range(start, end + 1)
            )
            candidate_supports_left = (
                left_key is not None
                and all(
                    left_key in _candidate_waterbody_keys(source_segments[index])
                    for index in range(start, end + 1)
                )
            )
            candidate_supports_transition = (
                left_key is not None
                and right_key is not None
                and all(
                    bool(
                        _candidate_waterbody_keys(source_segments[index])
                        & {left_key, right_key}
                    )
                    for index in range(start, end + 1)
                )
            )

            candidate_diagnostics = _run_candidate_diagnostics(
                source_segments,
                start,
                end,
            )
            distance_evidence_complete, distance_corroborates_common_anchor = (
                _distance_corroborates_common_anchor(
                    candidate_diagnostics,
                    left_key if left_key == right_key else None,
                    segment_count,
                )
            )

            final_status = STATUS_AMBIGUOUS
            resolved_identity = None
            basis: list[str] = []

            if (
                stable_anchors
                and left_key is not None
                and right_key is not None
                and left_key != right_key
                and candidate_supports_transition
                and surface_continuous
            ):
                final_status = STATUS_TRANSITION_CANDIDATE
                basis = [
                    "DIFFERENT_STABLE_DIRECT_ANCHORS",
                    "AMBIGUOUS_CANDIDATES_COMPATIBLE_WITH_ANCHOR_TRANSITION",
                    "EU_HYDRO_SURFACE_CONTINUITY",
                ]
            elif (
                stable_anchors
                and left_key is not None
                and left_key == right_key
                and candidate_supports_left
                and surface_continuous
                and (
                    within_gap_limit
                    or distance_corroborates_common_anchor
                )
            ):
                final_status = STATUS_CONTINUITY_SUPPORTED
                resolved_identity = deepcopy(left_identity)
                basis = [
                    "SAME_STABLE_DIRECT_ANCHORS",
                    "ANCHOR_WATERBODY_PRESENT_IN_ALL_AMBIGUOUS_CANDIDATES",
                    "EU_HYDRO_SURFACE_CONTINUITY",
                ]
                if within_gap_limit:
                    basis.append("AMBIGUOUS_GAP_WITHIN_POLICY_LIMIT")
                else:
                    basis.extend(
                        [
                            "LONG_GAP_DISTANCE_EVIDENCE_COMPLETE",
                            "ANCHOR_WATERBODY_DISTANCE_DOMINANT_IN_ALL_AMBIGUOUS_SEGMENTS",
                            "NEAREST_DISTANCE_USED_AS_CORROBORATION_ONLY",
                        ]
                    )

            for index in range(start, end + 1):
                segment_results[index]["resolution_status"] = final_status
                segment_results[index]["resolved_waterbody_identity"] = deepcopy(resolved_identity)
                segment_results[index]["resolution_basis"] = list(basis)
                segment_results[index]["continuity_run_index"] = run_index

            runs.append(
                {
                    "run_index": run_index,
                    "start_order_index": _integer(source_segments[start].get("order_index")),
                    "end_order_index": _integer(source_segments[end].get("order_index")),
                    "segment_count": segment_count,
                    "duration_ms": duration_ms,
                    "resolution_status": final_status,
                    "resolved_waterbody_identity": deepcopy(resolved_identity),
                    "left_anchor_identity": deepcopy(left_identity),
                    "right_anchor_identity": deepcopy(right_identity),
                    "left_anchor_stable_segment_count": left_anchor_segments,
                    "right_anchor_stable_segment_count": right_anchor_segments,
                    "stable_anchor_requirement_met": stable_anchors,
                    "within_gap_policy_limit": within_gap_limit,
                    "candidate_supports_common_anchor": candidate_supports_left,
                    "candidate_supports_anchor_transition": candidate_supports_transition,
                    "surface_continuous": surface_continuous,
                    "distance_evidence_complete": distance_evidence_complete,
                    "distance_corroborates_common_anchor": distance_corroborates_common_anchor,
                    "candidate_waterbody_diagnostics": candidate_diagnostics,
                    "resolution_basis": list(basis),
                }
            )
            run_index += 1
            cursor += 1

        counts = {
            STATUS_DIRECT_RESOLVED: 0,
            STATUS_CONTINUITY_SUPPORTED: 0,
            STATUS_AMBIGUOUS: 0,
            STATUS_TRANSITION_CANDIDATE: 0,
            STATUS_UNRESOLVED: 0,
        }
        for segment in segment_results:
            status = str(segment.get("resolution_status"))
            if status in counts:
                counts[status] += 1
                global_counts[status] += 1

        global_source_direct_resolved_count += source_direct_resolved_count
        global_direct_withheld_by_surface_count += direct_withheld_by_surface_count

        route_results.append(
            {
                "route_index": route_index,
                "exercise_index": exercise_index,
                "available": bool(segment_results),
                "status": _route_status(counts),
                "segment_count": len(segment_results),
                "source_direct_resolved_segment_count": source_direct_resolved_count,
                "direct_resolution_withheld_by_surface_segment_count": direct_withheld_by_surface_count,
                "direct_resolved_segment_count": counts[STATUS_DIRECT_RESOLVED],
                "continuity_supported_segment_count": counts[STATUS_CONTINUITY_SUPPORTED],
                "ambiguous_segment_count": counts[STATUS_AMBIGUOUS],
                "transition_candidate_segment_count": counts[STATUS_TRANSITION_CANDIDATE],
                "unresolved_segment_count": counts[STATUS_UNRESOLVED],
                "ambiguity_run_count": len(runs),
                "continuity_supported_run_count": sum(
                    run.get("resolution_status") == STATUS_CONTINUITY_SUPPORTED
                    for run in runs
                ),
                "transition_candidate_run_count": sum(
                    run.get("resolution_status") == STATUS_TRANSITION_CANDIDATE
                    for run in runs
                ),
                "resolution_runs": runs,
                "segments": segment_results,
            }
        )

    return {
        "provider": route_waterbody_context.get("provider") or "POLAR",
        "schema_version": SCHEMA_VERSION,
        "available": bool(route_results),
        "status": _route_status(global_counts),
        "route_count": len(route_results),
        "source_direct_resolved_segment_count": global_source_direct_resolved_count,
        "direct_resolution_withheld_by_surface_segment_count": global_direct_withheld_by_surface_count,
        "direct_resolved_segment_count": global_counts[STATUS_DIRECT_RESOLVED],
        "continuity_supported_segment_count": global_counts[STATUS_CONTINUITY_SUPPORTED],
        "ambiguous_segment_count": global_counts[STATUS_AMBIGUOUS],
        "transition_candidate_segment_count": global_counts[STATUS_TRANSITION_CANDIDATE],
        "unresolved_segment_count": global_counts[STATUS_UNRESOLVED],
        "policy": {
            "max_ambiguous_gap_segments": max_ambiguous_gap_segments,
            "max_ambiguous_gap_ms": max_ambiguous_gap_ms,
            "min_anchor_segments": min_anchor_segments,
            "direct_resolution_surface_gate": (
                "WITHHOLD_ONLY_WHEN_BOTH_ENDPOINTS_EXPLICIT_OUTSIDE"
            ),
        },
        "input_provenance": {
            "route_waterbody_context_schema_version": route_waterbody_context.get("schema_version"),
            "route_water_surface_evidence_schema_version": route_water_surface_evidence.get("schema_version"),
        },
        "scope": {
            "domain": "ROUTE_WATERBODY_TRAJECTORY_RESOLUTION",
            "preserves_direct_waterbody_evidence": True,
            "uses_temporal_continuity": True,
            "uses_surface_continuity": True,
            "uses_surface_evidence_to_validate_direct_resolution": True,
            "withholds_direct_resolution_only_for_both_endpoints_explicit_outside": True,
            "does_not_treat_missing_or_mixed_surface_evidence_as_negative": True,
            "uses_candidate_compatibility": True,
            "uses_heading_transition_evidence": False,
            "uses_candidate_distance_for_long_gap_corroboration": True,
            "collects_candidate_distance_diagnostics": True,
            "collects_heading_alignment_diagnostics": True,
            "treats_nearest_candidate_as_truth": False,
            "infers_navigability": False,
            "estimates_local_current_velocity": False,
            "mutates_input_evidence": False,
        },
        "routes": route_results,
    }


def build_route_waterbody_trajectory_resolution_summary(
    resolution: Mapping[str, object],
) -> dict[str, object]:
    raw_routes = resolution.get("routes")
    routes = (
        raw_routes
        if isinstance(raw_routes, Sequence)
        and not isinstance(raw_routes, (str, bytes))
        else []
    )
    route_summaries: list[dict[str, object]] = []
    for route in routes:
        if not isinstance(route, Mapping):
            continue
        raw_segments = route.get("segments")
        segment_count = len(raw_segments) if isinstance(raw_segments, Sequence) and not isinstance(raw_segments, (str, bytes)) else 0
        route_summary = {
            key: deepcopy(value)
            for key, value in route.items()
            if key != "segments"
        }
        route_summary["segments_included"] = False
        route_summary["segment_payload_count"] = segment_count
        route_summaries.append(route_summary)

    return {
        **{
            key: deepcopy(value)
            for key, value in resolution.items()
            if key != "routes"
        },
        "routes": route_summaries,
    }
