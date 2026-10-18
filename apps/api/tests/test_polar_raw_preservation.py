"""Preservation and actual sync-service paths without provider or production DB access."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.models.entities import Sport
from app.services.polar_raw_preservation import (
    MARKER, PolarRawPreservationError, merge_polar_raw, polar_session_time)


def raw():
    return {"identifier": {"id": "session-1"}, "startTime": "2026-07-01T10:00:00",
        "stopTime": "2026-07-01T10:01:00", "timezoneOffsetMinutes": 120, "durationMillis": 60000,
        "distanceMeters": 200, "sport": {"id": "95"}, "hrAvg": 130, "hrMax": 140,
        "trainingLoadReport": {"cardioLoad": 12},
        "exercises": [{"identifier": {"id": "exercise-1"}, "durationMillis": 60000}],
        "exerciseSamples": [{"identifier": {"id": "exercise-1"}, "durationMillis": 60000,
            "samples": {"samples": [{"type": "HEART_RATE", "intervalMillis": 1000, "values": [130, 131]}]},
            "routes": {"route": {"latitude": [47.0], "longitude": [19.0]}}, "pauseTimes": [{"retained": True}]}],
        "exerciseStatistics": [{"retained": True}], MARKER: {"source_sha256": "a" * 64}}


def base(old=None):
    old = raw() if old is None else old
    return {k: deepcopy(v) for k, v in old.items() if k not in ("exerciseSamples", "exerciseStatistics", MARKER, "trainingLoadReport")}


def test_base_refresh_preserves_samples_routes_statistics_reports_and_provenance():
    old = raw(); original = deepcopy(old); incoming = base(old); incoming["modified"] = "new"
    merged = merge_polar_raw(old, incoming, "session-1")
    for key in ("exerciseSamples", "exerciseStatistics", "trainingLoadReport", MARKER):
        assert merged[key] == old[key]
    assert merged["modified"] == "new" and old == original


def test_samples_only_refresh_retains_full_exercise_and_does_not_alias_input():
    old = raw(); incoming = base(old)
    incoming["exercises"] = deepcopy(old["exerciseSamples"])
    incoming["exercises"][0].pop("routes")
    incoming["exercises"][0].pop("pauseTimes")
    result = merge_polar_raw(old, incoming, "session-1", feature="samples")
    assert result == old
    result["exerciseSamples"][0]["samples"]["samples"][0]["values"][0] = 999
    assert old["exerciseSamples"][0]["samples"]["samples"][0]["values"][0] == 130


@pytest.mark.parametrize("key,value", [("startTime", "2026-07-01T11:00:00"), ("durationMillis", 90000),
    ("distanceMeters", 300), ("timezoneOffsetMinutes", 60), ("sport", {"id": "1"}),
    ("trainingTarget", {"id": "different"})])
def test_native_bound_metadata_conflicts_are_blocked(key, value):
    old = raw(); incoming = base(old)
    if key == "trainingTarget": old[key] = {"id": "original"}
    incoming[key] = value
    with pytest.raises(PolarRawPreservationError):
        merge_polar_raw(old, incoming, "session-1")


@pytest.mark.parametrize("case", ["different_values", "different_interval", "different_exercise", "different_route"])
def test_conflicting_native_measurements_cannot_overwrite_established_view(case):
    old = raw(); incoming = base(old); incoming["exercises"] = deepcopy(old["exerciseSamples"])
    exercise = incoming["exercises"][0]
    if case == "different_values": exercise["samples"]["samples"][0]["values"][0] = 999
    elif case == "different_interval": exercise["samples"]["samples"][0]["intervalMillis"] = 500
    elif case == "different_exercise": exercise["identifier"]["id"] = "different"
    else: exercise["routes"] = {"different": True}
    with pytest.raises(PolarRawPreservationError):
        merge_polar_raw(old, incoming, "session-1", feature="samples")


@pytest.mark.parametrize("feature", [None, "samples"])
def test_sample_bearing_exercises_view_is_not_erased_by_base_refresh(feature):
    old = raw(); old["exercises"] = deepcopy(old.pop("exerciseSamples"))
    incoming = base(old)
    incoming["exercises"] = [{"identifier": {"id": "exercise-1"}, "durationMillis": 60000}]
    result = merge_polar_raw(old, incoming, "session-1", feature=feature)
    assert result["exercises"] == old["exercises"]
    assert "exerciseSamples" not in result


def test_missing_native_view_can_be_added_and_provenance_cannot_be_injected():
    old = raw(); exercise = old.pop("exerciseSamples")
    incoming = base(old); incoming["exercises"] = exercise
    result = merge_polar_raw(old, incoming, "session-1", feature="samples")
    assert result["exerciseSamples"] == exercise
    incoming[MARKER] = {"untrusted": True}
    with pytest.raises(PolarRawPreservationError):
        merge_polar_raw(old, incoming, "session-1")


def test_timezone_is_declared_not_guessed_and_fractional_clock_is_retained():
    item = raw(); item["startTime"] = "2026-07-01T10:00:00.125"
    assert polar_session_time(item, "startTime").isoformat() == "2026-07-01T08:00:00.125000+00:00"
    item.pop("timezoneOffsetMinutes")
    with pytest.raises(PolarRawPreservationError):
        polar_session_time(item, "startTime")
    item["startTime"] = "2026-07-01T10:00:00Z"
    assert polar_session_time(item, "startTime").tzinfo == timezone.utc


def test_sync_service_keeps_native_payloads_across_all_feature_paths(monkeypatch):
    import app.services.polar_sync as sync
    owner = uuid4(); old = raw()
    row = SimpleNamespace(user_id=owner, raw_data=deepcopy(old), cardio_load=12, perceived_load=3,
        avg_hr=130, max_hr=140, avg_speed=10, max_speed=12, sport=Sport.KAYAK)
    seen_queries = []
    class DB:
        commits = 0
        async def scalar(self, query):
            seen_queries.append(str(query))
            if "external_connections" in str(query): return SimpleNamespace()
            return row
        async def commit(self): self.commits += 1
        def add(self, value): raise AssertionError("no insert expected")
    class Polar:
        async def list_sports(self, token): return {"sports": [{"id": "95", "name": "WATERSPORTS_KAYAKING"}]}
        async def list_training_sessions(self, token, start, end, features=None):
            incoming = base(old)
            if features == ["samples"]:
                incoming["exercises"] = deepcopy(old["exerciseSamples"])
                incoming["exercises"][0].pop("routes")
            elif features == ["training-load-report"]:
                incoming["trainingLoadReport"] = {"cardioLoad": 13}
            elif features == ["statistics"]:
                incoming["exercises"][0]["statistics"] = {"statistics": []}
            return {"trainingSessions": [incoming]}
    async def token(db, connection): return "synthetic-token"
    monkeypatch.setattr(sync, "PolarClient", Polar)
    monkeypatch.setattr(sync, "get_valid_access_token", token)
    db = DB()
    assert asyncio.run(sync.sync_recent_sessions(db, SimpleNamespace(id=owner))) == 0
    assert row.raw_data["exerciseSamples"] == old["exerciseSamples"]
    assert row.raw_data[MARKER] == old[MARKER]
    assert row.cardio_load == 13 and row.perceived_load == 3 and row.avg_speed == 10
    assert row.started_at.isoformat() == "2026-07-01T08:00:00+00:00"
    assert db.commits == 4
    assert all("user_id" in q for q in seen_queries)


def test_sync_refuses_foreign_session_before_modifying_any_field(monkeypatch):
    import app.services.polar_sync as sync
    row = SimpleNamespace(user_id=uuid4(), raw_data=raw(), sport=Sport.RUNNING)
    class DB:
        commits = 0
        async def scalar(self, q): return SimpleNamespace() if "external_connections" in str(q) else row
        async def commit(self): self.commits += 1
    class Polar:
        async def list_sports(self, token): return {"sports": []}
        async def list_training_sessions(self, *args, **kwargs): return {"trainingSessions": [base()]}
    async def token(*args): return "synthetic"
    monkeypatch.setattr(sync, "PolarClient", Polar); monkeypatch.setattr(sync, "get_valid_access_token", token)
    db = DB()
    with pytest.raises(PolarRawPreservationError, match="ANOTHER_OWNER"):
        asyncio.run(sync.sync_recent_sessions(db, SimpleNamespace(id=uuid4())))
    assert db.commits == 0 and row.sport == Sport.RUNNING
