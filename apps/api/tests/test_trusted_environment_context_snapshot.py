from copy import deepcopy

from app.services.trusted_environment_context_snapshot import (
    build_trusted_route_environment_context_snapshot,
    trusted_environment_context_snapshot_hash,
    verify_trusted_environment_context_snapshot,
)


EVIDENCE_SET_ID = "7d68281a-ecb3-4a91-a726-2ceed5800beb"


def _water_snapshot(identity_hash="a" * 64):
    return {
        "snapshot_schema_version": "0.1",
        "identity_schema_version": "0.1",
        "identity_hash": identity_hash,
    }


def _hydrology_snapshot(decision_hash="b" * 64):
    return {
        "snapshot_schema_version": "0.1",
        "decision_hash": decision_hash,
        "decision_status": "TRUSTED_WITH_LIMITATIONS",
    }


def _component(status, usable, *, included=None, applicable=True):
    if included is None:
        included = usable
    return {
        "status": status,
        "available": status != "UNAVAILABLE",
        "applicable": applicable,
        "included": included,
        "usable_for_downstream_environment_context": usable,
    }


def _segment(
    order_index,
    *,
    water="TRUSTED",
    weather="TRUSTED_WITH_LIMITATIONS",
    wind="TRUSTED_WITH_LIMITATIONS",
    hydrology="TRUSTED_WITH_LIMITATIONS",
):
    components = {
        "water_identity": _component(water, water == "TRUSTED"),
        "weather": _component(
            weather,
            weather in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"},
        ),
        "wind": _component(
            wind,
            wind in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"},
        ),
        "hydrology": _component(
            hydrology,
            hydrology in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"},
            applicable=hydrology != "NOT_APPLICABLE",
        ),
    }
    overall = (
        "TRUSTED_WITH_LIMITATIONS"
        if any(
            value["status"] == "TRUSTED_WITH_LIMITATIONS"
            for value in components.values()
            if value["usable_for_downstream_environment_context"]
        )
        else "TRUSTED"
    )
    if not any(
        value["usable_for_downstream_environment_context"]
        for value in components.values()
    ):
        overall = "WITHHELD"
    return {
        "order_index": order_index,
        "segment_index": order_index,
        "status": overall,
        "usable_for_downstream_environment_context": overall
        in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"},
        "usable_with_limitations": overall == "TRUSTED_WITH_LIMITATIONS",
        "component_statuses": {
            key: value["status"] for key, value in components.items()
        },
        **components,
        "trust_basis": ["BASIS_B", "BASIS_A"],
        "limitations": ["LIMIT_B", "LIMIT_A"],
    }


def _trusted_context(*, hydrology_status="TRUSTED_WITH_LIMITATIONS"):
    segments = [
        _segment(0, hydrology=hydrology_status),
        _segment(1, hydrology=hydrology_status),
        _segment(2, wind="UNAVAILABLE", hydrology=hydrology_status),
    ]
    hydrology_usable = (
        3
        if hydrology_status in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"}
        else 0
    )
    return {
        "provider": "PADDLETRAINER",
        "schema_version": "0.1",
        "available": True,
        "status": "TRUSTED_WITH_LIMITATIONS",
        "route_count": 1,
        "trusted_route_count": 0,
        "trusted_with_limitations_route_count": 1,
        "withheld_route_count": 0,
        "unavailable_route_count": 0,
        "not_applicable_route_count": 0,
        "input_provenance": {
            "route_environment_context_input_schema_version": "0.1",
            "route_water_environment_identity_schema_version": "0.1",
            "route_weather_sample_matching_schema_version": None,
            "route_wind_context_schema_version": None,
            "trusted_route_hydrology_context_schema_version": "0.1",
            "weather_source_provider": "OPEN_METEO",
            "weather_source_product": "HISTORICAL_WEATHER_API",
            "weather_source_type": "MODELLED_HISTORICAL_WEATHER",
        },
        "policy": {
            "trusted_water_identity_statuses": [
                "CONTINUITY_SUPPORTED",
                "DIRECT_RESOLVED",
            ],
            "weather_match_available": "TRUSTED_WITH_LIMITATIONS",
            "wind_context_available": "TRUSTED_WITH_LIMITATIONS",
            "hydrology_trust_status_passthrough": True,
            "component_promotion_allowed": False,
            "segment_environment_usable_when_any_component_usable": True,
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "status": "TRUSTED_WITH_LIMITATIONS",
                "segment_count": 3,
                "trusted_segment_count": 0,
                "trusted_with_limitations_segment_count": 3,
                "withheld_segment_count": 0,
                "unavailable_segment_count": 0,
                "not_applicable_segment_count": 0,
                "downstream_usable_segment_count": 3,
                "water_identity_usable_segment_count": 3,
                "weather_usable_segment_count": 3,
                "wind_usable_segment_count": 2,
                "hydrology_usable_segment_count": hydrology_usable,
                "hydrology_route_trust_status": hydrology_status,
                "environment_types": ["RIVER_INLAND"],
                "mixed_environment_route": False,
                "route_limitations": ["LIMIT_B", "LIMIT_A"],
                "segments": segments,
            }
        ],
    }


