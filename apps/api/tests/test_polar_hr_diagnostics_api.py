import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from test_heart_rate_sample_validation import session as _session_fixture
from test_hr_acquisition_persistence import OTHER, OWNER
from test_polar_hr_acquisition_api import environment as _base_environment_fixture
from test_polar_hr_acquisition_api import post as post_declaration

from app.api.router import api_router
from app.api.routes import polar_hr_diagnostics as module
from app.integrations.polar.client import PolarAPIError
from app.models.entities import User
from app.models.hr_acquisition_declaration import HRAcquisitionDeclaration
from app.models.hr_timebase_snapshot import HeartRateTimebaseSnapshot
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.hr_acquisition_persistence import persist_hr_acquisition_declaration
from app.services.hr_timebase_persistence import persist_hr_timebase_snapshot
from app.services.tcx_heart_rate_timebase import build_tcx_heart_rate_timebase

session = _session_fixture
base_environment = _base_environment_fixture
BASE = "/api/v1/integrations/polar/sessions/hr-session/hr-diagnostics"


@pytest.fixture
def environment(base_environment):
    env = base_environment
    HeartRateTimebaseSnapshot.__table__.create(env.db.session.get_bind())
    env.client.app.include_router(module.router, prefix="/api/v1")
    return env


def get(env, **changes):
    return env.client.get(BASE, params={"sample_date": "2026-09-30", **changes})


def save_clock(env, owner=OWNER):
    points = "".join(
        "<Trackpoint>"
        f"<Time>2026-09-30T15:00:{i:02d}.500Z</Time>"
        f"<HeartRateBpm><Value>{110 + i}</Value></HeartRateBpm>"
        "</Trackpoint>"
        for i in range(4)
    )
    xml = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        '<Activities><Activity Sport="Other"><Id>2026-09-30T15:00:00.250Z</Id>'
        '<Lap StartTime="2026-09-30T15:00:00.250Z"><TotalTimeSeconds>4</TotalTimeSeconds>'
        f"<Track>{points}</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
    ).encode()
    verification = build_tcx_heart_rate_timebase(
        xml,
        env.source,
        expected_session_external_id="hr-session",
        sample_session_match_count=1,
    )
    assert verification["export_timebase_verified"] is True
    return asyncio.run(
        persist_hr_timebase_snapshot(
            env.db,
            verification,
            env.source,
            athlete_id=str(owner),
            session_external_id="hr-session",
            sample_session_match_count=1,
        )
    )


def evidence_rows(env):
    return deepcopy(
        [
            (row.id, row.snapshot_hash, row.snapshot_json)
            for row in env.db.session.scalars(select(HeartRateTimebaseSnapshot)).all()
        ]
        + [
            (row.id, row.declaration_hash, row.declaration_json)
            for row in env.db.session.scalars(select(HRAcquisitionDeclaration)).all()
        ]
    )


