from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.athlete_state_live_binding import (
    load_and_bind_athlete_state_scientific_views,
)


TARGET = "2026-09-30T17:35:18+02:00"


def _view(ts: str = "2026-09-30T08:00:00+02:00") -> dict:
    return {
        "schema_version": "0.7",
        "state_timestamp": ts,
        "available": True,
        "objective_metrics": [{"metric": "RESTING_HR", "value": 48}],
        "traceability_gaps": ["NO_SAME_DAY_SUBJECTIVE_INPUT"],
    }


@pytest.mark.asyncio
async def test_sync_loader_mapping_binds_existing_scientific_view():
    def loader():
        return _view()

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)

    assert result["status"] == "BOUND"
    assert result["athlete_state_context"]["objective_metrics"][0]["value"] == 48
    assert result["live_source"]["status"] == "LOADED"
    assert result["live_source"]["loader_result_shape"] == "MAPPING"


@pytest.mark.asyncio
async def test_async_loader_is_supported_without_changing_semantics():
    async def loader():
        return _view()

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] == "BOUND"
    assert result["live_source"]["loader_name"] == "test_async_loader_is_supported_without_changing_semantics.<locals>.loader"


@pytest.mark.asyncio
async def test_loader_args_and_kwargs_are_forwarded_only_to_existing_loader():
    seen = {}

    async def loader(db, user, *, as_of):
        seen.update(db=db, user=user, as_of=as_of)
        return _view()

    result = await load_and_bind_athlete_state_scientific_views(
        TARGET,
        loader,
        loader_args=("db", "user"),
        loader_kwargs={"as_of": "2026-09-30"},
    )
    assert result["status"] == "BOUND"
    assert seen == {"db": "db", "user": "user", "as_of": "2026-09-30"}


@pytest.mark.asyncio
async def test_existing_v22_1_wrapper_is_preserved():
    async def loader():
        return {
            "scientific_view": _view(),
            "state_timestamp": "2026-09-30T08:00:00+02:00",
            "snapshot_id": "state-1",
            "source_reference": {"kind": "TEST"},
        }

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] == "BOUND"
    assert result["selected_snapshot"]["snapshot_id"] == "state-1"


@pytest.mark.asyncio
async def test_sequence_selects_latest_eligible_non_future_state():
    async def loader():
        return [
            _view("2026-09-29T20:00:00+02:00"),
            _view("2026-09-30T12:00:00+02:00"),
            _view("2026-09-30T19:00:00+02:00"),
        ]

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] == "BOUND"
    assert result["selected_snapshot"]["state_timestamp"] == "2026-09-30T10:00:00+00:00"
    assert result["live_source"]["loader_result_shape"] == "SEQUENCE"


@pytest.mark.asyncio
async def test_none_source_remains_not_bound():
    async def loader():
        return None

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] == "NOT_BOUND"
    assert result["live_source"]["status"] == "EMPTY"


@pytest.mark.asyncio
async def test_empty_sequence_remains_not_bound():
    async def loader():
        return []

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] == "NOT_BOUND"
    assert result["live_source"]["scientific_view_wrapper_count"] == 0


@pytest.mark.asyncio
async def test_future_only_source_does_not_bind():
    async def loader():
        return _view("2026-09-30T18:00:00+02:00")

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] != "BOUND"


@pytest.mark.asyncio
async def test_missing_whole_view_timestamp_does_not_promote_component_timestamp():
    async def loader():
        return {
            "available": True,
            "objective_metrics": [
                {
                    "metric": "HRV",
                    "observed_at": "2026-09-30T07:00:00+02:00",
                }
            ],
        }

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] != "BOUND"
    assert result["live_source"]["infers_whole_view_timestamp_from_components"] is False


@pytest.mark.asyncio
async def test_readiness_shaped_mapping_is_not_promoted_without_state_timestamp():
    async def loader():
        return {
            "readiness": {"score": 82},
            "sleep": {"date": "2026-09-30"},
        }

    result = await load_and_bind_athlete_state_scientific_views(TARGET, loader)
    assert result["status"] != "BOUND"
    assert result["live_source"]["synthesizes_readiness_into_athlete_state"] is False


@pytest.mark.asyncio
async def test_invalid_loader_result_shape_fails_loudly():
    async def loader():
        return 42

    with pytest.raises(TypeError):
        await load_and_bind_athlete_state_scientific_views(TARGET, loader)


@pytest.mark.asyncio
async def test_non_callable_loader_fails_loudly():
    with pytest.raises(TypeError):
        await load_and_bind_athlete_state_scientific_views(TARGET, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_loader_exception_is_not_hidden_as_missing_evidence():
    async def loader():
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await load_and_bind_athlete_state_scientific_views(TARGET, loader)


@pytest.mark.asyncio
async def test_datetime_target_supported():
    async def loader():
        return _view()

    result = await load_and_bind_athlete_state_scientific_views(
        datetime(2026, 9, 30, 15, 35, 18, tzinfo=timezone.utc), loader
    )
    assert result["status"] == "BOUND"
