from __future__ import annotations

from copy import deepcopy

from app.services.route_waterbody_trajectory_resolution import (
    STATUS_AMBIGUOUS,
    STATUS_CONTINUITY_SUPPORTED,
    STATUS_DIRECT_RESOLVED,
    STATUS_TRANSITION_CANDIDATE,
    STATUS_UNRESOLVED,
    build_route_waterbody_trajectory_resolution,
    build_route_waterbody_trajectory_resolution_summary,
)


def _identity(waterbody_id: str) -> dict:
    return {
        "source_provider": "EEA_WISE_WFD",
        "source_product": "WFD2022_SURFACE_WATER_BODY_CENTRELINE",
        "waterbody_id": waterbody_id,
        "waterbody_name": None,
        "waterbody_type": "RIVER",
    }


def _candidate(waterbody_id: str, feature_id: str | None = None) -> dict:
    return {
        **_identity(waterbody_id),
        "source_feature_id": feature_id or f"feature-{waterbody_id}",
    }


def _segment(order: int, *, resolved: str | None = None, candidates: tuple[str, ...] = (), source_feature_status: str = "RESOLVED") -> dict:
    if resolved is not None:
        wb_status = "RESOLVED"
        resolved_identity = _identity(resolved)
    elif candidates:
        wb_status = "AMBIGUOUS"
        resolved_identity = None
    else:
        wb_status = "UNRESOLVED"
        resolved_identity = None
    return {
        "order_index": order,
        "segment_index": order,
        "segment_index_scope": "VIEW_LOCAL",
        "source_segment_index": order + 46,
        "source_segment_index_scope": "NORMALIZED_ROUTE_SOURCE",
        "source_segment_index_status": "AVAILABLE",
        "source_waypoint_contiguous": True,
        "start_waypoint_index": order + 46,
        "end_waypoint_index": order + 47,
        "start_exercise_elapsed_ms": order * 1000,
        "end_exercise_elapsed_ms": (order + 1) * 1000,
        "start_position": {"latitude_deg": 47.5, "longitude_deg": 19.05},
        "end_position": {"latitude_deg": 47.5001, "longitude_deg": 19.0501},
        "movement_bearing_deg": 12.0,
        "match_status": (
            "RESOLVED" if wb_status == "RESOLVED" and source_feature_status == "RESOLVED"
            else "WATERBODY_RESOLVED_FEATURE_AMBIGUOUS" if wb_status == "RESOLVED"
            else wb_status
        ),
        "waterbody_match_status": wb_status,
        "source_feature_match_status": source_feature_status,
        "candidate_count": len(candidates) if candidates else (1 if resolved else 0),
        "resolved_waterbody_identity": resolved_identity,
        "resolved_identity": None,
        "candidates": [_candidate(item) for item in candidates] if candidates else ([_candidate(resolved)] if resolved else []),
        "flow_relation": "UNRESOLVED",
    }


def _surface_segment(order: int, *, start_containment: str = "INSIDE", end_containment: str = "INSIDE", relation: str = "INSIDE") -> dict:
    return {
        "order_index": order,
        "segment_index": order,
        "start_surface_evidence": {
            "containment": start_containment,
            "relation": relation,
        },
        "end_surface_evidence": {
            "containment": end_containment,
            "relation": relation,
        },
    }


def _contexts(segments: list[dict], surface_segments: list[dict] | None = None) -> tuple[dict, dict]:
    waterbody = {
        "provider": "POLAR",
        "schema_version": "0.3",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }
    if surface_segments is None:
        surface_segments = [_surface_segment(i) for i in range(len(segments))]
    surface = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": surface_segments,
            }
        ],
    }
    return waterbody, surface


def _resolve(segments: list[dict], surface_segments: list[dict] | None = None, **kwargs) -> dict:
    waterbody, surface = _contexts(segments, surface_segments)
    return build_route_waterbody_trajectory_resolution(
        waterbody,
        surface,
        min_anchor_segments=kwargs.pop("min_anchor_segments", 2),
        max_ambiguous_gap_segments=kwargs.pop("max_ambiguous_gap_segments", 3),
        max_ambiguous_gap_ms=kwargs.pop("max_ambiguous_gap_ms", 5000),
        **kwargs,
    )


def test_direct_waterbody_resolution_is_preserved_even_if_feature_is_ambiguous() -> None:
    resolution = _resolve([
        _segment(0, resolved="HUAOC752", source_feature_status="AMBIGUOUS"),
    ], min_anchor_segments=1)
    segment = resolution["routes"][0]["segments"][0]
    assert segment["resolution_status"] == STATUS_DIRECT_RESOLVED
    assert segment["resolved_waterbody_identity"]["waterbody_id"] == "HUAOC752"
    assert segment["direct_source_feature_match_status"] == "AMBIGUOUS"


