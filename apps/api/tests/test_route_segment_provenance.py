from app.services.route_motion import (
    build_route_motion_evidence,
)
from app.services.route_external_workload_evidence import (
    build_route_external_workload_evidence,
)
from app.services.route_environment_context_input import (
    build_route_environment_context_input,
)
from app.services.route_environment_evidence_record import (
    build_route_environment_evidence_record,
)


def _normalized_points(
    waypoint_indices,
):
    points = []

    for offset, waypoint_index in enumerate(
        waypoint_indices
    ):
        points.append(
            {
                "waypoint_index": waypoint_index,
                "exercise_elapsed_ms": (
                    100_000
                    + offset
                    * 1_000
                ),
                "latitude_deg": (
                    47.5
                    + offset
                    * 0.00001
                ),
                "longitude_deg": (
                    19.0
                    + offset
                    * 0.00001
                ),
                "altitude_m": 100.0,
            }
        )

    return {
        "provider": "POLAR",
        "routes": [
            {
                "exercise_index": 0,
                "points": points,
            }
        ],
    }


def test_motion_keeps_view_index_separate_from_source_index():
    motion = build_route_motion_evidence(
        _normalized_points(
            [
                46,
                47,
                48,
            ]
        )
    )

    first = motion["routes"][0]["segments"][0]
    second = motion["routes"][0]["segments"][1]

    assert first["segment_index"] == 0
    assert first["segment_index_scope"] == "VIEW_LOCAL"
    assert first["source_segment_index"] == 46
    assert (
        first["source_segment_index_scope"]
        == "NORMALIZED_ROUTE_SOURCE"
    )
    assert (
        first["source_segment_index_status"]
        == "DIRECT_FROM_CONSECUTIVE_SOURCE_WAYPOINTS"
    )
    assert first["source_waypoint_contiguous"] is True

    assert second["segment_index"] == 1
    assert second["source_segment_index"] == 47


def test_nonconsecutive_source_waypoints_do_not_invent_source_segment():
    motion = build_route_motion_evidence(
        _normalized_points(
            [
                46,
                48,
            ]
        )
    )

    segment = motion["routes"][0]["segments"][0]

    assert segment["segment_index"] == 0
    assert segment["source_segment_index"] is None
    assert segment["source_waypoint_contiguous"] is False
    assert (
        segment["source_segment_index_status"]
        == "UNAVAILABLE_NON_CONSECUTIVE_SOURCE_WAYPOINTS"
    )


def test_source_provenance_survives_external_and_environment_layers():
    normalized = _normalized_points(
        [
            46,
            47,
        ]
    )
    motion = build_route_motion_evidence(
        normalized
    )
    motion_segment = motion["routes"][0]["segments"][0]

    workload_input = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "source_branch": "TRUSTED_ROUTE_VIEW",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "reason": None,
                "usable_interval": {
                    "start_exercise_elapsed_ms": 100_000,
                    "end_exercise_elapsed_ms": 101_000,
                    "span_ms": 1_000,
                },
                "distance_evidence": {
                    "provider_reported": {
                        "value_m": None,
                    },
                    "raw_gps_surface_distance_m": None,
                    "trusted_gps_surface_distance_m": (
                        motion_segment[
                            "surface_distance_m"
                        ]
                    ),
                },
                "quality_provenance": {},
                "motion_segments": [
                    motion_segment
                ],
            }
        ],
    }

    external = (
        build_route_external_workload_evidence(
            workload_input
        )
    )

    observation = external["routes"][0][
        "observations"
    ][0]

    assert observation["segment_index"] == 0
    assert observation["source_segment_index"] == 46
    assert (
        observation["source_segment_index_status"]
        == "DIRECT_FROM_CONSECUTIVE_SOURCE_WAYPOINTS"
    )

    environment = (
        build_route_environment_context_input(
            normalized,
            external,
            session_time_context={
                "exercise_start_time": (
                    "2026-09-30T17:35:18"
                ),
                "timezone_offset_minutes": 120,
            },
        )
    )

    segment = environment["routes"][0][
        "segments"
    ][0]

    assert segment["segment_index"] == 0
    assert segment["source_segment_index"] == 46
    assert segment["source_waypoint_contiguous"] is True


