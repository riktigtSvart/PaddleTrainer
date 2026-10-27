"""Real stored exercise limits and backwards-compatible acquisition upgrades."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import BlockType, ProviderDataRecord, WorkoutBlock, WorkoutSession
from app.services import polar_session_details as details
from app.services.session_chart_zones import heart_rate_zones
from tests.planning.test_p2_4c6_calendar_workspace import agenda, ACTUAL, PLAN
from tests.planning.test_p2_4c9_session_analysis import get, raw
from tests.planning.test_p2_4c9r2_session_details_sync import connections, enriched, fetch, identity, read
from tests.planning.test_p2_4c7_data_connections import post, proposal


def source_zones():
    return [{"type": "ZONE_TYPE_HEART_RATE", "zones": [
        {"lowerLimit": low, "higherLimit": low + 20, "inZone": 0}
        for low in (90, 110, 130, 150, 170)]}]


def test_real_read_carries_exact_zone_limits_and_target_without_writing(agenda):
    source = raw(); source["exerciseSamples"][0]["zones"] = source_zones()
    with Session(agenda.engine) as db:
        db.get(WorkoutSession, UUID(ACTUAL)).raw_data = source
        db.add(WorkoutBlock(id=UUID(int=90030), workout_id=UUID(PLAN), position=0, block_type=BlockType.WORK,
            name="Folyamatos <script>literal</script>", distance_m=6000, repeat_count=1,
            intensity_type="HEART_RATE_ZONES", intensity_min=2, intensity_max=3))
        db.commit()
    result = get(agenda)
    limits = result["samples"]["exercises"][0]["heart_rate_zones"]
    assert limits["unit"] == "bpm" and limits["source_path"] == "exerciseSamples[0].zones[0]"
    assert limits["zones"][1] == {"index": 2, "low": 110, "high": 130}
    assert limits["zones"][2] == {"index": 3, "low": 130, "high": 150}
    assert result["plan"]["blocks"][0]["intensity_min"] == 2
    with Session(agenda.engine) as db:
        assert db.get(WorkoutSession, UUID(ACTUAL)).raw_data == source
    assert all(not r.in_transaction() for r in agenda.requests)
    target = os.environ.get("P24C9R3_FIXTURE_OUTPUT")
    if target:
        Path(target).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("mutate", [
    lambda z: z.clear(),
    lambda z: z.append(deepcopy(z[0])),
    lambda z: z[0].update(type="ZONE_TYPE_SPEED"),
    lambda z: z[0]["zones"].pop(1),
    lambda z: z[0]["zones"][1].update(lowerLimit=True),
    lambda z: z[0]["zones"][1].update(higherLimit=float("inf")),
    lambda z: z[0]["zones"][1].update(lowerLimit=80),
    lambda z: z[0]["zones"][1].update(higherLimit=100),
    lambda z: z[0]["zones"][1].update(lowerLimit="110"),
])
def test_invalid_partial_or_ambiguous_zones_never_become_personal_thresholds(mutate):
    zones = source_zones(); mutate(zones)
    assert heart_rate_zones({"zones": zones}, "exercises[0]") is None


def test_other_zone_types_are_not_mistaken_for_heart_rate():
    zones = [{"type": "ZONE_TYPE_POWER", "zones": [{"lowerLimit": 0, "higherLimit": 100}]}] + source_zones()
    result = heart_rate_zones({"zones": zones}, "exercises[1]")
    assert result["source_path"] == "exercises[1].zones[1]"
    assert result["zones"][0]["low"] == 90


def test_zone_limits_follow_each_separate_exercise(agenda):
    source = raw(); one = source["exerciseSamples"][0]; one["zones"] = source_zones()
    two = deepcopy(one)
    for z in two["zones"][0]["zones"]:
        z["lowerLimit"] += 7; z["higherLimit"] += 7
    source["exerciseSamples"].append(two)
    with Session(agenda.engine) as db:
        db.get(WorkoutSession, UUID(ACTUAL)).raw_data = source; db.commit()
    exercises = get(agenda)["samples"]["exercises"]
    assert [e["heart_rate_zones"]["zones"][0]["low"] for e in exercises] == [90, 97]


def test_native_zones_are_preserved_when_preferred_samples_are_added():
    incoming = {"identifier": {"id": "test"}, "exercises": [{"identifier": {"id": "e1"}}]}
    old = deepcopy(incoming); old["exercises"][0]["zones"] = source_zones()
    result = details.merge_details(old, incoming, "test")
    assert result["exerciseSamples"][0]["zones"] == source_zones()
    assert old["exercises"][0]["zones"] == source_zones()
    assert "exerciseSamples" not in old


def test_old_details_marker_is_valid_but_upgrades_to_zones_on_the_next_new_sync(connections):
    e = connections
    post(e, proposal(token=880001, datasets=["sessions"]))
    first = fetch(e)
    with Session(e.engine) as db:
        marker = db.scalar(select(ProviderDataRecord).where(ProviderDataRecord.data_type == details.RECEIPT_TYPE))
        marker.raw_data = {**marker.raw_data, "features": details.LEGACY_FEATURES}
        marker.provider_record_id = "sync:" + details.digest(marker.raw_data)
        db.commit()
    response = enriched(e.session_payload["trainingSessions"][0])
    response["exercises"][0]["zones"] = source_zones()
    e.detail_responses["2026-10-22"] = {"trainingSessions": [response]}
    old_retry = fetch(e, status=200)
    assert old_retry["result"] == first["result"] and len(e.detail_calls) == 1
    upgraded = fetch(e, 880003)
    assert upgraded["run"]["state"] == "succeeded" and len(e.detail_calls) == 2
    assert read(e, identity(e))["samples"]["exercises"][0]["heart_rate_zones"]["zones"][2]["high"] == 150
    again = fetch(e, 880004)
    assert again["run"]["datasets"][0]["details"]["already_complete"] == 1
    assert len(e.detail_calls) == 2