def test_short_same_anchor_ambiguity_is_continuity_supported() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, candidates=("HUAOC752", "HUAOC845")),
        _segment(4, resolved="HUAOC752"),
        _segment(5, resolved="HUAOC752"),
    ]
    resolution = _resolve(segments)
    route = resolution["routes"][0]
    assert route["continuity_supported_segment_count"] == 2
    assert route["ambiguous_segment_count"] == 0
    assert route["status"] == STATUS_CONTINUITY_SUPPORTED
    assert route["segments"][2]["resolution_status"] == STATUS_CONTINUITY_SUPPORTED
    assert route["segments"][2]["resolved_waterbody_identity"]["waterbody_id"] == "HUAOC752"


def test_boundary_near_inside_does_not_break_surface_continuity() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    surface = [_surface_segment(i) for i in range(len(segments))]
    surface[2] = _surface_segment(2, relation="BOUNDARY_NEAR")
    resolution = _resolve(segments, surface)
    segment = resolution["routes"][0]["segments"][2]
    assert segment["resolution_status"] == STATUS_CONTINUITY_SUPPORTED
    assert segment["surface_boundary_near_inside"] is True


def test_candidate_must_include_common_anchor_waterbody() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC845", "HUAOC999")),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    resolution = _resolve(segments)
    route = resolution["routes"][0]
    assert route["segments"][2]["resolution_status"] == STATUS_AMBIGUOUS
    assert route["resolution_runs"][0]["candidate_supports_common_anchor"] is False


def test_surface_outside_breaks_continuity_bridge() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    surface = [_surface_segment(i) for i in range(len(segments))]
    surface[2] = _surface_segment(2, start_containment="OUTSIDE")
    resolution = _resolve(segments, surface)
    route = resolution["routes"][0]
    assert route["segments"][2]["resolution_status"] == STATUS_AMBIGUOUS
    assert route["resolution_runs"][0]["surface_continuous"] is False


def test_different_stable_anchors_create_transition_candidate_not_smoothing() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, candidates=("HUAOC752", "HUAOC845")),
        _segment(4, resolved="HUAOC845"),
        _segment(5, resolved="HUAOC845"),
    ]
    resolution = _resolve(segments)
    route = resolution["routes"][0]
    assert route["transition_candidate_segment_count"] == 2
    assert route["segments"][2]["resolution_status"] == STATUS_TRANSITION_CANDIDATE
    assert route["segments"][2]["resolved_waterbody_identity"] is None


def test_gap_over_policy_limit_remains_ambiguous() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        *[_segment(i, candidates=("HUAOC752", "HUAOC845")) for i in range(2, 6)],
        _segment(6, resolved="HUAOC752"),
        _segment(7, resolved="HUAOC752"),
    ]
    resolution = _resolve(segments, max_ambiguous_gap_segments=3)
    route = resolution["routes"][0]
    assert route["ambiguous_segment_count"] == 4
    assert route["resolution_runs"][0]["within_gap_policy_limit"] is False


def test_unresolved_segments_are_not_bridged_and_inputs_are_not_mutated() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    waterbody, surface = _contexts(segments)
    original_waterbody = deepcopy(waterbody)
    original_surface = deepcopy(surface)
    resolution = build_route_waterbody_trajectory_resolution(
        waterbody,
        surface,
        min_anchor_segments=2,
    )
    assert resolution["routes"][0]["segments"][2]["resolution_status"] == STATUS_UNRESOLVED
    assert waterbody == original_waterbody
    assert surface == original_surface


def test_summary_excludes_segment_payload_but_keeps_resolution_runs() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    resolution = _resolve(segments)
    summary = build_route_waterbody_trajectory_resolution_summary(resolution)
    route = summary["routes"][0]
    assert "segments" not in route
    assert route["segments_included"] is False
    assert route["segment_payload_count"] == 5
    assert len(route["resolution_runs"]) == 1


def test_long_gap_collects_candidate_distance_diagnostics_without_relaxing_resolution() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, candidates=("HUAOC752", "HUAOC845")),
        _segment(4, candidates=("HUAOC752", "HUAOC845")),
        _segment(5, candidates=("HUAOC752", "HUAOC845")),
        _segment(6, resolved="HUAOC752"),
        _segment(7, resolved="HUAOC752"),
    ]
    distances = [
        (20.0, 120.0),
        (25.0, 100.0),
        (30.0, 80.0),
        (35.0, 70.0),
    ]
    for segment, (duna, other) in zip(segments[2:6], distances):
        segment["candidates"][0]["match_distance_m"] = duna
        segment["candidates"][1]["match_distance_m"] = other

    resolution = _resolve(segments, max_ambiguous_gap_segments=3)
    run = resolution["routes"][0]["resolution_runs"][0]
    assert run["resolution_status"] == STATUS_CONTINUITY_SUPPORTED
    assert run["distance_corroborates_common_anchor"] is True
    diagnostics = {item["waterbody_id"]: item for item in run["candidate_waterbody_diagnostics"]}
    assert diagnostics["HUAOC752"]["segment_presence_count"] == 4
    assert diagnostics["HUAOC752"]["nearest_by_distance_segment_count"] == 4
    assert diagnostics["HUAOC752"]["median_match_distance_m"] == 27.5
    assert diagnostics["HUAOC845"]["nearest_by_distance_segment_count"] == 0


