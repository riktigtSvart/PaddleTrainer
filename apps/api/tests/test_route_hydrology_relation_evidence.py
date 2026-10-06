from copy import deepcopy

from app.services.route_hydrology_relation_evidence import (
    METRIC_TRANSFER_AMBIGUOUS,
    METRIC_TRANSFER_SUPPORTED,
    METRIC_TRANSFER_WITHHELD,
    STATUS_AMBIGUOUS,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_REQUIRED,
    STATUS_SUPPORTED_WITH_LIMITATIONS,
    STATUS_UNAVAILABLE,
    STATUS_WITHHELD,
    build_route_hydrology_relation_evidence,
    build_route_hydrology_relation_evidence_summary,
)


def _route_input():
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "start_timestamp": "2026-08-29T06:00:00+02:00",
                        "midpoint_timestamp": "2026-08-29T06:00:30+02:00",
                        "end_timestamp": "2026-08-29T06:01:00+02:00",
                    }
                ],
            }
        ],
    }


def _unresolved_source_resolution(*, waterbody_name="Szentendrei-Duna"):
    candidate = {
        "source_provider": "OVF_VRAQUERY",
        "station_registry_number": "1026",
        "station_name": "Budapest",
        "watercourse": "Duna",
        "latitude_deg": 47.49,
        "longitude_deg": 19.04,
    }
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "applicable": True,
                "status": "UNRESOLVED",
                "trusted_river_inland_identities": [
                    {
                        "waterbody_id": "HU:BRANCH:1",
                        "identity_names": [waterbody_name],
                    }
                ],
                "resolved_hydrology_source": None,
                "evaluated_candidates": [
                    {
                        "candidate_source": candidate,
                        "identity_compatibility": "IDENTITY_CONFLICT",
                    }
                ],
            }
        ],
    }


def _direct_source_resolution():
    result = _unresolved_source_resolution()
    route = result["routes"][0]
    route["status"] = "IDENTITY_SUPPORTED"
    route["resolved_hydrology_source"] = deepcopy(
        route["evaluated_candidates"][0]["candidate_source"]
    )
    route["resolved_hydrology_source"]["watercourse"] = "Szentendrei-Duna"
    return result


def _catalog(relation):
    return {
        "provider": "TEST_AUTHORITY",
        "product": "HYDROLOGY_RELATIONS",
        "schema_version": "0.1",
        "relations": [relation],
    }


def _uncontrolled_relation(*, water_level_allowed=True, discharge_allowed=False):
    return {
        "relation_id": "relation-1",
        "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
        "target": {
            "waterbody_ids": ["HU:BRANCH:1"],
            "waterbody_names": ["Szentendrei-Duna"],
        },
        "source": {"station_registry_numbers": [1026]},
        "authority": {
            "provider": "TEST_AUTHORITY",
            "product": "OFFICIAL_RELATION_REGISTER",
            "reference": "REL-001",
        },
        "metrics": [
            {
                "metric_key": "WATER_LEVEL",
                "transfer_allowed": water_level_allowed,
                "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
                "limitations": ["CROSS_WATERBODY_WATER_LEVEL_PROXY"],
            },
            {
                "metric_key": "DISCHARGE",
                "transfer_allowed": discharge_allowed,
                "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
            },
        ],
    }


def test_direct_local_identity_does_not_require_cross_waterbody_relation():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _direct_source_resolution(),
        None,
    )
    assert result["routes"][0]["status"] == STATUS_NOT_REQUIRED


def test_unresolved_branch_without_catalog_is_unavailable():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        None,
    )
    assert result["routes"][0]["status"] == STATUS_UNAVAILABLE


def test_uncontrolled_connection_can_support_water_level_but_withhold_discharge():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(_uncontrolled_relation()),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_SUPPORTED_WITH_LIMITATIONS
    by_metric = {item["metric_key"]: item for item in route["metric_relations"]}
    assert by_metric["WATER_LEVEL"]["decision"] == METRIC_TRANSFER_SUPPORTED
    assert by_metric["WATER_LEVEL"]["representativeness_ceiling"] == (
        "PARTIALLY_REPRESENTATIVE"
    )
    assert by_metric["DISCHARGE"]["decision"] == METRIC_TRANSFER_WITHHELD
    assert "WATER_LEVEL" in route["selected_source_by_metric"]
    assert "DISCHARGE" not in route["selected_source_by_metric"]


def test_topological_connection_without_explicit_metric_transfer_is_withheld():
    relation = _uncontrolled_relation(
        water_level_allowed=False,
        discharge_allowed=False,
    )
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(relation),
    )
    assert result["routes"][0]["status"] == STATUS_WITHHELD


