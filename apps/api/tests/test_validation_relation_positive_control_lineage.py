import json
from copy import deepcopy

import pytest

from app.services.hydrology_relation_decision_persistence import (
    persist_hydrology_relation_decision_snapshot,
)
from app.services.hydrology_relation_decision_snapshot import (
    build_hydrology_relation_decision_snapshot,
    verify_hydrology_relation_decision_snapshot,
)
from app.services.route_hydrology_relation_live_projection import (
    build_route_hydrology_relation_live_projection,
)
from app.services.validation_hydrology_relation_catalog import (
    PROVIDER,
    build_validation_hydrology_relation_catalog,
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
            self.rows.append(
                {
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
            )
            return _Result()
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1


def _projection():
    candidate = {
        "station_registry_number": "1026",
        "station_name": "Budapest",
        "watercourse": "Duna",
    }
    route_input = {
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
    resolution = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "status": "UNRESOLVED",
                "applicable": True,
                "trusted_river_inland_identities": [
                    {
                        "waterbody_id": "HU:HUAOC756",
                        "identity_names": ["Szentendrei-Duna"],
                    }
                ],
                "resolved_hydrology_source": None,
                "evaluated_candidates": [{"candidate_source": candidate}],
            }
        ],
    }
    raw_context = {
        "provider": "OVF_VRAQUERY",
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    {
                        "segment_index": 0,
                        "water_level": {"value": 310, "unit": "cm"},
                        "discharge": {"value": 1200, "unit": "m3/s"},
                    }
                ],
            }
        ],
    }
    direct = {
        "schema_version": "0.1",
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "trust_status": "WITHHELD",
                "hydrology_context_included": False,
                "trusted_context": None,
            }
        ],
    }
    catalog = build_validation_hydrology_relation_catalog()
    projection = build_route_hydrology_relation_live_projection(
        route_environment_context_input=route_input,
        route_hydrology_source_resolution=resolution,
        route_hydrology_context=raw_context,
        trusted_route_hydrology_context=direct,
        relation_catalog=catalog,
    )
    return catalog, projection


def _snapshot():
    catalog, projection = _projection()
    return build_hydrology_relation_decision_snapshot(
        environment_evidence_set_id=EVIDENCE_SET_ID,
        environment_evidence_hash="e" * 64,
        route_hydrology_source_resolution_snapshot={"resolution_hash": "s" * 64},
        hydrology_relation_catalog=catalog,
        route_hydrology_relation_evidence=projection[
            "route_hydrology_relation_evidence"
        ],
        relation_aware_trusted_route_hydrology_context=projection[
            "relation_aware_trusted_route_hydrology_context"
        ],
    )


def test_positive_control_lineage_commits_water_level_only_authorization():
    snapshot = _snapshot()
    assert verify_hydrology_relation_decision_snapshot(snapshot)
    assert snapshot["relation_catalog_provider"] == PROVIDER
    assert snapshot["relation_derived_route_count"] == 1
    route = snapshot["routes"][0]
    assert route["trust_mode"] == "RELATION_DERIVED_METRIC_PROJECTION"
    assert route["authorized_metric_keys"] == ["WATER_LEVEL"]
    assert set(route["withheld_metric_keys"]) == {"DISCHARGE", "WATER_TEMPERATURE"}


@pytest.mark.asyncio
async def test_positive_control_relation_lineage_persistence_is_idempotent():
    db = FakeAsyncSession()
    snapshot = _snapshot()
    first = await persist_hydrology_relation_decision_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        snapshot=snapshot,
    )
    second = await persist_hydrology_relation_decision_snapshot(
        db,
        evidence_set_id=EVIDENCE_SET_ID,
        snapshot=snapshot,
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "ALREADY_CURRENT"
    assert second["lineage_snapshot_count"] == 1
    assert second["relation_decision_hash"] == snapshot["relation_decision_hash"]
    assert db.commit_count == 1


def test_positive_control_projection_never_commits_measurement_payload_to_relation_snapshot():
    snapshot = _snapshot()
    serialized = json.dumps(snapshot, sort_keys=True)
    route = snapshot["routes"][0]
    assert "trusted_context" not in route
    assert "segments" not in route
    assert '"value": 310' not in serialized
    assert '"value": 1200' not in serialized
    assert '"unit": "cm"' not in serialized
    assert '"unit": "m3/s"' not in serialized
    assert snapshot["scope"]["stores_full_hydrology_measurements"] is False
