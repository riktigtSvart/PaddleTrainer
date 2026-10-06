import json
from copy import deepcopy

import pytest

from app.services.trusted_environment_context_persistence import (
    count_trusted_route_environment_context_snapshots,
    load_trusted_route_environment_context_snapshot,
    persist_trusted_route_environment_context_snapshot,
)
from app.services.trusted_environment_context_snapshot import (
    build_trusted_route_environment_context_snapshot,
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
                    and row["projection_hash"] == str(params["projection_hash"])
                ),
                None,
            )
            return _Result(match)

        if "INSERT INTO ROUTE_TRUSTED_ENVIRONMENT_CONTEXT_SNAPSHOTS" in upper:
            row = {
                "snapshot_id": params["id"],
                "evidence_set_id": str(params["evidence_set_id"]),
                "snapshot_schema_version": params["snapshot_schema_version"],
                "trusted_environment_context_schema_version": params[
                    "trusted_environment_context_schema_version"
                ],
                "projection_policy_schema_version": params[
                    "projection_policy_schema_version"
                ],
                "projection_status": params["projection_status"],
                "water_environment_identity_hash": params[
                    "water_environment_identity_hash"
                ],
                "hydrology_trust_decision_hash": params[
                    "hydrology_trust_decision_hash"
                ],
                "hydrology_relation_decision_hash": params[
                    "hydrology_relation_decision_hash"
                ],
                "projection_policy_hash": params["projection_policy_hash"],
                "water_identity_mask_hash": params["water_identity_mask_hash"],
                "weather_mask_hash": params["weather_mask_hash"],
                "wind_mask_hash": params["wind_mask_hash"],
                "hydrology_mask_hash": params["hydrology_mask_hash"],
                "aggregate_environment_mask_hash": params[
                    "aggregate_environment_mask_hash"
                ],
                "projection_hash": params["projection_hash"],
                "snapshot_json": json.loads(params["snapshot_json"]),
            }
            self.rows.append(row)
            return _Result()

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1


def _context(policy_any=True):
    usable = True
    component = {
        "status": "TRUSTED_WITH_LIMITATIONS",
        "included": True,
        "applicable": True,
        "usable_for_downstream_environment_context": usable,
    }
    segment = {
        "order_index": 0,
        "status": "TRUSTED_WITH_LIMITATIONS",
        "usable_for_downstream_environment_context": True,
        "usable_with_limitations": True,
        "component_statuses": {
            "water_identity": "TRUSTED",
            "weather": "TRUSTED_WITH_LIMITATIONS",
            "wind": "TRUSTED_WITH_LIMITATIONS",
            "hydrology": "TRUSTED_WITH_LIMITATIONS",
        },
        "water_identity": {**component, "status": "TRUSTED"},
        "weather": deepcopy(component),
        "wind": deepcopy(component),
        "hydrology": deepcopy(component),
    }
    return {
        "schema_version": "0.1",
        "status": "TRUSTED_WITH_LIMITATIONS",
        "route_count": 1,
        "trusted_route_count": 0,
        "trusted_with_limitations_route_count": 1,
        "withheld_route_count": 0,
        "unavailable_route_count": 0,
        "not_applicable_route_count": 0,
        "input_provenance": {
            "weather_source_provider": "OPEN_METEO",
        },
        "policy": {
            "segment_environment_usable_when_any_component_usable": policy_any,
            "component_promotion_allowed": False,
        },
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "TRUSTED_WITH_LIMITATIONS",
                "segment_count": 1,
                "trusted_segment_count": 0,
                "trusted_with_limitations_segment_count": 1,
                "withheld_segment_count": 0,
                "unavailable_segment_count": 0,
                "not_applicable_segment_count": 0,
                "downstream_usable_segment_count": 1,
                "water_identity_usable_segment_count": 1,
                "weather_usable_segment_count": 1,
                "wind_usable_segment_count": 1,
                "hydrology_usable_segment_count": 1,
                "hydrology_route_trust_status": "TRUSTED_WITH_LIMITATIONS",
                "environment_types": ["RIVER_INLAND"],
                "mixed_environment_route": False,
                "route_limitations": ["LIMIT"],
                "segments": [segment],
            }
        ],
    }


def _snapshot(policy_any=True, relation_hash=None):
    return build_trusted_route_environment_context_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_water_environment_identity_snapshot={"identity_hash": "a" * 64},
        hydrology_trust_decision_snapshot={"decision_hash": "b" * 64},
        hydrology_relation_decision_snapshot=(
            {"relation_decision_hash": relation_hash}
            if relation_hash is not None
            else None
        ),
        trusted_route_environment_context=_context(policy_any=policy_any),
    )


@pytest.mark.asyncio
async def test_first_persist_creates_and_round_trips_exact_snapshot():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    result = await persist_trusted_route_environment_context_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        snapshot=snapshot,
    )
    assert result["status"] == "CREATED"
    assert result["round_trip_verified"] is True
    assert result["round_trip"] == snapshot
    assert result["lineage_snapshot_count"] == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_repeating_same_projection_is_already_current_and_idempotent():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    first = await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    second = await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=snapshot
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_CURRENT"
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["projection_hash"] == second["projection_hash"]
    assert second["lineage_snapshot_count"] == 1
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_changed_projection_policy_creates_second_lineage_version():
    db = FakeAsyncSession()
    first_snapshot = _snapshot(policy_any=True)
    second_snapshot = _snapshot(policy_any=False)
    first = await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=first_snapshot
    )
    second = await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=second_snapshot
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "CREATED"
    assert first["projection_hash"] != second["projection_hash"]
    assert second["lineage_snapshot_count"] == 2
    assert db.commit_count == 2




@pytest.mark.asyncio
async def test_changed_relation_lineage_creates_second_environment_projection():
    db = FakeAsyncSession()
    first = await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(relation_hash="r" * 64)
    )
    second = await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(relation_hash="q" * 64)
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "CREATED"
    assert first["projection_hash"] != second["projection_hash"]
    assert second["lineage_snapshot_count"] == 2

@pytest.mark.asyncio
async def test_snapshot_cannot_be_persisted_under_different_evidence_set():
    db = FakeAsyncSession()
    with pytest.raises(ValueError, match="does not match persistence target"):
        await persist_trusted_route_environment_context_snapshot(
            db,
            evidence_set_id="4839f32a-8286-40a1-afc4-f920bdb16b6d",
            snapshot=_snapshot(),
        )


@pytest.mark.asyncio
async def test_load_missing_projection_returns_none():
    db = FakeAsyncSession()
    result = await load_trusted_route_environment_context_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        projection_hash="x" * 64,
    )
    assert result is None


@pytest.mark.asyncio
async def test_count_tracks_multiple_lineage_versions():
    db = FakeAsyncSession()
    await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(True)
    )
    await persist_trusted_route_environment_context_snapshot(
        db, evidence_set_id=EVIDENCE_SET_ID, snapshot=_snapshot(False)
    )
    assert await count_trusted_route_environment_context_snapshots(
        db, evidence_set_id=EVIDENCE_SET_ID
    ) == 2
