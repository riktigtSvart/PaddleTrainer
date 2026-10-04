from datetime import date,datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.integrations.polar.client import PolarAPIError, PolarClient
from app.models.entities import (
    ExternalConnection,
    PlannedWorkout,
    WorkoutSession,
)
from app.services.polar_matching import (
    link_sessions_to_planned_workouts,
    reconcile_completed_planned_workouts,
)
from app.services.polar_sync import sync_recent_sessions
from app.services.polar_targets import (
    normalize_training_target,
    sync_training_targets, normalize_phase_tree,
)
from app.services.polar_tokens import get_valid_access_token
from app.services.users import get_or_create_demo_user
from app.services.polar_nightly_recharge import (
    normalize_nightly_recharge_measurements,
    save_nightly_recharge_payload,
)
from app.services.polar_sleep import (
    normalize_sleep_measurements,
    save_sleep_payload,
)
from app.services.readiness_projection import (
    project_readiness_for_date,
)
from app.services.polar_continuous_hr import (
    normalize_continuous_hr_measurements,
    save_continuous_hr_payload,
)
from app.services.polar_training_routes import (
    normalize_polar_training_routes,
)
from app.services.route_coverage import (
    build_route_coverage_evidence,
)
from app.services.route_motion import (
    build_route_motion_evidence,
)
from app.services.route_motion_summary import (
    build_route_motion_summary_evidence,
)
from app.services.polar_training_samples import (
    normalize_polar_training_samples,
)

from app.services.exercise_speed_gps_consistency import (
    build_exercise_speed_gps_consistency,
)
from app.services.route_motion_anomaly_evidence import (
    build_route_motion_anomaly_evidence,
)
from app.services.route_motion_startup_evidence import (
    build_route_motion_startup_evidence,
)

from app.services.route_motion_path_geometry import (
    build_route_motion_path_geometry_evidence,
    build_route_motion_path_geometry_summary,
)
from app.services.route_motion_forward_anchor_evidence import (
    build_forward_anchor_reconstruction_context,
    build_route_motion_forward_anchor_evidence,
)

from app.services.route_motion_trust_boundary import (
    build_route_motion_trust_boundary_evidence,
    build_trust_boundary_policy_context,
)

from app.services.route_motion_trust_mask import (
    build_route_motion_trust_mask,
    build_route_motion_trust_mask_summary,
)

from app.services.route_workload_input import (
    build_route_workload_input,
    build_route_workload_input_summary,
)

from app.services.route_external_workload_evidence import (
    build_route_external_workload_evidence,
    build_route_external_workload_evidence_summary,
)

from app.services.route_environment_context_input import (
    build_route_environment_context_input,
    build_route_environment_context_input_summary,
)

from app.services.route_weather_sample_matching import (
    build_route_weather_sample_matching,
    build_route_weather_sample_matching_summary,
)

from app.integrations.open_meteo.client import (
    OpenMeteoAPIError,
    OpenMeteoHistoricalWeatherClient,
)
from app.services.open_meteo_weather import (
    normalize_open_meteo_historical_weather,
)

from app.integrations.ovf_vra.client import (
    DATA_TYPE_OPERATIONAL,
    METRIC_DISCHARGE,
    METRIC_WATER_LEVEL,
    METRIC_WATER_TEMPERATURE,
    OVFVRAAPIError,
    OVFVRAClient,
)
from app.services.ovf_hydrology import (
    normalize_ovf_hydrology_measurements,
)
from app.services.route_hydrology_context import (
    build_route_hydrology_context,
    build_route_hydrology_context_summary,
)

from app.services.route_wind_context import (
    build_route_wind_context,
    build_route_wind_context_summary,
)

from app.services.route_environment_evidence_record import (
    build_route_environment_evidence_record,
    build_route_environment_evidence_record_summary,
)

from app.services.route_motion_artifact_policy import (
    build_route_motion_artifact_policy,
)
from app.services.route_motion_evidence_windows import (
    build_route_motion_evidence_windows,
    build_route_motion_evidence_windows_summary,
)
from app.services.route_motion_evidence_regions import (
    build_route_motion_evidence_regions,
)
from app.services.route_motion_evidence_ranking import (
    build_route_motion_evidence_ranking,
)
from app.services.route_motion_speed_trajectory import (
    build_route_motion_speed_trajectories,
)

from app.services.polar_training_session_experiment import (
    build_discovery_ranges,
    build_training_session_experiment_sample,
)


router = APIRouter(prefix="/integrations/polar", tags=["polar"])
settings = get_settings()
state_serializer = URLSafeSerializer(settings.polar_client_secret or "dev-state-secret", salt="polar-oauth")


