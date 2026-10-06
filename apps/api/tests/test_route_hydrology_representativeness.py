from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.services.route_hydrology_representativeness import (
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_REPRESENTATIVE,
    STATUS_PARTIALLY_REPRESENTATIVE,
    STATUS_REPRESENTATIVE,
    build_route_hydrology_representativeness,
    build_route_hydrology_representativeness_summary,
)


START = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)


def _route_input(*, segment_count: int = 4):
    segments = []
    for index in range(segment_count):
        timestamp = START + timedelta(minutes=30 * index)
        segments.append(
            {
                "segment_index": index,
                "midpoint_timestamp": timestamp.isoformat(),
                "start_position": {
                    "latitude_deg": 47.49 + index * 0.001,
                    "longitude_deg": 19.04 + index * 0.001,
                },
                "end_position": {
                    "latitude_deg": 47.491 + index * 0.001,
                    "longitude_deg": 19.041 + index * 0.001,
                },
            }
        )
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": segments,
            }
        ],
    }


def _station():
    return {
        "station_registry_number": "1026",
        "station_name": "Budapest",
        "watercourse": "Duna",
        "latitude_deg": 47.4948748393782,
        "longitude_deg": 19.0484017196182,
        "river_km": 1646.5,
    }


def _source(*, offsets_hours=(0, 1, 2), station_registry="1026"):
    measurements = []
    for metric in ("WATER_LEVEL", "DISCHARGE"):
        for offset in offsets_hours:
            station = _station()
            station["station_registry_number"] = station_registry
            measurements.append(
                {
                    "measurement_id": f"{metric}-{offset}",
                    "observed_at": (START + timedelta(hours=offset)).isoformat(),
                    "metric_key": metric,
                    "value": 100.0,
                    "unit": "TEST",
                    "source_provider": "OVF_VRAQUERY",
                    "source_product": "VRAQUERY_OPENAPI",
                    "source_type": "OPERATIONAL_HYDROLOGY_OBSERVATION",
                    "station": station,
                }
            )
    return {
        "provider": "OVF_VRAQUERY",
        "product": "VRAQUERY_OPENAPI",
        "measurements": measurements,
    }


def _resolution(
    status="IDENTITY_SUPPORTED",
    *,
    applicable=True,
    resolved=True,
    basis=None,
):
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "applicable": applicable,
                "status": status,
                "resolved_hydrology_source": _station() if resolved else None,
                "evaluated_candidates": [],
                "resolution_basis": basis
                or [
                    "SINGLE_HYDROLOGY_STATION_WATERCOURSE_IDENTITY_MATCH",
                    "NO_AUTHORITATIVE_WATERBODY_STATION_CROSSWALK_CLAIMED",
                ],
            }
        ],
    }


def test_identity_supported_plus_temporal_coverage_is_only_partial():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(),
        _source(),
    )

    route = result["routes"][0]
    assert result["status"] == STATUS_PARTIALLY_REPRESENTATIVE
    assert route["status"] == STATUS_PARTIALLY_REPRESENTATIVE
    assert route["station_identity_supported"] is True
    assert route["authoritative_reach_crosswalk_available"] is False
    assert route["temporal_evidence"]["temporally_supported_segment_fraction"] == 1.0
    assert "NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK" in route["limitations"]


def test_direct_resolved_requires_authoritative_reach_basis_for_full_status():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(status="DIRECT_RESOLVED"),
        _source(),
    )
    assert result["routes"][0]["status"] == STATUS_PARTIALLY_REPRESENTATIVE


