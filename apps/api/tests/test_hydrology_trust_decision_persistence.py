import json
from copy import deepcopy

import pytest

from app.services.hydrology_trust_decision_persistence import (
    count_hydrology_trust_decision_snapshots,
    load_hydrology_trust_decision_snapshot,
    persist_hydrology_trust_decision_snapshot,
)
from app.services.hydrology_trust_decision_snapshot import (
    build_hydrology_trust_decision_snapshot,
)


EVIDENCE_SET_ID = "7d68281a-ecb3-4a91-a726-2ceed5800beb"


class _Mappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return _Mappings(self._row)


class FakeAsyncSession:
    def __init__(self):
        self.rows = []
        self.commit_count = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        upper = sql.upper()
        params = params or {}

        if "SELECT COUNT(*)" in upper:
            count = sum(
                1
                for row in self.rows
                if row["evidence_set_id"] == str(params["evidence_set_id"])
            )
            return _Result({"snapshot_count": count})

        if "SELECT" in upper:
            match = next(
                (
                    deepcopy(row)
                    for row in self.rows
                    if row["evidence_set_id"] == str(params["evidence_set_id"])
                    and row["decision_hash"] == str(params["decision_hash"])
                ),
                None,
            )
            return _Result(match)

        if "INSERT INTO ROUTE_HYDROLOGY_TRUST_DECISION_SNAPSHOTS" in upper:
            row = {
                "snapshot_id": str(params["id"]),
                "evidence_set_id": str(params["evidence_set_id"]),
                "snapshot_schema_version": params["snapshot_schema_version"],
                "trusted_context_schema_version": params[
                    "trusted_context_schema_version"
                ],
                "representativeness_schema_version": params[
                    "representativeness_schema_version"
                ],
                "trust_policy_schema_version": params[
                    "trust_policy_schema_version"
                ],
                "decision_status": params["decision_status"],
                "hydrology_source_resolution_hash": params[
                    "hydrology_source_resolution_hash"
                ],
                "trust_policy_hash": params["trust_policy_hash"],
                "representativeness_policy_hash": params[
                    "representativeness_policy_hash"
                ],
                "temporal_support_mask_hash": params[
                    "temporal_support_mask_hash"
                ],
                "decision_hash": params["decision_hash"],
                "snapshot_json": json.loads(params["snapshot_json"]),
            }
            self.rows.append(row)
            return _Result()

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1


def _snapshot(*, policy_target="TRUSTED_WITH_LIMITATIONS"):
    representativeness = {
        "schema_version": "0.2",
        "status": "PARTIALLY_REPRESENTATIVE",
        "policy": {
            "max_temporal_gap_seconds": 10800,
            "min_temporal_coverage_fraction": 0.8,
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "PARTIALLY_REPRESENTATIVE",
                "temporal_evidence": {
                    "route_segment_count": 2,
                    "timestamped_segment_count": 2,
                    "temporally_supported_segment_count": 2,
                },
                "segments": [
                    {"segment_index": 0, "temporally_supported": True},
                    {"segment_index": 1, "temporally_supported": True},
                ],
            }
        ],
    }
    trusted = {
        "schema_version": "0.1",
        "status": policy_target,
        "route_count": 1,
        "trusted_route_count": 0,
        "trusted_with_limitations_route_count": (
            1 if policy_target == "TRUSTED_WITH_LIMITATIONS" else 0
        ),
        "withheld_route_count": 1 if policy_target == "WITHHELD" else 0,
        "not_applicable_route_count": 0,
        "policy": {
            "representative": "TRUSTED",
            "partially_representative": policy_target,
            "insufficient_evidence": "WITHHELD",
            "not_representative": "WITHHELD",
            "not_applicable": "NOT_APPLICABLE",
            "missing_source_context": "WITHHELD",
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "representativeness_status": "PARTIALLY_REPRESENTATIVE",
                "trust_status": policy_target,
                "source_context_available": True,
                "hydrology_context_included": policy_target != "WITHHELD",
                "usable_for_downstream_environment_context": (
                    policy_target != "WITHHELD"
                ),
                "usable_with_limitations": (
                    policy_target == "TRUSTED_WITH_LIMITATIONS"
                ),
                "source_context_segment_count": 2,
                "trusted_context_segment_count": (
                    2 if policy_target != "WITHHELD" else 0
                ),
                "withheld_context_segment_count": (
                    0 if policy_target != "WITHHELD" else 2
                ),
                "segment_filter_applied": policy_target != "WITHHELD",
                "representativeness_resolution_basis": [],
                "representativeness_limitations": [],
                "trust_basis": [policy_target],
            }
        ],
    }
    return build_hydrology_trust_decision_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={
            "resolution_hash": "r" * 64,
        },
        route_hydrology_representativeness=representativeness,
        trusted_route_hydrology_context=trusted,
    )


@pytest.mark.asyncio
async def test_persist_decision_snapshot_round_trips_exact_payload():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    result = await persist_hydrology_trust_decision_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        snapshot=snapshot,
    )
    assert result["status"] == "CREATED"
    assert result["decision_hash"] == snapshot["decision_hash"]
    assert result["round_trip_verified"] is True
    assert result["round_trip"] == snapshot
    assert result["lineage_snapshot_count"] == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_repeating_same_decision_is_idempotent():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    first = await persist_hydrology_trust_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    second = await persist_hydrology_trust_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_CURRENT"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["lineage_snapshot_count"] == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_changed_policy_creates_new_lineage_snapshot_for_same_evidence_set():
    db = FakeAsyncSession()
    first_snapshot = _snapshot()
    second_snapshot = _snapshot(policy_target="WITHHELD")
    first = await persist_hydrology_trust_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=first_snapshot
    )
    second = await persist_hydrology_trust_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=second_snapshot
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "CREATED"
    assert first["decision_hash"] != second["decision_hash"]
    assert second["lineage_snapshot_count"] == 2
    assert db.commit_count == 2


@pytest.mark.asyncio
async def test_snapshot_cannot_be_persisted_under_different_evidence_set():
    db = FakeAsyncSession()
    with pytest.raises(ValueError, match="does not match persistence target"):
        await persist_hydrology_trust_decision_snapshot(
            db,
            evidence_set_id="4839f32a-8286-40a1-afc4-f920bdb16b6d",
            snapshot=_snapshot(),
        )


@pytest.mark.asyncio
async def test_load_missing_decision_returns_none():
    db = FakeAsyncSession()
    result = await load_hydrology_trust_decision_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        decision_hash="x" * 64,
    )
    assert result is None


@pytest.mark.asyncio
async def test_count_tracks_multiple_lineage_versions():
    db = FakeAsyncSession()
    await persist_hydrology_trust_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot()
    )
    await persist_hydrology_trust_decision_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        snapshot=_snapshot(policy_target="WITHHELD"),
    )
    assert await count_hydrology_trust_decision_snapshots(
        db, evidence_set_id=EVIDENCE_SET_ID
    ) == 2
