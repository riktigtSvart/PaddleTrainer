"""Explicit capture, owner-scoped listing, and environment-provider-free replay."""

from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import polar
from app.db.session import get_db
from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import ExternalConnection
from app.schemas.response_dataset import ResponseDatasetRequest
from app.services.environment_replay_persistence import (
    list_environment_replay_snapshots,
    load_environment_replay_snapshot,
)
from app.services.environment_replay_snapshot import canonical_hash, replay_environment_dataset
from app.services.hr_acquisition_persistence import load_current_hr_acquisition_declarations
from app.services.hr_timebase_persistence import load_current_hr_timebase_snapshots
from app.services.route_response_dataset import summarize_route_response_dataset

router = APIRouter(prefix="/integrations/polar", tags=["polar"])
SessionId = Annotated[str, Path(min_length=1, max_length=200)]


class EnvironmentReplayRequest(ResponseDatasetRequest):
    replay_snapshot_id: str = Field(min_length=36, max_length=36)

    @field_validator("replay_snapshot_id")
    @classmethod
    def canonical_uuid(cls, value):
        return str(UUID(value))


class EnvironmentCaptureRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


async def _owner(db):
    user = await polar.get_or_create_demo_user(db)
    connection = (
        await db.execute(
            select(ExternalConnection).where(
                ExternalConnection.user_id == user.id, ExternalConnection.provider == "POLAR"
            )
        )
    ).scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=404, detail="Polar connection not found")
    if "training_sessions:read" not in (connection.scopes or []):
        raise HTTPException(
            status_code=403, detail="Polar training_sessions:read scope not authorized"
        )
    return user, connection


@router.get("/sessions/{session_external_id}/response-dataset/replay-snapshots")
async def list_saved_environment_replay_snapshots(
    session_external_id: SessionId,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    user, _ = await _owner(db)
    try:
        return await list_environment_replay_snapshots(
            db, user_id=user.id, session_external_id=session_external_id, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_external_id}/response-dataset/capture")
async def capture_environment_replay_snapshot(
    session_external_id: SessionId,
    route_date: Annotated[date, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Annotated[EnvironmentCaptureRequest | None, Body()] = None,
    artifact_policy_profile: str = Query(default="BALANCED"),
    weather_provider: str | None = Query(default=None),
    hydrology_provider: str | None = Query(default=None),
    hydrology_station_registry_number: int | None = Query(default=None, ge=1),
    hydrology_relation_provider: str | None = Query(default=None),
    waterbody_provider: str | None = Query(default=None),
    water_surface_provider: str | None = Query(default=None),
    marine_surface_provider: str | None = Query(default=None),
):
    try:
        result = await polar._build_training_session_route_inspection(
            route_date=route_date,
            db=db,
            persist_environment_evidence=True,
            capture_environment_replay=True,
            response_dataset_session_id=session_external_id,
            artifact_policy_profile=artifact_policy_profile,
            wind_speed_mps=None,
            wind_direction_from_deg=None,
            weather_provider=weather_provider,
            hydrology_provider=hydrology_provider,
            hydrology_station_registry_number=hydrology_station_registry_number,
            hydrology_relation_provider=hydrology_relation_provider,
            hydrology_relation_validation_mode=False,
            waterbody_provider=waterbody_provider,
            water_surface_provider=water_surface_provider,
            marine_surface_provider=marine_surface_provider,
        )
    except (PolarAPIError, httpx.RequestError) as exc:
        raise HTTPException(status_code=502, detail="Replay capture source request failed") from exc
    session = result["route_sessions"][0]
    return {
        "persistence": session["environment_replay_snapshot_persistence"],
        "environment_evidence_persistence": session["environment_evidence_persistence"],
        "response_dataset_contract": session["response_dataset_contract"],
        "training_authorized": False,
    }


@router.post("/sessions/{session_external_id}/response-dataset/replay")
async def inspect_saved_environment_response_dataset(
    session_external_id: SessionId,
    route_date: Annotated[date, Query()],
    request: EnvironmentReplayRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if route_date == date.max:
        raise HTTPException(status_code=422, detail="route_date cannot be the maximum date")
    user, connection = await _owner(db)
    try:
        saved = await load_environment_replay_snapshot(
            db,
            user_id=user.id,
            session_external_id=session_external_id,
            snapshot_id=request.replay_snapshot_id,
        )
        if saved is None:
            raise HTTPException(
                status_code=404, detail="Saved environment replay snapshot not found"
            )
        token = await polar.get_valid_access_token(db, connection)
        client = PolarClient()
        sources = []
        for feature in ("routes", "samples"):
            result = await client.list_training_sessions(
                token, route_date, route_date + timedelta(days=1), features=[feature]
            )
            if not isinstance(result, dict) or not isinstance(result.get("trainingSessions"), list):
                raise HTTPException(status_code=502, detail="Replay current-source payload invalid")
            matches = [
                item
                for item in result.get("trainingSessions", [])
                if isinstance(item, dict)
                and isinstance(item.get("identifier"), dict)
                and str(item["identifier"].get("id")) == session_external_id
            ]
            if len(matches) != 1:
                raise HTTPException(
                    status_code=404 if not matches else 409,
                    detail="Current Polar source session missing or ambiguous",
                )
            sources.append(matches[0])
        kwargs = {
            "athlete_id": str(user.id),
            "session_external_id": session_external_id,
            "sample_session_match_count": 1,
        }
        clocks = await load_current_hr_timebase_snapshots(db, sources[1], **kwargs)
        declarations = await load_current_hr_acquisition_declarations(db, sources[1], **kwargs)
        dataset = replay_environment_dataset(
            saved.snapshot_json,
            snapshot_id=saved.id,
            athlete_id=user.id,
            session_external_id=session_external_id,
            route_session=sources[0],
            sample_session=sources[1],
            clocks=clocks,
            declarations=declarations,
            split_manifest=request.split_manifest.model_dump() if request.split_manifest else None,
        )
        # This flag is established by the database verifier above, never by client claims.
        dataset["input_provenance"].update(
            database_environment_replay_verified=True,
            scope="VERIFIED_SAVED_ENVIRONMENT_WITH_CURRENT_POLAR_SOURCE_AND_PINNED_HR_PROOFS",
        )
        dataset["package_hash"] = canonical_hash(
            {k: v for k, v in dataset.items() if k != "package_hash"}
        )
        return dataset if request.include_payload else summarize_route_response_dataset(dataset)
    except (PolarAPIError, httpx.RequestError) as exc:
        raise HTTPException(status_code=502, detail="Replay current-source request failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