def test_get_without_export_returns_descriptions_without_assumed_utc_or_storage(environment):
    before = deepcopy(environment.source)
    baseline = build_training_session_heart_rate_validation(
        before, expected_session_external_id="hr-session", sample_session_match_count=1
    )
    response = get(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["diagnosed_exercise_count"] == 1 and data["verified_clock_exercise_count"] == 0
    assert data["input_provenance"]["raw_validation_decision_hash"] == baseline["decision_hash"]
    entry = data["exercises"][0]
    assert entry["slot_count"] == entry["positive_finite_sample_count"] == 4
    assert entry["timebase"]["time_mapping_available"] is False
    assert entry["acquisition_context"]["declared_sensor"] is None
    for item in entry["observations"]["largest_adjacent_changes"]["items"]:
        assert item["time_mapping_available"] is False
        assert item["first_sample_timestamp_utc"] is None
    assert data["policy"]["read_only"] is True
    assert data["policy"]["persists_diagnostics"] is False
    assert data["acquisition_quality_verified"] is data["training_authorized"] is False
    assert environment.source == before and evidence_rows(environment) == []
    assert environment.db.commit_count == 0
    assert "private-test-token" not in response.text
    assert "unused-encrypted-token" not in response.text
    assert "values" not in response.text
    environment.provider.assert_awaited_with(
        "private-test-token", date(2026, 9, 30), date(2026, 10, 1), features=["samples"]
    )


def test_repeated_get_reuses_actual_owned_database_evidence_and_never_writes(environment):
    clock = save_clock(environment)
    declaration = post_declaration(environment).json()
    before = evidence_rows(environment)
    commits = environment.db.commit_count
    first, repeat = get(environment), get(environment)
    assert first.status_code == repeat.status_code == 200
    assert first.json() == repeat.json()
    data = first.json()
    entry = data["exercises"][0]
    assert data["verified_clock_exercise_count"] == 1
    assert entry["timebase"]["snapshot_id"] == clock["snapshot_id"]
    assert entry["timebase"]["first_sample_offset_from_api_exercise_start_us"] == 500_000
    sensor = entry["acquisition_context"]
    assert sensor["active_declaration_ids"] == [declaration["persistence"]["declaration_id"]]
    assert sensor["declaration_source"] == "USER_DECLARATION"
    assert sensor["sensor_identity_verified"] is sensor["acquisition_quality_verified"] is False
    item = entry["observations"]["largest_adjacent_changes"]["items"][0]
    assert item["first_sample_timestamp_utc"] == "2026-09-30T15:00:00.500000+00:00"
    assert evidence_rows(environment) == before
    assert environment.db.commit_count == commits


def test_complete_source_change_detaches_old_clock_and_declaration_without_deleting(environment):
    save_clock(environment)
    post_declaration(environment)
    before = evidence_rows(environment)
    environment.source["modified"] = "2026-10-01T00:00:00Z"
    data = get(environment).json()
    assert data["source_binding_verified"] is True
    assert data["verified_clock_exercise_count"] == 0
    entry = data["exercises"][0]
    assert entry["timebase"]["snapshot_id"] is None
    assert entry["acquisition_context"]["status"] == "NOT_DECLARED"
    assert entry["acquisition_context"]["active_declaration_ids"] == []
    assert evidence_rows(environment) == before


def test_identical_provider_source_for_another_owner_cannot_supply_evidence(environment):
    environment.db.session.add(
        User(id=OTHER, email="other-diagnostic-owner@example.test", created_at=datetime.now(UTC))
    )
    environment.db.session.commit()
    save_clock(environment, owner=OTHER)
    payload = {
        "exercise_external_id": "exercise-1",
        "sensor_modality": "ELECTRICAL",
        "body_location": "CHEST",
        "sensor_model": "Other owner's sensor",
    }
    asyncio.run(
        persist_hr_acquisition_declaration(
            environment.db,
            payload,
            environment.source,
            athlete_id=str(OTHER),
            session_external_id="hr-session",
            sample_session_match_count=1,
        )
    )
    before = evidence_rows(environment)
    response = get(environment)
    data = response.json()
    assert data["verified_clock_exercise_count"] == 0
    assert data["exercises"][0]["acquisition_context"]["declared_sensor"] is None
    assert "Other owner's sensor" not in response.text
    assert evidence_rows(environment) == before


@pytest.mark.parametrize("kind", ["CLOCK", "DECLARATION"])
def test_corrupt_owned_evidence_is_withheld_but_raw_diagnostics_remain_descriptive(
    environment, kind
):
    save_clock(environment)
    post_declaration(environment)
    if kind == "CLOCK":
        row = environment.db.session.scalar(select(HeartRateTimebaseSnapshot))
        row.snapshot_json = {}
    else:
        row = environment.db.session.scalar(select(HRAcquisitionDeclaration))
        row.declaration_json = {}
    environment.db.session.commit()
    before = evidence_rows(environment)
    response = get(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["diagnosed_exercise_count"] == 1
    entry = data["exercises"][0]
    if kind == "CLOCK":
        assert entry["timebase"]["time_mapping_available"] is False
        assert entry["timebase"]["blocking_reasons"]
        assert (
            entry["observations"]["largest_adjacent_changes"]["items"][0][
                "first_sample_timestamp_utc"
            ]
            is None
        )
    else:
        assert entry["acquisition_context"]["status"] == "WITHHELD"
        assert entry["acquisition_context"]["declared_sensor"] is None
    assert data["acquisition_quality_verified"] is data["training_authorized"] is False
    assert evidence_rows(environment) == before


def test_detail_query_bounds_output_but_counts_and_provenance_cover_complete_source(environment):
    small, large = (
        get(environment, detail_limit=1).json(),
        get(environment, detail_limit=100).json(),
    )
    assert small["input_provenance"] == large["input_provenance"]
    a, b = [
        data["exercises"][0]["observations"]["largest_adjacent_changes"] for data in (small, large)
    ]
    assert a["total_count"] == b["total_count"] == 3
    assert a["returned_count"] == 1 and a["truncated"] is True
    assert b["returned_count"] == 3 and b["truncated"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"detail_limit": 0},
        {"detail_limit": 101},
        {"detail_limit": "1.5"},
        {"sample_date": "invalid"},
        {"sample_date": "9999-12-31"},
    ],
)
def test_invalid_query_is_rejected_before_provider_or_storage(environment, params):
    assert get(environment, **params).status_code == 422
    environment.provider.assert_not_awaited()
    assert evidence_rows(environment) == []