def test_evidence_record_exposes_view_and_source_indices_separately():
    normalized = _normalized_points(
        [
            46,
            47,
        ]
    )
    motion = build_route_motion_evidence(
        normalized
    )
    motion_segment = motion["routes"][0]["segments"][0]

    workload_input = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "source_branch": "TRUSTED_ROUTE_VIEW",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "reason": None,
                "usable_interval": {
                    "start_exercise_elapsed_ms": 100_000,
                    "end_exercise_elapsed_ms": 101_000,
                    "span_ms": 1_000,
                },
                "distance_evidence": {
                    "provider_reported": {
                        "value_m": None,
                    },
                    "raw_gps_surface_distance_m": None,
                    "trusted_gps_surface_distance_m": (
                        motion_segment[
                            "surface_distance_m"
                        ]
                    ),
                },
                "quality_provenance": {},
                "motion_segments": [
                    motion_segment
                ],
            }
        ],
    }

    external = (
        build_route_external_workload_evidence(
            workload_input
        )
    )

    environment = (
        build_route_environment_context_input(
            normalized,
            external,
            session_time_context={
                "exercise_start_time": (
                    "2026-09-30T17:35:18"
                ),
                "timezone_offset_minutes": 120,
            },
        )
    )

    record = (
        build_route_environment_evidence_record(
            session_external_id="session-1",
            route_environment_context_input=(
                environment
            ),
            route_external_workload_evidence=(
                external
            ),
        )
    )

    locator = record["routes"][0][
        "segments"
    ][0][
        "source_locator"
    ]

    assert locator["view_segment_index"] == 0
    assert locator["segment_index_scope"] == "VIEW_LOCAL"
    assert locator["source_segment_index"] == 46
    assert (
        locator["source_segment_index_scope"]
        == "NORMALIZED_ROUTE_SOURCE"
    )
    assert locator["source_waypoint_contiguous"] is True



def test_summary_exposes_compact_source_provenance_without_segment_payload():
    normalized = _normalized_points(
        [
            46,
            47,
            48,
        ]
    )
    motion = build_route_motion_evidence(
        normalized
    )

    workload_input = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "source_branch": "TRUSTED_ROUTE_VIEW",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "reason": None,
                "usable_interval": {
                    "start_exercise_elapsed_ms": 100_000,
                    "end_exercise_elapsed_ms": 102_000,
                    "span_ms": 2_000,
                },
                "distance_evidence": {
                    "provider_reported": {
                        "value_m": None,
                    },
                    "raw_gps_surface_distance_m": None,
                    "trusted_gps_surface_distance_m": sum(
                        segment[
                            "surface_distance_m"
                        ]
                        or 0.0
                        for segment
                        in motion[
                            "routes"
                        ][0][
                            "segments"
                        ]
                    ),
                },
                "quality_provenance": {},
                "motion_segments": (
                    motion[
                        "routes"
                    ][0][
                        "segments"
                    ]
                ),
            }
        ],
    }

    external = (
        build_route_external_workload_evidence(
            workload_input
        )
    )

    environment = (
        build_route_environment_context_input(
            normalized,
            external,
            session_time_context={
                "exercise_start_time": (
                    "2026-09-30T17:35:18"
                ),
                "timezone_offset_minutes": 120,
            },
        )
    )

    record = (
        build_route_environment_evidence_record(
            session_external_id="session-1",
            route_environment_context_input=(
                environment
            ),
            route_external_workload_evidence=(
                external
            ),
        )
    )

    from app.services.route_environment_evidence_record import (
        build_route_environment_evidence_record_summary,
    )

    summary = (
        build_route_environment_evidence_record_summary(
            record
        )
    )

    route = summary["routes"][0]

    assert route["segments_included"] is False
    assert "segments" not in route

    assert (
        route[
            "source_segment_index_available_count"
        ]
        == 2
    )
    assert (
        route[
            "source_waypoint_contiguous_count"
        ]
        == 2
    )

    first = route[
        "first_segment_source_locator"
    ]
    last = route[
        "last_segment_source_locator"
    ]

    assert first["view_segment_index"] == 0
    assert first["source_segment_index"] == 46
    assert first["start_waypoint_index"] == 46
    assert first["end_waypoint_index"] == 47

    assert last["view_segment_index"] == 1
    assert last["source_segment_index"] == 47
    assert last["start_waypoint_index"] == 47
    assert last["end_waypoint_index"] == 48
