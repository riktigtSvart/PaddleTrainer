"""Creation, no-partial-write guarantees, ownership and frozen retry history."""

from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.routes import planning_cycles as api
from app.models.entities import TrainingPeriod, User
from app.planning.application import create_cycle_program as service
from app.planning.domain import cycle_program as domain
from app.planning.domain.common.serialization import canonical_json
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4c3_goal_workflow_api import (
    ATHLETE,
    OTHER_EMAIL,
    count,
)
from tests.planning.test_p2_4c3_goal_workflow_api import (
    environment as environment_fixture,
)

BASE = "/api/v1/planning/cycles"


def mesocycles(start, end, prefix="m"):
    cursor, last, result = date.fromisoformat(start), date.fromisoformat(end), []
    while cursor <= last:
        finish = min(last, cursor + timedelta(days=27))
        result.append(
            {
                "key": prefix + str(len(result)),
                "title": "Felülvizsgálandó blokk",
                "start_date": cursor.isoformat(),
                "end_date": finish.isoformat(),
            }
        )
        cursor = finish + timedelta(days=1)
    return result


def proposal(mode="recreation", token=50001):
    start, end = "2030-01-01", "2030-03-25"
    if mode == "olympic":
        end = "2030-02-17"
    if mode == "season":
        end = "2030-12-31"
    result = {
        "program_id": str(UUID(int=token)),
        "mode": mode,
        "title": "Teszt felkészülés",
        "sport": "Kajak",
        "start_date": start,
        "end_date": None if mode == "recreation" else end,
        "olympic_key": "alpes-2030" if mode == "olympic" else None,
        "seasons": [],
        "macrocycles": [],
        "competitions": [],
        "goals": [{"key": "regular_activity", "target_description": "Heti három alkalom"}],
        "continued_from": None,
    }
    parent = None
    if mode in {"olympic", "season"}:
        parent = "season-1"
        result["seasons"] = [
            {"key": parent, "title": "Első szezon", "start_date": start, "end_date": end}
        ]
    result["macrocycles"] = [
        {
            "key": "macro-1",
            "title": "Első makrociklus",
            "start_date": start,
            "end_date": end,
            "season_key": parent,
            "mesocycles": mesocycles(start, end),
        }
    ]
    if mode != "recreation":
        result["competitions"] = [
            {
                "key": "main-race",
                "title": "Főverseny",
                "start_date": end,
                "end_date": end,
                "precision": "exact",
                "priority": "main",
                "status": "planned",
            }
        ]
    return result


@pytest.fixture
def cycles(tmp_path, monkeypatch):
    fixture = environment_fixture.__wrapped__(tmp_path, monkeypatch)
    environment = next(fixture)
    environment.app.include_router(api.router, prefix="/api/v1")
    monkeypatch.setattr(service, "_now", environment.clock.tick)
    try:
        yield environment
    finally:
        fixture.close()


def post(env, path, payload, expected=201):
    response = env.client.post(BASE + path, json=payload)
    assert response.status_code == expected, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def get(env, path, expected=200):
    response = env.client.get(BASE + path)
    assert response.status_code == expected, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


@pytest.mark.parametrize("mode", ["olympic", "season", "race", "recreation"])
def test_all_modes_create_real_connected_periods_with_exact_retry(cycles, mode):
    payload = proposal(mode)
    before = count(cycles, TrainingPeriod)
    preview = post(cycles, "/preview", payload, 200)
    assert preview["committed"] is False
    assert count(cycles, TrainingPeriod) == before
    saved = post(cycles, "/programs", payload)
    assert saved["committed"] is True and saved["planning_authorized"] is False
    assert saved["artifact"]["periods"] == preview["periods"]
    assert any(p["period_type"] == "MACROCYCLE" for p in preview["periods"])
    assert saved["artifact"]["proposal"] == payload
    assert count(cycles, TrainingPeriod) == before + len(preview["periods"])
    assert count(cycles, PlanningAuditArtifactRow) == 1
    retried = post(cycles, "/programs", payload, 200)
    assert retried["reused"] is True and retried["artifact"] == saved["artifact"]
    assert count(cycles, PlanningAuditArtifactRow) == 1
    detail = get(cycles, "/programs/" + saved["artifact"]["artifact_id"])
    assert detail["program"]["artifact"] == saved["artifact"]
    assert detail["competition_revisions"] == []
    assert get(cycles, "/programs")["items"][0]["artifact"] == saved["artifact"]


