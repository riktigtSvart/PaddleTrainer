from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import app.services.athlete_state_scientific_view_live_source as live_source
from app.services.athlete_state_live_binding import (
    load_and_bind_athlete_state_scientific_views,
)


@pytest.mark.asyncio
async def test_prior_local_day_closed_loader_uses_previous_budapest_date(monkeypatch):
    seen = {}

    async def fake_build(*, db, user, as_of_date):
        seen.update(db=db, user=user, as_of_date=as_of_date)
        return {
            "as_of_date": as_of_date,
            "evidence_inventory": {"gaps": ["TRAVEL_STATUS_UNKNOWN"]},
        }

    monkeypatch.setattr(
        live_source,
        "build_athlete_state_scientific_view_for_date",
        fake_build,
    )
    user = SimpleNamespace(timezone="Europe/Budapest")

    result = await live_source.load_prior_local_day_closed_scientific_view(
        db="db",
        user=user,
        target_timestamp="2026-09-30T17:35:18+02:00",
    )

    assert seen["as_of_date"] == date(2026, 9, 29)
    assert result["state_timestamp"] == "2026-09-29T22:00:00+00:00"
    assert result["source_reference"]["source_as_of_date"] == "2026-09-29"
    assert result["source_reference"]["target_local_date"] == "2026-09-30"
    assert result["source_reference"]["same_day_state_used"] is False


@pytest.mark.asyncio
async def test_closed_loader_preserves_dst_local_midnight(monkeypatch):
    async def fake_build(*, db, user, as_of_date):
        return {"as_of_date": as_of_date}

    monkeypatch.setattr(
        live_source,
        "build_athlete_state_scientific_view_for_date",
        fake_build,
    )
    user = SimpleNamespace(timezone="Europe/Budapest")

    result = await live_source.load_prior_local_day_closed_scientific_view(
        db="db",
        user=user,
        target_timestamp="2026-10-25T12:00:00+01:00",
    )

    assert result["source_reference"]["effective_timestamp_local"].startswith(
        "2026-10-25T00:00:00+02:00"
    )
    assert result["state_timestamp"] == "2026-10-24T22:00:00+00:00"


@pytest.mark.asyncio
async def test_closed_loader_does_not_build_for_invalid_target(monkeypatch):
    async def fail_build(**kwargs):
        raise AssertionError("scientific view must not be loaded")

    monkeypatch.setattr(
        live_source,
        "build_athlete_state_scientific_view_for_date",
        fail_build,
    )
    user = SimpleNamespace(timezone="Europe/Budapest")

    result = await live_source.load_prior_local_day_closed_scientific_view(
        db="db",
        user=user,
        target_timestamp="2026-09-30T17:35:18",
    )
    assert result is None


def test_route_target_prefers_earliest_segment_start_timestamp():
    value = {
        "routes": [
            {
                "segments": [
                    {
                        "start_timestamp": "2026-09-30T15:35:20+00:00",
                        "midpoint_timestamp": "2026-09-30T15:35:21+00:00",
                    },
                    {
                        "start_timestamp": "2026-09-30T15:35:18+00:00",
                        "midpoint_timestamp": "2026-09-30T15:35:19+00:00",
                    },
                ]
            }
        ]
    }
    assert live_source.extract_route_athlete_state_target_timestamp(value) == (
        "2026-09-30T15:35:18+00:00"
    )


def test_route_target_falls_back_to_midpoint_timestamp():
    value = {
        "routes": [
            {
                "segments": [
                    {"midpoint_timestamp": "2026-09-30T15:35:19+00:00"}
                ]
            }
        ]
    }
    assert live_source.extract_route_athlete_state_target_timestamp(value) == (
        "2026-09-30T15:35:19+00:00"
    )


def test_route_target_rejects_timezone_naive_segment_time():
    value = {
        "routes": [
            {"segments": [{"start_timestamp": "2026-09-30T17:35:18"}]}
        ]
    }
    assert live_source.extract_route_athlete_state_target_timestamp(value) is None


