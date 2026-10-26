"""Real owner-scoped HTTP, production repository, isolated DB and mocked watch API."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.routes import athlete_setup as api
from app.core.security import encrypt_secret
from app.db.base import Base
from app.integrations.polar.client import PolarAPIError
from app.models.entities import (
    AthleteReadiness,
    ExternalConnection,
    PlannedWorkout,
    ProviderDataRecord,
    Sport,
    WorkoutSession,
)
from app.planning.application import register_athlete_setup as service
from app.planning.domain import athlete_setup as domain
from app.planning.infrastructure.adapters.athlete_history import polar_values
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.athlete_setup import ProfileData
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER_EMAIL, count
from tests.planning.test_p2_4c5_cycle_creation import cycles as cycles_fixture
from tests.planning.test_p2_4c5_cycle_creation import proposal as cycle_proposal

BASE = "/api/v1/planning/athlete"


@pytest.fixture
def intake(tmp_path, monkeypatch):
    wrapper = cycles_fixture.__wrapped__(tmp_path, monkeypatch)
    env = next(wrapper)
    Base.metadata.create_all(
        env.engine,
        tables=[
            AthleteReadiness.__table__,
            ExternalConnection.__table__,
            ProviderDataRecord.__table__,
            PlannedWorkout.__table__,
            WorkoutSession.__table__,
        ],
    )
    from types import SimpleNamespace

    from app.core import security

    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(token_encryption_key=""))
    env.app.include_router(api.router, prefix="/api/v1")
    monkeypatch.setattr(service, "_now", env.clock.tick)
    try:
        yield env
    finally:
        wrapper.close()


def post(env, resource, payload, status=201):
    response = env.client.post(BASE + "/" + resource, json=payload)
    assert response.status_code == status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def get(env, resource, status=200):
    response = env.client.get(BASE + "/" + resource)
    assert response.status_code == status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def profile(token=61001, previous=None):
    data = ProfileData().model_dump()
    data.update(
        birth_date="1982-05-30",
        sex_reference="female",
        target_sport="Futás",
        sport_history_status="recorded",
        sport_history=[
            {
                "sport": "Kajak",
                "discipline": "Síkvíz",
                "start_year": 1995,
                "current": True,
                "last_active_date": None,
                "level": "professional",
                "usual_sessions_per_week": 5,
                "notes": "",
            }
        ],
        constraint_status="none_known",
        participation="unrestricted",
        interruption="none",
        typical_days_per_week=3,
    )
    return {
        "request_id": str(UUID(int=token)),
        "previous_reference": domain.reference(previous) if previous else None,
        "data": data,
    }


def window(key="morning", start="06:00", end="07:00", minutes=45):
    return {
        "key": key,
        "start_time": start,
        "end_time": end,
        "ends_next_day": False,
        "start_fold": None,
        "end_fold": None,
        "max_minutes": minutes,
        "sport_scope": "specified",
        "sports": ["Futás"],
        "effort_cap": "easy",
        "resources": ["Futópad"],
        "location": "Otthon",
        "notes": "",
    }


def calendar(token=62001, previous=None, first="2026-10-23", length=14):
    start = datetime.fromisoformat(first).date()
    days = [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "status": "unknown",
            "max_total_minutes": None,
            "windows": [],
            "notes": "",
        }
        for i in range(length)
    ]
    days[0].update(
        status="available",
        windows=[window(), window("evening", "18:00", "19:30", 60)],
        max_total_minutes=90,
    )
    return {
        "request_id": str(UUID(int=token)),
        "previous_reference": domain.reference(previous) if previous else None,
        "data": {
            "timezone_name": "Europe/Budapest",
            "start_date": days[0]["date"],
            "end_date": days[-1]["date"],
            "mesocycle_id": None,
            "days": days,
        },
    }


def constraint(duration="temporary"):
    return {
        "key": "knee",
        "duration": duration,
        "area": "movement",
        "affected_area": "Térd",
        "restricted_activities": ["Ugrás"],
        "adaptations": "Ülő gyakorlatok",
        "professional_guidance": "Könnyű terhelés",
        "starts_on": "2026-10-01",
        "review_on": "2026-10-21",
    }


def manual(metric="sleep_duration_sec", value="28800", token=63001):
    return {
        "observation_id": str(UUID(int=token)),
        "metric": metric,
        "value": value,
        "start_date": "2026-10-20",
        "end_date": "2026-10-20",
        "method": "self_report",
        "aggregation": "total" if metric == "daily_steps" else "single",
        "sport": "",
        "protocol": "",
        "conditions": "",
        "supersedes_candidate_id": None,
    }


def connect(env, scopes=None):
    with Session(env.engine) as sync:
        sync.add(
            ExternalConnection(
                user_id=UUID(ATHLETE),
                provider="POLAR",
                access_token_encrypted=encrypt_secret("synthetic-access"),
                refresh_token_encrypted=encrypt_secret("synthetic-refresh"),
                expires_at=datetime(2030, 1, 1, tzinfo=UTC),
                scopes=scopes if scopes is not None else list(service.SCOPES.values()),
            )
        )
        sync.commit()


def test_initial_context_does_not_create_profile_or_assume_weekly_availability(intake):
    before = count(intake, PlanningAuditArtifactRow)
    result = get(intake, "context?start_date=2026-10-23&end_date=2026-11-05")
    assert result["profile"] is None and result["availability"] is None
    assert result["calendar_context"]["status"] == "UNKNOWN"
    assert not result["polar"]["connected"] and not result["planning_authorized"]
    assert count(intake, PlanningAuditArtifactRow) == before


def test_profile_has_sport_specific_history_and_distinguishes_unknown_from_no_history(intake):
    saved = post(intake, "profiles", profile())
    assert saved["artifact"]["proposal"]["data"]["sport_history"][0]["sport"] == "Kajak"
    assert saved["artifact"]["proposal"]["data"]["target_sport"] == "Futás"
    assert saved["artifact"]["review"]["age_years"] == 44
    assert saved["artifact"]["review"]["global_entry_gate"] == "OPEN"
    assert (
        get(intake, "profiles/" + saved["artifact"]["artifact_id"])["artifact"] == saved["artifact"]
    )
    assert post(intake, "profiles", profile(), 200)["reused"]
    assert count(intake, PlanningAuditArtifactRow) == 1
    empty = ProfileData().model_dump()
    assert "SPORT_HISTORY_UNKNOWN" in domain.review_profile(empty, "2026-10-23")["reasons"]
    empty["sport_history_status"] = "none"
    assert "SPORT_HISTORY_UNKNOWN" not in domain.review_profile(empty, "2026-10-23")["reasons"]


def test_revisions_cas_and_exact_old_retry_never_restore_old_current_values(intake):
    p = profile()
    first = post(intake, "profiles", p)["artifact"]
    second_input = profile(61002, first)
    second_input["data"]["typical_days_per_week"] = 7
    second = post(intake, "profiles", second_input)["artifact"]
    assert second["revision"] == 2
    assert post(intake, "profiles", p, 200)["artifact"] == first
    assert get(intake, "context")["profile"]["artifact"] == second
    stale = profile(61003, first)
    assert (
        post(intake, "profiles", stale, 409)["detail"]["code"] == "ATHLETE_REVISION_CONFLICT_RELOAD"
    )
    conflict = deepcopy(p)
    conflict["data"]["target_sport"] = "Kajak"
    post(intake, "profiles", conflict, 409)
    assert count(intake, PlanningAuditArtifactRow) == 2


@pytest.mark.parametrize(
    "birth,participation,constraints,expected,reason",
    [
        ("2014-02-03", "unrestricted", [], "REVIEW_REQUIRED", "YOUTH_PLANNING_REVIEW"),
        (None, "unrestricted", [], "REVIEW_REQUIRED", "AGE_UNKNOWN"),
        ("1982-05-30", "paused", [], "HOLD", "USER_DECLARED_PAUSE"),
        ("1982-05-30", "adapted", [constraint()], "REVIEW_REQUIRED", "CONSTRAINT_REVIEW_DUE"),
    ],
)
def test_review_path_respects_age_pause_and_injury_without_guessing_recovery(
    intake, birth, participation, constraints, expected, reason
):
    p = profile()
    p["data"].update(
        birth_date=birth,
        participation=participation,
        constraints=constraints,
        constraint_status="present" if constraints else "none_known",
    )
    result = post(intake, "profiles", p)["artifact"]["review"]
    assert result["global_entry_gate"] == expected and reason in result["reasons"]
    assert result["clinical_clearance"] is False
    if constraints:
        assert result["constraints"] == constraints


def test_permanent_vision_constraint_with_adaptation_is_not_a_blanket_training_ban(intake):
    p = profile()
    c = constraint("permanent")
    c.update(area="vision", affected_area="Látás", review_on=None)
    p["data"].update(constraint_status="present", constraints=[c], participation="adapted")
    review = post(intake, "profiles", p)["artifact"]["review"]
    assert (
        review["global_entry_gate"] == "OPEN_WITH_CONSTRAINTS"
        and review["participation_status"] == "READY_WITH_CONSTRAINTS"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"birth_date": "2027-01-01"},
        {"typical_days_per_week": 8},
        {"typical_days_per_week": True},
        {"constraint_status": "present"},
        {"sport_history_status": "none"},
        {"manual_observations": [manual(value="1e3")]},
        {"manual_observations": [manual(metric="daily_steps", value="0.5")]},
    ],
)
def test_bad_intake_cannot_partially_persist(intake, change):
    p = profile()
    p["data"].update(change)
    response = intake.client.post(BASE + "/profiles", json=p)
    assert response.status_code in (409, 422), response.text
    assert count(intake, PlanningAuditArtifactRow) == 0


def test_two_daily_opportunities_and_unknown_days_survive_and_can_be_revised(intake):
    p = calendar()
    saved = post(intake, "availability", p)["artifact"]
    assert saved["calendar"]["coverage"] == {"unknown": 13, "available": 1, "unavailable": 0}
    assert saved["calendar"]["days"][0]["windows"][0]["elapsed_minutes"] == 60
    assert len(saved["calendar"]["days"][0]["windows"]) == 2
    assert not saved["calendar"]["all_opportunities_are_required"]
    nextp = calendar(62002, saved)
    nextp["data"]["days"][1]["status"] = "unavailable"
    changed = post(intake, "availability", nextp)["artifact"]
    assert get(intake, "availability/" + saved["artifact_id"])["artifact"] == saved
    context = get(intake, "context?start_date=2026-10-23&end_date=2026-11-10")["calendar_context"]
    assert context["status"] == "UNKNOWN" and "2026-11-10" in context["missing_days"]
    assert context["reference"] == domain.reference(changed)
    assert post(intake, "availability", p, 200)["artifact"] == saved


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("missing", "ATHLETE_CALENDAR_CENSUS_INVALID"),
        ("overlap", "ATHLETE_WINDOWS_OVERLAP"),
        ("duration", "ATHLETE_WINDOW_DURATION_INVALID"),
        ("budget", "ATHLETE_DAILY_BUDGET_INVALID"),
        ("timezone", "ATHLETE_CALENDAR_TIMEZONE_DIFFERS"),
    ],
)
def test_calendar_rejects_bad_census_overlap_budget_and_foreign_zone(intake, kind, expected):
    p = calendar()
    if kind == "missing":
        p["data"]["days"].pop()
    if kind == "overlap":
        p["data"]["days"][0]["windows"][1]["start_time"] = "06:30"
    if kind == "duration":
        p["data"]["days"][0]["windows"][0]["max_minutes"] = 61
    if kind == "budget":
        p["data"]["days"][0]["max_total_minutes"] = 200
    if kind == "timezone":
        p["data"]["timezone_name"] = "UTC"
    assert post(intake, "availability", p, 409)["detail"]["code"] == expected
    assert count(intake, PlanningAuditArtifactRow) == 0


@pytest.mark.parametrize(
    "first,code",
    [("2026-03-29", "ATHLETE_TIME_DOES_NOT_EXIST"), ("2026-10-25", "ATHLETE_TIME_IS_AMBIGUOUS")],
)
def test_budapest_dst_requires_real_unambiguous_local_instants(intake, first, code):
    p = calendar(first=first, length=1)
    p["data"]["days"][0].update(
        windows=[window(start="02:15", end="03:30", minutes=30)], max_total_minutes=None
    )
    assert post(intake, "availability/preview", p, 409)["detail"]["code"] == code
    assert count(intake, PlanningAuditArtifactRow) == 0
    if code.endswith("AMBIGUOUS"):
        p["data"]["days"][0]["windows"][0]["start_fold"] = 1
        view = post(intake, "availability/preview", p, 200)
        assert view["calendar"]["days"][0]["windows"][0]["start_at"] == "2026-10-25T01:15:00+00:00"
        assert view["committed"] is False


def test_owner_switch_cannot_read_or_reference_another_athlete(intake, monkeypatch):
    saved = post(intake, "profiles", profile())["artifact"]

    intake.email = OTHER_EMAIL
    get(intake, "profiles/" + saved["artifact_id"], 404)
    assert get(intake, "context")["profile"] is None
    post(intake, "profiles", profile(61004, saved), 409)


def test_real_stored_training_history_is_owned_and_missing_durations_are_not_zero(intake):
    with Session(intake.engine) as sync:
        sync.add(
            WorkoutSession(
                user_id=UUID(ATHLETE),
                external_provider="POLAR",
                external_id="run-1",
                sport=Sport.RUNNING,
                started_at=datetime(2026, 10, 20, 8, tzinfo=UTC),
                duration_sec=3600,
                raw_data={"keep": "original"},
            )
        )
        sync.add(
            WorkoutSession(
                user_id=UUID(ATHLETE),
                external_provider="POLAR",
                external_id="run-2",
                sport=Sport.RUNNING,
                started_at=datetime(2026, 10, 21, 8, tzinfo=UTC),
                duration_sec=None,
                raw_data={},
            )
        )
        sync.commit()
    result = get(intake, "history?start_date=2026-10-19&end_date=2026-10-22")
    assert len(result["items"]) == 3 and not result["absence_means_zero"]
    minutes = [c for c in result["items"] if c["metric"] == "training_minutes"]
    assert len(minutes) == 1 and minutes[0]["value"] == "60"
    p = profile()
    p["data"].update(
        source_window={"start_date": "2026-10-19", "end_date": "2026-10-22"},
        source_selections=[domain.reference(c) for c in result["items"]],
    )
    saved = post(intake, "profiles", p)["artifact"]
    assert len(saved["imported_observations"]) == 3
    with Session(intake.engine) as sync:
        assert sync.scalar(
            select(WorkoutSession).where(WorkoutSession.external_id == "run-1")
        ).raw_data == {"keep": "original"}


def steps_payload(values=None):
    return {
        "activities": {
            "activityDays": [
                {
                    "date": "2026-10-20",
                    "activitiesPerDevice": [
                        {
                            "deviceReference": {"deviceId": "watch-1"},
                            "activitySamples": [
                                {
                                    "stepSamples": {
                                        "startTime": "08:00:00",
                                        "interval": "60000",
                                        "steps": [1, 2, 0] if values is None else values,
                                    }
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "unmapped": {"retain": True},
    }


def test_polar_api_raw_data_receipt_retry_and_manual_correction_are_independent(
    intake, monkeypatch
):
    connect(intake)
    calls = []
    payload = steps_payload()

    async def fake(self, token, first, last):
        calls.append((token, first.isoformat(), last.isoformat()))
        return deepcopy(payload)

    monkeypatch.setattr(service.PolarClient, "list_daily_activity", fake)
    request = {"request_id": str(UUID(int=64001)), "day": "2026-10-20", "domain": "activity"}
    imported = post(intake, "polar-imports", request)
    assert not imported["artifact"]["profile_changed"]
    assert (
        post(intake, "polar-imports", request, 200)["artifact"] == imported["artifact"]
        and len(calls) == 1
    )
    assert count(intake, ProviderDataRecord) == 1 and get(intake, "context")["profile"] is None
    candidate = get(intake, "history?start_date=2026-10-20&end_date=2026-10-20")["items"][0]
    assert (
        candidate["metric"] == "daily_steps"
        and candidate["value"] == "3"
        and candidate["coverage"]["observed_minutes"] == "3"
    )
    p = profile()
    correction = manual("daily_steps", "5")
    correction["supersedes_candidate_id"] = candidate["artifact_id"]
    p["data"].update(
        source_window={"start_date": "2026-10-20", "end_date": "2026-10-20"},
        source_selections=[domain.reference(candidate)],
        manual_observations=[correction],
    )
    saved = post(intake, "profiles", p)["artifact"]
    assert (
        saved["imported_observations"][0]["value"] == "3"
        and saved["proposal"]["data"]["manual_observations"][0]["value"] == "5"
    )
    with Session(intake.engine) as sync:
        assert sync.scalar(select(ProviderDataRecord)).raw_data == payload
    payload["activities"]["activityDays"][0]["activitiesPerDevice"][0]["activitySamples"][0][
        "stepSamples"
    ]["steps"] = [100]
    request["request_id"] = str(UUID(int=64002))
    post(intake, "polar-imports", request)
    assert count(intake, ProviderDataRecord) == 2
    assert get(intake, "profiles/" + saved["artifact_id"])["artifact"] == saved


@pytest.mark.parametrize(
    "values,expected", [([], None), ([0, 0], "0"), ([-1], None), ([True], None)]
)
def test_step_samples_distinguish_measured_zero_missing_and_invalid(values, expected):
    observations = list(polar_values("activity", steps_payload(values), "2026-10-20"))
    assert (observations[0]["value"] if observations else None) == expected


def test_continuous_hr_only_uses_background_samples_and_is_not_resting_hr():
    payload = {
        "continuousSamples": {
            "heartRateSamplesPerDay": [
                {
                    "date": "2026-10-20",
                    "samples": [
                        {"triggerType": "TRIGGER_TIMED_247", "heartRate": 70, "offsetMillis": 1},
                        {"triggerType": "TRIGGER_TIMED_247", "heartRate": 90, "offsetMillis": 2},
                        {"triggerType": "TRAINING", "heartRate": 190, "offsetMillis": 3},
                    ],
                }
            ]
        }
    }
    value = next(polar_values("continuous_hr", payload, "2026-10-20"))
    assert (
        value["metric"] == "background_hr_mean_bpm"
        and value["value"] == "80"
        and value["coverage"]["sample_count"] == 2
        and value["coverage"]["is_resting_hr"] is False
    )


def test_watch_fitness_test_remains_an_estimate_not_a_lab_result():
    value = next(
        polar_values(
            "tests",
            {
                "data": {
                    "tests": [
                        {"startTime": "2026-10-20T09:00:00", "fitnessTestResult": {"ownIndex": 51}}
                    ]
                }
            },
            "2026-10-20",
        )
    )
    assert value["metric"] == "vo2max_ml_kg_min" and value["method"] == "device_estimate"


def test_missing_scope_and_provider_failure_never_change_profile_or_raw_data(intake, monkeypatch):
    request = {"request_id": str(UUID(int=64003)), "day": "2026-10-20", "domain": "activity"}
    post(intake, "polar-imports", request, 409)
    connect(intake, [])
    post(intake, "polar-imports", request, 409)
    with Session(intake.engine) as sync:
        sync.execute(update(ExternalConnection).values(scopes=["activity:read"]))
        sync.commit()

    async def unavailable(*args, **kwargs):
        raise PolarAPIError("synthetic; no credentials")

    monkeypatch.setattr(service.PolarClient, "list_daily_activity", unavailable)
    post(intake, "polar-imports", request, 502)
    assert count(intake, PlanningAuditArtifactRow) == 0 and count(intake, ProviderDataRecord) == 0


def test_new_cycle_pins_intake_and_calendar_and_old_retry_does_not_capture_new_profile(
    intake, monkeypatch
):
    p = profile()
    p["data"].update(participation="paused")
    prof = post(intake, "profiles", p)["artifact"]
    cal = post(intake, "availability", calendar(first="2030-01-01"))["artifact"]
    body = cycle_proposal()
    body["athlete_context"] = {
        "profile_reference": domain.reference(prof),
        "availability_reference": domain.reference(cal),
    }
    response = intake.client.post("/api/v1/planning/cycles/programs", json=body)
    assert response.status_code == 201, response.text
    saved = response.json()["artifact"]
    snapshot = saved["athlete_context_snapshot"]
    assert saved["schema_version"] == "cycle-program-registration-v0.3"
    assert (
        snapshot["review"]["global_entry_gate"] == "HOLD"
        and snapshot["first_mesocycle_availability"]["status"] == "UNKNOWN"
    )
    assert not saved["planning_authorized"] and not saved["workouts_created"]
    new = profile(61009, prof)
    post(intake, "profiles", new)
    retry = intake.client.post("/api/v1/planning/cycles/programs", json=body)
    assert retry.status_code == 200 and retry.json()["artifact"] == saved
    changed = deepcopy(body)
    changed["program_id"] = str(UUID(int=65002))
    response = intake.client.post("/api/v1/planning/cycles/programs", json=changed)
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "ATHLETE_CONTEXT_CHANGED_REVIEW_AGAIN"
    )


def test_goal_fields_support_one_weight_for_maintenance_and_keep_legacy_replay(intake):
    p = cycle_proposal()
    p["planning_basis"] = {
        "version": "cycle-planning-basis-v0.1",
        "mesocycle_dates": "provisional",
        "initial_mesocycle_days": 28,
    }
    details = {
        "version": "cycle-goal-fields-v0.1",
        "direction": None,
        "weekly_sessions": None,
        "event_keys": [],
        "result_target": "",
        "notes": "",
    }
    p["goals"] = [
        {
            "key": "weight_maintenance",
            "target_description": "Megtartandó testsúly: 72.500 kg.",
            "body_mass": {"current_kg": "72.500"},
            "details": details,
        }
    ]
    response = intake.client.post("/api/v1/planning/cycles/programs", json=p)
    assert response.status_code == 201, response.text
    saved = response.json()["artifact"]
    assert saved["proposal"]["goals"][0]["body_mass"] == {"current_kg": "72.500"}
    assert (
        intake.client.post("/api/v1/planning/cycles/programs", json=p).json()["artifact"] == saved
    )


@pytest.mark.parametrize(
    "category,method,payload,metric",
    [
        (
            "sessions",
            "list_training_sessions",
            {
                "trainingSessions": [
                    {
                        "identifier": {"id": "one"},
                        "startTime": "2026-10-20T10:00:00",
                        "durationMillis": 3600000,
                        "sport": {"id": "1"},
                    }
                ]
            },
            "training_minutes",
        ),
        (
            "sleep",
            "list_sleeps",
            {
                "nightSleeps": [
                    {"sleepDate": "2026-10-20", "sleepEvaluation": {"asleepDuration": "28800s"}}
                ]
            },
            "sleep_duration_sec",
        ),
        (
            "nightly_recharge",
            "list_nightly_recharge_results",
            {
                "nightlyRechargeResults": [
                    {"sleepResultDate": "2026-10-20", "meanNightlyRecoveryRmssd": 44}
                ]
            },
            "hrv_rmssd_ms",
        ),
        (
            "continuous_hr",
            "list_continuous_samples",
            {
                "continuousSamples": {
                    "heartRateSamplesPerDay": [
                        {
                            "date": "2026-10-20",
                            "samples": [
                                {
                                    "heartRate": 70,
                                    "offsetMillis": 1,
                                    "triggerType": "TRIGGER_TIMED_247",
                                }
                            ],
                        }
                    ]
                }
            },
            "background_hr_mean_bpm",
        ),
        (
            "tests",
            "list_tests",
            {
                "data": {
                    "tests": [
                        {"startTime": "2026-10-20T10:00:00", "fitnessTestResult": {"ownIndex": 45}}
                    ]
                }
            },
            "vo2max_ml_kg_min",
        ),
    ],
)
def test_each_supported_watch_domain_uses_owned_connection_and_retains_provider_payload(
    intake, monkeypatch, category, method, payload, metric
):
    connect(intake)
    calls = []

    async def fetch(self, token, first, last, **kwargs):
        calls.append((token, first.isoformat(), last.isoformat(), kwargs))
        return deepcopy(payload)

    monkeypatch.setattr(service.PolarClient, method, fetch)
    request = {"request_id": str(UUID(int=66001)), "day": "2026-10-20", "domain": category}
    saved = post(intake, "polar-imports", request)
    assert calls[0][0:3] == ("synthetic-access", "2026-10-20", "2026-10-21")
    assert any(
        c["metric"] == metric
        for c in get(intake, "history?start_date=2026-10-20&end_date=2026-10-20")["items"]
    )
    with Session(intake.engine) as sync:
        assert sync.scalar(select(ProviderDataRecord)).raw_data == payload
    assert not saved["artifact"]["profile_changed"]


def test_a_missing_imported_raw_record_is_not_repaired_or_reported_as_available(
    intake, monkeypatch
):
    connect(intake)

    async def fetch(*args, **kwargs):
        return steps_payload()

    monkeypatch.setattr(service.PolarClient, "list_daily_activity", fetch)
    request = {"request_id": str(UUID(int=66002)), "day": "2026-10-20", "domain": "activity"}
    post(intake, "polar-imports", request)
    with Session(intake.engine) as sync:
        row = sync.scalar(select(ProviderDataRecord))
        sync.delete(row)
        sync.commit()
    post(intake, "polar-imports", request, 503)
    assert count(intake, ProviderDataRecord) == 0


def test_profile_registration_failure_rolls_back_all_writes(intake, monkeypatch):
    async def failed(*args, **kwargs):
        raise RuntimeError("synthetic insertion failure")

    monkeypatch.setattr(api.SqlAlchemyPlanningAuditRepository, "save", failed)
    post(intake, "profiles", profile(), 503)
    assert count(intake, PlanningAuditArtifactRow) == 0


def test_import_insertion_failure_keeps_neither_orphan_raw_data_nor_receipt(intake, monkeypatch):
    connect(intake)

    async def fetch(*args, **kwargs):
        return steps_payload()

    async def failed(*args, **kwargs):
        raise RuntimeError("synthetic receipt failure")

    monkeypatch.setattr(service.PolarClient, "list_daily_activity", fetch)
    monkeypatch.setattr(api.SqlAlchemyPlanningAuditRepository, "save", failed)
    request = {"request_id": str(UUID(int=66003)), "day": "2026-10-20", "domain": "activity"}
    post(intake, "polar-imports", request, 503)
    assert count(intake, ProviderDataRecord) == 0 and count(intake, PlanningAuditArtifactRow) == 0


def test_whole_mesocycle_requires_current_owned_period_dates(intake):
    from app.models.entities import TrainingPeriod

    cycle = intake.client.post("/api/v1/planning/cycles/programs", json=cycle_proposal()).json()[
        "artifact"
    ]
    meso = next(p for p in cycle["periods"] if p["period_type"] == "MESOCYCLE")
    p = calendar(first=meso["start_date"], length=28)
    p["data"]["mesocycle_id"] = meso["id"]
    saved = post(intake, "availability", p)["artifact"]
    with Session(intake.engine) as sync:
        row = sync.get(TrainingPeriod, UUID(meso["id"]))
        row.end_date += timedelta(days=1)
        sync.commit()
    newer = deepcopy(p)
    newer["request_id"] = str(UUID(int=66004))
    newer["previous_reference"] = domain.reference(saved)
    assert (
        post(intake, "availability", newer, 409)["detail"]["code"]
        == "ATHLETE_MESOCYCLE_DATES_CHANGED"
    )
    assert post(intake, "availability", p, 200)["artifact"] == saved
    assert (
        get(intake, f"context?start_date={meso['start_date']}&end_date=2030-01-29")[
            "calendar_context"
        ]["missing_days"][-1]
        == "2030-01-29"
    )


def test_history_source_change_requires_a_new_review_before_first_profile_selection(intake):
    with Session(intake.engine) as sync:
        sync.add(
            WorkoutSession(
                user_id=UUID(ATHLETE),
                external_provider="POLAR",
                external_id="changed",
                sport=Sport.RUNNING,
                started_at=datetime(2026, 10, 20, 8, tzinfo=UTC),
                duration_sec=3600,
                raw_data={},
            )
        )
        sync.commit()
    candidate = get(intake, "history?start_date=2026-10-20&end_date=2026-10-20")["items"][0]
    with Session(intake.engine) as sync:
        sync.execute(update(WorkoutSession).values(duration_sec=7200))
        sync.commit()
    p = profile()
    p["data"].update(
        source_window={"start_date": "2026-10-20", "end_date": "2026-10-20"},
        source_selections=[domain.reference(candidate)],
    )
    post(intake, "profiles", p, 409)
    assert count(intake, PlanningAuditArtifactRow) == 0


def test_manual_period_average_is_not_silently_treated_as_one_day_or_total(intake):
    p = profile()
    m = manual("daily_steps", "1234.5")
    m.update(start_date="2026-10-14", aggregation="mean")
    p["data"]["manual_observations"] = [m]
    saved = post(intake, "profiles", p)["artifact"]
    assert saved["proposal"]["data"]["manual_observations"][0]["aggregation"] == "mean"
    p["request_id"] = str(UUID(int=66005))
    p["previous_reference"] = domain.reference(saved)
    p["data"]["manual_observations"][0]["aggregation"] = "single"
    post(intake, "profiles", p, 422)


@pytest.mark.parametrize("value", [True, 0.0, "0"])
def test_dst_fold_is_an_explicit_integer(intake, value):
    p = calendar()
    p["data"]["days"][0]["windows"][0]["start_fold"] = value
    post(intake, "availability", p, 422)


def test_cancelled_target_race_retains_original_goal_link_without_blocking_refinement(intake):
    from tests.planning.test_p2_4c5r1_cycle_intent_and_boundaries import structured

    p = structured("season")
    p["goals"] = [
        {
            "key": "performance",
            "target_description": "Versenyteljesítmény",
            "details": {
                "version": "cycle-goal-fields-v0.1",
                "direction": None,
                "weekly_sessions": None,
                "event_keys": ["main-race"],
                "result_target": "",
                "notes": "",
            },
        }
    ]
    second = deepcopy(p["competitions"][0])
    second.update(
        key="second", title="Második főverseny", start_date="2030-08-01", end_date="2030-08-01"
    )
    p["competitions"].append(second)
    response = intake.client.post("/api/v1/planning/cycles/programs", json=p)
    assert response.status_code == 201, response.text
    program = response.json()["artifact"]
    events = deepcopy(p["competitions"])
    events[0]["status"] = "cancelled"
    revision = {
        "program_reference": domain.reference(program),
        "revision": 1,
        "previous_reference": None,
        "competitions": events,
        "rationale": "A célverseny elmarad; a képességcélok felülvizsgálandók.",
    }
    response = intake.client.post("/api/v1/planning/cycles/competition-revisions", json=revision)
    assert response.status_code == 201, response.text
    detail = intake.client.get("/api/v1/planning/cycles/programs/" + program["artifact_id"]).json()
    assert detail["program"]["artifact"]["proposal"]["goals"][0]["details"]["event_keys"] == [
        "main-race"
    ]
    assert (
        detail["competition_revisions"][0]["artifact"]["proposal"]["competitions"][0]["status"]
        == "cancelled"
    )


def test_identical_cycle_request_is_rechecked_after_waiting_for_owner_lock(intake, monkeypatch):
    prof = post(intake, "profiles", profile())["artifact"]
    body = cycle_proposal()
    body["athlete_context"] = {
        "profile_reference": domain.reference(prof),
        "availability_reference": None,
    }
    saved = intake.client.post("/api/v1/planning/cycles/programs", json=body).json()["artifact"]
    from app.planning.application import create_cycle_program

    repository_class = api.SqlAlchemyPlanningAuditRepository
    original = repository_class.get
    hidden = []

    async def stale_first_read(self, *, artifact_kind, artifact_id):
        if (
            artifact_kind == create_cycle_program.PROGRAM
            and artifact_id == saved["artifact_id"]
            and not hidden
        ):
            hidden.append(True)
            return None
        return await original(self, artifact_kind=artifact_kind, artifact_id=artifact_id)

    monkeypatch.setattr(repository_class, "get", stale_first_read)
    response = intake.client.post("/api/v1/planning/cycles/programs", json=body)
    assert hidden and response.status_code == 200, response.text
    assert response.json()["artifact"] == saved and response.json()["reused"] is True


@pytest.mark.parametrize("operation", ["profile", "polar_import"])
@pytest.mark.parametrize("defect", ["other_session", "active_transaction", "unknown_transaction"])
def test_registration_rejects_unowned_or_nonfresh_transactions_before_any_db_or_provider_call(
    operation, defect
):
    import asyncio
    from types import SimpleNamespace

    class UnsafeSession:
        def in_transaction(self):
            return (
                True
                if defect == "active_transaction"
                else None
                if defect == "unknown_transaction"
                else False
            )

        async def execute(self, *args, **kwargs):
            raise AssertionError("No DB work is allowed before session ownership is established.")

    session = UnsafeSession()
    repository = SimpleNamespace(session=object() if defect == "other_session" else session)
    if operation == "profile":
        coroutine = service.save(
            owner=ATHLETE,
            kind="profile",
            proposal=profile(),
            repository=repository,
            session=session,
        )
    else:
        coroutine = service.polar_import(
            owner=ATHLETE,
            proposal={
                "request_id": str(UUID(int=67001)),
                "day": "2026-10-20",
                "domain": "activity",
            },
            repository=repository,
            session=session,
        )
    with pytest.raises(service.SetupStorageError):
        asyncio.run(coroutine)