@router.get("/connect")
async def connect(db: AsyncSession = Depends(get_db)):
    if not settings.polar_client_id or not settings.polar_client_secret:
        raise HTTPException(500, "Set POLAR_CLIENT_ID and POLAR_CLIENT_SECRET first")
    user = await get_or_create_demo_user(db)
    state = state_serializer.dumps({"user_id": str(user.id)})
    return RedirectResponse(PolarClient().authorization_url(state))


@router.get("/callback")
async def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        raise HTTPException(400, f"Polar authorization failed: {error}")
    if not code or not state:
        raise HTTPException(400, "Missing OAuth code or state")
    try:
        state_serializer.loads(state)
    except BadSignature as exc:
        raise HTTPException(400, "Invalid OAuth state") from exc

    try:
        token = await PolarClient().exchange_code(code)
    except PolarAPIError as exc:
        raise HTTPException(502, str(exc)) from exc

    user = await get_or_create_demo_user(db)
    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id, ExternalConnection.provider == "POLAR"
        )
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token.get("expires_in", 43199)))
    if not connection:
        connection = ExternalConnection(
            user_id=user.id,
            provider="POLAR",
            access_token_encrypted=encrypt_secret(token["access_token"]),
            refresh_token_encrypted=encrypt_secret(token.get("refresh_token")),
            expires_at=expires_at,
            scopes=token.get("scope", "").split(),
        )
        db.add(connection)
    else:
        connection.access_token_encrypted = encrypt_secret(token["access_token"])
        if token.get("refresh_token"):
            connection.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
        connection.expires_at = expires_at
        connection.scopes = token.get("scope", "").split()
        connection.updated_at = datetime.now(timezone.utc)
    await db.commit()

    query = urlencode({"polar": "connected"})
    return RedirectResponse(f"{settings.frontend_url}?{query}")


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    user = await get_or_create_demo_user(db)
    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id, ExternalConnection.provider == "POLAR"
        )
    )
    return {
        "connected": bool(connection),
        "expires_at": connection.expires_at if connection else None,
        "scopes": connection.scopes if connection else [],
    }


