from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

import pytest
from test_environment_replay_persistence import scientific_state
from test_response_model_inputs import (
    archive as _archive,
    chronological as _chronological,
    completed as _completed,
    environment as _environment,
    sources as _sources,
)

from app.services import response_session_inventory as module
from app.services.environment_replay_snapshot import canonical_hash
from app.services.heart_rate_sample_validation import build_training_session_heart_rate_validation
from app.services.heart_rate_signal_diagnostics import build_training_session_hr_signal_diagnostics
from app.services.hr_acquisition_declarations import resolve_hr_acquisition_declarations

archive, chronological, completed, environment, sources = (
    _archive,
    _chronological,
    _completed,
    _environment,
    _sources,
)


def candidate(source, identity, start, owner):
    _, route, sample = deepcopy(source)
    local = start + timedelta(hours=2)
    for obj in (route, sample):
        obj["identifier"]["id"] = identity
        obj["startTime"] = local.replace(tzinfo=None).isoformat()
        obj["stopTime"] = (local + timedelta(seconds=5)).replace(tzinfo=None).isoformat()
        exercise = obj["exercises"][0]
        exercise["startTime"] = obj["startTime"]
        exercise["stopTime"] = (local + timedelta(seconds=4)).replace(tzinfo=None).isoformat()
        if "routes" in exercise:
            exercise["routes"]["route"]["startTime"] = obj["startTime"]
    route["exercises"][0]["routes"] = {
        "route": {
            "startTime": route["startTime"],
            "wayPoints": [
                {"elapsedMillis": i * 2000, "latitude": 47.5 + i / 100000, "longitude": 19.0}
                for i in range(3)
            ],
        }
    }
    sample["product"] = {"modelName": "Grit X"}
    session = {
        "id": str(uuid5(NAMESPACE_URL, identity)),
        "external_provider": "POLAR",
        "external_id": identity,
        "started_at": start.isoformat(),
        "sport": "KAYAK",
        "name": None,
        "duration_sec": 4,
    }
    detail = {**session, "raw_data": deepcopy(route)}
    kwargs = {"athlete_id": owner, "session_external_id": identity, "sample_session_match_count": 1}
    validation = build_training_session_heart_rate_validation(
        sample, expected_session_external_id=identity, sample_session_match_count=1
    )
    diagnostics = build_training_session_hr_signal_diagnostics(sample, **kwargs)
    acquisition = resolve_hr_acquisition_declarations([], sample, **kwargs)
    inspection = {
        "route_date": local.date().isoformat(),
        "raw": {"routes": {"trainingSessions": [route]}, "samples": {"trainingSessions": [sample]}},
        "route_sessions": [
            {
                "external_id": identity,
                "heart_rate_sample_validation": validation,
                "heart_rate_signal_diagnostics": diagnostics,
                "heart_rate_acquisition_context": acquisition,
            }
        ],
    }
    replay = {
        "status": "CAPTURE_REQUIRED",
        "total_count": 0,
        "returned_count": 0,
        "truncated": False,
        "snapshots": [],
        "training_authorized": False,
    }
    return session, {
        "session_external_id": identity,
        "status": "CAPTURED",
        "detail": detail,
        "inspection": inspection,
        "replays": replay,
    }


@pytest.fixture
def available(archive, sources):
    sessions, observations = [], []
    for i in range(6):
        session, observation = candidate(
            sources, f"older-{i}", datetime(2026, 9, 27 - i, 15, tzinfo=UTC), archive["owner_id"]
        )
        sessions.append(session)
        observations.append(observation)
    for member in archive["cohort_index"]["members"]:
        sessions.append(
            {
                "id": str(uuid5(NAMESPACE_URL, member["session_external_id"])),
                "external_provider": "POLAR",
                "external_id": member["session_external_id"],
                "started_at": member["temporal_evidence"]["start_utc"],
                "sport": "KAYAK",
                "name": None,
                "duration_sec": 4,
            }
        )
    running = {
        **sessions[0],
        "id": str(uuid5(NAMESPACE_URL, "running")),
        "external_id": "running",
        "sport": "RUNNING",
    }
    sessions.append(running)
    return sessions, observations


