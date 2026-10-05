import json
from copy import deepcopy

import pytest

from app.services.hydrology_source_resolution_persistence import (
    load_route_hydrology_source_resolution_snapshot,
    persist_route_hydrology_source_resolution_snapshot,
)
from app.services.route_hydrology_source_resolution_snapshot import (
    build_route_hydrology_source_resolution_snapshot,
)


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
        self.rows = {}
        self.commit_count = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "SELECT" in sql.upper():
            return _Result(deepcopy(self.rows.get(str(params["evidence_set_id"]))))

        if "INSERT INTO route_hydrology_source_resolution_snapshots" in sql:
            evidence_set_id = str(params["evidence_set_id"])
            self.rows[evidence_set_id] = {
                "snapshot_id": str(params["id"]),
                "evidence_set_id": evidence_set_id,
                "snapshot_schema_version": params["snapshot_schema_version"],
                "resolution_schema_version": params["resolution_schema_version"],
                "resolution_hash": params["resolution_hash"],
                "snapshot_json": json.loads(params["snapshot_json"]),
            }
            return _Result()

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1


def _snapshot(status="IDENTITY_SUPPORTED"):
    resolution = {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "available": True,
        "status": status,
        "route_count": 1,
        "candidate_source_count": 1,
        "identity_supported_route_count": 1 if status == "IDENTITY_SUPPORTED" else 0,
        "direct_resolved_route_count": 0,
        "ambiguous_route_count": 0,
        "unresolved_route_count": 1 if status == "UNRESOLVED" else 0,
        "not_applicable_route_count": 0,
        "input_provenance": {},
        "scope": {"domain": "ROUTE_HYDROLOGY_SOURCE_RESOLUTION"},
        "candidate_sources": [
            {
                "source_provider": "OVF_VRAQUERY",
                "station_registry_number": "1026",
                "station_name": "Budapest",
                "watercourse": "Duna",
            }
        ],
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "applicable": True,
                "status": status,
                "trusted_river_inland_identity_count": 1,
                "trusted_river_inland_identities": [],
                "candidate_source_count": 1,
                "evaluated_candidate_count": 0,
                "evaluated_candidates": [],
                "resolved_hydrology_source": None,
                "resolution_basis": [status],
            }
        ],
    }
    return build_route_hydrology_source_resolution_snapshot(resolution)


@pytest.mark.asyncio
async def test_persist_resolution_snapshot_round_trips_exact_payload():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    evidence_set_id = "7d68281a-ecb3-4a91-a726-2ceed5800beb"

    result = await persist_route_hydrology_source_resolution_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=snapshot
    )

    assert result["status"] == "CREATED"
    assert result["resolution_hash"] == snapshot["resolution_hash"]
    assert result["round_trip_verified"] is True
    assert result["round_trip"] == snapshot
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_repeating_same_resolution_snapshot_is_idempotent():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    evidence_set_id = "7d68281a-ecb3-4a91-a726-2ceed5800beb"

    first = await persist_route_hydrology_source_resolution_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=snapshot
    )
    second = await persist_route_hydrology_source_resolution_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=snapshot
    )

    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_CURRENT"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["round_trip_verified"] is True
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_different_resolution_cannot_mutate_same_evidence_set():
    db = FakeAsyncSession()
    evidence_set_id = "7d68281a-ecb3-4a91-a726-2ceed5800beb"
    await persist_route_hydrology_source_resolution_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=_snapshot("IDENTITY_SUPPORTED")
    )

    with pytest.raises(ValueError, match="Immutable environment evidence set"):
        await persist_route_hydrology_source_resolution_snapshot(
            db, evidence_set_id=evidence_set_id, snapshot=_snapshot("UNRESOLVED")
        )


@pytest.mark.asyncio
async def test_load_missing_resolution_snapshot_returns_none():
    db = FakeAsyncSession()
    result = await load_route_hydrology_source_resolution_snapshot(
        db, evidence_set_id="7d68281a-ecb3-4a91-a726-2ceed5800beb"
    )
    assert result is None