@pytest.mark.parametrize("mode", ["season", "olympic"])
def test_created_hierarchy_is_accepted_by_existing_c1_goal_workflow(cycles, mode):
    saved = post(cycles, "/programs", proposal(mode))["artifact"]
    macro = next(p for p in saved["periods"] if p["period_type"] == "MACROCYCLE")
    mesos = [p for p in saved["periods"] if p["period_type"] == "MESOCYCLE"]
    payload = {
        "macrocycle_period_id": macro["id"],
        "revision": 1,
        "supersedes": None,
        "goals": [
            {
                "capability_key": "VO2_CAPACITY",
                "role": "primary_development",
                "rationale": "Explicit test goal",
            }
        ],
        "mesocycle_directives": [
            {
                "mesocycle_period_id": p["id"],
                "capability_key": "VO2_CAPACITY",
                "role": "maintenance",
                "rationale": "Explicit test phase",
            }
            for p in mesos
        ],
        "rationale": "Synthetic complete assignment",
    }
    response = cycles.client.post("/api/v1/planning/goals/macrocycle-plans", json=payload)
    assert response.status_code == 201, response.text
    assert len(response.json()["artifact"]["sources"]["mesocycles"]) == len(mesos)


@pytest.mark.parametrize("days,expected", [(3, 409), (27, 409), (28, 201), (365, 201), (366, 409)])
def test_race_policy_boundaries_are_inclusive_calendar_days(cycles, days, expected):
    payload = proposal("race")
    end = (date(2030, 1, 1) + timedelta(days=days - 1)).isoformat()
    payload["end_date"] = payload["macrocycles"][0]["end_date"] = end
    payload["macrocycles"][0]["mesocycles"] = mesocycles(payload["start_date"], end)
    payload["competitions"][0].update(start_date=end, end_date=end)
    post(cycles, "/programs", payload, expected)
    assert count(cycles, PlanningAuditArtifactRow) == int(expected == 201)


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda p: p["macrocycles"][0]["mesocycles"][0].update(start_date="2030-01-02"),
            "CYCLE_MESO_COVERAGE",
        ),
        (
            lambda p: p["macrocycles"][0]["mesocycles"][0].update(end_date="2030-01-29"),
            "CYCLE_MESO_COVERAGE",
        ),
        (lambda p: p["macrocycles"][0].update(season_key="missing"), "CYCLE_MACRO_PARENT"),
        (lambda p: p["macrocycles"][0]["mesocycles"][0].update(key="macro-1"), "CYCLE_PERIOD_KEYS"),
        (lambda p: p.update(end_date="2030-03-25"), "CYCLE_PROGRAM_END_REQUIRED"),
        (lambda p: p.update(olympic_key="la-2028"), "CYCLE_UNEXPECTED_OLYMPIC_REFERENCE"),
        (lambda p: p["goals"].append(deepcopy(p["goals"][0])), "CYCLE_GOAL_KEYS"),
    ],
)
def test_invalid_structure_never_partially_writes(cycles, mutation, code):
    payload = proposal()
    before = count(cycles, TrainingPeriod)
    mutation(payload)
    assert post(cycles, "/programs", payload, 409)["detail"]["code"] == code
    assert count(cycles, TrainingPeriod) == before
    assert count(cycles, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(unexpected=True),
        lambda p: p.update(program_id="not-a-uuid"),
        lambda p: p.update(start_date="2030-1-1"),
        lambda p: p.update(start_date="9999-12-31"),
        lambda p: p.update(title="  "),
        lambda p: p.update(macrocycles=[]),
        lambda p: p.update(goals=[]),
        lambda p: p["goals"][0].update(key="automatic_weight_loss"),
        lambda p: p["macrocycles"][0]["mesocycles"][0].update(key="../x"),
        lambda p: p.update(program_id=1),
    ],
)
def test_closed_strict_inputs(cycles, mutation):
    payload = proposal()
    mutation(payload)
    post(cycles, "/programs", payload, 422)
    assert count(cycles, PlanningAuditArtifactRow) == 0


