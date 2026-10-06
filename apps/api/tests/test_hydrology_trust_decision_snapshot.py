from copy import deepcopy

from app.services.hydrology_trust_decision_snapshot import (
    build_hydrology_trust_decision_snapshot,
    hydrology_trust_decision_snapshot_hash,
    verify_hydrology_trust_decision_snapshot,
)


EVIDENCE_SET_ID = "7d68281a-ecb3-4a91-a726-2ceed5800beb"


def _resolution_snapshot(resolution_hash="a" * 64):
    return {
        "snapshot_schema_version": "0.1",
        "resolution_schema_version": "0.1",
        "resolution_hash": resolution_hash,
    }


def _representativeness(status="PARTIALLY_REPRESENTATIVE"):
    segments = [
        {"segment_index": 0, "temporally_supported": True},
        {"segment_index": 1, "temporally_supported": True},
        {"segment_index": 2, "temporally_supported": False},
    ]
    return {
        "schema_version": "0.2",
        "status": status,
        "policy": {
            "max_temporal_gap_seconds": 10800,
            "min_temporal_coverage_fraction": 0.8,
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": status,
                "temporal_evidence": {
                    "route_segment_count": 3,
                    "timestamped_segment_count": 3,
                    "temporally_supported_segment_count": 2,
                },
                "segments": segments if status != "NOT_APPLICABLE" else [],
            }
        ],
    }


def _trusted(status="TRUSTED_WITH_LIMITATIONS"):
    included = status in {"TRUSTED", "TRUSTED_WITH_LIMITATIONS"}
    return {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "available": True,
        "status": status,
        "route_count": 1,
        "trusted_route_count": 1 if status == "TRUSTED" else 0,
        "trusted_with_limitations_route_count": (
            1 if status == "TRUSTED_WITH_LIMITATIONS" else 0
        ),
        "withheld_route_count": 1 if status == "WITHHELD" else 0,
        "not_applicable_route_count": 1 if status == "NOT_APPLICABLE" else 0,
        "policy": {
            "representative": "TRUSTED",
            "partially_representative": "TRUSTED_WITH_LIMITATIONS",
            "insufficient_evidence": "WITHHELD",
            "not_representative": "WITHHELD",
            "not_applicable": "NOT_APPLICABLE",
            "missing_source_context": "WITHHELD",
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "representativeness_status": (
                    "PARTIALLY_REPRESENTATIVE"
                    if status == "TRUSTED_WITH_LIMITATIONS"
                    else "NOT_REPRESENTATIVE"
                    if status == "WITHHELD"
                    else "NOT_APPLICABLE"
                    if status == "NOT_APPLICABLE"
                    else "REPRESENTATIVE"
                ),
                "trust_status": status,
                "source_context_available": True,
                "hydrology_context_included": included,
                "usable_for_downstream_environment_context": included,
                "usable_with_limitations": status == "TRUSTED_WITH_LIMITATIONS",
                "source_context_segment_count": 3,
                "trusted_context_segment_count": 2 if included else 0,
                "withheld_context_segment_count": 1 if included else 3,
                "segment_filter_applied": included,
                "representativeness_resolution_basis": ["B", "A"],
                "representativeness_limitations": ["L2", "L1"],
                "trust_basis": ["T2", "T1"],
                "trusted_context": (
                    {
                        "segments": [
                            {"segment_index": 0, "water_level": 100},
                            {"segment_index": 1, "water_level": 101},
                        ]
                    }
                    if included
                    else None
                ),
            }
        ],
    }


def _snapshot(**kwargs):
    return build_hydrology_trust_decision_snapshot(
        environment_evidence_set_id=kwargs.get(
            "environment_evidence_set_id", EVIDENCE_SET_ID
        ),
        environment_evidence_hash=kwargs.get("environment_evidence_hash", "e" * 64),
        route_hydrology_source_resolution_snapshot=kwargs.get(
            "route_hydrology_source_resolution_snapshot", _resolution_snapshot()
        ),
        route_hydrology_representativeness=kwargs.get(
            "route_hydrology_representativeness", _representativeness()
        ),
        trusted_route_hydrology_context=kwargs.get(
            "trusted_route_hydrology_context", _trusted()
        ),
    )


