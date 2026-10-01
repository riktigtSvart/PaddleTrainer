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


def test_get_scientific_assessment_returns_public_contract(
    monkeypatch,
):
    async def fake_get_or_create_demo_user(db):
        return SimpleNamespace(
            timezone="Europe/Budapest",
        )

    async def fake_get_current_coach_state(
        as_of_date,
        db,
    ):
        return {
            "as_of_date": as_of_date,
            "readiness": {
                "view": {
                    "values": {
                        "objective": {
                            "hrv_rmssd_ms": 58.4,
                        },
                    },
                },
            },
            "sentinel": "coach-state",
        }

    hrv_reference = {
        "metric_key": "hrv_rmssd_ms",
        "method": "RECENT_MEDIAN",
        "sample_count": 6,
        "reference_value": 54.0,
    }

    async def fake_get_hrv_reference(
        db,
        user,
        as_of_date,
    ):
        return hrv_reference

    comparison = {
        "metric_key": "hrv_rmssd_ms",
        "current_value": 58.4,
        "reference_value": 54.0,
        "relation": (
            "ABOVE_PERSONAL_REFERENCE"
        ),
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 6,
    }

    def fake_compare_hrv_to_reference(
        current_value,
        reference,
    ):
        assert current_value == 58.4
        assert reference == hrv_reference

        return comparison

    expected = {
        "as_of_date": "2026-09-30",
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": None,
            "traceability": None,
            "objective_evidence": None,
            "subjective_evidence": None,
            "context_evidence": None,
            "hrv_reference_comparison": comparison,
        },
    }

    def fake_build_scientific_assessment(
        coach_state,
        hrv_reference_comparison,
    ):
        assert (
            coach_state["sentinel"]
            == "coach-state"
        )

        assert (
            hrv_reference_comparison
            == comparison
        )

        return expected

    monkeypatch.setattr(
        coach,
        "get_or_create_demo_user",
        fake_get_or_create_demo_user,
    )

    monkeypatch.setattr(
        coach,
        "get_current_coach_state",
        fake_get_current_coach_state,
    )

    monkeypatch.setattr(
        coach,
        "get_hrv_reference",
        fake_get_hrv_reference,
    )

    monkeypatch.setattr(
        coach,
        "compare_hrv_to_reference",
        fake_compare_hrv_to_reference,
    )

    monkeypatch.setattr(
        coach,
        "build_scientific_assessment",
        fake_build_scientific_assessment,
    )

    app.dependency_overrides[
        get_db
    ] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.get(
                (
                    "/api/v1/coach/"
                    "scientific-assessment"
                ),
                params={
                    "as_of_date": "2026-09-30",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == expected