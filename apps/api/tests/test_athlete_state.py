from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

import app.services.athlete_state as athlete_state_service


class FakeDb:
    def __init__(self, readiness):
        self.readiness = readiness

    async def scalar(self, statement):
        return self.readiness


@pytest.mark.asyncio
async def test_get_athlete_state_aggregates_load_and_readiness(
    monkeypatch,
):
    as_of_date = date(2026, 9, 30)

    user = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000001"
        )
    )

    readiness = SimpleNamespace(
        marker="readiness"
    )

    db = FakeDb(readiness)

    expected_load = {
        "smoothed": {
            "method": "NORMALIZED_EWMA",
        },
    }

    expected_readiness = {
        "recorded_date": "2026-09-30",
        "source": "MANUAL",
    }

    expected_responses = [
        {
            "workout_session_id": "session-1",
            "response_timing": "IMMEDIATE",
            "fatigue_score": 6.0,
        },
    ]

    expected_trajectories = {
        "by_workout_session": [
            {
                "workout_session_id": "session-1",
                "observations": expected_responses,
            },
        ],
        "unlinked_observations": [],
    }

    expected_capacity_observations = [
        {
            "capacity_type": "GENERAL_AEROBIC",
            "sport": None,
            "value": 68.2,
            "unit": "ml/kg/min",
            "source": "ASSESSMENT",
            "confidence": 0.95,
        },
    ]

    expected_capacity_evidence = {
        "groups": [
            {
                "capacity_type": "GENERAL_AEROBIC",
                "sport": None,
                "observations": (
                    expected_capacity_observations
                ),
            },
        ],
    }

    async def fake_get_training_load_proxies(
        db,
        user,
        as_of_date,
        timezone_name,
    ):
        assert db is not None
        assert user.id == UUID(
            "00000000-0000-0000-0000-000000000001"
        )
        assert as_of_date == date(2026, 9, 30)
        assert timezone_name == "Europe/Budapest"

        return expected_load

    def fake_build_readiness_evidence(
        readiness_value,
    ):
        assert readiness_value is readiness

        return expected_readiness

    async def fake_get_daily_response_observations(
        db,
        user,
        recorded_date,
        timezone_name,
    ):
        assert recorded_date == date(2026, 9, 30)
        assert timezone_name == "Europe/Budapest"

        return expected_responses

    async def fake_get_capacity_observations(
        db,
        user,
        as_of_date,
        timezone_name,
    ):
        assert as_of_date == date(2026, 9, 30)
        assert timezone_name == "Europe/Budapest"

        return expected_capacity_observations

    def fake_build_capacity_evidence(
        observations,
    ):
        assert (
            observations
            is expected_capacity_observations
        )

        return expected_capacity_evidence

    monkeypatch.setattr(
        athlete_state_service,
        "get_training_load_proxies",
        fake_get_training_load_proxies,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "build_readiness_evidence",
        fake_build_readiness_evidence,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "get_daily_response_observations",
        fake_get_daily_response_observations,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "get_capacity_observations",
        fake_get_capacity_observations,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "build_capacity_evidence",
        fake_build_capacity_evidence,
    )

    state = await athlete_state_service.get_athlete_state(
        db=db,
        user=user,
        as_of_date=as_of_date,
        timezone_name="Europe/Budapest",
    )

    assert state == {
        "as_of_date": as_of_date,
        "training_load": expected_load,
        "readiness": expected_readiness,
        "responses": expected_responses,
        "response_trajectories": (
            expected_trajectories
        ),
        "capacity_observations": (
            expected_capacity_observations
        ),
        "capacity_evidence": (
            expected_capacity_evidence
        ),
    }


@pytest.mark.asyncio
async def test_get_athlete_state_allows_missing_readiness(
    monkeypatch,
):
    as_of_date = date(2026, 9, 30)

    user = SimpleNamespace(
        id=UUID(
            "00000000-0000-0000-0000-000000000001"
        )
    )

    db = FakeDb(None)

    expected_load = {
        "smoothed": {
            "method": "NORMALIZED_EWMA",
        },
    }

    expected_capacity_evidence = {
        "groups": [],
    }

    async def fake_get_training_load_proxies(
        db,
        user,
        as_of_date,
        timezone_name,
    ):
        return expected_load

    def fail_if_called(readiness_value):
        raise AssertionError(
            "Readiness evidence must not be built "
            "when readiness is missing"
        )

    async def fake_get_daily_response_observations(
        db,
        user,
        recorded_date,
        timezone_name,
    ):
        return []

    async def fake_get_capacity_observations(
        db,
        user,
        as_of_date,
        timezone_name,
    ):
        return []

    def fake_build_capacity_evidence(
        observations,
    ):
        assert observations == []

        return expected_capacity_evidence

    monkeypatch.setattr(
        athlete_state_service,
        "get_training_load_proxies",
        fake_get_training_load_proxies,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "build_readiness_evidence",
        fail_if_called,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "get_daily_response_observations",
        fake_get_daily_response_observations,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "get_capacity_observations",
        fake_get_capacity_observations,
    )

    monkeypatch.setattr(
        athlete_state_service,
        "build_capacity_evidence",
        fake_build_capacity_evidence,
    )

    state = await athlete_state_service.get_athlete_state(
        db=db,
        user=user,
        as_of_date=as_of_date,
        timezone_name="Europe/Budapest",
    )

    assert state == {
        "as_of_date": as_of_date,
        "training_load": expected_load,
        "readiness": None,
        "responses": [],
        "response_trajectories": {
            "by_workout_session": [],
            "unlinked_observations": [],
        },
        "capacity_observations": [],
        "capacity_evidence": {
            "groups": [],
        },
    }