def test_snapshot_is_deterministic_and_verifiable():
    first = _snapshot()
    second = _snapshot()
    assert first == second
    assert verify_hydrology_trust_decision_snapshot(first)
    assert first["decision_hash"] == hydrology_trust_decision_snapshot_hash(first)


def test_snapshot_is_compact_and_does_not_duplicate_trusted_context_segments():
    snapshot = _snapshot()
    assert "trusted_context" not in snapshot["routes"][0]
    assert "segments" not in snapshot["routes"][0]
    assert len(snapshot["temporal_support_mask_hash"]) == 64
    assert len(snapshot["routes"][0]["temporal_support_mask_hash"]) == 64


def test_same_semantics_with_reordered_basis_lists_hashes_the_same():
    trusted = _trusted()
    trusted["routes"][0]["trust_basis"].reverse()
    trusted["routes"][0]["representativeness_limitations"].reverse()
    trusted["routes"][0]["representativeness_resolution_basis"].reverse()
    assert _snapshot()["decision_hash"] == _snapshot(
        trusted_route_hydrology_context=trusted
    )["decision_hash"]


def test_changed_trust_policy_creates_new_decision_hash():
    trusted = _trusted()
    trusted["policy"]["partially_representative"] = "WITHHELD"
    changed = _snapshot(trusted_route_hydrology_context=trusted)
    assert changed["decision_hash"] != _snapshot()["decision_hash"]
    assert changed["trust_policy_hash"] != _snapshot()["trust_policy_hash"]


def test_changed_representativeness_policy_creates_new_decision_hash():
    rep = _representativeness()
    rep["policy"]["min_temporal_coverage_fraction"] = 0.9
    changed = _snapshot(route_hydrology_representativeness=rep)
    assert changed["decision_hash"] != _snapshot()["decision_hash"]
    assert (
        changed["representativeness_policy_hash"]
        != _snapshot()["representativeness_policy_hash"]
    )


def test_changed_temporal_support_mask_creates_new_decision_hash():
    rep = _representativeness()
    rep["routes"][0]["segments"][2]["temporally_supported"] = True
    rep["routes"][0]["temporal_evidence"][
        "temporally_supported_segment_count"
    ] = 3
    changed = _snapshot(route_hydrology_representativeness=rep)
    assert changed["temporal_support_mask_hash"] != _snapshot()[
        "temporal_support_mask_hash"
    ]
    assert changed["decision_hash"] != _snapshot()["decision_hash"]


def test_changed_source_resolution_hash_creates_new_decision_hash():
    changed = _snapshot(
        route_hydrology_source_resolution_snapshot=_resolution_snapshot("b" * 64)
    )
    assert changed["decision_hash"] != _snapshot()["decision_hash"]


def test_changed_environment_evidence_set_creates_new_decision_hash():
    changed = _snapshot(
        environment_evidence_set_id="4839f32a-8286-40a1-afc4-f920bdb16b6d"
    )
    assert changed["decision_hash"] != _snapshot()["decision_hash"]


def test_withheld_and_not_applicable_are_first_class_snapshot_states():
    for status, rep_status in (
        ("WITHHELD", "NOT_REPRESENTATIVE"),
        ("NOT_APPLICABLE", "NOT_APPLICABLE"),
    ):
        snapshot = _snapshot(
            trusted_route_hydrology_context=_trusted(status),
            route_hydrology_representativeness=_representativeness(rep_status),
        )
        assert snapshot["decision_status"] == status
        assert verify_hydrology_trust_decision_snapshot(snapshot)


def test_tampered_snapshot_fails_verification():
    snapshot = _snapshot()
    tampered = deepcopy(snapshot)
    tampered["routes"][0]["trust_status"] = "WITHHELD"
    assert not verify_hydrology_trust_decision_snapshot(tampered)


def test_missing_trusted_context_returns_none():
    assert build_hydrology_trust_decision_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot=_resolution_snapshot(),
        route_hydrology_representativeness=_representativeness(),
        trusted_route_hydrology_context=None,
    ) is None
