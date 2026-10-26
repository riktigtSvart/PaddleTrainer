"""Regression for the three distance legs actually excluded by the R1 eligibility rule."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.entities import BlockType, PlannedWorkout, WorkoutBlock, WorkoutSession, Sport
from app.planning.application.calendar_duration import simple_distance_plan
from tests.planning.test_p2_4c81r1_calendar_duration import (
    ATHLETE, OBSERVATION, TARGET, agenda as prior_agenda, get,
)


# Reported measurements and elapsed times from the reproduced issue; identifiers
# are synthetic. No provider payloads, credentials or personal identifiers ship.
HISTORY = [
    ("2026-10-26T05:08:39+00:00", "2026-10-26T05:42:04+00:00", 6043.5, 2000),
    ("2026-10-25T15:34:58+00:00", "2026-10-25T16:21:53+00:00", 6102.0, 2038),
    ("2026-10-22T04:31:03+00:00", "2026-10-22T05:01:12+00:00", 5282.5, 1804),
    ("2026-10-20T15:23:53+00:00", "2026-10-20T15:55:53+00:00", 6100.2001953125, 1915),
    ("2026-10-18T13:19:07+00:00", "2026-10-18T13:55:12+00:00", 6095.5, 1919),
    ("2026-10-16T04:33:05+00:00", "2026-10-16T05:20:29+00:00", 6170.10009765625, 2039),
    ("2026-10-09T13:37:16+00:00", "2026-10-09T14:15:59+00:00", 6190.2001953125, 2317),
    ("2026-10-05T15:47:12+00:00", "2026-10-05T16:20:40+00:00", 5712.7998046875, 1841),
    ("2026-09-28T15:57:05+00:00", "2026-09-28T16:32:57+00:00", 6042.10009765625, 2147),
    ("2026-09-01T04:36:25+00:00", "2026-09-01T05:13:33+00:00", 5816.5, 2223),
    ("2026-08-26T15:46:49+00:00", "2026-08-26T16:20:05+00:00", 6282.7001953125, 1849),
    ("2026-08-08T05:00:45+00:00", "2026-08-08T05:39:15+00:00", 6126.0, 2297),
]


@pytest.fixture
def segmented_agenda(tmp_path, monkeypatch):
    wrapper = prior_agenda.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    with Session(env.engine) as db:
        db.execute(delete(WorkoutSession).where(WorkoutSession.id == UUID(OBSERVATION)))
        for i, (start, end, distance, duration) in enumerate(HISTORY):
            db.add(WorkoutSession(id=UUID(int=85000+i), user_id=UUID(ATHLETE), external_id=f"segmented-{i}",
                sport=Sport.KAYAK, started_at=datetime.fromisoformat(start), ended_at=datetime.fromisoformat(end),
                distance_m=distance, duration_sec=duration, raw_data={"fixture": True}))
        for i, (kind, distance, name, lower) in enumerate([
            (BlockType.WARMUP, 1000, "Warm Up 1km", 1),
            (BlockType.WORK, 2000, "2km upwards", 2),
            (BlockType.WORK, 3000, "3km downwards", 2),
        ]):
            db.add(WorkoutBlock(id=UUID(int=86000+i), workout_id=UUID(TARGET), position=i, block_type=kind,
                name=name, distance_m=distance, duration_sec=None, repeat_count=1,
                intensity_type="HEART_RATE_ZONES", intensity_min=lower, intensity_max=3))
        db.commit()
    try:
        yield env
    finally:
        wrapper.close()


def target(env):
    return next(p for p in get(env)["planned"] if p["id"] == TARGET)


def test_segmented_target_receives_same_transparent_estimate_in_feed_and_conflicts(segmented_agenda):
    p = target(segmented_agenda)
    e = p["duration_estimate"]
    assert e is not None and (e["duration_sec"], e["lower_sec"], e["upper_sec"]) == (2120, 1680, 2580)
    assert len(e["samples"]) == 12 and e["sample_count"] == 10
    assert len(p["blocks"]) == 3 and sum(b["distance_m"] for b in p["blocks"]) == 6000
    assert p["duration_sec"] is None and all(b["duration_sec"] is None for b in p["blocks"])
    context = get(segmented_agenda, "constraints")
    assert context["duration_estimates"][TARGET] == e
    assert not any(c["plan_id"] == TARGET for c in context["conflicts"])
    with Session(segmented_agenda.engine) as db:
        source = db.get(PlannedWorkout, UUID(TARGET))
        measured = db.get(WorkoutSession, UUID(int=85000))
        assert source.duration_sec is None and source.raw_data == {"provider_duration": None}
        assert [b.distance_m for b in source.blocks] == [1000, 2000, 3000]
        assert measured.duration_sec == 2000 and measured.ended_at.replace(tzinfo=UTC) == datetime(2026,10,26,5,42,4,tzinfo=UTC)


@pytest.mark.parametrize("kind", [BlockType.WARMUP, BlockType.WORK, BlockType.COOLDOWN])
def test_flat_continuous_distance_leg_types_are_supported(segmented_agenda, kind):
    with Session(segmented_agenda.engine) as db:
        db.get(WorkoutBlock, UUID(int=86002)).block_type = kind
        db.commit()
    assert target(segmented_agenda)["duration_estimate"] is not None


@pytest.mark.parametrize("changes", [
    {"block_type": BlockType.RECOVERY}, {"block_type": BlockType.REPEAT},
    {"repeat_count": 2}, {"parent_block_id": UUID(int=86000)},
    {"duration_sec": 300}, {"distance_m": None}, {"distance_m": 2500},
])
def test_incomplete_or_interval_structure_is_still_withheld(segmented_agenda, changes):
    with Session(segmented_agenda.engine) as db:
        block = db.get(WorkoutBlock, UUID(int=86002))
        for key, value in changes.items():
            setattr(block, key, value)
        db.commit()
    assert target(segmented_agenda)["duration_estimate"] is None


@pytest.mark.parametrize("changes", [
    {"repeat_count": 0}, {"duration_sec": 0}, {"distance_m": 0}, {"distance_m": -3000},
])
def test_invalid_legacy_block_values_never_become_eligible(segmented_agenda, changes):
    # These values are already rejected by WorkoutOut. Check eligibility before
    # that independent output-schema guard rather than asking for a valid feed.
    with Session(segmented_agenda.engine) as db:
        plan = db.get(PlannedWorkout, UUID(TARGET))
        block = next(b for b in plan.blocks if b.id == UUID(int=86002))
        for key, value in changes.items():
            setattr(block, key, value)
        assert not simple_distance_plan(plan)


@pytest.mark.parametrize("seconds", [0, 2400])
def test_segmented_plan_with_explicit_duration_keeps_the_source_value(segmented_agenda, seconds):
    with Session(segmented_agenda.engine) as db:
        db.get(PlannedWorkout, UUID(TARGET)).duration_sec = seconds
        db.commit()
    p = target(segmented_agenda)
    assert p["duration_sec"] == seconds and p["duration_estimate"] is None


def test_estimate_does_not_depend_on_names_of_legs(segmented_agenda):
    before = deepcopy(target(segmented_agenda)["duration_estimate"])
    with Session(segmented_agenda.engine) as db:
        for block in db.query(WorkoutBlock).filter(WorkoutBlock.workout_id == UUID(TARGET)):
            block.name = "<img src=x onerror=alert(1)>"
        db.commit()
    assert target(segmented_agenda)["duration_estimate"] == before