def test_olympic_first_season_needs_main_event_and_snapshot_is_frozen(cycles, monkeypatch):
    payload = proposal("olympic")
    payload["competitions"] = []
    post(cycles, "/programs", payload, 409)
    payload = proposal("olympic")
    saved = post(cycles, "/programs", payload)
    monkeypatch.setattr(domain, "OLYMPICS", ())
    assert post(cycles, "/programs", payload, 200)["artifact"] == saved["artifact"]
    assert saved["artifact"]["calendar_snapshot"]["version"] == domain.CALENDAR_VERSION


def test_same_identity_different_intent_cannot_duplicate_or_overwrite(cycles):
    payload = proposal()
    saved = post(cycles, "/programs", payload)
    payload["title"] = "Different intent"
    post(cycles, "/programs", payload, 409)
    assert get(cycles, "/programs")["items"][0]["artifact"] == saved["artifact"]


def test_retry_restores_original_timezone_and_periods_without_repair(cycles):
    payload = proposal()
    saved = post(cycles, "/programs", payload)["artifact"]
    period = saved["periods"][-1]
    with Session(cycles.engine) as sync:
        sync.execute(
            update(User).where(User.id == UUID(ATHLETE)).values(timezone="Pacific/Auckland")
        )
        sync.execute(
            update(TrainingPeriod)
            .where(TrainingPeriod.id == UUID(period["id"]))
            .values(title="Later edit")
        )
        sync.commit()
    assert post(cycles, "/programs", payload, 200)["artifact"] == saved
    with Session(cycles.engine) as sync:
        assert sync.get(TrainingPeriod, UUID(period["id"])).title == "Later edit"


@pytest.mark.parametrize("fail_after", [1, 3, 5])
def test_storage_failure_rolls_back_every_created_period(cycles, monkeypatch, fail_after):
    before = count(cycles, TrainingPeriod)
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

    original = AsyncSQLiteBridge.flush
    calls = 0

    async def failing(self):
        nonlocal calls
        calls += 1
        await original(self)
        if calls == fail_after:
            raise service.CycleStorageError("Synthetic failure")

    monkeypatch.setattr(AsyncSQLiteBridge, "flush", failing)
    post(cycles, "/programs", proposal(), 503)
    assert count(cycles, TrainingPeriod) == before
    assert count(cycles, PlanningAuditArtifactRow) == 0


def revision_for(program, *, number=1, previous=None):
    events = deepcopy(program["proposal"]["competitions"])
    return {
        "program_reference": domain.reference(program),
        "revision": number,
        "previous_reference": domain.reference(previous) if previous else None,
        "competitions": events,
        "rationale": "A főverseny dátumának pontosítása",
    }


