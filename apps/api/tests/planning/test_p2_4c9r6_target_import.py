"""Actual importer and disposable database: sparse targets must not erase phases."""
import asyncio
from copy import deepcopy
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, ProviderDataRecord, User, WorkoutBlock
from app.services import polar_targets as importer
from app.services.polar_target_structure import TargetStructureError, phase_structure
from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE
from tests.planning.test_p2_4c7_data_connections import connections, post, proposal


def phased(env):
    raw = deepcopy(env.target_payload[0])
    raw["session"]["name"] = "4×12′ paddling"
    raw["session"]["startTime"] = {"year": 2026, "month": 8, "day": 12, "hour": 13}
    raw["exercise"][0].update(type="PHASED", phaseOrRepeat=[
        {"name": "Warm Up 2.5km", "goal": {"type": "DISTANCE", "distance": 2500}},
        {"name": "Work and rest", "repeatCount": 4, "phaseOrRepeat": [
            {"name": "12′ paddling", "goal": {"type": "DURATION", "duration": 720000}},
            {"name": "Rest 2′", "goal": {"type": "DURATION", "duration": 120000}},
        ]},
    ])
    return raw


def state(env):
    with Session(env.engine) as db:
        plan = db.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id == "new-target"))
        blocks = db.scalars(select(WorkoutBlock).where(WorkoutBlock.workout_id == plan.id).order_by(WorkoutBlock.position)).all()
        return {"id": plan.id, "raw": deepcopy(plan.raw_data), "duration": plan.duration_sec, "distance": plan.distance_m,
                "status": plan.status.value, "title": plan.title, "sport": plan.sport.value, "description": plan.description, "blocks": [(b.id, b.parent_block_id, b.position, b.name, b.duration_sec, b.distance_m, b.repeat_count) for b in blocks]}


def sync(env, raw, sequence=1):
    env.target_payload = [deepcopy(raw)]
    return post(env, proposal(token=986000 + sequence, datasets=["targets"], past_days=89))


@pytest.mark.parametrize("change", ["missing_exercise", "empty_exercise", "missing_phases", "empty_phases", "non_phased_type"])
def test_sparse_completed_target_is_archived_without_erasing_the_august_prescription(connections, change):
    raw = phased(connections); sync(connections, raw)
    before = state(connections)
    incoming = deepcopy(raw); incoming["session"]["done"] = True
    if change == "missing_exercise": incoming.pop("exercise")
    elif change == "empty_exercise": incoming["exercise"] = []
    elif change == "missing_phases": incoming["exercise"][0].pop("phaseOrRepeat")
    else:
        incoming["exercise"][0]["phaseOrRepeat"] = []
        if change == "non_phased_type": incoming["exercise"][0]["type"] = "VOLUME"
    result = sync(connections, incoming, 2)
    assert state(connections) == before
    report = result["run"]["datasets"][0]
    assert report["skip_reasons"] == {"incomplete_phase_structure": 1} and result["run"]["state"] == "partial"
    with Session(connections.engine) as db:
        archives = db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.data_type == "DATA_SYNC_TARGETS")).all()
        assert any(incoming in row.raw_data.get("targets", []) for row in archives)


def test_unchanged_source_keeps_block_ids_parents_and_the_distance_warmup_unknown(connections):
    raw = phased(connections); sync(connections, raw)
    before = state(connections); sync(connections, raw, 2)
    assert state(connections) == before and len(before["blocks"]) == 4
    assert before["blocks"][0][4:6] == (None, 2500)
    assert before["blocks"][2][1] == before["blocks"][1][0]


def test_complete_changed_structure_is_applied_and_previous_native_source_is_archived(connections):
    raw = phased(connections); sync(connections, raw)
    before = state(connections)
    incoming = deepcopy(raw); incoming["exercise"][0]["phaseOrRepeat"][1]["phaseOrRepeat"][0]["goal"]["duration"] = 660000
    result = sync(connections, incoming, 2); after = state(connections)
    assert result["run"]["state"] == "succeeded" and after["raw"] == incoming
    assert after["blocks"][2][4] == 660 and after["blocks"][2][0] != before["blocks"][2][0]
    with Session(connections.engine) as db:
        saved = db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.data_type == "DATA_SYNC_PREVIOUS_TARGET")).all()
        assert any(r.raw_data["raw_data"] == raw for r in saved)


@pytest.mark.parametrize("value", [None, False, 0, 1.5, "4", 100])
def test_unknown_or_invalid_repeat_never_becomes_one_or_replaces_an_existing_tree(connections, value):
    raw = phased(connections); sync(connections, raw); before = state(connections)
    raw["exercise"][0]["phaseOrRepeat"][1]["repeatCount"] = value
    result = sync(connections, raw, 2)
    assert state(connections) == before
    assert result["run"]["datasets"][0]["skip_reasons"] == {"invalid_phase_structure": 1}


