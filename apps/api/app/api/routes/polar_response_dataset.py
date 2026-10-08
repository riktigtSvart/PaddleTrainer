"""Explicit read-only dataset assembly with an optional session split manifest."""

from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.polar import _build_training_session_route_inspection
from app.db.session import get_db
from app.integrations.polar.client import PolarAPIError
from app.schemas.response_dataset import ResponseDatasetRequest

router = APIRouter(prefix="/integrations/polar", tags=["polar"])


@router.post("/sessions/{session_external_id}/response-dataset/inspect")
async def inspect_training_session_response_dataset(
    session_external_id: Annotated[str, Path(min_length=1, max_length=200)],
    route_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Annotated[ResponseDatasetRequest | None, Body()] = None,
    artifact_policy_profile: str = Query(default="BALANCED"),
    weather_provider: str | None = Query(default=None),
    hydrology_provider: str | None = Query(default=None),
    hydrology_station_registry_number: int | None = Query(default=None, ge=1),
    hydrology_relation_provider: str | None = Query(default=None),
    waterbody_provider: str | None = Query(default=None),
    water_surface_provider: str | None = Query(default=None),
    marine_surface_provider: str | None = Query(default=None),
):
    options = request or ResponseDatasetRequest()
    response = await _read_only_inspection(
        route_date=route_date,
        artifact_policy_profile=artifact_policy_profile,
        wind_speed_mps=None,
        wind_direction_from_deg=None,
        weather_provider=weather_provider,
        hydrology_provider=hydrology_provider,
        hydrology_station_registry_number=hydrology_station_registry_number,
        hydrology_relation_provider=hydrology_relation_provider,
        hydrology_relation_validation_mode=False,
        persist_environment_evidence=False,
        db=db,
        waterbody_provider=waterbody_provider,
        water_surface_provider=water_surface_provider,
        marine_surface_provider=marine_surface_provider,
        response_dataset_session_id=session_external_id,
        response_dataset_manifest=options.split_manifest.model_dump()
        if options.split_manifest
        else None,
        include_response_dataset_payload=options.include_payload,
    )
    return response["route_sessions"][0]["response_dataset_contract"]


async def _read_only_inspection(**kwargs):
    try:
        return await _build_training_session_route_inspection(**kwargs)
    except (PolarAPIError, httpx.RequestError) as exc:
        raise HTTPException(status_code=502, detail="Dataset source request failed") from exc