def contract(archive):
    from app.services.response_experiment_contract import build_response_experiment_manifest

    return build_response_experiment_manifest(archive, experiment_id="inventory-protected-control")


def ready(archive, available, size=4):
    sessions, observations = available
    manifest = contract(archive)
    plan = module.prepare_session_inventory(manifest, archive, sessions, batch_size=size)
    return plan, sessions, observations[:size], manifest, archive


def report(data):
    return module.build_session_inventory(*data)


def test_all_synced_sessions_listed_four_older_kayak_sessions_selected_control_protected(
    archive, available, completed
):
    env, _ = completed
    before = scientific_state(env), env.provider.await_count, env.db.commit_count
    data = ready(archive, available)
    original = deepcopy(data)
    result = report(data)
    assert result["total_synced_sessions"] == result["polar_session_count"] == 10
    assert result["kayak_session_count"] == 9
    assert result["plan"]["selected_session_ids"] == [f"older-{i}" for i in range(4)]
    assert result["plan"]["eligible_older_session_count"] == 6
    assert result["status"] == "COMPLETED_WITH_LIMITATIONS"
    assert result["completed_inspection_count"] == 4
    assert sum(s["role"] == "PROTECTED_CONTROL" for s in result["sessions"]) == 3
    assert sum(s["inspection_status"] == "NOT_INSPECTED" for s in result["sessions"]) == 5
    inspected = [s for s in result["sessions"] if s["role"] == "SELECTED_THIS_BATCH"]
    for row in inspected:
        assert row["gps"]["timestamped_coordinate_count"] >= 2
        assert row["hr"]["slot_count"] == row["hr"]["positive_finite_sample_count"] == 4
        assert row["reported_export_timebase"]["status"] == "NOT_PROVIDED"
        assert row["reported_sensor_declaration"]["status"] == "NOT_DECLARED"
        assert row["reported_sensor_declaration"]["exercises"][0]["declared_sensor"] is None
        assert row["reported_replay_storage"]["total_count"] == 0
        assert row["preparation_actions"] == [
            "TCX_EXPORT_TIMEBASE_MATCH_REQUIRED",
            "SENSOR_DECLARATION_OR_CORRECTION_REQUIRED",
            "ENVIRONMENT_CAPTURE_AND_PINNED_REPLAY_REQUIRED",
            "MODEL_INPUT_AND_HISTORY_COVERAGE_CHECK_REQUIRED",
        ]
        assert row["split_assignment"] == "NOT_ASSIGNED"
    checked = module.check_session_inventory(result, *data)
    assert checked["reconstruction_verified"] is True
    for key in (
        "training_authorized",
        "numeric_output_authorized",
        "model_fit_performed",
        "test_scoring_performed",
        "source_evidence_verified",
        "owner_authorization_verified",
        "current_replay_source_binding_verified",
        "environment_feature_coverage_verified",
        "split_assignment_persisted",
    ):
        assert result[key] is False
    assert data == original
    assert before == (scientific_state(env), env.provider.await_count, env.db.commit_count)


def test_plan_is_deterministic_under_session_list_order_but_commits_exact_list(archive, available):
    sessions, _ = available
    first = module.prepare_session_inventory(contract(archive), archive, sessions)
    repeated = module.prepare_session_inventory(contract(archive), archive, deepcopy(sessions))
    reversed_plan = module.prepare_session_inventory(
        contract(archive), archive, list(reversed(sessions))
    )
    assert first == repeated
    assert first["selected_session_ids"] == reversed_plan["selected_session_ids"]
    assert first["session_list_hash"] != reversed_plan["session_list_hash"]


