"""Exact source comparison, read-only queries and sanitized optional transport."""
import asyncio
from copy import deepcopy
from datetime import date, datetime, UTC
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Select
from sqlalchemy.sql.elements import TextClause

from app.models.entities import ExternalConnection, PlannedWorkout, ProviderDataRecord, Sport, User, WorkoutSession
from app.integrations.polar.client import PolarClient
from app.services import polar_phase_diagnostic as diagnostic
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER
from tests.planning.test_p2_4c7_data_connections import connections
from tests.planning.test_p2_4c9r6_target_import import phased, sync, state

ORIGINAL_SESSIONS = PolarClient.list_training_sessions
ORIGINAL_TARGETS = PolarClient.list_training_targets
DAY = date(2026, 8, 12)


class ReadOnly(AsyncSQLiteBridge):
    async def execute(self, statement):
        assert isinstance(statement, Select), "Diagnostic attempted a database mutation"
        return await super().execute(statement)


def seed(env):
    raw = phased(env); sync(env, raw)
    current = state(env)
    with Session(env.engine) as db:
        actual = WorkoutSession(user_id=UUID(ATHLETE), external_provider="POLAR", external_id="august-12-session",
            sport=Sport.KAYAK,
            started_at=datetime(2026, 8, 12, 11, tzinfo=UTC), planned_workout_id=current["id"],
            raw_data={"identifier": {"id": "august-12-session"}, "trainingTarget": {"id": "new-target"},
                "startTime": "2026-08-12T13:00:00", "exercises": [{"identifier": {"id": "owned-exercise"},
                    "samples": {"samples": [{"type": "HEART_RATE", "intervalMillis": 1000, "values": [115, 116]}]},
                    "laps": {"laps": [{"splitTimeMillis": 1123000, "durationMillis": 1123000,
                        "distanceMeters": 2600}], "autoLaps": []}}]})
        db.add(actual); db.commit()
    return raw


def read(env):
    with Session(env.engine, expire_on_commit=False) as db:
        user = db.get(User, UUID(ATHLETE)); bridge = ReadOnly(db)
        result = asyncio.run(diagnostic.local_report(bridge, user, DAY))
        assert not db.dirty and not db.new and not db.deleted and bridge.commit_count == 0
        db.rollback()
    return result


def test_august_report_keeps_native_lap_times_and_unknown_distance_plan_duration(connections):
    seed(connections); before = state(connections); report = read(connections)
    session = report["sessions"][0]["stored"]; exercise = session["exercise_views"]["exercises"]["exercises"][0]
    assert session["native_target_id"] == "new-target"
    assert exercise["phase_fields"]["fields"][0]["value"]["laps"][0]["splitTimeMillis"] == 1123000
    assert exercise["sample_clocks"] == [{"type": "HEART_RATE", "intervalMillis": 1000, "slot_count": 2}]
    assert report["plans"][0]["blocks"][0]["duration_sec"] is None
    assert not report["application_data_changed"] and state(connections) == before
    assert "values" not in str(report) and "access_token" not in str(report)


def test_owned_archives_can_reveal_a_previously_lost_phase_source_without_repairing_it(connections):
    raw = seed(connections); old = state(connections)
    with Session(connections.engine) as db:
        plan = db.get(PlannedWorkout, old["id"])
        blocks = list(plan.blocks)
        for block in blocks: block.parent_block_id = None
        db.flush()
        for block in blocks: db.delete(block)
        plan.raw_data = {"session": raw["session"], "exercise": []}; db.commit()
    report = read(connections)
    result = diagnostic.findings(report)
    assert any(i["code"] == "ARCHIVED_PHASE_SOURCE_AVAILABLE" for i in result)
    assert report["plans"][0]["blocks"] == [] and state(connections)["blocks"] == []


def test_other_owners_archive_and_workout_never_enter_the_report(connections):
    seed(connections)
    with Session(connections.engine) as db:
        db.add(ProviderDataRecord(user_id=UUID(OTHER), provider="POLAR", data_type="DATA_SYNC_TARGETS",
            raw_data={"targets": [{"session": {"id": "new-target", "name": "PRIVATE FOREIGN SOURCE"}}]}))
        db.commit()
    report = read(connections)
    assert "PRIVATE FOREIGN SOURCE" not in json.dumps(report)
    assert all(p["stored"]["name"] != "PRIVATE FOREIGN SOURCE" for p in report["plans"])


def test_native_and_enriched_lap_views_are_both_retained_for_comparison():
    raw = {"exercises": [{"laps": {"laps": [{"durationMillis": 1123000}]}}],
           "exerciseSamples": [{"laps": {"autoLaps": [{"durationMillis": 600000}]}}]}
    view = diagnostic.session_view(raw)
    assert set(view["exercise_views"]) == {"exercises", "exerciseSamples"}
    assert raw["exercises"][0]["laps"]["laps"][0]["durationMillis"] == 1123000


def test_phase_discovery_retains_undocumented_fields_and_redacts_private_data():
    raw = {"phaseResults": [{"durationMillis": 1123000, "name": "warmup", "phaseId": 17,
                            "access_token": "NEVER SHARE", "latitude": 1.23}],
           "samples": {"values": [1] * 50000}, "authorization": "NEVER SHARE"}
    result = diagnostic.related_fields(raw)
    assert result["fields"][0]["path"] == "$.phaseResults"
    assert result["fields"][0]["value"][0]["durationMillis"] == 1123000
    assert "NEVER SHARE" not in json.dumps(result) and "latitude" not in json.dumps(result)
    assert not result["scan_truncated"]


