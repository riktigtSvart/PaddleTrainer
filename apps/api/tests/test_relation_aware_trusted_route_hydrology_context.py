from copy import deepcopy

from app.services.relation_aware_trusted_route_hydrology_context import (
    STATUS_MIXED,
    STATUS_NOT_APPLICABLE,
    STATUS_TRUSTED,
    STATUS_TRUSTED_WITH_LIMITATIONS,
    STATUS_WITHHELD,
    TRUST_MODE_DIRECT,
    TRUST_MODE_RELATION,
    build_relation_aware_trusted_route_hydrology_context,
    build_relation_aware_trusted_route_hydrology_context_summary,
)


def _raw_context(*, segment_count=2):
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "segments": [
                    {
                        "segment_index": index,
                        "order_index": index,
                        "water_level": {"value": 300 + index, "unit": "cm"},
                        "discharge": {"value": 1000 + index, "unit": "m3/s"},
                        "water_temperature": {"value": 18 + index, "unit": "degC"},
                        "current_speed_estimate_mps": 9.9,
                        "current_direction_deg": 180.0,
                        "future_metric": {"value": 42},
                    }
                    for index in range(segment_count)
                ],
            }
        ],
    }


def _direct_trust(status="WITHHELD"):
    route = {
        "route_index": 0,
        "exercise_index": 0,
        "available": True,
        "applicable": status != "NOT_APPLICABLE",
        "representativeness_status": "NOT_REPRESENTATIVE",
        "trust_status": status,
        "source_context_available": True,
        "hydrology_context_included": False,
        "usable_for_downstream_environment_context": False,
        "usable_with_limitations": False,
        "source_context_segment_count": 2,
        "trusted_context_segment_count": 0,
        "withheld_context_segment_count": 2,
        "segment_filter_applied": False,
        "representativeness_resolution_basis": ["DIRECT_REPRESENTATIVENESS_CHECK"],
        "representativeness_limitations": ["IDENTITY_CONFLICT"],
        "trust_basis": ["HYDROLOGY_CONTEXT_WITHHELD_NOT_REPRESENTATIVE"],
        "trusted_context": None,
    }
    if status in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"}:
        route.update(
            {
                "representativeness_status": "REPRESENTATIVE",
                "hydrology_context_included": True,
                "usable_for_downstream_environment_context": True,
                "usable_with_limitations": status == "TRUSTED_WITH_LIMITATIONS",
                "trusted_context_segment_count": 2,
                "withheld_context_segment_count": 0,
                "segment_filter_applied": True,
                "trusted_context": deepcopy(_raw_context()["routes"][0]),
            }
        )
    return {"schema_version": "0.1", "routes": [route]}


def _relation(*, water_level=True, discharge=False, temperature=False):
    rows = []
    for metric_key, supported, relation_id in (
        ("WATER_LEVEL", water_level, "rel-water"),
        ("DISCHARGE", discharge, "rel-discharge"),
        ("WATER_TEMPERATURE", temperature, "rel-temp"),
    ):
        rows.append(
            {
                "metric_key": metric_key,
                "decision": "TRANSFER_SUPPORTED" if supported else "TRANSFER_WITHHELD",
                "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
                "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
                "relation_id": relation_id,
                "source": {
                    "station_registry_number": "1026",
                    "station_name": "Budapest",
                    "watercourse": "Duna",
                },
                "limitations": [f"{metric_key}_CROSS_WATERBODY_PROXY"],
            }
        )
    return {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "SUPPORTED_WITH_LIMITATIONS",
                "metric_relations": rows,
            }
        ],
    }


def test_existing_direct_trust_takes_precedence_and_is_not_metric_filtered():
    direct = _direct_trust("TRUSTED")
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), direct, _relation(water_level=True, discharge=False)
    )
    route = result["routes"][0]
    segment = route["trusted_context"]["segments"][0]
    assert route["trust_status"] == STATUS_TRUSTED
    assert route["trust_mode"] == TRUST_MODE_DIRECT
    assert route["relation_metric_projection_applied"] is False
    assert "water_level" in segment
    assert "discharge" in segment


def test_relation_can_authorize_water_level_without_authorizing_discharge():
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), _relation(water_level=True, discharge=False)
    )
    route = result["routes"][0]
    segment = route["trusted_context"]["segments"][0]
    assert route["trust_status"] == STATUS_TRUSTED_WITH_LIMITATIONS
    assert route["trust_mode"] == TRUST_MODE_RELATION
    assert route["authorized_metric_keys"] == ["WATER_LEVEL"]
    assert "DISCHARGE" in route["withheld_metric_keys"]
    assert segment["water_level"]["value"] == 300
    assert "discharge" not in segment
    assert "water_temperature" not in segment


def test_relation_derived_projection_never_copies_current_velocity_fields():
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), _relation(water_level=True)
    )
    segment = result["routes"][0]["trusted_context"]["segments"][0]
    assert "current_speed_estimate_mps" not in segment
    assert "current_direction_deg" not in segment


def test_relation_derived_projection_does_not_copy_unknown_future_metrics():
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), _relation(water_level=True)
    )
    segment = result["routes"][0]["trusted_context"]["segments"][0]
    assert "future_metric" not in segment


def test_multiple_explicitly_supported_metrics_are_each_projected():
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(),
        _direct_trust(),
        _relation(water_level=True, discharge=True, temperature=False),
    )
    route = result["routes"][0]
    segment = route["trusted_context"]["segments"][0]
    assert route["authorized_metric_keys"] == ["WATER_LEVEL", "DISCHARGE"]
    assert "water_level" in segment
    assert "discharge" in segment
    assert "water_temperature" not in segment