def test_structure_controlled_branch_requires_control_state_evidence():
    relation = _uncontrolled_relation()
    relation["relation_type"] = "STRUCTURE_CONTROLLED"
    relation["control_structure_state_required"] = True
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(waterbody_name="Controlled branch"),
        _catalog({
            **relation,
            "target": {"waterbody_ids": ["HU:BRANCH:1"]},
        }),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    water_level = next(
        item for item in route["metric_relations"] if item["metric_key"] == "WATER_LEVEL"
    )
    assert "CONTROL_STRUCTURE_STATE_EVIDENCE_REQUIRED" in water_level["limitations"]


def test_structure_controlled_branch_can_be_represented_when_control_state_is_supplied():
    relation = _uncontrolled_relation()
    relation["relation_type"] = "STRUCTURE_CONTROLLED"
    relation["control_structure_state_required"] = True
    relation["control_state_evidence"] = {
        "available": True,
        "source": "OFFICIAL_OPERATIONAL_STATE",
    }
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(waterbody_name="Controlled branch"),
        _catalog({
            **relation,
            "target": {"waterbody_ids": ["HU:BRANCH:1"]},
        }),
    )
    assert result["routes"][0]["status"] == STATUS_SUPPORTED_WITH_LIMITATIONS


def test_missing_authoritative_relation_provenance_withholds_transfer():
    relation = _uncontrolled_relation()
    relation["authority"] = {}
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(relation),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    assert any(
        "AUTHORITATIVE_RELATION_PROVENANCE_MISSING" in item["limitations"]
        for item in route["metric_relations"]
    )


def test_empirical_proxy_requires_calibration_evidence():
    relation = _uncontrolled_relation(discharge_allowed=False)
    relation["relation_type"] = "EMPIRICAL_PROXY"
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(relation),
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_WITHHELD
    water_level = next(
        item for item in route["metric_relations"] if item["metric_key"] == "WATER_LEVEL"
    )
    assert (
        "CALIBRATION_EVIDENCE_REQUIRED_FOR_PROXY_OR_MODEL_TRANSFER"
        in water_level["limitations"]
    )


def test_empirical_proxy_with_calibration_can_support_metric_transfer():
    relation = _uncontrolled_relation(discharge_allowed=False)
    relation["relation_type"] = "EMPIRICAL_PROXY"
    relation["calibration_evidence"] = {
        "available": True,
        "reference": "calibration-1",
    }
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(relation),
    )
    assert result["routes"][0]["status"] == STATUS_SUPPORTED_WITH_LIMITATIONS


def test_wrong_station_relation_does_not_transfer():
    relation = _uncontrolled_relation()
    relation["source"] = {"station_registry_numbers": [9999]}
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(relation),
    )
    assert result["routes"][0]["status"] == STATUS_WITHHELD
    assert result["routes"][0]["metric_relations"] == []


def test_relation_outside_declared_validity_window_does_not_transfer():
    relation = _uncontrolled_relation()
    relation["valid_to"] = "2026-08-01T00:00:00+02:00"
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(relation),
    )
    assert result["routes"][0]["status"] == STATUS_WITHHELD


def test_two_distinct_supported_relations_for_same_metric_are_ambiguous():
    relation_a = _uncontrolled_relation(discharge_allowed=False)
    relation_b = deepcopy(relation_a)
    relation_b["relation_id"] = "relation-2"
    catalog = _catalog(relation_a)
    catalog["relations"].append(relation_b)

    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        catalog,
    )
    route = result["routes"][0]
    assert route["status"] == STATUS_AMBIGUOUS
    water_level = next(
        item for item in route["metric_relations"] if item["metric_key"] == "WATER_LEVEL"
    )
    assert water_level["decision"] == METRIC_TRANSFER_AMBIGUOUS


def test_marine_or_not_applicable_route_remains_not_applicable():
    source = _unresolved_source_resolution()
    source["routes"][0]["status"] = "NOT_APPLICABLE"
    source["routes"][0]["applicable"] = False
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        source,
        _catalog(_uncontrolled_relation()),
    )
    assert result["routes"][0]["status"] == STATUS_NOT_APPLICABLE


def test_summary_omits_detailed_evaluated_relations():
    result = build_route_hydrology_relation_evidence(
        _route_input(),
        _unresolved_source_resolution(),
        _catalog(_uncontrolled_relation()),
    )
    summary = build_route_hydrology_relation_evidence_summary(result)
    assert "evaluated_relations" not in summary["routes"][0]
    assert summary["routes"][0]["evaluated_relations_included"] is False


def test_builder_does_not_mutate_inputs():
    route_input = _route_input()
    source = _unresolved_source_resolution()
    catalog = _catalog(_uncontrolled_relation())
    originals = tuple(deepcopy(item) for item in (route_input, source, catalog))

    build_route_hydrology_relation_evidence(route_input, source, catalog)

    assert (route_input, source, catalog) == originals
