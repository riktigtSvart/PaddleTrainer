"""Owned HTTP planning: current durations, older experience and empty starts."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.entities import Sport, WorkoutSession
from tests.planning.test_p2_4c20_1_prescriptions import planner, completed, locations
from tests.planning.test_p2_4c18_4_training_plan import review, accept, owned_plans
from tests.planning.test_p2_4c5r2_athlete_setup import profile, post
from tests.planning.test_p2_4c3_goal_workflow_api import OTHER
from tests.planning.test_c21_9_1_calendar_endurance import env, prepare, review as mixed_review
from tests.planning.test_p2_4c19_training_options import save as save_options
from app.services import training_options, training_prescriptions
from copy import deepcopy


def export(name, value):
    if os.getenv("C21_9_2_EXPORT"):
        path = Path(os.environ["C21_9_2_EXPORT"])
        values = json.loads(path.read_text()) if path.exists() else {}
        values[name] = value
        path.write_text(json.dumps(values), encoding="utf-8")


def metadata(value):
    result = value["result"]
    assert result["proposals"] and {c["sport"] for c in result["proposals"]} == {"RUNNING"}
    return [result["prescription_context"]["by_candidate"][c["candidate_key"]] for c in result["proposals"]]


def test_no_running_record_can_create_and_accept_an_explicit_walk_run_start(planner):
    locations(planner)
    value = review(planner)
    for dose in metadata(value):
        assert dose["running"]["mode"] == "run_walk_start"
        assert dose["product_default_used"] is True and dose["reference_session_ids"] == []
        assert dose["duration_sec"] == 1200
    for candidate in value["result"]["proposals"]:
        assert "4 × (1 perc" in candidate["description"]
        assert sum(b["duration_sec"] for b in candidate["blocks"]) == 1200
        assert candidate["duration_reference_session_id"] is None
    before = len(owned_plans(planner)); accept(planner, value)
    assert len(owned_plans(planner)) > before
    repeated = review(planner)
    assert not repeated["result"]["create"] and not repeated["result"]["cancel"]
    export("empty", value)


def test_twelve_minute_test_does_not_override_three_longer_fresh_runs(planner):
    locations(planner)
    for token, minutes, day in [(219201, 40, "2026-10-10"), (219202, 35, "2026-10-12"), (219203, 30, "2026-10-14"), (219204, 12, "2026-10-20")]:
        completed(planner, token, minutes=minutes, day=day)
    value = review(planner)
    for dose in metadata(value):
        assert dose["running"]["mode"] == "recent_duration"
        assert dose["reference_cap_seconds"] == 1800
        assert str(UUID(int=219204)) not in dose["reference_session_ids"]
        assert str(UUID(int=219204)) in dose["running"]["recent_session_ids"]
        assert dose["duration_sec"] == 1800
    export("short_test", value)


def test_only_a_short_record_allows_a_bounded_easy_start_without_claiming_capacity(planner):
    locations(planner); completed(planner, 219205, minutes=12)
    value = review(planner)
    for dose in metadata(value):
        assert dose["duration_sec"] == 1200 and dose["reference_cap_seconds"] is None
        assert dose["running"]["mode"] == "experience_start"
        assert dose["running"]["current_capacity_inferred"] is False
    assert all("sétára váltva" in c["description"] for c in value["result"]["proposals"])


def test_old_own_runs_are_experience_not_current_duration_or_weekly_volume(planner):
    locations(planner)
    completed(planner, 219206, minutes=120, day="2021-12-15")
    completed(planner, 219207, minutes=180, day="2022-01-15", user_id=UUID(OTHER))
    value = review(planner)
    assert value["inputs"]["recent_sessions"] == []
    assert [s["id"] for s in value["inputs"]["running_background"]["sessions"]] == [str(UUID(int=219206))]
    for dose in metadata(value):
        assert dose["duration_sec"] == 1200 and dose["reference_cap_seconds"] is None
        assert dose["running"]["historical_session_ids"] == [str(UUID(int=219206))]
        assert dose["running"]["mode"] == "experience_start"
    assert value["result"]["prescription_context"]["starting_budget"]["mode"] == "declared_and_product_defaults"
    export("historical", value)
    # Correcting the old source invalidates this exact preview before writing.
    with Session(planner.engine) as db:
        db.get(WorkoutSession, UUID(int=219206)).duration_sec = 60
        db.commit()
    accept(planner, value, expected=409)


def test_an_old_personal_best_is_used_without_turning_race_pace_into_a_current_target(planner):
    locations(planner)
    p = profile(token=219208, previous=planner.profile)
    p["data"]["sport_history"].append({"sport": "Futás", "discipline": "", "current": False,
        "level": "unknown", "performances": [{"result_id": str(UUID(int=219210)), "kind": "personal_best",
            "distance_m": "5000", "time": "18:00", "recorded_on": "2022-06-15", "year": None,
            "conditions": "Pálya", "source": "self_report", "protocol": "distance_time"}]})
    post(planner, "profiles", p)
    value = review(planner)
    for dose in metadata(value):
        assert dose["running"]["mode"] == "experience_start" and dose["duration_sec"] == 1200
        assert dose["running"]["performance_references"] == [{"sport_index": 1, "result_id": str(UUID(int=219210))}]
        assert dose["intensity_basis"] == "product_default_not_personal_threshold"
    for candidate in value["result"]["proposals"]:
        assert all(b["intensity_min"] is None and b["intensity_max"] is None for b in candidate["blocks"])
    export("personal_best", value)


def test_new_running_evidence_is_visible_inside_an_existing_calibration_without_raising_its_budget(planner):
    locations(planner)
    request = {"start_date": "2026-10-24", "end_date": "2026-10-29", "coordinate_mesocycles": True}
    before = planner.client.post(planner.plan_url + "/review", json=request).json()["review"]
    completed(planner, 219209, minutes=35)
    request.pop("coordinate_mesocycles")
    after = planner.client.post(planner.plan_url + "/review", json=request).json()["review"]
    assert after["calibration_review"]["artifact_id"] == before["artifact_id"]
    a, b = [v["result"]["prescription_context"]["starting_budget"] for v in [before, after]]
    for key in ["mode", "max_sessions_per_7_days", "max_minutes_per_7_days"]:
        assert a[key] == b[key]
    assert a["weeks"] != b["weeks"]  # Current evidence is never hidden by calibration.
    assert all(d["running"]["mode"] == "recent_duration" for d in metadata(after))
    export("current_evidence", after)


def test_refresh_replaces_a_legacy_strength_only_plan_with_a_running_starter_inside_the_same_budget(env, monkeypatch):
    first = prepare(env, running=False)
    p = deepcopy(first['artifact']['proposal'])
    p.update(request_id=str(UUID(int=219211)), previous_reference=training_options.reference(first['artifact']))
    p['data']['locations'][0]['coordinates'] = {'latitude': '90', 'longitude': '0', 'timezone_name': 'UTC'}
    save_options(env, p)
    original = training_prescriptions.references
    def legacy_references(data):
        values = original(data)
        values['RUN_EASY_AEROBIC_FALLBACK'] = {'cap_seconds': None, 'session_ids': [], 'anchor_id': None}
        return values
    with monkeypatch.context() as old:
        old.setattr(training_prescriptions, 'references', legacy_references)
        old.setitem(training_prescriptions.FAMILIES, 'RUN_EASY_AEROBIC_FALLBACK',
            {**training_prescriptions.FAMILIES['RUN_EASY_AEROBIC_FALLBACK'], 'default': None})
        before = mixed_review(env)
        assert {c['sport'] for c in before['result']['proposals']} == {'STRENGTH'}
        accept(env, before, token=219212)
    after = mixed_review(env)
    assert {c['sport'] for c in after['result']['proposals']} == {'STRENGTH', 'RUNNING'}
    for key in ['max_sessions_per_7_days', 'max_minutes_per_7_days']:
        assert after['result']['preparation'][key] == before['result']['preparation'][key]
    assert after['result']['cancel'] and after['result']['create']
    accept(env, after, token=219213)
    again = mixed_review(env)
    assert not again['result']['create'] and not again['result']['cancel']
