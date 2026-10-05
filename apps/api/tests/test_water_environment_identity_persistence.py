import json
from copy import deepcopy

import pytest

from app.services.route_water_environment_identity_snapshot import (
    build_route_water_environment_identity_snapshot,
)
from app.services.water_environment_identity_persistence import (
    load_route_water_environment_identity_snapshot,
    persist_route_water_environment_identity_snapshot,
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
            evidence_set_id = str(params["evidence_set_id"])
            row = self.rows.get(evidence_set_id)
            return _Result(deepcopy(row))

        if "INSERT INTO route_water_environment_identity_snapshots" in sql:
            evidence_set_id = str(params["evidence_set_id"])
            snapshot = json.loads(params["snapshot_json"])
            self.rows[evidence_set_id] = {
                "snapshot_id": str(params["id"]),
                "evidence_set_id": evidence_set_id,
                "snapshot_schema_version": params["snapshot_schema_version"],
                "identity_schema_version": params["identity_schema_version"],
                "identity_hash": params["identity_hash"],
                "snapshot_json": snapshot,
            }
            return _Result()

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1


def _snapshot(environment_type="MARINE"):
    is_marine = environment_type == "MARINE"
    identity = {
        "provider": "POLAR",
        "schema_version": "0.1",
        "available": True,
        "status": "DIRECT_RESOLVED",
        "route_count": 1,
        "river_inland_segment_count": 0 if is_marine else 2,
        "marine_segment_count": 2 if is_marine else 0,
        "ambiguous_environment_segment_count": 0,
        "unresolved_environment_segment_count": 0,
        "direct_resolved_segment_count": 2,
        "continuity_supported_segment_count": 0,
        "ambiguous_segment_count": 0,
        "transition_candidate_segment_count": 0,
        "unresolved_segment_count": 0,
        "cross_domain_conflict_segment_count": 0,
        "input_provenance": {},
        "scope": {"domain": "ROUTE_WATER_ENVIRONMENT_IDENTITY"},
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "available": True,
                "status": "DIRECT_RESOLVED",
                "segment_count": 2,
                "environment_types": [environment_type],
                "mixed_environment_route": False,
                "river_inland_segment_count": 0 if is_marine else 2,
                "marine_segment_count": 2 if is_marine else 0,
                "ambiguous_environment_segment_count": 0,
                "unresolved_environment_segment_count": 0,
                "direct_resolved_segment_count": 2,
                "continuity_supported_segment_count": 0,
                "ambiguous_segment_count": 0,
                "transition_candidate_segment_count": 0,
                "unresolved_segment_count": 0,
                "cross_domain_conflict_segment_count": 0,
                "river_inland_identity_count": 0 if is_marine else 1,
                "river_inland_identities": [] if is_marine else [
                    {"source_provider": "EEA_WISE_WFD", "waterbody_id": "HUAOC752"}
                ],
                "marine_region_identity_count": 1 if is_marine else 0,
                "marine_region_identities": [
                    {
                        "source_provider": "EEA_MSFD",
                        "marine_subregion_id": "MAD",
                        "marine_subregion_name": "Adriatic Sea",
                    }
                ] if is_marine else [],
                "segments": [],
            }
        ],
    }
    return build_route_water_environment_identity_snapshot(identity)


@pytest.mark.asyncio
async def test_persist_snapshot_round_trips_exact_payload():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    evidence_set_id = "7d68281a-ecb3-4a91-a726-2ceed5800beb"

    result = await persist_route_water_environment_identity_snapshot(
        db,
        evidence_set_id=evidence_set_id,
        snapshot=snapshot,
    )

    assert result["status"] == "CREATED"
    assert result["evidence_set_id"] == evidence_set_id
    assert result["identity_hash"] == snapshot["identity_hash"]
    assert result["round_trip_verified"] is True
    assert result["round_trip"] == snapshot
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_repeating_same_snapshot_is_idempotent():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    evidence_set_id = "7d68281a-ecb3-4a91-a726-2ceed5800beb"

    first = await persist_route_water_environment_identity_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=snapshot
    )
    second = await persist_route_water_environment_identity_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=snapshot
    )

    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_CURRENT"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["round_trip_verified"] is True
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_different_snapshot_cannot_mutate_same_evidence_set():
    db = FakeAsyncSession()
    evidence_set_id = "7d68281a-ecb3-4a91-a726-2ceed5800beb"
    await persist_route_water_environment_identity_snapshot(
        db, evidence_set_id=evidence_set_id, snapshot=_snapshot("MARINE")
    )

    with pytest.raises(ValueError, match="Immutable environment evidence set"):
        await persist_route_water_environment_identity_snapshot(
            db,
            evidence_set_id=evidence_set_id,
            snapshot=_snapshot("RIVER_INLAND"),
        )


@pytest.mark.asyncio
async def test_load_missing_snapshot_returns_none():
    db = FakeAsyncSession()
    result = await load_route_water_environment_identity_snapshot(
        db,
        evidence_set_id="7d68281a-ecb3-4a91-a726-2ceed5800beb",
    )
    assert result is None
