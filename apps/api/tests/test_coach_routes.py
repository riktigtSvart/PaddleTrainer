from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import coach
from app.db.session import get_db
from app.main import app


async def override_get_db():
    yield object()


def test_get_coach_state_returns_public_contract(
    monkeypatch,
):
    async def fake_get_or_create_demo_user(db):
        return SimpleNamespace(
            timezone="Europe/Budapest",
        )

    async def fake_get_athlete_state(
        db,
        user,
        as_of_date,
        timezone_name,
    ):
        return {
            "as_of_date": as_of_date,
        }

    monkeypatch.setattr(
        coach,
        "get_or_create_demo_user",
        fake_get_or_create_demo_user,
    )

    monkeypatch.setattr(
        coach,
        "get_athlete_state",
        fake_get_athlete_state,
    )

    monkeypatch.setattr(
        coach,
        "build_coach_context",
        lambda **kwargs: {
            "context": True,
        },
    )

    monkeypatch.setattr(
        coach,
        "build_coach_inputs",
        lambda context: {
            "inputs": True,
        },
    )

    monkeypatch.setattr(
        coach,
        "build_interpretation_facts",
        lambda inputs: {
            "facts": True,
        },
    )

    monkeypatch.setattr(
        coach,
        "build_descriptive_flags",
        lambda facts: {
            "flags": True,
        },
    )

    readiness_view = {
        "available": True,
        "source": "MANUAL",
    }

    monkeypatch.setattr(
        coach,
        "build_readiness_coach_view",
        lambda facts: readiness_view,
    )

    monkeypatch.setattr(
        coach,
        "build_interpretation_signals",
        lambda **kwargs: {
            "as_of_date": "2026-09-30",
            "signals": [],
        },
    )

    monkeypatch.setattr(
        coach,
        "build_coach_assessment",
        lambda signals: {
            "assessment": True,
        },
    )

    expected = {
        "as_of_date": "2026-09-30",
        "plan": {
            "execution": None,
            "period_focus": None,
            "today_workouts": [],
        },
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": None,
            "view": readiness_view,
        },
        "signal_codes": [],
    }

    monkeypatch.setattr(
        coach,
        "build_coach_state",
        lambda **kwargs: expected,
    )

    app.dependency_overrides[
        get_db
    ] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/coach/state",
                params={
                    "as_of_date": "2026-09-30",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()

    assert payload == expected