def test_batch_skip_advances_to_other_old_sessions_without_protected_reassignment(
    archive, available
):
    sessions, _ = available
    plan = module.prepare_session_inventory(
        contract(archive), archive, sessions, skip_ids=[f"older-{i}" for i in range(4)]
    )
    assert plan["selected_session_ids"] == ["older-4", "older-5"]
    assert plan["operator_skip_session_ids"] == [f"older-{i}" for i in range(4)]


@pytest.mark.parametrize("size", [0, 9, True, 4.0])
def test_batch_bound_is_technical_not_overridable(archive, available, size):
    with pytest.raises(ValueError, match="INVENTORY_BATCH_LIMIT"):
        ready(archive, available, size)


@pytest.mark.parametrize("skips", [["unknown"], ["older-0", "older-0"], ["session-1"], [True]])
def test_skip_list_requires_distinct_known_older_candidates(archive, available, skips):
    with pytest.raises(ValueError, match="INVENTORY_SKIP_IDENTITIES_INVALID"):
        module.prepare_session_inventory(contract(archive), archive, available[0], skip_ids=skips)


def test_partial_checkpoint_and_failed_request_do_not_invent_missing_gps_or_hr(archive, available):
    data = ready(archive, available)
    data = (
        *data[:2],
        [
            {
                "session_external_id": "older-0",
                "status": "REQUEST_FAILED",
                "reason": "INVENTORY_HTTP_502",
            }
        ],
        *data[3:],
    )
    result = report(data)
    assert result["status"] == "PARTIAL_INVENTORY"
    assert result["failed_inspection_count"] == 1
    failed = next(s for s in result["sessions"] if s["external_id"] == "older-0")
    assert failed["inspection_status"] == "REQUEST_FAILED"
    assert "gps" not in failed and "reported_export_timebase" not in failed
    pending = next(s for s in result["sessions"] if s["external_id"] == "older-1")
    assert pending["inspection_status"] == "NOT_INSPECTED"


def test_naive_database_time_is_explicitly_unsupported_and_not_assumed_utc(archive, available):
    sessions, _ = deepcopy(available)
    sessions[0]["started_at"] = "2026-09-27T15:00:00"
    manifest = contract(archive)
    plan = module.prepare_session_inventory(manifest, archive, sessions)
    result = report((plan, sessions, [], manifest, archive))
    row = next(s for s in result["sessions"] if s["external_id"] == "older-0")
    assert row["role"] == "STORED_START_METADATA_UNSUPPORTED"
    assert "older-0" not in plan["selected_session_ids"]


@pytest.mark.parametrize("which", ["routes", "samples"])
def test_duplicate_current_source_match_is_visible_without_selecting_last(
    archive, available, which
):
    data = deepcopy(ready(archive, available, 1))
    source = data[2][0]["inspection"]["raw"][which]["trainingSessions"]
    source.append(deepcopy(source[0]))
    row = next(s for s in report(data)["sessions"] if s["role"] == "SELECTED_THIS_BATCH")
    assert row[f"{'route' if which == 'routes' else 'sample'}_session_match_count"] == 2
    assert row["gps"] is row["hr"] is None
    assert row["preparation_actions"] == ["CURRENT_ROUTE_AND_SAMPLE_SOURCE_MATCH_REQUIRED"]


def test_existing_snapshot_is_historical_storage_not_current_replay_binding(archive, available):
    data = deepcopy(ready(archive, available, 1))
    data[2][0]["replays"] = {
        "status": "AVAILABLE",
        "total_count": 150,
        "returned_count": 1,
        "truncated": True,
        "snapshots": [
            {
                "snapshot_id": str(uuid5(NAMESPACE_URL, "historical")),
                "snapshot_hash": "a" * 64,
                "captured_unassigned_package_hash": "b" * 64,
            }
        ],
    }
    row = next(s for s in report(data)["sessions"] if s["role"] == "SELECTED_THIS_BATCH")
    assert row["reported_replay_storage"]["truncated"] is True
    assert row["reported_replay_storage"]["current_source_binding_verified"] is False
    assert "EXPLICIT_PINNED_REPLAY_SOURCE_CHECK_REQUIRED" in row["preparation_actions"]
    assert row["environment_feature_coverage"] == "NOT_CHECKED_FROM_PINNED_REPLAY"


