import json
from copy import deepcopy

import pytest

from app.services.hydrology_relation_decision_persistence import (
    count_hydrology_relation_decision_snapshots,
    load_hydrology_relation_decision_snapshot,
    persist_hydrology_relation_decision_snapshot,
)
from app.services.hydrology_relation_decision_snapshot import (
    build_hydrology_relation_decision_snapshot,
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
                    and row["relation_decision_hash"]
                    == str(params["relation_decision_hash"])
                ),
                None,
            )
            return _Result(match)
        if "INSERT INTO ROUTE_HYDROLOGY_RELATION_DECISION_SNAPSHOTS" in upper:
            row = {
                "snapshot_id": params["id"],
                "evidence_set_id": str(params["evidence_set_id"]),
                "snapshot_schema_version": params["snapshot_schema_version"],
                "relation_catalog_schema_version": params[
                    "relation_catalog_schema_version"
                ],
                "relation_catalog_provider": params["relation_catalog_provider"],
                "relation_catalog_product": params["relation_catalog_product"],
                "relation_evidence_schema_version": params[
                    "relation_evidence_schema_version"
                ],
                "relation_aware_context_schema_version": params[
                    "relation_aware_context_schema_version"
                ],
                "relation_evidence_status": params["relation_evidence_status"],
                "relation_aware_context_status": params[
                    "relation_aware_context_status"
                ],
                "hydrology_source_resolution_hash": params[
                    "hydrology_source_resolution_hash"
                ],
                "relation_catalog_hash": params["relation_catalog_hash"],
                "relation_policy_hash": params["relation_policy_hash"],
                "relation_decision_hash": params["relation_decision_hash"],
                "snapshot_json": json.loads(params["snapshot_json"]),
            }
            self.rows.append(row)
            return _Result()
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1


def _snapshot(*, catalog_hash="a" * 64, policy_hash="b" * 64):
    # Use a minimal valid builder input; catalog content changes drive the real hash.
    catalog = {
        "provider": "TEST_AUTH",
        "product": "RELATIONS_V1" if catalog_hash.startswith("a") else "RELATIONS_V2",
        "schema_version": "0.1",
        "catalog_type": "AUTHORITATIVE_HYDROLOGY_RELATION_CATALOG",
        "source_mode": "CURATED_OFFICIAL_DOCUMENTS",
        "source_documents": [],
        "metadata": {},
        "relations": [],
    }
    relation_evidence = {
        "schema_version": "0.1",
        "status": "WITHHELD",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "source_resolution_status": "UNRESOLVED",
                "status": "WITHHELD",
                "metric_relations": [],
                "selected_source_by_metric": {},
                "resolution_basis": ["NO_RELATION"],
                "limitations": ["NO_TRANSFER"],
            }
        ],
    }
    relation_context = {
        "schema_version": "0.1",
        "status": "WITHHELD",
        "policy": {
            "direct_trust_precedence": True,
            "test_policy": policy_hash,
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "direct_trust_status": "WITHHELD",
                "trust_status": "WITHHELD",
                "trust_mode": "WITHHELD",
                "hydrology_context_included": False,
                "usable_for_downstream_environment_context": False,
                "authorized_metric_keys": [],
                "withheld_metric_keys": [],
                "unsupported_metric_payload_keys": [],
                "relation_metric_trust": [],
                "representativeness_limitations": [],
            }
        ],
    }
    return build_hydrology_relation_decision_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={"resolution_hash": "s" * 64},
        hydrology_relation_catalog=catalog,
        route_hydrology_relation_evidence=relation_evidence,
        relation_aware_trusted_route_hydrology_context=relation_context,
    )


@pytest.mark.asyncio
async def test_first_relation_decision_persist_creates_and_round_trips():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    result = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    assert result["status"] == "CREATED"
    assert result["round_trip_verified"] is True
    assert result["lineage_snapshot_count"] == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_same_relation_decision_is_already_current_and_idempotent():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    first = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    second = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_CURRENT"
    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["lineage_snapshot_count"] == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_changed_catalog_creates_second_relation_lineage_version():
    db = FakeAsyncSession()
    first = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(catalog_hash="a" * 64)
    )
    second = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(catalog_hash="c" * 64)
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "CREATED"
    assert first["relation_decision_hash"] != second["relation_decision_hash"]
    assert second["lineage_snapshot_count"] == 2


@pytest.mark.asyncio
async def test_changed_relation_policy_creates_second_lineage_version():
    db = FakeAsyncSession()
    first = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(policy_hash="b" * 64)
    )
    second = await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(policy_hash="d" * 64)
    )
    assert first["relation_decision_hash"] != second["relation_decision_hash"]
    assert second["lineage_snapshot_count"] == 2


@pytest.mark.asyncio
async def test_relation_snapshot_cannot_persist_under_different_evidence_set():
    db = FakeAsyncSession()
    with pytest.raises(ValueError, match="does not match persistence target"):
        await persist_hydrology_relation_decision_snapshot(
            db,
            evidence_set_id="4839f32a-8286-40a1-afc4-f920bdb16b6d",
            snapshot=_snapshot(),
        )


@pytest.mark.asyncio
async def test_load_missing_relation_decision_returns_none():
    db = FakeAsyncSession()
    result = await load_hydrology_relation_decision_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        relation_decision_hash="x" * 64,
    )
    assert result is None


@pytest.mark.asyncio
async def test_count_tracks_relation_lineage_versions():
    db = FakeAsyncSession()
    await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(catalog_hash="a" * 64)
    )
    await persist_hydrology_relation_decision_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(catalog_hash="c" * 64)
    )
    assert await count_hydrology_relation_decision_snapshots(
        db, evidence_set_id=EVIDENCE_SET_ID
    ) == 2
