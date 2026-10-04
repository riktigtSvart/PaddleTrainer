from datetime import date

import pytest

from app.api.routes import polar


@pytest.mark.asyncio
async def test_route_inspect_wrapper_is_read_only(
    monkeypatch,
):
    calls = []

    async def fake_builder(**kwargs):
        calls.append(
            kwargs
        )
        return {
            "sentinel": "inspect",
        }

    monkeypatch.setattr(
        polar,
        "_build_training_session_route_inspection",
        fake_builder,
    )

    result = await polar.inspect_training_session_routes(
        route_date=date(
            2026,
            9,
            30,
        ),
        artifact_policy_profile="BALANCED",
        wind_speed_mps=None,
        wind_direction_from_deg=None,
        weather_provider="OPEN_METEO_HISTORICAL",
        hydrology_provider="OVF_VRAQUERY",
        hydrology_station_registry_number=1026,
        db=object(),
    )

    assert result == {
        "sentinel": "inspect",
    }
    assert len(calls) == 1
    assert (
        calls[0][
            "persist_environment_evidence"
        ]
        is False
    )


@pytest.mark.asyncio
async def test_route_persist_wrapper_explicitly_enables_persistence(
    monkeypatch,
):
    calls = []

    async def fake_builder(**kwargs):
        calls.append(
            kwargs
        )
        return {
            "sentinel": "persist",
        }

    monkeypatch.setattr(
        polar,
        "_build_training_session_route_inspection",
        fake_builder,
    )

    result = (
        await polar.persist_training_session_route_environment_evidence(
            route_date=date(
                2026,
                9,
                30,
            ),
            artifact_policy_profile="BALANCED",
            wind_speed_mps=None,
            wind_direction_from_deg=None,
            weather_provider="OPEN_METEO_HISTORICAL",
            hydrology_provider="OVF_VRAQUERY",
            hydrology_station_registry_number=1026,
            db=object(),
        )
    )

    assert result == {
        "sentinel": "persist",
    }
    assert len(calls) == 1
    assert (
        calls[0][
            "persist_environment_evidence"
        ]
        is True
    )


def test_router_exposes_separate_read_and_write_routes():
    route_methods = {
        (
            route.path,
            tuple(
                sorted(
                    route.methods
                    or []
                )
            ),
        )
        for route in polar.router.routes
    }

    assert (
        "/integrations/polar/sessions/routes/inspect",
        (
            "GET",
        ),
    ) in route_methods

    assert (
        "/integrations/polar/sessions/routes/environment-evidence/persist",
        (
            "POST",
        ),
    ) in route_methods