def _snapshot(**kwargs):
    return build_trusted_route_environment_context_snapshot(
        environment_evidence_set_id=kwargs.get(
            "environment_evidence_set_id", EVIDENCE_SET_ID
        ),
        environment_evidence_hash=kwargs.get(
            "environment_evidence_hash", "e" * 64
        ),
        route_water_environment_identity_snapshot=kwargs.get(
            "route_water_environment_identity_snapshot", _water_snapshot()
        ),
        hydrology_trust_decision_snapshot=kwargs.get(
            "hydrology_trust_decision_snapshot", _hydrology_snapshot()
        ),
        hydrology_relation_decision_snapshot=kwargs.get(
            "hydrology_relation_decision_snapshot"
        ),
        trusted_route_environment_context=kwargs.get(
            "trusted_route_environment_context", _trusted_context()
        ),
    )


def test_snapshot_is_deterministic_and_verifiable():
    first = _snapshot()
    second = _snapshot()
    assert first == second
    assert verify_trusted_environment_context_snapshot(first)
    assert first["projection_hash"] == trusted_environment_context_snapshot_hash(
        first
    )


def test_snapshot_is_compact_and_does_not_duplicate_segment_payloads():
    snapshot = _snapshot()
    assert "segments" not in snapshot["routes"][0]
    assert len(snapshot["aggregate_environment_mask_hash"]) == 64
    assert all(
        len(value) == 64 for value in snapshot["component_mask_hashes"].values()
    )
    assert all(
        len(value) == 64
        for value in snapshot["routes"][0]["component_mask_hashes"].values()
    )


def test_snapshot_preserves_environment_provenance_without_inventing_schema_versions():
    snapshot = _snapshot()
    provenance = snapshot["input_provenance"]
    assert provenance["weather_source_provider"] == "OPEN_METEO"
    assert provenance["route_weather_sample_matching_schema_version"] is None
    assert provenance["route_wind_context_schema_version"] is None


def test_reordered_route_limitations_and_environment_types_hash_the_same():
    context = _trusted_context()
    context["routes"][0]["route_limitations"].reverse()
    context["routes"][0]["environment_types"] = ["RIVER_INLAND", "RIVER_INLAND"]
    changed = _snapshot(trusted_route_environment_context=context)
    baseline = _snapshot()
    assert changed["routes"][0]["route_limitations"] == ["LIMIT_A", "LIMIT_B"]
    assert changed["routes"][0]["environment_types"] == ["RIVER_INLAND"]
    assert changed["projection_hash"] == baseline["projection_hash"]