@pytest.mark.asyncio
async def test_closed_daily_view_binds_through_existing_v22_policy(monkeypatch):
    async def fake_build(*, db, user, as_of_date):
        return {
            "as_of_date": as_of_date,
            "evidence_inventory": {
                "gaps": ["ILLNESS_STATUS_UNKNOWN"],
                "objective_metrics": ["hrv_rmssd_ms"],
            },
            "capacity": {"available": False, "items": [], "evidence": []},
        }

    monkeypatch.setattr(
        live_source,
        "build_athlete_state_scientific_view_for_date",
        fake_build,
    )
    user = SimpleNamespace(timezone="Europe/Budapest")
    target = "2026-09-30T17:35:18+02:00"

    binding = await load_and_bind_athlete_state_scientific_views(
        target,
        live_source.load_prior_local_day_closed_scientific_view,
        loader_kwargs={"db": "db", "user": user, "target_timestamp": target},
    )

    assert binding["status"] == "BOUND"
    assert binding["selected_snapshot"]["carried_forward"] is True
    assert "ILLNESS_STATUS_UNKNOWN" in binding["limitations"]
    assert binding["athlete_state_context"]["as_of_date"] == date(2026, 9, 29)


@pytest.mark.asyncio
async def test_scientific_view_for_date_uses_exact_existing_builder_chain(monkeypatch):
    calls = []
    user = SimpleNamespace(timezone="Europe/Budapest")
    as_of = date(2026, 9, 29)

    async def async_value(name, value):
        calls.append(name)
        return value

    monkeypatch.setattr(
        live_source,
        "get_athlete_state",
        lambda **kwargs: async_value("athlete_state", {"raw": True}),
    )
    monkeypatch.setattr(
        live_source,
        "build_coach_context",
        lambda **kwargs: calls.append("coach_context") or {"context": True},
    )
    monkeypatch.setattr(
        live_source,
        "build_coach_inputs",
        lambda value: calls.append("coach_inputs") or {"inputs": True},
    )
    monkeypatch.setattr(
        live_source,
        "build_interpretation_facts",
        lambda value: calls.append("facts") or {"facts": True},
    )
    monkeypatch.setattr(
        live_source,
        "build_descriptive_flags",
        lambda value: calls.append("flags") or {"flags": True},
    )
    monkeypatch.setattr(
        live_source,
        "build_readiness_coach_view",
        lambda value: calls.append("readiness_view")
        or {"values": {"objective": {"hrv_rmssd_ms": 55.0}}},
    )
    monkeypatch.setattr(
        live_source,
        "build_interpretation_signals",
        lambda **kwargs: calls.append("signals") or {"signals": True},
    )
    monkeypatch.setattr(
        live_source,
        "build_coach_assessment",
        lambda value: calls.append("assessment") or {"assessment": True},
    )
    monkeypatch.setattr(
        live_source,
        "build_coach_state",
        lambda **kwargs: calls.append("coach_state")
        or {
            "as_of_date": as_of,
            "readiness": {
                "view": {"values": {"objective": {"hrv_rmssd_ms": 55.0}}}
            },
        },
    )

    for attr, value in (
        ("get_hrv_reference", {"hrv": True}),
        ("get_sleep_duration_reference", {"sleep": True}),
        ("get_hrv_trend_evidence", {"trend": True}),
        ("get_resting_hr_reference", {"rhr": True}),
    ):
        monkeypatch.setattr(
            live_source,
            attr,
            lambda _value=value, _name=attr, **kwargs: async_value(
                _name, _value
            ),
        )

    monkeypatch.setattr(
        live_source,
        "compare_hrv_to_reference",
        lambda **kwargs: {"metric_key": "hrv_rmssd_ms"},
    )
    monkeypatch.setattr(
        live_source,
        "compare_sleep_duration_to_reference",
        lambda **kwargs: {"metric_key": "sleep_duration_sec"},
    )
    monkeypatch.setattr(
        live_source,
        "compare_resting_hr_to_reference",
        lambda **kwargs: {"metric_key": "resting_hr_bpm"},
    )
    monkeypatch.setattr(
        live_source,
        "build_scientific_assessment",
        lambda **kwargs: calls.append("scientific_assessment")
        or {"as_of_date": as_of, "load": {}, "readiness": {}},
    )
    monkeypatch.setattr(
        live_source,
        "get_current_capacity_state",
        lambda **kwargs: async_value("capacity", [{"capacity_type": "GENERAL_AEROBIC"}]),
    )
    monkeypatch.setattr(
        live_source,
        "build_athlete_state_scientific_view",
        lambda assessment, capacity_state=None: calls.append("scientific_view")
        or {"as_of_date": assessment["as_of_date"], "capacity": capacity_state},
    )

    result = await live_source.build_athlete_state_scientific_view_for_date(
        db="db", user=user, as_of_date=as_of
    )

    assert result["as_of_date"] == as_of
    assert result["capacity"] == [{"capacity_type": "GENERAL_AEROBIC"}]
    assert calls[0] == "athlete_state"
    assert calls[-1] == "scientific_view"
    assert "scientific_assessment" in calls
    assert "capacity" in calls
