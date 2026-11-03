"""Choosing a real supported alternative recalculates the whole reviewed horizon."""
from datetime import UTC, datetime
from itertools import pairwise

import pytest

from app.models.entities import PlannedWorkout, Sport
from app.planning.domain.athlete_setup import reference
from tests.planning.test_p2_4c3_goal_workflow_api import count
from tests.planning.test_p2_4c18_4_training_plan import (
    accept,
    add_session,
    owned_plans,
    post,
    review,
)
from tests.planning.test_p2_4c19_training_options import POOL, WATER, body, save
from tests.planning.test_p2_4c19_training_options import opportunities as opportunities_fixture


@pytest.fixture
def opportunities(tmp_path, monkeypatch):
    yield from opportunities_fixture.__wrapped__(tmp_path, monkeypatch)


def strength_history(env):
    add_session(env, token=194001, sport=Sport.STRENGTH, started_at=datetime(2026, 10, 17, 6, tzinfo=UTC), ended_at=datetime(2026, 10, 17, 6, 30, tzinfo=UTC), duration_sec=1800)


def configure(env):
    value = body()
    value["data"]["locations"][0].update(sports=["KAYAK", "STRENGTH"], resources=["Kajak", "Kézisúlyzó"], combine_allowed=True)
    save(env, value)
    strength_history(env)


def choice(env, viewed, day, candidate, expected=200):
    return post(env, "choose", {"review_reference": reference(viewed), "date": day, "candidate_key": candidate}, expected)


def test_alternative_is_a_complete_supported_workout_not_an_additional_session(opportunities):
    configure(opportunities)
    original = review(opportunities)
    group = next(group for group in original["result"]["alternatives"] if len(group["candidates"]) > 1 and any(candidate["sport"] == "STRENGTH" and candidate["candidate_key"] != group["selected_candidate_key"] for candidate in group["candidates"]))
    assert group["recommended_candidate_key"] == group["selected_candidate_key"]
    alternative = next(item for item in group["candidates"] if item["sport"] == "STRENGTH" and item["candidate_key"] != group["selected_candidate_key"])
    before = count(opportunities, PlannedWorkout)
    changed = choice(opportunities, original, group["date"], alternative["candidate_key"])["review"]
    selected = [candidate for candidate in changed["result"]["proposals"] if candidate["date"] == group["date"]]
    assert len(selected) == 1 and selected[0]["sport"] == "STRENGTH"
    assert selected[0]["location_id"] == WATER
    assert sum(block["duration_sec"] for block in selected[0]["blocks"]) == selected[0]["duration_sec"]
    assert changed["selection_preferences"][group["date"]]["template_key"] == alternative["template_key"]
    assert changed["requires_explicit_acceptance"] is True and changed["committed_plan"] is False
    assert count(opportunities, PlannedWorkout) == before
    accepted = accept(opportunities, changed, token=194002)
    assert accepted["committed"] is True
    assert len(owned_plans(opportunities)) == len(changed["result"]["proposals"])


def test_lost_choice_reply_replays_the_exact_review_without_rewriting_head(opportunities):
    configure(opportunities)
    original = review(opportunities)
    group = original["result"]["alternatives"][0]
    candidate = next(item for item in group["candidates"] if item["candidate_key"] != group["selected_candidate_key"])
    first = choice(opportunities, original, group["date"], candidate["candidate_key"])
    second = choice(opportunities, original, group["date"], candidate["candidate_key"])
    assert second["reused"] and second["review"] == first["review"]
    invalid = choice(opportunities, first["review"], group["date"], "0" * 64, 409)
    assert invalid["detail"]["code"] == "TRAINING_PLAN_ALTERNATIVE_NOT_AVAILABLE"


def test_changed_selection_is_preserved_by_future_review_and_old_accept_is_stale(opportunities):
    configure(opportunities)
    original = review(opportunities)
    group = original["result"]["alternatives"][0]
    other = next(item for item in group["candidates"] if item["candidate_key"] != group["selected_candidate_key"])
    changed = choice(opportunities, original, group["date"], other["candidate_key"])["review"]
    again = review(opportunities)
    assert again["artifact_id"] == changed["artifact_id"]
    assert again["selection_preferences"] == changed["selection_preferences"]
    accept(opportunities, original, token=194003, expected=409)


def test_two_mesocycles_are_real_bounded_reviews_and_every_rolling_week_obeys_caps(opportunities):
    configure(opportunities)
    value = review(opportunities, first="2026-10-24", last="2026-12-17")
    proposals = value["result"]["proposals"]
    assert len(value["inputs"]["days"]) == 55
    assert any(candidate["date"] >= "2026-11-20" for candidate in proposals)
    assert len({candidate["date"] for candidate in proposals}) == len(proposals)
    dates = [datetime.fromisoformat(candidate["date"]).date() for candidate in proposals]
    for first in dates:
        window = [candidate for candidate in proposals if 0 <= (datetime.fromisoformat(candidate["date"]).date() - first).days <= 6]
        assert len(window) <= 3 and sum(candidate["duration_sec"] for candidate in window) <= 180 * 60
    assert all((datetime.fromisoformat(b["start_at"]) - datetime.fromisoformat(a["start_at"])).total_seconds() >= 36 * 3600 for a, b in pairwise(proposals))


def test_closed_location_cannot_borrow_own_equipment_or_offer_a_fake_alternative(opportunities):
    value = body()
    value["data"]["weekly_slots"][0]["details"]["location_ids"] = [POOL]
    save(opportunities, value)
    result = review(opportunities)
    assert result["result"]["proposals"] == []
    assert result["result"]["alternatives"] == []
    assert all("SPORT_NOT_ALLOWED" in day["codes"] for day in result["result"]["preparation"]["selection_issues"])
    assert result["result"]["unavailable_alternatives"]


def test_location_cannot_borrow_strength_equipment_from_global_profile(opportunities):
    value = body()
    value["data"]["locations"][0].update(sports=["KAYAK", "STRENGTH"], resources=["Kajak"])
    save(opportunities, value)
    strength_history(opportunities)
    result = review(opportunities)
    assert all(candidate["sport"] != "STRENGTH" for group in result["result"]["alternatives"] for candidate in group["candidates"])


def test_changed_resources_make_a_selected_variant_reviewable_not_silently_replaced(opportunities):
    configure(opportunities)
    original = review(opportunities)
    group = original["result"]["alternatives"][0]
    strength = next(candidate for candidate in group["candidates"] if candidate["sport"] == "STRENGTH")
    chosen = choice(opportunities, original, group["date"], strength["candidate_key"])["review"]
    current = opportunities.client.get("/api/v1/planning/training-options").json()
    changed = body(194010, current["reference"])
    changed["data"]["locations"][0].update(sports=["KAYAK", "STRENGTH"], resources=["Kajak"])
    save(opportunities, changed)
    accept(opportunities, chosen, token=194011, expected=409)
    next_review = review(opportunities)
    assert "SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE" in next_review["result"]["blockers"]
    assert next_review["result"]["create"] == [] and next_review["result"]["cancel"] == []
    replacement_group = next(item for item in next_review["result"]["alternatives"] if item["date"] == group["date"])
    assert replacement_group["selected_candidate_key"] is None
    replacement = replacement_group["candidates"][0]
    recovered = choice(opportunities, next_review, group["date"], replacement["candidate_key"])["review"]
    assert recovered["result"]["blockers"] == []
