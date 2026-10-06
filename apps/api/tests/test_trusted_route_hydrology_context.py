from __future__ import annotations

from copy import deepcopy

from app.services.trusted_route_hydrology_context import (
    STATUS_MIXED,
    STATUS_NOT_APPLICABLE,
    STATUS_TRUSTED,
    STATUS_TRUSTED_WITH_LIMITATIONS,
    STATUS_WITHHELD,
    build_trusted_route_hydrology_context,
    build_trusted_route_hydrology_context_summary,
)


def _source_context(*, route_index=0, segment_count=3):
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": route_index,
                "exercise_index": route_index,
                "available": True,
                "matched_measurement_count": 6,
                "segments": [
                    {
                        "segment_index": index,
                        "water_level": {"value": 300 + index, "unit": "cm"},
                        "discharge": {"value": 1000 + index, "unit": "m3/s"},
                        "current_speed_estimate_mps": None,
                        "current_direction_deg": None,
                    }
                    for index in range(segment_count)
                ],
            }
        ],
    }


def _representativeness(status="PARTIALLY_REPRESENTATIVE", *, route_index=0):
    limitations = (
        [
            "NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK",
            "ALONG_RIVER_DISTANCE_NOT_ESTABLISHED",
        ]
        if status == "PARTIALLY_REPRESENTATIVE"
        else []
    )
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.2",
        "routes": [
            {
                "route_index": route_index,
                "exercise_index": route_index,
                "available": True,
                "applicable": status != "NOT_APPLICABLE",
                "status": status,
                "resolution_basis": [f"REPRESENTATIVENESS_{status}"],
                "limitations": limitations,
                "segments": [
                    {
                        "segment_index": index,
                        "temporally_supported": True,
                    }
                    for index in range(3)
                ] if status in {
                    "REPRESENTATIVE",
                    "PARTIALLY_REPRESENTATIVE",
                } else [],
            }
        ],
    }


def test_representative_context_is_trusted_and_included():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("REPRESENTATIVE"),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_TRUSTED
    assert result["trusted_route_count"] == 1
    assert route["trust_status"] == STATUS_TRUSTED
    assert route["hydrology_context_included"] is True
    assert route["usable_for_downstream_environment_context"] is True
    assert route["usable_with_limitations"] is False
    assert route["trusted_context_segment_count"] == 3
    assert len(route["trusted_context"]["segments"]) == 3


def test_partial_context_is_trusted_with_limitations_and_propagates_them():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("PARTIALLY_REPRESENTATIVE"),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert result["trusted_with_limitations_route_count"] == 1
    assert route["trust_status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert route["hydrology_context_included"] is True
    assert route["usable_with_limitations"] is True
    assert "NO_AUTHORITATIVE_ROUTE_REACH_TO_STATION_CROSSWALK" in route[
        "representativeness_limitations"
    ]
    assert "REPRESENTATIVENESS_LIMITATIONS_MUST_PROPAGATE_DOWNSTREAM" in route[
        "trust_basis"
    ]


def test_insufficient_evidence_withholds_context_but_preserves_source_evidence():
    source = _source_context()
    result = build_trusted_route_hydrology_context(
        source,
        _representativeness("INSUFFICIENT_EVIDENCE"),
    )
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["source_context_available"] is True
    assert route["source_context_segment_count"] == 3
    assert route["trusted_context_segment_count"] == 0
    assert route["trusted_context"] is None
    assert len(source["routes"][0]["segments"]) == 3


def test_not_representative_withholds_context():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("NOT_REPRESENTATIVE"),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_WITHHELD
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["hydrology_context_included"] is False
    assert "HYDROLOGY_CONTEXT_WITHHELD_NOT_REPRESENTATIVE" in route["trust_basis"]


def test_not_applicable_never_includes_river_hydrology_context():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("NOT_APPLICABLE"),
    )
    route = result["routes"][0]
    assert result["status"] == STATUS_NOT_APPLICABLE
    assert route["applicable"] is False
    assert route["trust_status"] == STATUS_NOT_APPLICABLE
    assert route["hydrology_context_included"] is False
    assert route["trusted_context"] is None