@pytest.mark.parametrize("connected,status", [(False, 404), (True, 403)])
def test_owned_connection_and_training_read_scope_are_required(environment, connected, status):
    if connected:
        environment.connection.scopes = []
    else:
        environment.db.session.delete(environment.connection)
    environment.db.session.commit()
    assert get(environment).status_code == status
    environment.provider.assert_not_awaited()
    environment.token.assert_not_awaited()


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_provider_session_has_no_diagnostics_or_assumed_clock(
    environment, count
):
    environment.provider.return_value = {"trainingSessions": [environment.source] * count}
    response = get(environment)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "WITHHELD" and data["source_binding_verified"] is False
    assert data["exercises"] == []
    assert data["diagnosed_exercise_count"] == data["verified_clock_exercise_count"] == 0
    assert evidence_rows(environment) == []


@pytest.mark.parametrize("failure", ["PROVIDER_ERROR", "INVALID_PAYLOAD"])
def test_provider_failures_are_reported_without_tokens_or_storage(environment, failure):
    if failure == "PROVIDER_ERROR":
        environment.provider.side_effect = PolarAPIError("private-test-token")
    else:
        environment.provider.return_value = {"unexpected": []}
    response = get(environment)
    assert response.status_code == 502
    assert "private-test-token" not in response.text
    assert evidence_rows(environment) == []


def test_client_query_cannot_claim_quality_or_training_authority(environment):
    response = get(environment, acquisition_quality_verified="true", training_authorized="true")
    assert response.status_code == 200
    assert response.json()["acquisition_quality_verified"] is False
    assert response.json()["training_authorized"] is False


def test_schema_registers_only_get_with_explicit_date_and_bounded_details():
    app = FastAPI()
    app.include_router(api_router)
    operation = app.openapi()["paths"][
        "/integrations/polar/sessions/{session_external_id}/hr-diagnostics"
    ]
    assert set(operation) == {"get"}
    assert "requestBody" not in operation["get"]
    params = {p["name"]: p for p in operation["get"]["parameters"]}
    assert params["sample_date"]["required"] is True
    assert params["detail_limit"]["schema"]["default"] == 25
    assert params["detail_limit"]["schema"]["minimum"] == 1
    assert params["detail_limit"]["schema"]["maximum"] == 100
