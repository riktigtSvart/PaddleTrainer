"""Structured intent, historical compatibility and reviewed live date changes."""

from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import PeriodType, PlannedWorkout, Sport, TrainingPeriod
from app.planning.domain import cycle_program_context as context
from app.planning.domain.common.serialization import compute_content_hash
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER_EMAIL, count
from tests.planning.test_p2_4c5_cycle_creation import BASE, post, proposal


@pytest.fixture
def reviewed(tmp_path, monkeypatch):
    from tests.planning.test_p2_4c5_cycle_creation import cycles as fixture

    generator = fixture.__wrapped__(tmp_path, monkeypatch)
    environment = next(generator)
    PlannedWorkout.__table__.create(environment.engine)
    try:
        yield environment
    finally:
        generator.close()


def profile(distance="500", unit="m"):
    return {
        "discipline": "Síkvízi kajak K1",
        "event_type": "sprint",
        "distance_status": "specified",
        "distance_value": distance,
        "distance_unit": unit,
        "expected_duration_minutes": "1.95",
        "course_description": "Síkvízi pálya",
        "capability_basis": "unassessed",
        "capability_keys": [],
    }


def structured(mode="recreation"):
    p = proposal(mode)
    p["planning_basis"] = {
        "version": "cycle-planning-basis-v0.1",
        "mesocycle_dates": "provisional",
        "initial_mesocycle_days": 28,
    }
    p["goals"] = [
        {
            "key": "weight_loss",
            "target_description": "Jelenlegi testsúly: 92.500 kg; céltestsúly: 85.0 kg.",
            "body_mass": {"current_kg": "92.500", "target_kg": "85.0"},
        }
    ]
    for c in p["competitions"]:
        c["profile"] = profile()
    return p


def boundary_body(saved, *, previous=None, competition=None, end="2030-01-21"):
    def ref(a):
        return {"artifact_id": a["artifact_id"], "content_hash": a["content_hash"]}

    mesos = [p for p in (previous or saved)["periods"] if p["period_type"] == "MESOCYCLE"]
    return {
        "program_reference": ref(saved),
        "revision": previous["proposal"]["revision"] + 1 if previous else 1,
        "previous_reference": ref(previous) if previous else None,
        "competition_reference": ref(competition or saved),
        "left_period_id": mesos[0]["id"],
        "right_period_id": mesos[1]["id"],
        "new_end_date": end,
        "reason": "fatigue",
        "observations": "Növekvő fáradtság, a fejlődés megtorpant.",
        "rationale": "Rövidebb blokk; a következő ciklus és a verseny előtti terhelés felülvizsgálandó.",
        "review_training_load": True,
    }


def dates(env):
    with Session(env.engine) as sync:
        return {
            str(p.id): (p.start_date.isoformat(), p.end_date.isoformat())
            for p in sync.scalars(select(TrainingPeriod))
        }