@pytest.mark.parametrize(
    "case", ["owner", "validation", "date", "clock_bool", "replay_count", "declaration_source"]
)
def test_changed_or_inconsistent_reported_evidence_is_rejected(archive, available, case):
    data = deepcopy(ready(archive, available, 1))
    item = data[2][0]
    summary = item["inspection"]["route_sessions"][0]
    if case == "owner":
        summary["heart_rate_signal_diagnostics"]["input_provenance"]["athlete_id"] = str(
            uuid5(NAMESPACE_URL, "foreign")
        )
    elif case == "validation":
        summary["heart_rate_sample_validation"]["available"] = False
    elif case == "date":
        item["inspection"]["route_date"] = "2026-09-26"
    elif case == "clock_bool":
        summary["heart_rate_signal_diagnostics"]["timebase_evidence"]["verified_exercise_count"] = (
            True
        )
    elif case == "replay_count":
        item["replays"]["returned_count"] = 1
    else:
        summary["heart_rate_acquisition_context"]["current_api_source_hash"] = "f" * 64
    with pytest.raises(ValueError):
        report(data)


@pytest.mark.parametrize("case", ["authority", "count", "role", "ready", "extra"])
def test_rehashed_inventory_cannot_promote_claim_or_change_counts(archive, available, case):
    data = ready(archive, available)
    value = report(data)
    if case == "authority":
        value["training_authorized"] = True
    elif case == "count":
        value["kayak_session_count"] += 1
    elif case == "role":
        value["sessions"][0]["role"] = "TRAIN"
    elif case == "ready":
        value["current_replay_source_binding_verified"] = True
    else:
        value["extra"] = True
    value["inventory_hash"] = canonical_hash(
        {k: v for k, v in value.items() if k != "inventory_hash"}
    )
    with pytest.raises(ValueError, match="INVENTORY_RECONSTRUCTION_MISMATCH"):
        module.check_session_inventory(value, *data)


def test_duplicate_ids_and_oversized_list_fail_before_selection(archive, available, monkeypatch):
    sessions, _ = available
    with pytest.raises(ValueError):
        module.prepare_session_inventory(contract(archive), archive, [*sessions, sessions[0]])
    monkeypatch.setattr(module, "MAX_SESSIONS", 1)
    with pytest.raises(ValueError, match="INVENTORY_SESSION_LIST_LIMIT_OR_SHAPE"):
        module.prepare_session_inventory(contract(archive), archive, sessions)


def test_provider_query_date_comes_from_stored_raw_metadata_without_timezone_guess(
    archive, available
):
    session = available[0][0]
    detail = deepcopy(available[1][0]["detail"])
    detail["raw_data"]["startTime"] = "2026-09-28T00:30:00"
    assert module.provider_date(session, detail) == "2026-09-28"
    del detail["raw_data"]["startTime"]
    with pytest.raises(ValueError, match="INVENTORY_PROVIDER_QUERY_DATE_UNAVAILABLE"):
        module.provider_date(session, detail)


def test_path_quoting_does_not_allow_query_parameter_injection():
    session = {
        "id": str(uuid5(NAMESPACE_URL, "path")),
        "external_id": "opaque/with?weather_provider=unsafe",
    }
    assert (
        module.request_path("replays", session)
        == "/integrations/polar/sessions/opaque%2Fwith%3Fweather_provider%3Dunsafe/response-dataset/replay-snapshots?limit=100"
    )