def test_approximate_event_refinement_is_append_only_and_does_not_retime_periods(cycles):
    payload = proposal("season")
    payload["competitions"][0].update(
        start_date="2030-07-01", end_date="2030-07-31", precision="window"
    )
    program = post(cycles, "/programs", payload)["artifact"]
    update = revision_for(program)
    update["competitions"][0].update(
        start_date="2030-07-15", end_date="2030-07-15", precision="exact"
    )
    updated = post(cycles, "/competition-revisions", update)["artifact"]
    retried = post(cycles, "/competition-revisions", update, 200)
    assert retried["artifact"] == updated
    detail = get(cycles, "/programs/" + program["artifact_id"])
    assert detail["program"]["artifact"] == program
    assert detail["competition_revisions"][0]["artifact"] == updated
    assert updated["period_dates_changed"] is False
    second = revision_for(program, number=2, previous=updated)
    second["rationale"] = "Második, megőrzött pontosítás"
    post(cycles, "/competition-revisions", second)
    assert len(get(cycles, "/programs/" + program["artifact_id"])["competition_revisions"]) == 2
    assert count(cycles, PlanningAuditArtifactRow) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(revision=2),
        lambda p: p["program_reference"].update(content_hash="0" * 64),
        lambda p: p.update(competitions=[]),
        lambda p: p["competitions"][0].update(end_date="2031-01-01"),
        lambda p: p["competitions"][0].update(start_date="2030-12-30"),
    ],
)
def test_event_refinement_rejects_broken_chains_disappearing_records_and_invalid_windows(
    cycles, mutation
):
    program = post(cycles, "/programs", proposal("season"))["artifact"]
    payload = revision_for(program)
    mutation(payload)
    post(cycles, "/competition-revisions", payload, 409)
    assert count(cycles, PlanningAuditArtifactRow) == 1


def test_event_revision_can_preserve_cancelled_event_and_add_replacement(cycles):
    program = post(cycles, "/programs", proposal("season"))["artifact"]
    payload = revision_for(program)
    payload["competitions"][0]["status"] = "cancelled"
    payload["competitions"].append(
        dict(payload["competitions"][0], key="replacement", status="planned")
    )
    saved = post(cycles, "/competition-revisions", payload)["artifact"]
    assert len(saved["proposal"]["competitions"]) == 2


def test_recreation_continuation_has_one_slot_and_retains_program_family(cycles):
    parent = post(cycles, "/programs", proposal())["artifact"]
    payload = proposal(token=50002)
    payload["continued_from"] = domain.reference(parent)
    payload["start_date"] = "2030-03-26"
    macro = payload["macrocycles"][0]
    macro.update(start_date="2030-03-26", end_date="2030-06-17")
    macro["mesocycles"] = mesocycles(macro["start_date"], macro["end_date"])
    preview = post(cycles, "/preview", payload, 200)
    assert preview["proposal_hash"] == sha256(canonical_json(payload).encode()).hexdigest()
    saved = post(cycles, "/programs", payload)["artifact"]
    assert (
        saved["content_hash"]
        == sha256(
            canonical_json({k: v for k, v in saved.items() if k != "content_hash"}).encode()
        ).hexdigest()
    )
    assert saved["program_family_id"] == parent["program_family_id"]
    assert saved["proposal"]["end_date"] is None
    assert post(cycles, "/programs", payload, 200)["artifact"] == saved
    payload["program_id"] = str(UUID(int=50003))
    post(cycles, "/programs", payload, 409)
    assert count(cycles, PlanningAuditArtifactRow) == 2


def test_ownership_missing_owner_and_read_queries(cycles):
    saved = post(cycles, "/programs", proposal())["artifact"]
    cycles.email = OTHER_EMAIL
    assert get(cycles, "/programs")["items"] == []
    get(cycles, "/programs/" + saved["artifact_id"], 404)
    post(cycles, "/competition-revisions", revision_for(saved), 404)
    for path in ("/programs?limit=0", "/programs?limit=1&limit=2", "/catalog?anything=x"):
        get(cycles, path, 422)
    cycles.email = "missing@example.invalid"
    before = count(cycles, User)
    get(cycles, "/catalog", 404)
    assert count(cycles, User) == before


def test_pagination_and_tampered_receipt_are_not_silent_empty_success(cycles):
    first = post(cycles, "/programs", proposal(token=50001))["artifact"]
    post(cycles, "/programs", proposal(token=50002))
    assert get(cycles, "/programs?limit=1&offset=0")["has_more"] is True
    assert get(cycles, "/programs?limit=1&offset=1")["items"][0]["artifact"] == first
    with Session(cycles.engine) as sync:
        row = sync.scalar(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_id == first["artifact_id"]
            )
        )
        row.contract_json = row.contract_json.replace("Heti három alkalom", "Changed goal")
        sync.commit()
    get(cycles, "/programs/" + first["artifact_id"], 503)