def test_supported_unknown_relation_metric_is_withheld_until_payload_mapping_exists():
    relation = _relation(water_level=False)
    relation["routes"][0]["metric_relations"].append(
        {
            "metric_key": "SEDIMENT_LOAD",
            "decision": "TRANSFER_SUPPORTED",
            "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
            "relation_type": "EMPIRICAL_PROXY",
            "relation_id": "rel-sediment",
            "source": {"station_registry_number": "1026"},
            "limitations": [],
        }
    )
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), relation
    )
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["unsupported_metric_payload_keys"] == ["SEDIMENT_LOAD"]
    assert "METRIC_PAYLOAD_MAPPING_REQUIRED_BEFORE_TRUSTED_TRANSFER" in (
        route["representativeness_limitations"]
    )


def test_ambiguous_relation_is_withheld():
    relation = _relation()
    relation["routes"][0]["status"] = "AMBIGUOUS"
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), relation
    )
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_WITHHELD
    assert route["trusted_context"] is None
    assert "HYDROLOGY_RELATION_AMBIGUOUS" in route["trust_basis"]


def test_withheld_relation_does_not_override_direct_withheld_state():
    relation = _relation()
    relation["routes"][0]["status"] = "WITHHELD"
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), relation
    )
    assert result["routes"][0]["trust_status"] == STATUS_WITHHELD


def test_relation_cannot_create_measurement_evidence_without_raw_source_context():
    result = build_relation_aware_trusted_route_hydrology_context(
        None, _direct_trust(), _relation()
    )
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_WITHHELD
    assert "RELATION_CANNOT_CREATE_MEASUREMENT_EVIDENCE" in route["trust_basis"]


def test_segment_without_authorized_metric_payload_is_not_included():
    raw = _raw_context(segment_count=2)
    raw["routes"][0]["segments"][1]["water_level"] = None
    result = build_relation_aware_trusted_route_hydrology_context(
        raw, _direct_trust(), _relation(water_level=True)
    )
    route = result["routes"][0]
    assert route["trusted_context_segment_count"] == 1
    assert route["withheld_context_segment_count"] == 1
    assert [s["segment_index"] for s in route["trusted_context"]["segments"]] == [0]


def test_relation_not_applicable_remains_not_applicable_when_direct_is_withheld():
    relation = _relation()
    relation["routes"][0]["status"] = "NOT_APPLICABLE"
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), relation
    )
    route = result["routes"][0]
    assert route["trust_status"] == STATUS_NOT_APPLICABLE
    assert route["trusted_context"] is None


def test_direct_not_applicable_has_precedence():
    direct = _direct_trust("NOT_APPLICABLE")
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), direct, _relation(water_level=True)
    )
    assert result["routes"][0]["trust_status"] == STATUS_NOT_APPLICABLE


def test_relation_derived_trust_is_never_promoted_to_fully_trusted():
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(),
        _direct_trust(),
        _relation(water_level=True, discharge=True, temperature=True),
    )
    assert result["routes"][0]["trust_status"] == STATUS_TRUSTED_WITH_LIMITATIONS


def test_builder_does_not_mutate_any_input():
    raw = _raw_context()
    direct = _direct_trust()
    relation = _relation()
    before = tuple(deepcopy(value) for value in (raw, direct, relation))
    build_relation_aware_trusted_route_hydrology_context(raw, direct, relation)
    assert (raw, direct, relation) == before


def test_summary_removes_relation_derived_segment_payloads():
    full = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), _relation()
    )
    summary = build_relation_aware_trusted_route_hydrology_context_summary(full)
    route = summary["routes"][0]
    assert route["segments_included"] is False
    assert route["trusted_context"]["segments_included"] is False
    assert "segments" not in route["trusted_context"]
    assert route["authorized_metric_keys"] == ["WATER_LEVEL"]


def test_mixed_overall_status_is_explicit():
    raw = _raw_context()
    raw["routes"].append(
        {
            "route_index": 1,
            "exercise_index": 1,
            "segments": [{"segment_index": 0, "water_level": {"value": 1}}],
        }
    )
    direct = _direct_trust("TRUSTED")
    direct["routes"].append(
        {
            "route_index": 1,
            "exercise_index": 1,
            "trust_status": "WITHHELD",
            "trusted_context": None,
        }
    )
    relation = _relation()
    relation["routes"].append(
        {
            "route_index": 1,
            "exercise_index": 1,
            "status": "SUPPORTED_WITH_LIMITATIONS",
            "metric_relations": deepcopy(relation["routes"][0]["metric_relations"]),
        }
    )
    result = build_relation_aware_trusted_route_hydrology_context(raw, direct, relation)
    assert result["status"] == STATUS_MIXED
    assert result["trusted_route_count"] == 1
    assert result["trusted_with_limitations_route_count"] == 1


def test_scope_explicitly_forbids_current_inference_and_unapproved_metric_copying():
    result = build_relation_aware_trusted_route_hydrology_context(
        _raw_context(), _direct_trust(), _relation()
    )
    scope = result["scope"]
    assert scope["controls_relation_derived_metric_inclusion"] is True
    assert scope["copies_unapproved_hydrology_metrics"] is False
    assert scope["estimates_local_current_velocity"] is False
    assert scope["infers_current_from_water_level"] is False
    assert scope["infers_current_from_discharge"] is False