def test_heading_alignment_diagnostics_treat_upstream_and_downstream_as_same_axis() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    ambiguous = segments[2]
    ambiguous["movement_bearing_deg"] = 190.0
    ambiguous["candidates"][0]["flow_direction_deg"] = 10.0
    ambiguous["candidates"][1]["flow_direction_deg"] = 90.0

    resolution = _resolve(segments)
    run = resolution["routes"][0]["resolution_runs"][0]
    diagnostics = {item["waterbody_id"]: item for item in run["candidate_waterbody_diagnostics"]}
    assert diagnostics["HUAOC752"]["median_axial_heading_error_deg"] == 0.0
    assert diagnostics["HUAOC752"]["best_heading_alignment_segment_count"] == 1
    assert diagnostics["HUAOC845"]["median_axial_heading_error_deg"] == 80.0
    assert diagnostics["HUAOC845"]["best_heading_alignment_segment_count"] == 0


def test_heading_diagnostics_do_not_resolve_long_gap_when_distance_evidence_is_incomplete() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        *[_segment(i, candidates=("HUAOC752", "HUAOC845")) for i in range(2, 7)],
        _segment(7, resolved="HUAOC752"),
        _segment(8, resolved="HUAOC752"),
    ]
    for segment in segments[2:7]:
        segment["movement_bearing_deg"] = 190.0
        segment["candidates"][0]["match_distance_m"] = 5.0
        segment["candidates"][0]["flow_direction_deg"] = 10.0
        segment["candidates"][1]["match_distance_m"] = 250.0
        segment["candidates"][1]["flow_direction_deg"] = 90.0
    segments[4]["candidates"][1].pop("match_distance_m")

    resolution = _resolve(segments, max_ambiguous_gap_segments=3)
    route = resolution["routes"][0]
    run = route["resolution_runs"][0]
    assert run["distance_evidence_complete"] is False
    assert route["ambiguous_segment_count"] == 5
    assert route["continuity_supported_segment_count"] == 0
    assert resolution["scope"]["uses_heading_transition_evidence"] is False
    assert resolution["scope"]["collects_heading_alignment_diagnostics"] is True
    assert resolution["scope"]["treats_nearest_candidate_as_truth"] is False


def test_long_gap_is_continuity_supported_when_distance_evidence_corroborates_same_anchor() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        *[_segment(i, candidates=("HUAOC752", "HUAOC845")) for i in range(2, 7)],
        _segment(7, resolved="HUAOC752"),
        _segment(8, resolved="HUAOC752"),
    ]
    for offset, segment in enumerate(segments[2:7]):
        segment["candidates"][0]["match_distance_m"] = 20.0 + offset
        segment["candidates"][1]["match_distance_m"] = 120.0 + offset

    resolution = _resolve(segments, max_ambiguous_gap_segments=3)
    route = resolution["routes"][0]
    run = route["resolution_runs"][0]
    assert run["within_gap_policy_limit"] is False
    assert run["distance_evidence_complete"] is True
    assert run["distance_corroborates_common_anchor"] is True
    assert route["continuity_supported_segment_count"] == 5
    assert route["ambiguous_segment_count"] == 0
    assert "LONG_GAP_DISTANCE_EVIDENCE_COMPLETE" in run["resolution_basis"]
    assert "NEAREST_DISTANCE_USED_AS_CORROBORATION_ONLY" in run["resolution_basis"]


def test_long_gap_remains_ambiguous_if_competitor_is_nearest_in_one_segment() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        *[_segment(i, candidates=("HUAOC752", "HUAOC845")) for i in range(2, 7)],
        _segment(7, resolved="HUAOC752"),
        _segment(8, resolved="HUAOC752"),
    ]
    for segment in segments[2:7]:
        segment["candidates"][0]["match_distance_m"] = 20.0
        segment["candidates"][1]["match_distance_m"] = 120.0
    segments[4]["candidates"][0]["match_distance_m"] = 130.0
    segments[4]["candidates"][1]["match_distance_m"] = 10.0

    resolution = _resolve(segments, max_ambiguous_gap_segments=3)
    route = resolution["routes"][0]
    run = route["resolution_runs"][0]
    assert run["distance_evidence_complete"] is True
    assert run["distance_corroborates_common_anchor"] is False
    assert route["ambiguous_segment_count"] == 5
    assert route["continuity_supported_segment_count"] == 0