@router.post("/nightly-recharge/sync")
async def sync_nightly_recharge(
    days: int = Query(
        default=7,
        ge=1,
        le=28,
    ),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "nightly_recharge:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar nightly_recharge:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    today = datetime.now(timezone.utc).date()

    from_date = (
        today
        - timedelta(days=days - 1)
    )

    to_date = today + timedelta(days=1)

    payload = (
        await PolarClient()
        .list_nightly_recharge_results(
            access_token,
            from_date,
            to_date,
        )
    )

    raw_result = await save_nightly_recharge_payload(
        db,
        user,
        payload,
    )

    normalized_result = (
        await normalize_nightly_recharge_measurements(
            db,
            user,
        )
    )

    readiness_results = []

    result_dates = sorted(
        {
            date.fromisoformat(
                item["sleepResultDate"]
            )
            for item in payload.get(
            "nightlyRechargeResults",
            [],
        )
            if item.get("sleepResultDate")
        }
    )

    for result_date in result_dates:
        readiness_results.append(
            await project_readiness_for_date(
                db,
                user,
                result_date,
            )
        )

    return {
        "from": from_date,
        "to": to_date,
        "days": days,
        "raw": raw_result,
        "normalized": normalized_result,
        "readiness": readiness_results,
    }


@router.get("/nightly-recharge/inspect")
async def inspect_nightly_recharge(
    days: int = Query(
        default=7,
        ge=1,
        le=28,
    ),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "nightly_recharge:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar nightly_recharge:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    today = datetime.now(timezone.utc).date()

    from_date = (
        today
        - timedelta(days=days - 1)
    )

    to_date = today + timedelta(days=1)

    payload = (
        await PolarClient()
        .list_nightly_recharge_results(
            access_token,
            from_date,
            to_date,
        )
    )

    return {
        "from": from_date,
        "to": to_date,
        "days": days,
        "raw": payload,
    }


@router.get("/sleep/inspect")
async def inspect_sleep(
    sleep_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "sleep:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar sleep:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    from_date = sleep_date
    to_date = sleep_date + timedelta(days=1)

    payload = await PolarClient().list_sleeps(
        access_token,
        from_date,
        to_date,
        features=[
            "sleep-result",
            "sleep-evaluation",
            "sleep-score",
        ],
    )

    return {
        "sleep_date": sleep_date,
        "from": from_date,
        "to": to_date,
        "raw": payload,
    }


@router.get("/continuous-heart-rate/inspect")
async def inspect_continuous_heart_rate(
    sample_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "continuous_samples:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar continuous_samples:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    from_date = sample_date
    to_date = sample_date

    payload = await PolarClient().list_continuous_samples(
        access_token,
        from_date,
        to_date,
        features=[
            "heart-rate-samples",
        ],
    )

    return {
        "sample_date": sample_date,
        "from": from_date,
        "to": to_date,
        "raw": payload,
    }


@router.post("/continuous-heart-rate/sync")
async def sync_continuous_heart_rate(
    sample_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "continuous_samples:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar continuous_samples:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    from_date = sample_date
    to_date = sample_date

    payload = await PolarClient().list_continuous_samples(
        access_token,
        from_date,
        to_date,
        features=[
            "heart-rate-samples",
        ],
    )

    raw_result = await save_continuous_hr_payload(
        db,
        user,
        payload,
    )

    normalized_result = (
        await normalize_continuous_hr_measurements(
            db,
            user,
        )
    )

    return {
        "sample_date": sample_date,
        "from": from_date,
        "to" : to_date,
        "raw": raw_result,
        "normalized": normalized_result,
    }


@router.post("/sleep/sync")
async def sync_sleep(
    sleep_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "sleep:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail="Polar sleep:read scope not authorized",
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    from_date = sleep_date
    to_date = sleep_date + timedelta(days=1)

    payload = await PolarClient().list_sleeps(
        access_token,
        from_date,
        to_date,
        features=[
            "sleep-result",
            "sleep-evaluation",
            "sleep-score",
        ],
    )

    raw_result = await save_sleep_payload(
        db,
        user,
        payload,
    )

    normalized_result = (
        await normalize_sleep_measurements(
            db,
            user,
        )
    )

    readiness_result = (
        await project_readiness_for_date(
            db,
            user,
            sleep_date,
        )
    )

    return {
        "sleep_date": sleep_date,
        "from": from_date,
        "to": to_date,
        "raw": raw_result,
        "normalized": normalized_result,
        "readiness": readiness_result,
    }

@router.get("/targets/inspect")
async def inspect_training_targets(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    access_token = await get_valid_access_token(db, connection)

    today = datetime.now(timezone.utc).date()

    from_date = today - timedelta(days=35)
    to_date = today + timedelta(days=30)

    payload = await PolarClient().list_training_targets(
        access_token,
        from_date,
        to_date,
    )

    print("TRAINING TARGET RANGE:", from_date, "->", to_date)
    print(
        "TRAINING TARGET IDS:",
        [
            str((item.get("session") or {}).get("id"))
            for item in payload
        ],
    )

    return {
        "raw": payload,
        "normalized": [
            normalize_training_target(item)
            for item in payload
        ],
    }

@router.get("/matches/inspect")
async def inspect_session_matches(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    sessions_result = await db.scalars(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.external_provider == "POLAR",
        )
    )

    sessions = list(sessions_result)
    matches = []
    unmatched_target_sessions = []

    for session in sessions:
        raw = session.raw_data or {}
        training_target = raw.get("trainingTarget") or {}
        target_id = training_target.get("id")

        if not target_id:
            continue

        target_id = str(target_id)

        planned = await db.scalar(
            select(PlannedWorkout).where(
                PlannedWorkout.user_id == user.id,
                PlannedWorkout.polar_target_id == target_id,
            )
        )

        if planned:
            matches.append(
                {
                    "session_id": str(session.id),
                    "session_external_id": session.external_id,
                    "session_started_at": session.started_at,
                    "training_target_id": target_id,
                    "planned_workout_id": str(planned.id),
                    "planned_title": planned.title,
                    "already_linked": (
                        str(session.planned_workout_id)
                        if session.planned_workout_id
                        else None
                    ),
                }
            )
        else:
            unmatched_target_sessions.append(
                {
                    "session_id": str(session.id),
                    "session_started_at": session.started_at,
                    "training_target_id": target_id,
                }
            )

    return {
        "matches": matches,
        "unmatched_target_sessions": unmatched_target_sessions,
    }

@router.get("/targets/{target_id}/inspect-raw")
async def inspect_raw_target(
    target_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    workout = await db.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.user_id == user.id,
            PlannedWorkout.polar_target_id == target_id,
        )
    )

    if workout is None:
        raise HTTPException(
            status_code=404,
            detail="Polar training target not found",
        )

    return {
        "polar_target_id": workout.polar_target_id,
        "title": workout.title,
        "raw_data": workout.raw_data,
    }

@router.get(
    "/targets/{target_id}/inspect-blocks"
)
async def inspect_target_blocks(
    target_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    workout = await db.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.user_id == user.id,
            PlannedWorkout.polar_target_id == target_id,
        )
    )

    if workout is None:
        raise HTTPException(
            status_code=404,
            detail="Polar training target not found",
        )

    raw = workout.raw_data or {}

    exercises = raw.get("exercise") or []

    result = []

    for exercise in exercises:
        result.extend(
            normalize_phase_tree(
                exercise.get("phaseOrRepeat") or []
            )
        )

    return {
        "polar_target_id": target_id,
        "title": workout.title,
        "blocks": result,
    }


@router.post("/matches/sync")
async def sync_session_matches(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    return await link_sessions_to_planned_workouts(
        db,
        user,
    )

@router.post("/sessions/sync")
async def sync_polar_sessions(
    days: int = 35,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    imported = await sync_recent_sessions(
        db,
        user,
        days=days,
    )

    return {
        "imported": imported,
        "days": min(days, 90),
    }

@router.post("/sync")
async def sync_polar(
    days: int = 35,
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    # 1. Completed training sessions
    sessions_imported = await sync_recent_sessions(
        db,
        user,
        days=days,
    )

    # 2. Planned / historical Polar targets
    targets_imported, targets_updated = (
        await sync_training_targets(
            db,
            user,
            past_days=days,
            future_days=30,
        )
    )

    # 3. Link completed sessions to planned workouts
    matching = await link_sessions_to_planned_workouts(
        db,
        user,
    )

    # 4. Mark linked planned workouts as completed
    reconciliation = (
        await reconcile_completed_planned_workouts(
            db,
            user,
        )
    )

    return {
        "sessions": {
            "imported": sessions_imported,
            "days": days,
        },
        "targets": {
            "imported": targets_imported,
            "updated": targets_updated,
        },
        "matching": matching,
        "reconciliation": reconciliation,
    }

@router.post("/targets/sync")
async def sync_targets(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    imported, updated = await sync_training_targets(
        db,
        user,
        past_days=35,
        future_days=30,
    )

    return {
        "imported": imported,
        "updated": updated,
    }

@router.post("/matches/reconcile")
async def reconcile_completed_workouts(
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    return await reconcile_completed_planned_workouts(
        db,
        user,
    )



@router.get("/sessions/routes/experiment-sample")
async def inspect_training_session_experiment_sample(
    from_date: date = Query(...),
    to_date: date = Query(...),
    sport_id: int = Query(
        default=95,
        ge=0,
    ),
    db: AsyncSession = Depends(get_db),
):
    if to_date <= from_date:
        raise HTTPException(
            status_code=422,
            detail=(
                "to_date must be after from_date; "
                "to_date is exclusive"
            ),
        )

    user = await get_or_create_demo_user(
        db
    )

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id
            == user.id,
            ExternalConnection.provider
            == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Polar connection not found"
            ),
        )

    if (
        "training_sessions:read"
        not in (
            connection.scopes
            or []
        )
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar training_sessions:read "
                "scope not authorized"
            ),
        )

    access_token = (
        await get_valid_access_token(
            db,
            connection,
        )
    )

    discovery_ranges = (
        build_discovery_ranges(
            from_date,
            to_date,
        )
    )

    catalog_payloads = []
    catalog_requests = []

    client = PolarClient()

    for (
        chunk_from,
        chunk_to,
    ) in discovery_ranges:
        payload = (
            await client
            .list_training_sessions(
                access_token,
                chunk_from,
                chunk_to,
            )
        )

        catalog_payloads.append(
            payload
        )

        catalog_requests.append(
            {
                "from": chunk_from,
                "to": chunk_to,
                "to_semantics": (
                    "EXCLUSIVE"
                ),
                "day_count": (
                    chunk_to
                    - chunk_from
                ).days,
                "training_session_count": (
                    len(
                        payload.get(
                            "trainingSessions",
                            [],
                        )
                    )
                    if isinstance(
                        payload,
                        dict,
                    )
                    else 0
                ),
            }
        )

    sample = (
        build_training_session_experiment_sample(
            catalog_payloads,
            from_date=from_date,
            to_date=to_date,
            sport_id=sport_id,
        )
    )

    return {
        "from": from_date,
        "to": to_date,
        "to_semantics": "EXCLUSIVE",
        "sport_id": sport_id,
        "discovery_request_count": (
            len(
                catalog_requests
            )
        ),
        "discovery_requests": (
            catalog_requests
        ),
        "sample": sample,
    }


@router.get("/sessions/samples/inspect")
async def inspect_training_session_samples(
    sample_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "training_sessions:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar training_sessions:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    from_date = sample_date
    to_date = sample_date + timedelta(days=1)

    payload = await PolarClient().list_training_sessions(
        access_token,
        from_date,
        to_date,
        features=[
            "samples",
        ],
    )

    return {
        "sample_date": sample_date,
        "from": from_date,
        "to": to_date,
        "raw": payload,
    }


@router.get("/sessions/routes/inspect")
async def inspect_training_session_routes(
    route_date: date = Query(...),
    artifact_policy_profile: str = Query(
        default="BALANCED",
    ),
    wind_speed_mps: float | None = Query(
        default=None,
        ge=0.0,
    ),
    wind_direction_from_deg: float | None = Query(
        default=None,
        ge=0.0,
        lt=360.0,
    ),
    weather_provider: str | None = Query(
        default=None,
    ),
    hydrology_provider: str | None = Query(
        default=None,
    ),
    hydrology_station_registry_number: int | None = Query(
        default=None,
        ge=1,
    ),
    db: AsyncSession = Depends(get_db),
):
    artifact_policy_profile = (
        artifact_policy_profile.upper()
    )

    weather_provider = (
        weather_provider.upper()
        if weather_provider
        else None
    )

    hydrology_provider = (
        hydrology_provider.upper()
        if hydrology_provider
        else None
    )

    if hydrology_provider not in (
        None,
        "OVF_VRAQUERY",
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "hydrology_provider must be "
                "OVF_VRAQUERY or omitted"
            ),
        )

    if (
        (hydrology_provider is None)
        != (
            hydrology_station_registry_number
            is None
        )
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "hydrology_provider and "
                "hydrology_station_registry_number "
                "must be provided together"
            ),
        )

    if weather_provider not in (
        None,
        "OPEN_METEO_HISTORICAL",
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "weather_provider must be "
                "OPEN_METEO_HISTORICAL or omitted"
            ),
        )

    if (
        weather_provider is not None
        and (
            wind_speed_mps is not None
            or wind_direction_from_deg is not None
        )
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "weather_provider cannot be combined "
                "with manual wind query parameters"
            ),
        )

    if (
        (wind_speed_mps is None)
        != (
            wind_direction_from_deg
            is None
        )
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "wind_speed_mps and "
                "wind_direction_from_deg must "
                "be provided together"
            ),
        )

    if artifact_policy_profile not in (
        "SENSITIVE",
        "BALANCED",
        "CONSERVATIVE",
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "artifact_policy_profile must be "
                "SENSITIVE, BALANCED, or CONSERVATIVE"
            ),
        )

    user = await get_or_create_demo_user(db)

    connection = await db.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user.id,
            ExternalConnection.provider == "POLAR",
        )
    )

    if connection is None:
        raise HTTPException(
            status_code=404,
            detail="Polar connection not found",
        )

    if (
        "training_sessions:read"
        not in (connection.scopes or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Polar training_sessions:read "
                "scope not authorized"
            ),
        )

    access_token = await get_valid_access_token(
        db,
        connection,
    )

    from_date = route_date
    to_date = route_date + timedelta(days=1)

    route_payload = await PolarClient().list_training_sessions(
        access_token,
        from_date,
        to_date,
        features=[
            "routes",
        ],
    )

    sample_payload = await PolarClient().list_training_sessions(
        access_token,
        from_date,
        to_date,
        features=[
            "samples",
        ],
    )

    sample_sessions_by_external_id = {}

    for sample_item in sample_payload.get(
            "trainingSessions",
            [],
    ):
        if not isinstance(sample_item, dict):
            continue

        sample_external_id = (
            (
                    sample_item.get("identifier")
                    or {}
            ).get("id")
        )

        if sample_external_id is None:
            continue

        sample_sessions_by_external_id[
            str(sample_external_id)
        ] = sample_item

    route_sessions = []

    for item in route_payload.get(
            "trainingSessions",
            [],
    ):
        if not isinstance(item, dict):
            continue

        external_id = (
            (
                    item.get("identifier")
                    or {}
            ).get("id")
        )

        sample_item = (
            sample_sessions_by_external_id.get(
                str(external_id)
            )
            if external_id is not None
            else None
        )

        normalized = (
            normalize_polar_training_routes(
                item
            )
        )

        coverage = (
            build_route_coverage_evidence(
                normalized,
                session_duration_ms=(
                    item.get("durationMillis")
                ),
            )
        )

        motion = build_route_motion_evidence(
            normalized
        )

        motion_summary = (
            build_route_motion_summary_evidence(
                motion
            )
        )

        normalized_samples = (
            normalize_polar_training_samples(
                {
                    "exerciseSamples": (
                        sample_item.get(
                            "exercises"
                        )
                        if sample_item is not None
                        else []
                    )
                }
            )
        )

        speed_gps_consistency = (
            build_exercise_speed_gps_consistency(
                normalized_samples,
                motion,
            )
        )

        motion_anomaly_evidence = (
            build_route_motion_anomaly_evidence(
                normalized,
                motion,
                speed_gps_consistency,
            )
        )

        motion_startup_evidence = (
            build_route_motion_startup_evidence(
                normalized,
                motion_anomaly_evidence,
            )
        )

        motion_path_geometry = (
            build_route_motion_path_geometry_evidence(
                normalized
            )
        )

        motion_path_geometry_summary = (
            build_route_motion_path_geometry_summary(
                motion_path_geometry
            )
        )

        motion_forward_anchor_evidence = (
            build_route_motion_forward_anchor_evidence(
                motion_path_geometry,
                motion_startup_evidence,
            )
        )

        motion_trust_boundary = (
            build_route_motion_trust_boundary_evidence(
                motion_startup_evidence,
                motion_forward_anchor_evidence,
            )
        )

        reconstruction_context_by_route_index = (
            build_trust_boundary_policy_context(
                motion_trust_boundary
            )
        )

        motion_artifact_policy = (
            build_route_motion_artifact_policy(
                motion_startup_evidence,
                profile=artifact_policy_profile,
                reconstruction_context_by_route_index=(
                    reconstruction_context_by_route_index
                ),
            )
        )

        trusted_normalized = (
            build_route_motion_trust_mask(
                normalized,
                motion_trust_boundary,
                motion_artifact_policy,
            )
        )

        motion_trust_mask = (
            build_route_motion_trust_mask_summary(
                trusted_normalized
            )
        )

        trusted_motion = (
            build_route_motion_evidence(
                trusted_normalized
            )
        )

        trusted_motion_summary = (
            build_route_motion_summary_evidence(
                trusted_motion
            )
        )

        trusted_speed_gps_consistency = (
            build_exercise_speed_gps_consistency(
                normalized_samples,
                trusted_motion,
            )
        )

        trusted_speed_gps_consistency_summary = {
            **trusted_speed_gps_consistency,
            "exercises": [
                {
                    key: value
                    for key, value in exercise.items()
                    if key != "comparisons"
                }
                for exercise in (
                    trusted_speed_gps_consistency.get(
                        "exercises"
                    )
                    or []
                )
                if isinstance(exercise, dict)
            ],
        }

        route_workload_input = (
            build_route_workload_input(
                trusted_normalized,
                trusted_motion,
                trusted_motion_summary,
                motion_summary,
                motion_trust_boundary,
                motion_artifact_policy,
                motion_trust_mask,
                speed_gps_consistency=(
                    trusted_speed_gps_consistency
                ),
                provider_distance_evidence={
                    "value_m": (
                        item.get(
                            "distanceMeters"
                        )
                    ),
                    "scope": (
                        "TRAINING_SESSION"
                    ),
                    "source": (
                        "PROVIDER_SESSION_SUMMARY"
                    ),
                },
            )
        )

        route_workload_input_summary = (
            build_route_workload_input_summary(
                route_workload_input
            )
        )

        route_external_workload_evidence = (
            build_route_external_workload_evidence(
                route_workload_input
            )
        )

        route_external_workload_evidence_summary = (
            build_route_external_workload_evidence_summary(
                route_external_workload_evidence
            )
        )

        route_environment_context_input = (
            build_route_environment_context_input(
                trusted_normalized,
                route_external_workload_evidence,
                session_time_context={
                    "exercise_start_time": (
                        item.get(
                            "startTime"
                        )
                    ),
                    "timezone_offset_minutes": (
                        item.get(
                            "timezoneOffsetMinutes"
                        )
                    ),
                },
            )
        )

        route_environment_context_input_summary = (
            build_route_environment_context_input_summary(
                route_environment_context_input
            )
        )

        hydrology_source = None
        route_hydrology_context = None
        route_hydrology_context_summary = None

        if (
            hydrology_provider
            == "OVF_VRAQUERY"
            and hydrology_station_registry_number
            is not None
        ):
            hydrology_anchor_segment = next(
                (
                    segment
                    for route in (
                        route_environment_context_input.get(
                            "routes"
                        )
                        or []
                    )
                    if isinstance(
                        route,
                        dict,
                    )
                    for segment in (
                        route.get(
                            "segments"
                        )
                        or []
                    )
                    if isinstance(
                        segment,
                        dict,
                    )
                    and segment.get(
                        "midpoint_timestamp"
                    )
                    is not None
                ),
                None,
            )

            if hydrology_anchor_segment is not None:
                try:
                    hydrology_anchor_datetime = (
                        datetime.fromisoformat(
                            str(
                                hydrology_anchor_segment.get(
                                    "midpoint_timestamp"
                                )
                            )
                        )
                    )
                except ValueError:
                    hydrology_anchor_datetime = None

                if hydrology_anchor_datetime is not None:
                    hydrology_start = (
                        hydrology_anchor_datetime
                        - timedelta(
                            hours=12
                        )
                    )
                    hydrology_end = (
                        hydrology_anchor_datetime
                        + timedelta(
                            hours=12
                        )
                    )

                    ovf_client = OVFVRAClient()

                    try:
                        ovf_station = (
                            await ovf_client.get_surface_station(
                                hydrology_station_registry_number
                            )
                        )

                        ovf_series = []

                        for metric_code in (
                            METRIC_WATER_LEVEL,
                            METRIC_DISCHARGE,
                            METRIC_WATER_TEMPERATURE,
                        ):
                            ovf_series.append(
                                await ovf_client.get_short_series(
                                    station_registry_number=(
                                        hydrology_station_registry_number
                                    ),
                                    metric_code=(
                                        metric_code
                                    ),
                                    data_type_code=(
                                        DATA_TYPE_OPERATIONAL
                                    ),
                                    start=(
                                        hydrology_start
                                    ),
                                    end=(
                                        hydrology_end
                                    ),
                                )
                            )

                    except OVFVRAAPIError as exc:
                        raise HTTPException(
                            status_code=502,
                            detail=str(
                                exc
                            ),
                        ) from exc

                    hydrology_source = (
                        normalize_ovf_hydrology_measurements(
                            station=(
                                ovf_station
                            ),
                            series_payloads=(
                                ovf_series
                            ),
                        )
                    )

                    route_hydrology_context = (
                        build_route_hydrology_context(
                            route_environment_context_input,
                            hydrology_source,
                        )
                    )

                    route_hydrology_context_summary = (
                        build_route_hydrology_context_summary(
                            route_hydrology_context
                        )
                    )

        weather_samples = []
        weather_source = None

        weather_anchor_segment = next(
            (
                segment
                for route in (
                    route_environment_context_input.get(
                        "routes"
                    )
                    or []
                )
                if isinstance(
                    route,
                    dict,
                )
                for segment in (
                    route.get(
                        "segments"
                    )
                    or []
                )
                if isinstance(
                    segment,
                    dict,
                )
                and segment.get(
                    "midpoint_timestamp"
                )
                is not None
                and isinstance(
                    segment.get(
                        "start_position"
                    ),
                    dict,
                )
            ),
            None,
        )

        if (
            wind_speed_mps is not None
            and wind_direction_from_deg is not None
            and weather_anchor_segment
            is not None
        ):
            anchor_position = (
                weather_anchor_segment.get(
                    "start_position"
                )
                or {}
            )

            weather_samples.append(
                {
                    "sample_id": (
                        "INSPECT_QUERY_WEATHER_0"
                    ),
                    "sample_timestamp": (
                        weather_anchor_segment.get(
                            "midpoint_timestamp"
                        )
                    ),
                    "latitude_deg": (
                        anchor_position.get(
                            "latitude_deg"
                        )
                    ),
                    "longitude_deg": (
                        anchor_position.get(
                            "longitude_deg"
                        )
                    ),
                    "wind_speed_mps": (
                        wind_speed_mps
                    ),
                    "wind_direction_from_deg": (
                        wind_direction_from_deg
                    ),
                    "source_provider": (
                        "INSPECT_QUERY"
                    ),
                    "source_product": (
                        "CONSTANT_WIND_TEST"
                    ),
                    "source_type": (
                        "SYNTHETIC_TEST_WEATHER"
                    ),
                    "spatial_support": (
                        "ROUTE_ANCHOR_POINT"
                    ),
                    "temporal_resolution_seconds": None,
                    "source_reference": None,
                }
            )

            weather_source = {
                "provider": (
                    "INSPECT_QUERY"
                ),
                "product": (
                    "CONSTANT_WIND_TEST"
                ),
                "source_type": (
                    "SYNTHETIC_TEST_WEATHER"
                ),
                "sample_count": 1,
            }

        elif (
            weather_provider
            == "OPEN_METEO_HISTORICAL"
            and weather_anchor_segment
            is not None
        ):
            anchor_position = (
                weather_anchor_segment.get(
                    "start_position"
                )
                or {}
            )

            anchor_latitude = (
                anchor_position.get(
                    "latitude_deg"
                )
            )
            anchor_longitude = (
                anchor_position.get(
                    "longitude_deg"
                )
            )
            anchor_timestamp = (
                weather_anchor_segment.get(
                    "midpoint_timestamp"
                )
            )

            try:
                anchor_datetime = (
                    datetime.fromisoformat(
                        str(
                            anchor_timestamp
                        )
                    )
                )
            except ValueError:
                anchor_datetime = None

            if (
                anchor_latitude is not None
                and anchor_longitude is not None
                and anchor_datetime is not None
            ):
                try:
                    open_meteo_payload = (
                        await OpenMeteoHistoricalWeatherClient().get_hourly_weather(
                            latitude=float(
                                anchor_latitude
                            ),
                            longitude=float(
                                anchor_longitude
                            ),
                            start_date=(
                                anchor_datetime.date()
                            ),
                            end_date=(
                                anchor_datetime.date()
                            ),
                        )
                    )
                except OpenMeteoAPIError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=str(
                            exc
                        ),
                    ) from exc

                weather_source = (
                    normalize_open_meteo_historical_weather(
                        open_meteo_payload
                    )
                )

                weather_samples = list(
                    weather_source.get(
                        "samples"
                    )
                    or []
                )

        route_weather_sample_matching = (
            build_route_weather_sample_matching(
                route_environment_context_input,
                weather_samples,
            )
        )

        route_weather_sample_matching_summary = (
            build_route_weather_sample_matching_summary(
                route_weather_sample_matching
            )
        )

        route_wind_context = (
            build_route_wind_context(
                route_environment_context_input,
                weather_sample_matching=(
                    route_weather_sample_matching
                ),
            )
        )

        route_wind_context_summary = (
            build_route_wind_context_summary(
                route_wind_context
            )
        )

        route_environment_evidence_record = (
            build_route_environment_evidence_record(
                session_external_id=(
                    str(
                        external_id
                    )
                    if external_id
                    is not None
                    else None
                ),
                route_environment_context_input=(
                    route_environment_context_input
                ),
                route_external_workload_evidence=(
                    route_external_workload_evidence
                ),
                route_weather_sample_matching=(
                    route_weather_sample_matching
                ),
                route_wind_context=(
                    route_wind_context
                ),
                weather_source=(
                    weather_source
                ),
                route_hydrology_context=(
                    route_hydrology_context
                ),
                hydrology_source=(
                    hydrology_source
                ),
            )
        )

        route_environment_evidence_record_summary = (
            build_route_environment_evidence_record_summary(
                route_environment_evidence_record
            )
        )

        motion_evidence_windows = (
            build_route_motion_evidence_windows(
                motion_anomaly_evidence
            )
        )

        motion_evidence_windows_summary = (
            build_route_motion_evidence_windows_summary(
                motion_evidence_windows
            )
        )

        motion_evidence_regions = (
            build_route_motion_evidence_regions(
                motion_evidence_windows
            )
        )

        motion_evidence_ranking = (
            build_route_motion_evidence_ranking(
                motion_evidence_windows,
                motion_evidence_regions,
            )
        )

        motion_speed_trajectories = (
            build_route_motion_speed_trajectories(
                motion_anomaly_evidence,
                motion_evidence_ranking,
            )
        )

        speed_gps_consistency_summary = {
            **speed_gps_consistency,
            "exercises": [
                {
                    key: value
                    for key, value in exercise.items()
                    if key != "comparisons"
                }
                for exercise in (
                        speed_gps_consistency.get(
                            "exercises"
                        )
                        or []
                )
                if isinstance(exercise, dict)
            ],
        }

        motion_anomaly_summary = {
            **motion_anomaly_evidence,
            "routes": [
                {
                    key: value
                    for key, value in route.items()
                    if key != "observations"
                }
                for route in (
                        motion_anomaly_evidence.get(
                            "routes"
                        )
                        or []
                )
                if isinstance(route, dict)
            ],
        }

        route_sessions.append(
            {
                "external_id": external_id,
                "sample_session_matched": (
                        sample_item is not None
                ),
                "normalized": normalized,
                "coverage": coverage,
                "motion_summary": motion_summary,
                "speed_gps_consistency": (
                    speed_gps_consistency_summary
                ),
                "motion_anomaly_evidence": (
                    motion_anomaly_summary
                ),
                "motion_startup_evidence": (
                    motion_startup_evidence
                ),
                "motion_path_geometry": (
                    motion_path_geometry_summary
                ),
                "motion_forward_anchor_evidence": (
                    motion_forward_anchor_evidence
                ),
                "motion_trust_boundary": (
                    motion_trust_boundary
                ),
                "motion_artifact_policy": (
                    motion_artifact_policy
                ),
                "motion_trust_mask": (
                    motion_trust_mask
                ),
                "trusted_motion_summary": (
                    trusted_motion_summary
                ),
                "trusted_speed_gps_consistency": (
                    trusted_speed_gps_consistency_summary
                ),
                "route_workload_input": (
                    route_workload_input_summary
                ),
                "route_external_workload_evidence": (
                    route_external_workload_evidence_summary
                ),
                "route_environment_context_input": (
                    route_environment_context_input_summary
                ),
                "hydrology_source": (
                    {
                        key: value
                        for key, value
                        in (
                            hydrology_source
                            or {}
                        ).items()
                        if key != "measurements"
                    }
                    if hydrology_source
                    is not None
                    else None
                ),
                "route_hydrology_context": (
                    route_hydrology_context_summary
                ),
                "weather_source": (
                    {
                        key: value
                        for key, value
                        in (
                            weather_source
                            or {}
                        ).items()
                        if key != "samples"
                    }
                    if weather_source
                    is not None
                    else None
                ),
                "route_weather_sample_matching": (
                    route_weather_sample_matching_summary
                ),
                "route_wind_context": (
                    route_wind_context_summary
                ),
                "route_environment_evidence_record": (
                    route_environment_evidence_record_summary
                ),
                "motion_evidence_windows": (
                    motion_evidence_windows_summary
                ),
                "motion_evidence_regions": (
                    motion_evidence_regions
                ),
                "motion_evidence_ranking": (
                    motion_evidence_ranking
                ),
                "motion_speed_trajectories": (
                    motion_speed_trajectories
                ),
            }
        )

    return {
        "route_date": route_date,
        "from": from_date,
        "to": to_date,
        "route_sessions": route_sessions,
        "raw": {
            "routes": route_payload,
            "samples": sample_payload,
        },
    }