def test_invalid_tree_does_not_block_a_separate_valid_target(connections):
    bad = phased(connections); bad["exercise"][0]["phaseOrRepeat"] = False
    good = deepcopy(connections.target_payload[0]); good["session"]["id"] = "another-target"
    connections.target_payload = [bad, good]
    result = post(connections, proposal(token=986010, datasets=["targets"]))
    report = result["run"]["datasets"][0]
    assert report["imported"] == 1 and report["skip_reasons"] == {"invalid_phase_structure": 1}
    with Session(connections.engine) as db:
        assert db.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id == "new-target")) is None
        assert db.scalar(select(PlannedWorkout).where(PlannedWorkout.polar_target_id == "another-target")) is not None


def test_missing_summary_values_are_preserved_and_explicit_zero_is_not_missing(connections):
    raw = phased(connections); raw["exercise"][0]["distance"] = 13660
    sync(connections, raw)
    incoming = deepcopy(raw); incoming["exercise"][0].pop("duration"); incoming["exercise"][0].pop("distance")
    sync(connections, incoming, 2)
    assert state(connections)["duration"] == 2700 and state(connections)["distance"] == 13660
    incoming["exercise"][0].update(duration=0, distance=0); sync(connections, incoming, 3)
    assert state(connections)["duration"] == 0 and state(connections)["distance"] == 0


def test_guard_precedes_any_delete_when_replacement_is_called_directly(connections):
    raw = phased(connections); sync(connections, raw); before = state(connections)
    bad = deepcopy(raw); bad["exercise"][0]["phaseOrRepeat"][1]["repeatCount"] = None
    with Session(connections.engine, expire_on_commit=False) as db:
        plan = db.get(PlannedWorkout, before["id"])
        bridge = AsyncSQLiteBridge(db)
        with pytest.raises(TargetStructureError):
            asyncio.run(importer._replace_workout_blocks(bridge, plan, bad))
        assert not db.deleted and not db.dirty and bridge.commit_count == 0
    assert state(connections) == before


def test_legacy_entry_point_also_preserves_source_without_a_sync_report(connections):
    raw = phased(connections); sync(connections, raw); before = state(connections)
    incoming = deepcopy(raw); incoming["exercise"] = []; connections.target_payload = [incoming]
    with Session(connections.engine, expire_on_commit=False) as db:
        user = db.get(User, UUID(ATHLETE)); bridge = AsyncSQLiteBridge(db)
        asyncio.run(importer.sync_training_targets(bridge, user, first=date(2026, 8, 12), last=date(2026, 8, 13)))
    assert state(connections) == before
    with Session(connections.engine) as db:
        assert any(incoming in r.raw_data.get("targets", []) for r in db.scalars(select(ProviderDataRecord).where(ProviderDataRecord.data_type == "DATA_SYNC_TARGETS")))


def test_native_structure_can_rebuild_missing_blocks_when_a_complete_source_arrives(connections):
    raw = phased(connections); sync(connections, raw)
    before = state(connections)
    with Session(connections.engine) as db:
        blocks = db.scalars(select(WorkoutBlock).where(WorkoutBlock.workout_id == before["id"])).all()
        for block in blocks: block.parent_block_id = None
        db.flush()
        for block in blocks: db.delete(block)
        db.commit()
    assert state(connections)["blocks"] == []
    sync(connections, raw, 2)
    assert len(state(connections)["blocks"]) == 4


@pytest.mark.parametrize("value", [False, {}, [None], [{"type": "PHASED", "phaseOrRepeat": False}]])
def test_malformed_exercise_collection_is_not_empty(value):
    with pytest.raises(TargetStructureError): phase_structure({"exercise": value})


@pytest.mark.parametrize("partial", [{"type": "PHASED", "sportId": "1"}, {"sportId": "1"}])
def test_partial_multisport_source_never_erases_an_unreported_exercise(connections, partial):
    raw = phased(connections); sync(connections, raw); before = state(connections)
    raw["exercise"].append(partial)
    result = sync(connections, raw, 2)
    assert state(connections) == before
    assert result["run"]["datasets"][0]["skip_reasons"] == {"incomplete_phase_structure": 1}


def test_omitted_title_description_and_sport_do_not_erase_known_metadata(connections):
    raw = phased(connections); raw["session"]["description"] = "Known prescription"
    sync(connections, raw); before = state(connections)
    raw["session"].pop("name"); raw["session"].pop("description"); raw["exercise"][0].pop("sportId")
    sync(connections, raw, 2); after = state(connections)
    assert after["title"] == before["title"] and after["description"] == before["description"] and after["sport"] == before["sport"]
    assert after["blocks"] == before["blocks"]


def test_session_sport_reference_is_used_when_the_exercise_omits_it(connections):
    raw = phased(connections); raw["exercise"][0].pop("sportId"); raw["session"]["sportId"] = "95"
    sync(connections, raw)
    assert state(connections)["sport"] == "KAYAK"