def test_long_gap_remains_ambiguous_when_competitor_distance_evidence_is_incomplete() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        *[_segment(i, candidates=("HUAOC752", "HUAOC845")) for i in range(2, 7)],
        _segment(7, resolved="HUAOC752"),
        _segment(8, resolved="HUAOC752"),
    ]
    for segment in segments[2:7]:
        segment["candidates"][0]["match_distance_m"] = 20.0
        segment["candidates"][1]["match_distance_m"] = 120.0
    segments[5]["candidates"][1].pop("match_distance_m")

    resolution = _resolve(segments, max_ambiguous_gap_segments=3)
    route = resolution["routes"][0]
    run = route["resolution_runs"][0]
    assert run["distance_evidence_complete"] is False
    assert run["distance_corroborates_common_anchor"] is False
    assert route["ambiguous_segment_count"] == 5
    assert route["continuity_supported_segment_count"] == 0
    assert resolution["scope"]["treats_nearest_candidate_as_truth"] is False


def test_direct_resolution_is_withheld_when_both_surface_endpoints_are_explicit_outside() -> None:
    segments = [_segment(0, resolved="HRJKR00046_000000")]
    surface = [
        _surface_segment(
            0,
            start_containment="OUTSIDE",
            end_containment="OUTSIDE",
            relation="OUTSIDE",
        )
    ]

    resolution = _resolve(segments, surface, min_anchor_segments=1)
    route = resolution["routes"][0]
    segment = route["segments"][0]

    assert resolution["schema_version"] == "0.4"
    assert route["source_direct_resolved_segment_count"] == 1
    assert route["direct_resolution_withheld_by_surface_segment_count"] == 1
    assert route["direct_resolved_segment_count"] == 0
    assert route["unresolved_segment_count"] == 1
    assert segment["direct_resolved_waterbody_identity"]["waterbody_id"] == "HRJKR00046_000000"
    assert segment["resolved_waterbody_identity"] is None
    assert segment["direct_surface_evidence_status"] == "EXPLICIT_OUTSIDE"
    assert segment["direct_resolution_withheld_by_surface"] is True
    assert "TRUSTED_DIRECT_RESOLUTION_WITHHELD" in segment["resolution_basis"]


def test_mixed_surface_evidence_does_not_negate_direct_waterbody_resolution() -> None:
    segments = [_segment(0, resolved="HUAOC752")]
    surface = [_surface_segment(0)]
    surface[0]["start_surface_evidence"] = {
        "containment": "OUTSIDE",
        "relation": "OUTSIDE",
    }

    resolution = _resolve(segments, surface, min_anchor_segments=1)
    segment = resolution["routes"][0]["segments"][0]

    assert segment["direct_surface_evidence_status"] == "INCONCLUSIVE"
    assert segment["direct_resolution_withheld_by_surface"] is False
    assert segment["resolution_status"] == STATUS_DIRECT_RESOLVED
    assert segment["resolved_waterbody_identity"]["waterbody_id"] == "HUAOC752"


def test_missing_surface_segment_does_not_negate_direct_waterbody_resolution() -> None:
    segments = [_segment(0, resolved="HUAOC752")]
    resolution = _resolve(segments, [], min_anchor_segments=1)
    segment = resolution["routes"][0]["segments"][0]

    assert segment["direct_surface_evidence_status"] == "UNAVAILABLE"
    assert segment["direct_resolution_withheld_by_surface"] is False
    assert segment["resolution_status"] == STATUS_DIRECT_RESOLVED


def test_surface_withheld_direct_segment_cannot_act_as_continuity_anchor() -> None:
    segments = [
        _segment(0, resolved="HUAOC752"),
        _segment(1, resolved="HUAOC752"),
        _segment(2, candidates=("HUAOC752", "HUAOC845")),
        _segment(3, resolved="HUAOC752"),
        _segment(4, resolved="HUAOC752"),
    ]
    surface = [_surface_segment(i) for i in range(len(segments))]
    surface[1] = _surface_segment(
        1,
        start_containment="OUTSIDE",
        end_containment="OUTSIDE",
        relation="OUTSIDE",
    )

    resolution = _resolve(segments, surface)
    route = resolution["routes"][0]
    run = route["resolution_runs"][0]

    assert route["direct_resolution_withheld_by_surface_segment_count"] == 1
    assert route["segments"][1]["resolution_status"] == STATUS_UNRESOLVED
    assert run["left_anchor_identity"] is None
    assert run["stable_anchor_requirement_met"] is False
    assert run["resolution_status"] == STATUS_AMBIGUOUS
    assert route["segments"][2]["resolution_status"] == STATUS_AMBIGUOUS
