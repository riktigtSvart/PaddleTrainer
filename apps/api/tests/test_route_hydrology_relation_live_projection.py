from app.services.hydrology_relation_catalog import build_hydrology_relation_catalog
from app.services.kdvvizig_hydrology_relation_catalog import (
    build_kdvvizig_hydrology_relation_catalog,
)
from app.services.route_hydrology_relation_live_projection import (
    build_route_hydrology_relation_live_projection,
    build_route_hydrology_relation_live_projection_summary,
)


def _route_input(name="Branch A"):
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "segment_index": 0,
                        "start_timestamp": "2026-08-29T06:00:00+02:00",
                        "end_timestamp": "2026-08-29T06:01:00+02:00",
                    }
                ],
            }
        ],
    }


def _resolution(name="Branch A", station=1026, status="UNRESOLVED", watercourse="Duna"):
    candidate = {
        "station_registry_number": str(station),
        "station_name": "station",
        "watercourse": watercourse,
    }
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": status,
                "applicable": True,
                "trusted_river_inland_identities": [
                    {"waterbody_id": None, "identity_names": [name]}
                ],
                "resolved_hydrology_source": (
                    candidate if status == "IDENTITY_SUPPORTED" else None
                ),
                "evaluated_candidates": [{"candidate_source": candidate}],
            }
        ],
    }


def _raw_context():
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "segment_index": 0,
                        "start_timestamp": "2026-08-29T06:00:00+02:00",
                        "end_timestamp": "2026-08-29T06:01:00+02:00",
                        "water_level": {"value": 300, "unit": "cm"},
                        "discharge": {"value": 1000, "unit": "m3/s"},
                        "current_speed_estimate_mps": 1.5,
                    }
                ],
            }
        ],
    }


def _direct_trust(status="WITHHELD"):
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "trust_status": status,
                "hydrology_context_included": status.startswith("TRUSTED"),
                "trusted_context": _raw_context()["routes"][0] if status.startswith("TRUSTED") else None,
            }
        ],
    }


def _positive_catalog():
    return build_hydrology_relation_catalog(
        provider="TEST_AUTH",
        product="POSITIVE_RELATION",
        relations=[
            {
                "relation_id": "positive-1",
                "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
                "target": {"waterbody_names": ["Branch A"]},
                "source": {"station_registry_numbers": [1026]},
                "authority": {"provider": "AUTH", "reference": "DOC-1"},
                "metrics": [
                    {
                        "metric_key": "WATER_LEVEL",
                        "transfer_allowed": True,
                        "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
                    },
                    {
                        "metric_key": "DISCHARGE",
                        "transfer_allowed": False,
                        "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                    },
                ],
            }
        ],
    )


def test_no_catalog_is_semantic_noop_for_existing_direct_trust():
    direct = _direct_trust("TRUSTED_WITH_LIMITATIONS")
    result = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(status="IDENTITY_SUPPORTED"),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=direct,
        relation_catalog=None,
    )
    assert result["enabled"] is False
    assert result["effective_trusted_route_hydrology_context"] is direct
    assert result["relation_derived_hydrology_in_use"] is False


def test_direct_trust_has_precedence_even_when_catalog_is_enabled():
    direct = _direct_trust("TRUSTED_WITH_LIMITATIONS")
    result = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input("Szentendrei-Duna"),
        route_hydrology_source_resolution=_resolution(
            name="Szentendrei-Duna",
            station=1038,
            status="IDENTITY_SUPPORTED",
            watercourse="Szentendrei-Duna",
        ),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=direct,
        relation_catalog=build_kdvvizig_hydrology_relation_catalog(),
    )
    route = result["effective_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_mode"] == "DIRECT_TRUST_PROJECTION"
    assert route["trust_status"] == "TRUSTED_WITH_LIMITATIONS"
    assert result["relation_derived_hydrology_in_use"] is False


def test_official_rsd_catalog_withholds_budapest_1026_as_branch_proxy():
    result = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input("Ráckevei (Soroksári)-Duna"),
        route_hydrology_source_resolution=_resolution(
            name="Ráckevei (Soroksári)-Duna",
            station=1026,
            status="UNRESOLVED",
        ),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=_direct_trust("WITHHELD"),
        relation_catalog=build_kdvvizig_hydrology_relation_catalog(),
    )
    assert result["status"] == "WITHHELD"
    route = result["effective_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "WITHHELD"
    assert route["trusted_context"] is None
    assert result["relation_derived_hydrology_in_use"] is False


def test_positive_relation_projects_only_authorized_metric_and_marks_lineage_need():
    result = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=_direct_trust("WITHHELD"),
        relation_catalog=_positive_catalog(),
    )
    route = result["effective_trusted_route_hydrology_context"]["routes"][0]
    segment = route["trusted_context"]["segments"][0]
    assert route["trust_mode"] == "RELATION_DERIVED_METRIC_PROJECTION"
    assert segment["water_level"]["value"] == 300
    assert "discharge" not in segment
    assert "current_speed_estimate_mps" not in segment
    assert result["relation_derived_hydrology_in_use"] is True
    assert result["persistence_requires_relation_lineage"] is True


def test_live_projection_summary_does_not_duplicate_effective_segment_payloads():
    full = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=_raw_context(),
        trusted_route_hydrology_context=_direct_trust("WITHHELD"),
        relation_catalog=_positive_catalog(),
    )
    summary = build_route_hydrology_relation_live_projection_summary(full)
    assert "route_hydrology_relation_evidence" not in summary
    assert "relation_aware_trusted_route_hydrology_context" not in summary
    assert "effective_trusted_route_hydrology_context" not in summary
    assert summary["full_relation_evidence_included"] is False
    assert summary["full_relation_aware_trusted_context_included"] is False
    assert summary["effective_trusted_route_hydrology_context_included"] is False
    relation_summary = summary["route_hydrology_relation_evidence_summary"]
    assert relation_summary["routes"][0]["evaluated_relations_included"] is False


def test_relation_catalog_never_creates_measurement_evidence_without_raw_context():
    result = build_route_hydrology_relation_live_projection(
        route_environment_context_input=_route_input(),
        route_hydrology_source_resolution=_resolution(),
        route_hydrology_context=None,
        trusted_route_hydrology_context=_direct_trust("WITHHELD"),
        relation_catalog=_positive_catalog(),
    )
    route = result["effective_trusted_route_hydrology_context"]["routes"][0]
    assert route["trust_status"] == "WITHHELD"
    assert route["trusted_context"] is None