def test_catalog_defaults_use_owner_timezone_and_do_not_write(cycles):
    result = get(cycles, "/catalog")
    assert result["timezone_name"] == "Europe/Budapest"
    assert result["limits_are_product_policy"] is True
    assert result["race_min_days"] == 28
    assert result["default_recreation_weeks"] == 12
    assert count(cycles, PlanningAuditArtifactRow) == 0


def test_multiyear_olympic_graph_retains_later_seasons_without_inventing_races(cycles):
    payload = proposal("olympic")
    payload.update(start_date="2027-01-01", seasons=[], macrocycles=[])
    ranges = [
        ("2027-01-01", "2027-12-31"),
        ("2028-01-01", "2028-12-31"),
        ("2029-01-01", "2029-12-31"),
        ("2030-01-01", "2030-02-17"),
    ]
    for index, (start, end) in enumerate(ranges):
        key = f"season-{index}"
        payload["seasons"].append({"key": key, "title": key, "start_date": start, "end_date": end})
        payload["macrocycles"].append(
            {
                "key": f"macro-{index}",
                "title": f"Macro {index}",
                "season_key": key,
                "start_date": start,
                "end_date": end,
                "mesocycles": mesocycles(start, end, prefix=f"s{index}-m"),
            }
        )
    payload["competitions"][0].update(start_date="2027-07-15", end_date="2027-07-15")
    saved = post(cycles, "/programs", payload)["artifact"]
    assert len(saved["periods"]) == 53
    assert len([p for p in saved["periods"] if p["period_type"] == "MACROCYCLE"]) == 4
    assert len(saved["proposal"]["competitions"]) == 1


@pytest.mark.parametrize(
    "start,end,status",
    [
        ("2028-01-01", "2028-12-31", 201),
        ("2028-02-29", "2029-02-27", 201),
        ("2028-02-29", "2029-02-28", 409),
    ],
)
def test_race_upper_limit_uses_calendar_anniversary_in_leap_years(cycles, start, end, status):
    payload = proposal("race")
    payload.update(start_date=start, end_date=end)
    payload["macrocycles"][0].update(
        start_date=start, end_date=end, mesocycles=mesocycles(start, end)
    )
    payload["competitions"][0].update(start_date=end, end_date=end)
    post(cycles, "/programs", payload, status)


@pytest.mark.parametrize("skip", [False, True])
def test_failed_or_skipped_commit_is_never_reported_as_durable_success(cycles, monkeypatch, skip):
    from tests.planning.test_p2_4a2_planning_utility_storage import AsyncSQLiteBridge

    before = count(cycles, TrainingPeriod)

    async def broken_commit(self):
        if not skip:
            raise RuntimeError("Synthetic failed commit")

    monkeypatch.setattr(AsyncSQLiteBridge, "commit", broken_commit)
    post(cycles, "/programs", proposal(), 503)
    assert count(cycles, TrainingPeriod) == before
    assert count(cycles, PlanningAuditArtifactRow) == 0


def test_database_readback_mismatch_rolls_back_periods_and_audit(cycles, monkeypatch):
    from app.planning.infrastructure.repositories.postgres_planning_audit import (
        SqlAlchemyPlanningAuditRepository,
    )

    original = SqlAlchemyPlanningAuditRepository.save
    before = count(cycles, TrainingPeriod)

    async def coerced(self, record):
        result = await original(self, record)
        first = domain.period_id(ATHLETE, proposal()["program_id"], "macro-1")
        await self.session.execute(
            update(TrainingPeriod)
            .where(TrainingPeriod.id == UUID(first))
            .values(title="Synthetic database coercion")
        )
        return result

    monkeypatch.setattr(SqlAlchemyPlanningAuditRepository, "save", coerced)
    post(cycles, "/programs", proposal(), 503)
    assert count(cycles, TrainingPeriod) == before
    assert count(cycles, PlanningAuditArtifactRow) == 0
