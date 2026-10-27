"""Owned, report-pinned repair on real disposable repositories; no provider use."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import BlockType, PlannedWorkout, ProviderDataRecord, Sport, User, WorkoutBlock, WorkoutSession, WorkoutStatus
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningLogicalPlanRow
from app.services import polar_plan_projection_repair as repair
from app.services.session_plan_timeline import plan_timeline
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER
from tests.planning.test_p2_4c7_data_connections import connections
from tests.planning.test_p2_4c9r6_target_import import phased, sync, state


def seed(env):
    raw = phased(env)
    first = raw["exercise"][0]["phaseOrRepeat"][1]
    first["repeatCount"] = 2
    first["phaseOrRepeat"][0]["intensity"] = {"type": "SPEED_ZONES", "lowerZone": 2, "upperZone": 2}
    second = deepcopy(first)
    second["phaseOrRepeat"][0]["intensity"].update(lowerZone=5, upperZone=5)
    raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["distance"] = 2600.0
    raw["exercise"][0]["phaseOrRepeat"].append(second)
    raw["session"]["done"] = True
    sync(env, raw)
    identity = state(env)["id"]
    with Session(env.engine) as db:
        blocks = db.scalars(select(WorkoutBlock).where(WorkoutBlock.workout_id == identity)).all()
        for b in blocks: b.parent_block_id = None
        db.flush()
        for b in blocks: db.delete(b)
        db.add(WorkoutSession(user_id=UUID(ATHLETE), planned_workout_id=identity,
            external_provider="POLAR", external_id="repair-august-actual", sport=Sport.KAYAK,
            started_at=datetime(2026, 8, 12, 16, 1, 49, tzinfo=UTC), duration_sec=4436,
            distance_m=13663.5, raw_data={"trainingTarget": {"id": "new-target"}, "storedMeasurements": [123, None, 124]}))
        db.commit()
    report = {"schema_version": "polar-phase-import-diagnostic-v1", "athlete_id": ATHLETE, "date": "2026-08-12",
        "plans": [{"id": str(identity), "native_target_id": "new-target", "status": "COMPLETED", "source": "POLAR",
            "calendar_date": "2026-08-12", "blocks": [], "stored": {"native_target_id": "new-target", "structure": "complete",
            "exercise_count": 1, "phase_fields": {"scan_truncated": False, "fields": [{"path": "$.exercise[0].phaseOrRepeat", "value": deepcopy(raw["exercise"][0]["phaseOrRepeat"])}]}}}]}
    return report


def invoke(env, report, apply=False, *, bridge_type=AsyncSQLiteBridge, owner=ATHLETE):
    with Session(env.engine, expire_on_commit=False) as db:
        bridge = bridge_type(db)
        result = asyncio.run(repair.repair(bridge, owner=owner, expected=repair.expected_source(report), apply=apply))
        assert not db.in_transaction()
        return result, bridge


def receipts(env):
    with Session(env.engine) as db:
        return [deepcopy(r.raw_data) for r in db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.data_type == repair.CATEGORY))]


def actuals(env):
    with Session(env.engine) as db:
        return [{c.name: repair.value(getattr(row, c.name)) for c in WorkoutSession.__table__.columns}
                for row in db.scalars(select(WorkoutSession).order_by(WorkoutSession.id))]


def test_check_builds_the_reported_seven_nodes_without_mutating_or_using_polar(connections):
    report = seed(connections); before = state(connections); measured = actuals(connections)
    calls = list(connections.provider_calls)
    preview, bridge = invoke(connections, report)
    assert preview["eligible"] and preview["state"] == "preview" and preview["proposed_block_count"] == 7
    assert preview["proposed_blocks"][0]["distance_m"] == 2600 and preview["proposed_blocks"][0]["duration_sec"] is None
    assert [b["intensity_min"] for b in preview["proposed_blocks"] if b["block_type"] == "WORK"] == [2, 5]
    assert bridge.commit_count == 0 and bridge.rollback_count == 1
    assert state(connections) == before and actuals(connections) == measured and receipts(connections) == []
    assert connections.provider_calls == calls


def test_apply_restores_hierarchy_and_nine_planned_phases_without_editing_the_native_or_measured_source(connections):
    report = seed(connections); before = state(connections); measured = actuals(connections)
    result, bridge = invoke(connections, report, True)
    after = state(connections)
    assert result["state"] == "repaired" and result["committed"] and bridge.commit_count == 1
    assert len(after["blocks"]) == 7 and after["raw"] == before["raw"] and actuals(connections) == measured
    assert len(receipts(connections)) == 1 and len(receipts(connections)[0]["inserted_block_ids"]) == 7
    with Session(connections.engine) as db:
        plan = db.get(PlannedWorkout, before["id"])
        assert repair.digest(repair.planned_fields(plan)) == result["planned_row_sha256"]
        timeline = plan_timeline(plan)
        assert len(timeline["parts"][0]["phases"]) == 9
        assert timeline["parts"][0]["phases"][0]["duration_ms"] is None
        assert timeline["parts"][0]["total_ms"] is None


def test_repeating_apply_is_idempotent_and_preserves_persistent_block_ids(connections):
    report = seed(connections); invoke(connections, report, True)
    before = state(connections)
    second, bridge = invoke(connections, report, True)
    assert second["state"] == "already_repaired" and not second["committed"] and bridge.commit_count == 0
    assert state(connections) == before and len(receipts(connections)) == 1


@pytest.mark.parametrize("field", ["phases", "date", "status", "native_id", "source", "invalid_repeat"])
def test_a_changed_source_is_refused_before_inserting_any_block(connections, field):
    report = seed(connections); identity = state(connections)["id"]
    with Session(connections.engine) as db:
        row = db.get(PlannedWorkout, identity)
        if field == "phases":
            raw = deepcopy(row.raw_data); raw["exercise"][0]["phaseOrRepeat"][0]["goal"]["distance"] += 1; row.raw_data = raw
        elif field == "date": row.date = row.date.replace(day=13)
        elif field == "status": row.status = WorkoutStatus.PLANNED
        elif field == "native_id":
            raw = deepcopy(row.raw_data); raw["session"]["id"] = "another-target"; row.raw_data = raw
        elif field == "invalid_repeat":
            raw = deepcopy(row.raw_data); raw["exercise"][0]["phaseOrRepeat"][1]["repeatCount"] = None; row.raw_data = raw
        else: row.source = "MANUAL"
        db.commit()
    before = state(connections)
    with pytest.raises(repair.ProjectionRepairError): invoke(connections, report, True)
    assert state(connections) == before and receipts(connections) == []


def test_another_owner_cannot_apply_a_report(connections):
    report = seed(connections)
    with pytest.raises(repair.ProjectionRepairError, match="OWNER_MISMATCH"):
        invoke(connections, report, True, owner=OTHER)
    assert state(connections)["blocks"] == [] and receipts(connections) == []


def test_forging_the_report_owner_does_not_make_a_foreign_workout_readable(connections):
    report = seed(connections); report["athlete_id"] = OTHER
    with pytest.raises(repair.ProjectionRepairError, match="PLAN_NOT_FOUND"):
        invoke(connections, report, True, owner=OTHER)
    assert state(connections)["blocks"] == [] and receipts(connections) == []


def test_an_existing_different_projection_is_never_replaced(connections):
    report = seed(connections); identity = state(connections)["id"]
    with Session(connections.engine) as db:
        db.add(WorkoutBlock(workout_id=identity, position=0,
            block_type=BlockType.WORK, name="Existing different data", repeat_count=1))
        db.commit()
    before = state(connections); preview, _ = invoke(connections, report)
    assert not preview["eligible"] and preview["blocked_reason"] == "PROJECTION_NOT_EMPTY"
    with pytest.raises(repair.ProjectionRepairError, match="NOT_EMPTY"): invoke(connections, report, True)
    assert state(connections) == before and receipts(connections) == []


def test_planning_owned_sources_keep_the_normal_import_protection(connections):
    report = seed(connections); identity = state(connections)["id"]
    with Session(connections.engine) as db:
        db.add(PlanningLogicalPlanRow(logical_plan_id="protected-source", athlete_id=UUID(ATHLETE), source_workout_id=identity,
            current_revision_id=None, current_revision_number=0, authority_established_at=None,
            created_at=datetime(2026, 8, 12, tzinfo=UTC), updated_at=datetime(2026, 8, 12, tzinfo=UTC)))
        db.commit()
    preview, _ = invoke(connections, report)
    assert preview["blocked_reason"] == "PROJECTION_PLANNING_OWNED"
    with pytest.raises(repair.ProjectionRepairError, match="PLANNING_OWNED"): invoke(connections, report, True)
    assert state(connections)["blocks"] == [] and receipts(connections) == []


def test_failed_commit_rolls_back_insertions_and_the_receipt_together(connections):
    report = seed(connections)
    class FailCommit(AsyncSQLiteBridge):
        async def commit(self): raise RuntimeError("Synthetic lost commit acknowledgement")
    with pytest.raises(repair.ProjectionRepairError, match="COMMIT_OUTCOME_UNKNOWN"):
        invoke(connections, report, True, bridge_type=FailCommit)
    assert state(connections)["blocks"] == [] and receipts(connections) == []


def test_a_new_competing_block_is_detected_without_any_delete_operation(connections):
    report = seed(connections); identity = state(connections)["id"]
    class Race(AsyncSQLiteBridge):
        async def flush(self):
            if self.session.new:
                self.session.add(WorkoutBlock(workout_id=identity, position=99,
                    block_type=BlockType.WORK, repeat_count=1))
            await super().flush()
        async def delete(self, *args): raise AssertionError("Repair must never delete a block")
    with pytest.raises(repair.ProjectionRepairError, match="POSTWRITE_MISMATCH"):
        invoke(connections, report, True, bridge_type=Race)
    assert state(connections)["blocks"] == [] and receipts(connections) == []


@pytest.mark.parametrize("change", ["truncated", "omitted", "multi", "not_empty", "foreign_native", "ambiguous", "boolean_count"])
def test_an_incomplete_or_ambiguous_report_cannot_authorize_repair(connections, change):
    report = seed(connections); plan = report["plans"][0]
    if change == "truncated": plan["stored"]["phase_fields"]["scan_truncated"] = True
    elif change == "omitted": plan["stored"]["phase_fields"]["fields"][0]["value"].append({"diagnostic_omitted": "item_limit"})
    elif change == "multi": plan["stored"]["exercise_count"] = 2
    elif change == "not_empty": plan["blocks"] = [{"id": "existing"}]
    elif change == "foreign_native": plan["stored"]["native_target_id"] = "other"
    elif change == "boolean_count": plan["stored"]["exercise_count"] = True
    else: report["plans"].append(deepcopy(plan))
    with pytest.raises(repair.ProjectionRepairError): repair.expected_source(report)
    assert state(connections)["blocks"] == []


def test_receipt_failure_rolls_back_the_source_projection(connections, monkeypatch):
    report = seed(connections)
    async def unavailable(*args, **kwargs): raise RuntimeError("Synthetic receipt storage failure")
    monkeypatch.setattr(repair, "archive_payload", unavailable)
    with pytest.raises(RuntimeError, match="receipt storage"):
        invoke(connections, report, True)
    assert state(connections)["blocks"] == [] and receipts(connections) == []


def test_source_row_is_reread_instead_of_verified_from_a_stale_orm_object(connections):
    report = seed(connections); before = state(connections)
    class Trigger(AsyncSQLiteBridge):
        changed = False
        async def flush(self):
            await super().flush()
            if not self.changed:
                self.changed = True
                self.session.execute(update(PlannedWorkout).where(PlannedWorkout.id == before["id"]).values(
                    title="Simulated database trigger change").execution_options(synchronize_session=False))
    with pytest.raises(repair.ProjectionRepairError, match="POSTWRITE_MISMATCH"):
        invoke(connections, report, True, bridge_type=Trigger)
    assert state(connections) == before and receipts(connections) == []


def test_actual_cli_checks_applies_and_retries_using_the_configured_owner_and_saved_report(connections, monkeypatch, tmp_path):
    report = seed(connections)
    repo = Path(__file__).resolve().parents[4]
    path = repo / "tools/repair_polar_plan_blocks.py"
    spec = importlib.util.spec_from_file_location("projection_repair_cli", path)
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    from app.db import session as database
    from app.core import config
    with Session(connections.engine) as db: email = db.get(User, UUID(ATHLETE)).email
    class Context:
        async def __aenter__(self):
            self.db = Session(connections.engine, expire_on_commit=False)
            return AsyncSQLiteBridge(self.db)
        async def __aexit__(self, *args): self.db.close()
    async def dispose(): pass
    monkeypatch.setattr(database, "SessionLocal", Context)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(demo_user_email=email))
    selected = tmp_path / "report.json"; selected.write_text(json.dumps(report), encoding="utf-8")
    import sys
    command = ["repair", "--repo", str(repo), "--report", str(selected), "--output-dir", str(tmp_path)]
    with monkeypatch.context() as patch:
        patch.setattr(sys, "argv", command + ["--check"])
        assert cli.main() == 0
    assert state(connections)["blocks"] == []
    with monkeypatch.context() as patch:
        patch.setattr(sys, "argv", command + ["--apply"])
        assert cli.main() == 0
    before = state(connections)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "argv", command + ["--apply"])
        assert cli.main() == 0
    assert state(connections) == before and len(before["blocks"]) == 7 and len(receipts(connections)) == 1
    saved = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("PaddleTrainer_plan_blocks_*.json")]
    assert {s["state"] for s in saved} == {"preview", "repaired", "already_repaired"}
