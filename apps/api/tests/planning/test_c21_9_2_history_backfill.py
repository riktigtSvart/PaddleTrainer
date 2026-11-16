"""Bounded V4 history commands use existing owned, durable sync receipts."""
import json
import os
from copy import deepcopy
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import PlannedWorkout, WorkoutSession
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c7_data_connections import connections, post, proposal, BASE


def request(token=219230, first="2021-12-01", last="2022-03-01", **changes):
    return proposal(token, datasets=["sessions"], future_days=0,
        history_range={"from_date": first, "to_exclusive": last}, **changes)


def source(env, identifier="old-running", start="2021-12-15T07:00:00Z", stop="2021-12-15T08:00:00Z"):
    env.session_payload = {"trainingSessions": [{"identifier": {"id": identifier},
        "startTime": start, "stopTime": stop, "durationMillis": 3600000,
        "sport": {"id": "95"}, "name": "Synthetic historical session", "distanceMeters": 8000,
        "unknownHistoricalField": {"retained": True}}]}


def export(value):
    if os.getenv("C21_9_2_HISTORY_EXPORT"):
        Path(os.environ["C21_9_2_HISTORY_EXPORT"]).write_text(json.dumps(value), encoding="utf-8")


def test_history_import_retains_source_is_idempotent_and_never_imports_planned_targets(connections):
    source(connections)
    before = count(connections, PlannedWorkout)
    saved = post(connections, request())
    assert saved["run"]["window"]["from_date"] == "2021-12-01"
    assert saved["run"]["window"]["sessions_to_exclusive"] == "2022-03-01"
    assert saved["run"]["state"] == "succeeded"
    assert saved["run"]["datasets"][0]["imported"] == 1
    assert connections.provider_calls == [("sports", None, None), ("sessions", "2021-12-01", "2022-03-01")]
    calls = deepcopy(connections.provider_calls)
    again = post(connections, request(), status=200)
    assert again["result"] == saved["result"] and connections.provider_calls == calls
    assert count(connections, PlannedWorkout) == before
    with Session(connections.engine) as db:
        row = db.scalar(select(WorkoutSession).where(WorkoutSession.external_id == "old-running"))
        assert row.raw_data["unknownHistoricalField"] == {"retained": True} and row.duration_sec == 3600
    export(saved)


def test_range_uses_original_provider_civil_date_before_conversion_to_utc(connections):
    source(connections, start="2021-12-01T00:30:00+02:00", stop="2021-12-01T01:30:00+02:00")
    saved = post(connections, request())
    assert saved["run"]["state"] == "succeeded"
    with Session(connections.engine) as db:
        row = db.scalar(select(WorkoutSession).where(WorkoutSession.external_id == "old-running"))
        assert row.started_at.date() == date(2021, 11, 30)


@pytest.mark.parametrize("first,last", [("2021-12-01", "2022-03-02"), ("2021-12-01", "2021-12-01"),
    ("2022-03-01", "2021-12-01"), ("2021-02-30", "2021-03-01"), ("1899-12-31", "1900-01-01")])
def test_invalid_history_range_makes_no_provider_call(connections, first, last):
    post(connections, request(first=first, last=last), status=422)
    assert connections.provider_calls == []


@pytest.mark.parametrize("changes", [{"datasets": ["targets"]}, {"datasets": ["sessions", "session_details"]},
    {"future_days": 1}, {"provider": "GARMIN"}])
def test_history_cannot_silently_fetch_targets_or_detailed_samples(connections, changes):
    body = request(); body.update(changes)
    post(connections, body, status=422)
    assert connections.provider_calls == []


def test_future_history_window_is_rejected_before_provider_access(connections):
    post(connections, request(first="2027-01-01", last="2027-02-01"), status=409)
    assert connections.provider_calls == []


def test_out_of_range_source_is_not_imported_or_marked_as_completed_history(connections):
    source(connections, start="2022-03-01T00:00:00Z", stop="2022-03-01T01:00:00Z")
    saved = post(connections, request())
    assert saved["run"]["state"] == "failed"
    with Session(connections.engine) as db:
        assert db.scalar(select(WorkoutSession).where(WorkoutSession.external_id == "old-running")) is None


def test_failed_later_batch_preserves_earlier_commits_and_exact_retry_identity(connections):
    source(connections); first = post(connections, request())
    connections.failures["sessions"] = PolarAPIError("synthetic", status_code=429)
    second_body = request(token=219231, first="2021-09-02", last="2021-12-01")
    failed = post(connections, second_body)
    assert first["run"]["state"] == "succeeded" and failed["run"]["state"] == "failed"
    calls = len(connections.provider_calls)
    post(connections, second_body, status=200)
    assert len(connections.provider_calls) == calls
    connections.failures.clear()
    source(connections, identifier="older-running", start="2021-10-15T07:00:00Z", stop="2021-10-15T08:00:00Z")
    second_body["request_id"] = str(UUID(int=219232))
    resumed = post(connections, second_body)
    assert resumed["run"]["state"] == "succeeded"
    with Session(connections.engine) as db:
        assert set(db.scalars(select(WorkoutSession.external_id).where(WorkoutSession.external_id.in_(["old-running", "older-running"])))) == {"old-running", "older-running"}