def test_excessive_candidate_data_is_explicitly_truncated():
    result = diagnostic.related_fields({"phases": [{"name": str(i)} for i in range(300)]})
    value = result["fields"][0]["value"]
    assert value[-1] == {"diagnostic_omitted": "item_limit", "source_count": 300}


def test_actual_transport_fetches_one_day_with_laps_and_pauses_without_refreshing_or_importing(connections, monkeypatch):
    raw = seed(connections); before = state(connections); calls = []
    monkeypatch.setattr(PolarClient, "list_training_sessions", ORIGINAL_SESSIONS)
    monkeypatch.setattr(PolarClient, "list_training_targets", ORIGINAL_TARGETS)
    def handle(request):
        calls.append(request)
        assert request.method == "GET" and request.headers["Authorization"] == "Bearer NOT FOR REPORT"
        if "training-sessions" in request.url.path:
            assert request.url.params.get_list("features") == ["statistics", "laps", "pause-times"]
            assert request.url.params["from"] == "2026-08-12T00:00:00" and request.url.params["to"] == "2026-08-13T00:00:00"
            return httpx.Response(200, json={"trainingSessions": [{"identifier": {"id": "august-12-session"}, "phaseResults": [{"durationMillis": 1123000}]}]})
        assert request.url.params["from"] == "2026-08-12" and request.url.params["to"] == "2026-08-13"
        return httpx.Response(200, json={"trainingTarget": [raw]})
    actual = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: actual(**kwargs, transport=httpx.MockTransport(handle)))
    report = asyncio.run(diagnostic.provider_report(PolarClient(), "NOT FOR REPORT", ["training_sessions:read", "training_targets:read"], DAY))
    assert len(calls) == 2 and report["sessions"]["state"] == report["targets"]["state"] == "succeeded"
    assert "NOT FOR REPORT" not in json.dumps(report) and state(connections) == before
    assert report["sessions"]["records"][0]["phase_fields"]["fields"][0]["value"] == [{"durationMillis": 1123000}]


def test_provider_rejection_does_not_export_private_error_body():
    class Reject:
        async def list_training_sessions(self, *args, **kwargs):
            from app.integrations.polar.client import PolarAPIError
            raise PolarAPIError("PRIVATE BODY AND TOKEN", status_code=400)
    result = asyncio.run(diagnostic.provider_report(Reject(), "secret", ["training_sessions:read"], DAY))
    assert result["sessions"]["http_status"] == 400 and result["targets"]["state"] == "scope_missing"
    assert "PRIVATE" not in str(result) and "secret" not in str(result)


@pytest.mark.parametrize("online,expired", [(False, False), (True, True)])
def test_cli_only_selects_and_rolls_back_without_decrypting_offline_or_expired_access(connections, monkeypatch, online, expired):
    seed(connections)
    if expired:
        with Session(connections.engine) as db:
            db.execute(update(ExternalConnection).where(ExternalConnection.user_id == UUID(ATHLETE)).values(expires_at=datetime(2000, 1, 1, tzinfo=UTC)))
            db.commit()
    path = Path(__file__).resolve().parents[4] / "tools/diagnose_polar_phases.py"
    spec = importlib.util.spec_from_file_location("phase_diagnostic_cli", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    from app.db import session as database
    from app.core import config, security
    with Session(connections.engine, expire_on_commit=False) as db:
        user = db.get(User, UUID(ATHLETE)); email = user.email
        class PostgreSQLReadOnly(ReadOnly):
            def get_bind(self):
                return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
            async def execute(self, statement):
                if isinstance(statement, TextClause):
                    assert str(statement) == "SET TRANSACTION READ ONLY" and not self.events
                    self.events.append("read_only_transaction")
                    return None
                assert self.events[0] == "read_only_transaction"
                return await super().execute(statement)
        bridge = PostgreSQLReadOnly(db)
        class Context:
            async def __aenter__(self): return bridge
            async def __aexit__(self, *args): return False
        async def dispose(): pass
        monkeypatch.setattr(database, "SessionLocal", lambda: Context())
        monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(demo_user_email=email))
        def forbidden(*args): raise AssertionError("Offline diagnostic decrypted credentials")
        monkeypatch.setattr(security, "decrypt_secret", forbidden)
        result = asyncio.run(module.collect(SimpleNamespace(date=DAY, fetch_provider=online)))
        assert not result["provider"]["requested"] and bridge.rollback_count == 1 and bridge.commit_count == 0
        assert bridge.events == ["read_only_transaction", "rollback"]


def test_target_absence_is_a_day_scoped_finding_not_a_general_polar_claim(connections):
    seed(connections); report = read(connections)
    report["provider"] = {"targets": {"state": "succeeded", "records": []}}
    results = diagnostic.findings(report)
    assert results == [{"plan_id": report["plans"][0]["id"], "code": "TARGET_NOT_RETURNED_FOR_SELECTED_DAY", "planned_calendar_date": "2026-08-12"}]