def test_direct_resolved_with_authoritative_reach_and_time_support_is_representative():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(
            status="DIRECT_RESOLVED",
            basis=["AUTHORITATIVE_RIVER_REACH_STATION_CROSSWALK"],
        ),
        _source(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_REPRESENTATIVE
    assert route["authoritative_reach_crosswalk_available"] is True


def test_all_candidate_identity_conflicts_are_not_representative():
    resolution = _resolution(status="UNRESOLVED", resolved=False)
    resolution["routes"][0]["evaluated_candidates"] = [
        {"identity_compatibility": "IDENTITY_CONFLICT"}
    ]
    result = build_route_hydrology_representativeness(
        _route_input(), resolution, _source()
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_NOT_REPRESENTATIVE
    assert route["segments"] == []
    assert route["temporal_evidence"]["route_segment_count"] == 4
    assert route["temporal_evidence"]["timestamped_segment_count"] == 4
    assert route["temporal_evidence"]["matching_measurement_count"] == 0
    assert route["temporal_evidence"]["temporally_supported_segment_count"] == 0


def test_ambiguous_source_resolution_is_insufficient_evidence():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(status="AMBIGUOUS", resolved=False),
        _source(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_INSUFFICIENT_EVIDENCE
    assert route["temporal_evidence"]["route_segment_count"] == 4
    assert route["temporal_evidence"]["timestamped_segment_count"] == 4
    assert route["temporal_evidence"]["matching_measurement_count"] == 0
    assert route["temporal_evidence"]["temporally_supported_segment_count"] == 0


def test_marine_not_applicable_stays_not_applicable():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(status="NOT_APPLICABLE", applicable=False, resolved=False),
        _source(),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_NOT_APPLICABLE
    assert route["applicable"] is False
    assert route["temporal_evidence"]["route_segment_count"] == 4
    assert route["temporal_evidence"]["timestamped_segment_count"] == 4
    assert route["temporal_evidence"]["matching_measurement_count"] == 0
    assert route["temporal_evidence"]["temporally_supported_segment_count"] == 0


def test_stale_measurements_do_not_support_representativeness():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(),
        _source(offsets_hours=(24, 25)),
        max_temporal_gap_seconds=3600,
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_INSUFFICIENT_EVIDENCE
    assert route["temporal_evidence"]["temporally_supported_segment_count"] == 0


def test_measurements_from_other_station_are_not_used():
    result = build_route_hydrology_representativeness(
        _route_input(),
        _resolution(),
        _source(station_registry="9999"),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_INSUFFICIENT_EVIDENCE
    assert route["temporal_evidence"]["matching_measurement_count"] == 0


def test_geodesic_distance_is_context_not_representativeness_proof():
    resolution = _resolution()
    source = _source()
    far_station = deepcopy(resolution["routes"][0]["resolved_hydrology_source"])
    far_station["latitude_deg"] = 46.0
    far_station["longitude_deg"] = 18.0
    resolution["routes"][0]["resolved_hydrology_source"] = far_station
    for measurement in source["measurements"]:
        measurement["station"]["latitude_deg"] = 46.0
        measurement["station"]["longitude_deg"] = 18.0

    result = build_route_hydrology_representativeness(
        _route_input(), resolution, source
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_PARTIALLY_REPRESENTATIVE
    assert route["spatial_evidence"]["station_to_route_min_geodesic_m"] > 100_000
    assert route["spatial_evidence"]["geodesic_distance_used_as_representativeness_proof"] is False


def test_metric_temporal_coverage_is_preserved_as_evidence():
    result = build_route_hydrology_representativeness(
        _route_input(), _resolution(), _source()
    )
    metric_coverage = result["routes"][0]["temporal_evidence"]["metric_coverage"]
    assert [item["metric_key"] for item in metric_coverage] == [
        "DISCHARGE",
        "WATER_LEVEL",
    ]
    assert all(item["temporally_supported_segment_fraction"] == 1.0 for item in metric_coverage)


def test_summary_omits_segment_payload_but_keeps_route_evidence():
    full = build_route_hydrology_representativeness(
        _route_input(), _resolution(), _source()
    )
    summary = build_route_hydrology_representativeness_summary(full)

    assert len(full["routes"][0]["segments"]) == 4
    assert "segments" not in summary["routes"][0]
    assert summary["routes"][0]["segments_included"] is False
    assert summary["routes"][0]["status"] == STATUS_PARTIALLY_REPRESENTATIVE


def test_policy_validation_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        build_route_hydrology_representativeness(
            _route_input(), _resolution(), _source(), max_temporal_gap_seconds=0
        )
    with pytest.raises(ValueError):
        build_route_hydrology_representativeness(
            _route_input(),
            _resolution(),
            _source(),
            min_temporal_coverage_fraction=1.5,
        )

def test_negative_branch_preserves_route_count_with_missing_timestamps():
    route_input = _route_input(segment_count=3)
    route_input["routes"][0]["segments"][1]["midpoint_timestamp"] = None
    resolution = _resolution(status="UNRESOLVED", resolved=False)
    resolution["routes"][0]["evaluated_candidates"] = [
        {"identity_compatibility": "IDENTITY_CONFLICT"}
    ]

    result = build_route_hydrology_representativeness(
        route_input, resolution, _source()
    )

    temporal = result["routes"][0]["temporal_evidence"]
    assert temporal["route_segment_count"] == 3
    assert temporal["timestamped_segment_count"] == 2
    assert temporal["matching_measurement_count"] == 0
    assert temporal["temporally_supported_segment_count"] == 0
    assert temporal["temporally_supported_segment_fraction"] == 0.0