def test_weight_and_event_data_survive_preview_commit_load_and_exact_retry(reviewed):
    p = structured("season")
    event = p["competitions"][0]
    event["profile"]["capability_keys"] = context.sprint_keys(event["profile"])
    event["profile"]["capability_basis"] = "icf_sprint_v0_1"
    preview = post(reviewed, "/preview", p, 200)
    assert preview["proposal_hash"] == compute_content_hash(p, exclude_fields=frozenset())
    saved = post(reviewed, "/programs", p)
    assert saved["artifact"]["schema_version"] == context.CONTEXT_SCHEMA
    assert saved["artifact"]["proposal"] == p
    assert post(reviewed, "/programs", p, 200)["artifact"] == saved["artifact"]
    loaded = reviewed.client.get(BASE + "/programs/" + saved["artifact"]["artifact_id"])
    assert loaded.status_code == 200
    assert loaded.json()["program"]["artifact"]["proposal"]["goals"][0]["body_mass"] == {
        "current_kg": "92.500",
        "target_kg": "85.0",
    }
    assert count(reviewed, PlanningAuditArtifactRow) == 1


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "1e2", "092", "92,5", "92.1234", 92.5])
def test_api_weight_is_positive_exact_decimal_text_not_a_float(reviewed, value):
    p = structured()
    p["goals"][0]["body_mass"]["current_kg"] = value
    post(reviewed, "/programs", p, 422)
    assert count(reviewed, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize(
    "alter,code",
    [
        (lambda p: p["goals"][0].pop("body_mass"), "CYCLE_BODY_MASS_REQUIRED"),
        (lambda p: p["goals"][0]["body_mass"].update(target_kg="93"), "CYCLE_BODY_MASS_DIRECTION"),
        (lambda p: p["competitions"][0].pop("profile"), "CYCLE_EVENT_PROFILE_REQUIRED"),
    ],
)
def test_new_intent_is_complete_before_any_write(reviewed, alter, code):
    p = structured("season")
    alter(p)
    before = count(reviewed, TrainingPeriod)
    assert post(reviewed, "/programs", p, 409)["detail"]["code"] == code
    assert count(reviewed, TrainingPeriod) == before


@pytest.mark.parametrize(
    "patch",
    [
        {"distance_value": None},
        {"distance_status": "unknown", "distance_value": "500"},
        {"distance_value": "0"},
        {"distance_unit": "mile"},
        {"capability_basis": "coach_declared", "capability_keys": ["UNSUPPORTED"]},
        {"capability_basis": "unassessed", "capability_keys": ["VO2_CAPACITY"]},
        {"capability_basis": "icf_sprint_v0_1", "capability_keys": ["VO2_CAPACITY"]},
    ],
)
def test_event_profile_cannot_fabricate_units_or_supported_requirements(reviewed, patch):
    p = structured("season")
    p["competitions"][0]["profile"].update(patch)
    post(reviewed, "/programs", p, 422)
    assert count(reviewed, PlanningAuditArtifactRow) == 0


def test_unknown_distance_and_unassessed_capabilities_remain_explicit(reviewed):
    p = structured("season")
    p["competitions"][0]["profile"].update(
        distance_status="unknown", distance_value=None, distance_unit=None
    )
    saved = post(reviewed, "/programs", p)
    assert saved["artifact"]["proposal"]["competitions"][0]["profile"]["capability_keys"] == []


def test_old_payloads_retain_exact_old_schema_and_receipt(reviewed):
    p = proposal()
    saved = post(reviewed, "/programs", p)
    assert saved["artifact"]["schema_version"] == "cycle-program-registration-v0.1"
    assert saved["artifact"]["proposal"] == p
    assert "planning_basis" not in saved["artifact"]["proposal"]
    assert post(reviewed, "/programs", p, 200)["artifact"] == saved["artifact"]


def test_two_competition_season_can_reach_preview_and_commit(reviewed):
    p = structured("season")
    first = deepcopy(p["competitions"][0])
    first.update(
        key="summer", title="Nyári főverseny", start_date="2030-07-14", end_date="2030-07-14"
    )
    p["competitions"].insert(0, first)
    post(reviewed, "/preview", p, 200)
    saved = post(reviewed, "/programs", p)
    assert len(saved["artifact"]["proposal"]["competitions"]) == 2


def test_boundary_can_shorten_then_extend_without_moving_macro_or_competitions(reviewed):
    saved = post(reviewed, "/programs", structured("season"))["artifact"]
    before = dates(reviewed)
    body = boundary_body(saved)
    first = post(reviewed, "/boundary-revisions", body)["artifact"]
    assert first["previous_periods"][0]["end_date"] == "2030-01-28"
    assert first["training_load_replanned"] is False
    assert first["required_reviews"] == [
        "training_load",
        "mesocycle_capability_roles",
        "measurement_windows",
    ]
    after = dates(reviewed)
    assert (
        after[body["left_period_id"]][1] == "2030-01-21"
        and after[body["right_period_id"]][0] == "2030-01-22"
    )
    assert sum(before[k] != after[k] for k in before) == 2
    body2 = boundary_body(saved, previous=first, end="2030-02-04")
    body2["reason"] = "progress_continues"
    second = post(reviewed, "/boundary-revisions", body2)["artifact"]
    assert second["competition_snapshot"] == saved["proposal"]["competitions"]
    assert [p for p in second["periods"] if p["period_type"] != "MESOCYCLE"] == [
        p for p in saved["periods"] if p["period_type"] != "MESOCYCLE"
    ]
    loaded = reviewed.client.get(BASE + "/programs/" + saved["artifact_id"]).json()
    assert len(loaded["boundary_revisions"]) == 2 and loaded["program"]["artifact"] == saved


def test_boundary_retry_restores_original_receipt_without_repairing_live_rows(reviewed):
    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    receipt = post(reviewed, "/boundary-revisions", body)
    with Session(reviewed.engine) as sync:
        sync.execute(
            update(TrainingPeriod)
            .where(TrainingPeriod.id == UUID(body["left_period_id"]))
            .values(title="Később átnevezve")
        )
        sync.commit()
    reviewed.clock.current = datetime(2031, 1, 1, tzinfo=UTC)
    assert post(reviewed, "/boundary-revisions", body, 200)["artifact"] == receipt["artifact"]
    assert count(reviewed, PlanningAuditArtifactRow) == 2
    with Session(reviewed.engine) as sync:
        assert sync.get(TrainingPeriod, UUID(body["left_period_id"])).title == "Később átnevezve"


@pytest.mark.parametrize(
    "patch,code",
    [
        ({"new_end_date": "2030-01-28"}, "CYCLE_BOUNDARY_UNCHANGED"),
        ({"new_end_date": "2030-02-25"}, "CYCLE_BOUNDARY_RANGE"),
        ({"new_end_date": "2029-12-31"}, "CYCLE_BOUNDARY_RANGE"),
        ({"revision": 2}, "CYCLE_REVISION_CHAIN"),
        ({"left_period_id": str(UUID(int=8888))}, "CYCLE_BOUNDARY_PAIR"),
    ],
)
def test_invalid_boundary_keeps_all_period_dates_and_audits_unchanged(reviewed, patch, code):
    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    body.update(patch)
    before = dates(reviewed)
    assert post(reviewed, "/boundary-revisions", body, 409)["detail"]["code"] == code
    assert dates(reviewed) == before and count(reviewed, PlanningAuditArtifactRow) == 1


def test_boundary_cannot_rewrite_completed_days_or_hide_latest_event_change(reviewed):
    saved = post(reviewed, "/programs", proposal("season"))["artifact"]
    body = boundary_body(saved)
    reviewed.clock.current = datetime(2030, 1, 25, 12, tzinfo=UTC)
    assert (
        post(reviewed, "/boundary-revisions", body, 409)["detail"]["code"] == "CYCLE_BOUNDARY_PAST"
    )
    reviewed.clock.current = datetime(2026, 10, 23, 12, tzinfo=UTC)
    revision = {
        "program_reference": body["program_reference"],
        "revision": 1,
        "previous_reference": None,
        "competitions": deepcopy(saved["proposal"]["competitions"]),
        "rationale": "A főverseny helyszíne pontosítva.",
    }
    revision["competitions"][0]["title"] = "Pontosított főverseny"
    post(reviewed, "/competition-revisions", revision)
    assert (
        post(reviewed, "/boundary-revisions", body, 409)["detail"]["code"]
        == "CYCLE_REFERENCE_DIFFERS"
    )


def test_boundary_does_not_move_workouts_across_their_period_assignment(reviewed):
    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    with Session(reviewed.engine) as sync:
        sync.add(
            PlannedWorkout(
                user_id=UUID(ATHLETE),
                training_period_id=UUID(body["left_period_id"]),
                date=date(2030, 1, 27),
                sport=Sport.OTHER,
                title="A ciklushoz rendelt edzés",
            )
        )
        sync.commit()
    before = dates(reviewed)
    assert (
        post(reviewed, "/boundary-revisions", body, 409)["detail"]["code"]
        == "CYCLE_BOUNDARY_WORKOUT_REPLAN_REQUIRED"
    )
    assert dates(reviewed) == before and count(reviewed, PlanningAuditArtifactRow) == 1


def test_boundary_preserves_existing_nested_period_containment(reviewed):
    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    with Session(reviewed.engine) as sync:
        sync.add(
            TrainingPeriod(
                user_id=UUID(ATHLETE),
                parent_id=UUID(body["left_period_id"]),
                period_type=PeriodType.MESOCYCLE,
                title="Már létező alárendelt ciklus",
                start_date=date(2030, 1, 22),
                end_date=date(2030, 1, 28),
            )
        )
        sync.commit()
    before = dates(reviewed)
    assert (
        post(reviewed, "/boundary-revisions", body, 409)["detail"]["code"]
        == "CYCLE_BOUNDARY_CHILD_REPLAN_REQUIRED"
    )
    assert dates(reviewed) == before


@pytest.mark.parametrize("skip", [False, True])
def test_failed_or_skipped_boundary_commit_rolls_back_both_dates_and_audit(
    reviewed, monkeypatch, skip
):
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    before = dates(reviewed)

    async def broken(_self):
        if not skip:
            raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(AsyncSQLiteBridge, "commit", broken)
    post(reviewed, "/boundary-revisions", body, 503)
    assert dates(reviewed) == before and count(reviewed, PlanningAuditArtifactRow) == 1


def test_boundary_rejects_foreign_owner_and_unrecorded_source_mutation(reviewed):
    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    original = reviewed.email
    reviewed.email = OTHER_EMAIL
    post(reviewed, "/boundary-revisions", body, 404)
    reviewed.email = original
    with Session(reviewed.engine) as sync:
        sync.execute(
            update(TrainingPeriod)
            .where(TrainingPeriod.id == UUID(body["left_period_id"]))
            .values(title="Más állapot")
        )
        sync.commit()
    assert (
        post(reviewed, "/boundary-revisions", body, 409)["detail"]["code"]
        == "CYCLE_BOUNDARY_SOURCE_CHANGED"
    )
    assert count(reviewed, PlanningAuditArtifactRow) == 1


def test_boundary_slot_rejects_a_conflicting_second_client(reviewed):
    saved = post(reviewed, "/programs", proposal())["artifact"]
    body = boundary_body(saved)
    post(reviewed, "/boundary-revisions", body)
    other = deepcopy(body)
    other["new_end_date"] = "2030-01-22"
    assert (
        post(reviewed, "/boundary-revisions", other, 409)["detail"]["code"]
        == "CYCLE_REQUEST_IDENTITY_CONFLICT"
    )
    assert count(reviewed, PlanningAuditArtifactRow) == 2
