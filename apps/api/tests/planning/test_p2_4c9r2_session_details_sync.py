"""Regression: real UI sync request -> stored provider samples -> chart read API."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.polar.client import PolarAPIError, PolarClient
ORIGINAL_LIST_SESSIONS = PolarClient.list_training_sessions
from app.models.entities import ExternalConnection, ProviderDataRecord, WorkoutSession
from app.services import polar_session_details as details
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count
from tests.planning.test_p2_4c7_data_connections import connections as prior, get, post, proposal


def enriched(item):
    result = deepcopy(item)
    result["exercises"] = [{"identifier": {"id": "exercise-" + item["identifier"]["id"]},
        "startTime": item["startTime"], "unknownExerciseField": {"retained": True},
        "statistics": {"statistics": [{"type": "STATISTICS_TYPE_SPEED", "avg": 10.8, "max": 14.1},
            {"type": "STATISTICS_TYPE_POWER", "avg": 0, "max": 200}]},
        "samples": {"samples": [{"type": "HEART_RATE", "intervalMillis": 1000, "values": [110, 111, None, 113]},
            {"type": "SPEED", "intervalMillis": 1000, "values": [10, 11, 0, 12]}]}}]
    return result


@pytest.fixture
def connections(tmp_path, monkeypatch):
    wrapper = prior.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    env.detail_calls, env.detail_responses = [], {}
    env.on_detail = None
    async def sessions(self, token, first, last, features=None):
        if features is None:
            env.provider_calls.append(("sessions", first.isoformat(), last.isoformat()))
            return deepcopy(env.session_payload)
        assert features == ["statistics", "samples", "zones", "laps", "routes"]
        assert last == first + timedelta(days=1)
        env.detail_calls.append(first.isoformat())
        if env.on_detail:
            env.on_detail(first)
        answer = env.detail_responses.get(first.isoformat())
        if isinstance(answer, Exception):
            raise answer
        return deepcopy(answer) if answer is not None else {"trainingSessions": [enriched(item) for item in env.session_payload["trainingSessions"] if date.fromisoformat(item["startTime"][:10]) == first]}
    monkeypatch.setattr(PolarClient, "list_training_sessions", sessions)
    monkeypatch.setattr(details, "now", env.clock.tick)
    try:
        yield env
    finally:
        wrapper.close()


def identity(env, external="new-session"):
    with Session(env.engine) as db:
        return str(db.scalar(select(WorkoutSession.id).where(WorkoutSession.user_id == UUID(ATHLETE), WorkoutSession.external_id == external)))


def fetch(env, token=880002, status=201):
    return post(env, proposal(token=token, datasets=["session_details"]), status=status)


def read(env, session_id):
    r = env.client.get("/api/v1/planning/calendar/sessions/" + session_id)
    assert r.status_code == 200, r.text
    return r.json()


def test_ui_scope_sync_fills_previously_empty_chart_read_and_preserves_measurements(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    sid = identity(e)
    before = read(e, sid)
    assert before["samples"]["series"] == []
    status = get(e)
    assert status["providers"][0]["allowed_datasets"] == ["sessions", "targets", "session_details"]
    body = proposal(token=880002, datasets=status["providers"][0]["allowed_datasets"])
    result = post(e, body)
    assert result["run"]["state"] == "succeeded"
    report = result["run"]["datasets"][2]
    assert report["updated"] == 1 and report["details"]["with_samples"] == 1
    after = read(e, sid)
    assert [s["metric_key"] for s in after["samples"]["series"]] == ["heart_rate_bpm", "speed_kmh"]
    for key in ("started_at", "ended_at", "duration_sec", "distance_m", "calories", "planned_workout_id"):
        assert after["session"][key] == before["session"][key]
    assert after["session"]["avg_speed"] == 10.8 and after["session"]["avg_power"] == 0
    with Session(e.engine) as db:
        row = db.get(WorkoutSession, UUID(sid))
        assert row.raw_data["unknownProviderField"] == {"retained": True}
        assert row.raw_data["exerciseSamples"][0]["unknownExerciseField"] == {"retained": True}
        records = list(db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.user_id == UUID(ATHLETE))))
        assert any(r.data_type == "DATA_SYNC_PREVIOUS_SESSION" and r.raw_data["raw_data"] == e.session_payload["trainingSessions"][0] for r in records)
        assert any(r.data_type == "DATA_SYNC_SESSION_DETAILS" for r in records)
    assert e.detail_calls == ["2026-10-22"]
    assert all(not request.in_transaction() for request in e.requests)
    output = os.environ.get("P24C9R2_FIXTURE_OUTPUT")
    if output:
        Path(output).write_text(json.dumps({"body": body, "receipt": result, "status": get(e), "before": before, "after": after}, ensure_ascii=False, indent=2) + "\n")


def test_recent_first_bounded_batches_resume_and_old_retry_never_reimports(connections, monkeypatch):
    e = connections
    one = e.session_payload["trainingSessions"][0]
    e.session_payload["trainingSessions"] = [{**deepcopy(one), "identifier": {"id": "day-" + str(day)},
        "startTime": f"2026-10-{day:02}T07:00:00Z", "stopTime": f"2026-10-{day:02}T08:00:00Z"} for day in (20, 21, 22)]
    post(e, proposal(token=880001, datasets=["sessions"]))
    monkeypatch.setattr(details, "DAY_LIMIT", 1)
    first = fetch(e)
    assert first["run"]["state"] == "partial" and first["run"]["error_code"] == "DATA_SYNC_DETAILS_PENDING"
    assert first["run"]["datasets"][0]["details"]["pending_sessions"] == 2
    second = fetch(e, 880003)
    assert second["run"]["datasets"][0]["details"]["already_complete"] == 1
    assert second["run"]["datasets"][0]["skipped"] == 1
    third = fetch(e, 880004)
    assert third["run"]["state"] == "succeeded"
    assert e.detail_calls == ["2026-10-22", "2026-10-21", "2026-10-20"]
    again = fetch(e, status=200)
    assert again["reused"] and again["result"] == first["result"]
    fourth = fetch(e, 880005)
    assert fourth["run"]["datasets"][0]["details"]["already_complete"] == 3
    assert len(e.detail_calls) == 3


def test_known_absence_is_reported_and_can_be_rechecked_after_its_short_cache(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    e.detail_responses["2026-10-22"] = deepcopy(e.session_payload)
    result = fetch(e)
    report = result["run"]["datasets"][0]
    assert report["details"]["without_samples"] == 1 and report["details"]["with_samples"] == 0
    assert read(e, identity(e))["samples"]["series"] == []
    fetch(e, 880003)
    assert len(e.detail_calls) == 1
    with Session(e.engine) as db:
        for row in db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.data_type == details.RECEIPT_TYPE)):
            row.fetched_at = e.clock.current - timedelta(hours=1)
        db.commit()
    del e.detail_responses["2026-10-22"]
    result = fetch(e, 880004)
    assert result["run"]["datasets"][0]["details"]["with_samples"] == 1 and len(e.detail_calls) == 2


def test_missing_provider_record_is_pending_not_a_claimed_absence(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    e.detail_responses["2026-10-22"] = {"trainingSessions": []}
    result = fetch(e)
    d = result["run"]["datasets"][0]
    assert d["error_code"] == "DATA_SYNC_DETAILS_NOT_RETURNED" and d["details"]["pending_sessions"] == 1
    assert d["details"]["without_samples"] == 0


@pytest.mark.parametrize("error,code", [(PolarAPIError("secret", status_code=403), "DATA_SYNC_PERMISSION_MISSING"),
    (PolarAPIError("secret", status_code=400), "DATA_SYNC_PROVIDER_HTTP_400"), (TimeoutError(), "DATA_SYNC_TIMEOUT")])
def test_provider_failure_is_durable_and_does_not_erase_saved_base_data(connections, error, code):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    before = read(e, identity(e))
    e.detail_responses["2026-10-22"] = error
    result = fetch(e)
    assert result["run"]["state"] == "failed" and result["run"]["error_code"] == code
    assert read(e, identity(e))["session"] == before["session"]
    assert "secret" not in json.dumps(result)


def test_foreign_owner_rows_are_never_updated_or_used_as_receipts(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    with Session(e.engine) as db:
        db.add(WorkoutSession(id=UUID(int=998899), user_id=UUID(OTHER), external_provider="POLAR", external_id="foreign",
            sport=db.get(WorkoutSession, UUID(identity(e))).sport, started_at=datetime(2026, 10, 22, 9, tzinfo=UTC), raw_data={"foreign": True}))
        db.commit()
    fetch(e)
    with Session(e.engine) as db:
        assert db.get(WorkoutSession, UUID(int=998899)).raw_data == {"foreign": True}


def test_source_changed_during_provider_io_requires_new_acquisition(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    sid = identity(e)
    def change(_day):
        with Session(e.engine) as db:
            row = db.get(WorkoutSession, UUID(sid)); row.raw_data = {**row.raw_data, "modified": "changed-during-fetch"}; db.commit()
    e.on_detail = change
    result = fetch(e)
    assert result["run"]["error_code"] == "DATA_SYNC_DETAILS_SOURCE_CONFLICT"
    assert read(e, sid)["samples"]["series"] == []


def test_additive_merge_fills_route_only_views_without_losing_routes_or_unknown_fields():
    incoming = enriched({"identifier": {"id": "s"}, "startTime": "2026-10-22T06:00:00"})
    original = {"identifier": {"id": "s"}, "exerciseSamples": [{"identifier": {"id": "exercise-s"},
        "startTime": "2026-10-22T06:00:00", "routes": {"retained": True}, "unknown": [1, 2]}]}
    before = deepcopy(original)
    result = details.merge_details(original, incoming, "s")
    assert original == before and result["exerciseSamples"][0]["routes"] == {"retained": True}
    assert result["exerciseSamples"][0]["samples"]["samples"][0]["values"] == [110, 111, None, 113]
    assert result["exerciseSamples"][0]["unknown"] == [1, 2]


def test_additive_merge_accepts_both_sample_wrappers_and_rejects_changed_measurements():
    incoming = enriched({"identifier": {"id": "s"}, "startTime": "2026-10-22T06:00:00"})
    original = {"identifier": {"id": "s"}, "exerciseSamples": deepcopy(incoming["exercises"])}
    original["exerciseSamples"][0]["samples"] = original["exerciseSamples"][0]["samples"]["samples"]
    assert details.merge_details(original, incoming, "s")["exerciseSamples"][0]["samples"]["samples"] == incoming["exercises"][0]["samples"]["samples"]
    changed = deepcopy(incoming); changed["exercises"][0]["samples"]["samples"][0]["values"][0] = 999
    with pytest.raises(details.PolarRawPreservationError):
        details.merge_details(original, changed, "s")


def test_statistics_only_response_does_not_hide_preserved_native_samples():
    source = enriched({"identifier": {"id": "s"}, "startTime": "2026-10-22T06:00:00"})
    old = deepcopy(source)
    del source["exercises"][0]["samples"]
    result = details.merge_details(old, source, "s")
    assert result["exercises"] == old["exercises"]
    assert result["exerciseSamples"][0]["samples"] == old["exercises"][0]["samples"]


def test_empty_owned_window_does_not_call_the_provider(connections):
    e = connections
    result = fetch(e)
    assert result["run"]["state"] == "succeeded" and e.detail_calls == []
    assert result["run"]["datasets"][0]["details"]["requested_sessions"] == 0


def test_scope_is_required_even_for_details_only_request(connections):
    with Session(connections.engine) as db:
        c = db.scalar(select(ExternalConnection).where(ExternalConnection.user_id == UUID(ATHLETE)))
        c.scopes = ["training_targets:read"]; db.commit()
    result = post(connections, proposal(datasets=["session_details"]), status=409)
    assert result["detail"]["code"] == "DATA_SYNC_PERMISSION_MISSING"


def test_actual_polar_transport_requests_one_day_with_all_optional_features(connections, monkeypatch):
    import httpx
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    captured = []
    def handler(request):
        assert request.url.path == "/v4/data/training-sessions/list"
        assert request.url.params.get_list("features") == ["statistics", "samples", "zones", "laps", "routes"]
        assert request.url.params["from"] == "2026-10-22T00:00:00"
        assert request.url.params["to"] == "2026-10-23T00:00:00"
        captured.append(True)
        return httpx.Response(200, json={"trainingSessions": [enriched(e.session_payload["trainingSessions"][0])]})
    original = httpx.AsyncClient
    monkeypatch.setattr(PolarClient, "list_training_sessions", ORIGINAL_LIST_SESSIONS)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = fetch(e)
    assert result["run"]["state"] == "succeeded" and captured == [True]
    assert read(e, identity(e))["samples"]["valid_sample_count"] == 7


def test_failed_day_commit_preserves_original_raw_and_reports_no_uncommitted_progress(connections, monkeypatch):
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    sid = identity(e)
    original = AsyncSQLiteBridge.commit
    async def commit(self):
        if self.session.scalar(select(ProviderDataRecord.id).where(ProviderDataRecord.data_type == details.RECEIPT_TYPE)) is not None:
            raise RuntimeError("Synthetic detail commit failure")
        await original(self)
    monkeypatch.setattr(AsyncSQLiteBridge, "commit", commit)
    result = fetch(e)
    report = result["run"]["datasets"][0]
    assert report["state"] == "failed" and report["updated"] == 0 and report["details"]["pending_sessions"] == 1
    assert read(e, sid)["samples"]["series"] == []
    with Session(e.engine) as db:
        assert db.get(WorkoutSession, UUID(sid)).raw_data == e.session_payload["trainingSessions"][0]
        assert not list(db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.data_type == details.RECEIPT_TYPE)))


def test_an_error_after_a_saved_day_retains_that_progress_for_next_request(connections):
    e = connections
    one = e.session_payload["trainingSessions"][0]
    e.session_payload["trainingSessions"] = [{**deepcopy(one), "identifier": {"id": "day-" + str(day)},
        "startTime": f"2026-10-{day:02}T07:00:00Z", "stopTime": f"2026-10-{day:02}T08:00:00Z"} for day in (21, 22)]
    post(e, proposal(token=880001, datasets=["sessions"]))
    e.detail_responses["2026-10-21"] = TimeoutError()
    result = fetch(e)
    assert result["run"]["datasets"][0]["details"]["fetched_sessions"] == 1
    assert result["run"]["datasets"][0]["error_code"] == "DATA_SYNC_TIMEOUT"
    assert len(read(e, identity(e, "day-22"))["samples"]["series"]) == 2
    del e.detail_responses["2026-10-21"]
    result = fetch(e, 880003)
    assert result["run"]["state"] == "succeeded"
    assert result["run"]["datasets"][0]["details"]["already_complete"] == 1
    assert e.detail_calls == ["2026-10-22", "2026-10-21", "2026-10-21"]


def test_tampered_fetch_marker_cannot_silently_skip_acquisition(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    fetch(e)
    with Session(e.engine) as db:
        row = db.scalar(select(ProviderDataRecord).where(ProviderDataRecord.data_type == details.RECEIPT_TYPE))
        row.raw_data = {**row.raw_data, "with_samples": False}; db.commit()
    result = fetch(e, 880003)
    assert result["run"]["state"] == "failed"
    assert len(e.detail_calls) == 1