def test_changed_projection_policy_creates_new_projection_hash():
    context = _trusted_context()
    context["policy"]["segment_environment_usable_when_any_component_usable"] = False
    changed = _snapshot(trusted_route_environment_context=context)
    assert changed["projection_policy_hash"] != _snapshot()["projection_policy_hash"]
    assert changed["projection_hash"] != _snapshot()["projection_hash"]


def test_changed_weather_segment_mask_creates_new_projection_hash():
    context = _trusted_context()
    context["routes"][0]["segments"][1]["weather"] = _component(
        "UNAVAILABLE", False, included=False
    )
    context["routes"][0]["segments"][1]["component_statuses"][
        "weather"
    ] = "UNAVAILABLE"
    changed = _snapshot(trusted_route_environment_context=context)
    assert changed["component_mask_hashes"]["weather"] != _snapshot()[
        "component_mask_hashes"
    ]["weather"]
    assert changed["projection_hash"] != _snapshot()["projection_hash"]


def test_changed_hydrology_trust_decision_hash_changes_projection_hash():
    changed = _snapshot(
        hydrology_trust_decision_snapshot=_hydrology_snapshot("c" * 64)
    )
    assert changed["projection_hash"] != _snapshot()["projection_hash"]


def test_changed_water_identity_hash_changes_projection_hash():
    changed = _snapshot(
        route_water_environment_identity_snapshot=_water_snapshot("d" * 64)
    )
    assert changed["projection_hash"] != _snapshot()["projection_hash"]


def test_changed_environment_evidence_hash_changes_projection_hash():
    changed = _snapshot(environment_evidence_hash="f" * 64)
    assert changed["projection_hash"] != _snapshot()["projection_hash"]


def test_changed_environment_evidence_set_changes_projection_hash():
    changed = _snapshot(
        environment_evidence_set_id="4839f32a-8286-40a1-afc4-f920bdb16b6d"
    )
    assert changed["projection_hash"] != _snapshot()["projection_hash"]


def test_missing_hydrology_decision_is_allowed_for_weather_water_projection():
    snapshot = _snapshot(hydrology_trust_decision_snapshot=None)
    assert snapshot["hydrology_trust_decision_hash"] is None
    assert verify_trusted_environment_context_snapshot(snapshot)


def test_withheld_hydrology_is_first_class_projection_state():
    context = _trusted_context(hydrology_status="WITHHELD")
    snapshot = _snapshot(
        trusted_route_environment_context=context,
        hydrology_trust_decision_snapshot=_hydrology_snapshot("c" * 64),
    )
    route = snapshot["routes"][0]
    assert route["hydrology_route_trust_status"] == "WITHHELD"
    assert route["hydrology_usable_segment_count"] == 0
    assert verify_trusted_environment_context_snapshot(snapshot)




def test_relation_decision_hash_is_linked_when_present():
    snapshot = _snapshot(
        hydrology_relation_decision_snapshot={
            "relation_decision_hash": "r" * 64
        }
    )
    assert snapshot["hydrology_relation_decision_hash"] == "r" * 64
    assert verify_trusted_environment_context_snapshot(snapshot)


def test_changed_relation_decision_hash_changes_projection_hash():
    first = _snapshot(
        hydrology_relation_decision_snapshot={
            "relation_decision_hash": "r" * 64
        }
    )
    second = _snapshot(
        hydrology_relation_decision_snapshot={
            "relation_decision_hash": "q" * 64
        }
    )
    assert first["projection_hash"] != second["projection_hash"]

def test_tampered_snapshot_fails_verification():
    snapshot = _snapshot()
    tampered = deepcopy(snapshot)
    tampered["routes"][0]["weather_usable_segment_count"] = 0
    assert not verify_trusted_environment_context_snapshot(tampered)


def test_missing_trusted_environment_context_returns_none():
    assert build_trusted_route_environment_context_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_water_environment_identity_snapshot=_water_snapshot(),
        hydrology_trust_decision_snapshot=_hydrology_snapshot(),
        trusted_route_environment_context=None,
    ) is None