def test_missing_source_context_cannot_become_trusted():
    result = build_trusted_route_hydrology_context(
        None,
        _representativeness("REPRESENTATIVE"),
    )
    route = result["routes"][0]
    assert route["representativeness_status"] == "REPRESENTATIVE"
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["source_context_available"] is False
    assert "TRUST_CANNOT_BE_CREATED_WITHOUT_SOURCE_EVIDENCE" in route["trust_basis"]


def test_unknown_representativeness_status_is_withheld_conservatively():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("FUTURE_UNKNOWN_STATUS"),
    )
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["trusted_context"] is None
    assert "HYDROLOGY_CONTEXT_WITHHELD_CONSERVATIVELY" in route["trust_basis"]


def test_context_route_without_representativeness_is_withheld():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        {"schema_version": "0.2", "routes": []},
    )
    route = result["routes"][0]
    assert route["representativeness_status"] is None
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["source_context_available"] is True


def test_builder_does_not_mutate_source_context_or_representativeness():
    source = _source_context()
    rep = _representativeness("PARTIALLY_REPRESENTATIVE")
    source_before = deepcopy(source)
    rep_before = deepcopy(rep)

    result = build_trusted_route_hydrology_context(source, rep)
    result["routes"][0]["trusted_context"]["segments"][0]["water_level"]["value"] = -1

    assert source == source_before
    assert rep == rep_before


def test_summary_omits_trusted_segment_payload_but_keeps_counts_and_metadata():
    full = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("PARTIALLY_REPRESENTATIVE"),
    )
    summary = build_trusted_route_hydrology_context_summary(full)
    route = summary["routes"][0]
    assert route["trusted_context_segment_count"] == 3
    assert route["segments_included"] is False
    assert "segments" not in route["trusted_context"]
    assert route["trusted_context"]["segments_included"] is False


def test_mixed_route_status_is_explicit_and_counts_are_preserved():
    source = _source_context(route_index=0, segment_count=2)
    source["routes"].append(
        {
            "route_index": 1,
            "exercise_index": 1,
            "segments": [{"segment_index": 0}],
        }
    )
    rep = _representativeness("REPRESENTATIVE", route_index=0)
    rep["routes"].append(
        {
            "route_index": 1,
            "exercise_index": 1,
            "status": "NOT_REPRESENTATIVE",
            "limitations": ["IDENTITY_CONFLICT"],
            "resolution_basis": ["CONFLICT"],
        }
    )

    result = build_trusted_route_hydrology_context(source, rep)
    assert result["status"] == STATUS_MIXED
    assert result["trusted_route_count"] == 1
    assert result["withheld_route_count"] == 1


def test_only_temporally_supported_segments_are_included_in_trusted_projection():
    source = _source_context(segment_count=3)
    rep = _representativeness("PARTIALLY_REPRESENTATIVE")
    rep["routes"][0]["segments"][1]["temporally_supported"] = False

    result = build_trusted_route_hydrology_context(source, rep)
    route = result["routes"][0]
    trusted_indices = [
        segment["segment_index"]
        for segment in route["trusted_context"]["segments"]
    ]
    assert route["trust_status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert route["source_context_segment_count"] == 3
    assert route["trusted_context_segment_count"] == 2
    assert route["withheld_context_segment_count"] == 1
    assert trusted_indices == [0, 2]


def test_accepted_route_without_segment_support_rows_is_withheld():
    rep = _representativeness("PARTIALLY_REPRESENTATIVE")
    rep["routes"][0]["segments"] = []

    result = build_trusted_route_hydrology_context(_source_context(), rep)
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["trusted_context"] is None
    assert "REPRESENTATIVENESS_SEGMENT_SUPPORT_UNAVAILABLE" in route["trust_basis"]


def test_scope_explicitly_forbids_current_inference_and_marks_gating_role():
    result = build_trusted_route_hydrology_context(
        _source_context(),
        _representativeness("PARTIALLY_REPRESENTATIVE"),
    )
    scope = result["scope"]
    assert scope["controls_downstream_hydrology_context_use"] is True
    assert scope["preserves_source_route_hydrology_context"] is True
    assert scope["estimates_local_current_velocity"] is False
    assert scope["infers_current_from_water_level"] is False
    assert scope["infers_current_from_discharge"] is False
    trusted_segment = result["routes"][0]["trusted_context"]["segments"][0]
    assert trusted_segment["current_speed_estimate_mps"] is None
    assert trusted_segment["current_direction_deg"] is None
