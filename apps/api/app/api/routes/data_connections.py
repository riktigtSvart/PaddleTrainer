"""One local status/read boundary and an explicit provider import command."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.routes.planning_goals import DB, GoalRoute, Owner, _fresh
from app.core.config import get_settings
from app.planning.domain.persistence.audit import AuditArtifactConflictError
from app.schemas.data_connections import DataSyncInput
from app.services import data_connections as service


class ConnectionRoute(GoalRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse({"detail": {"code": "DATA_SYNC_INPUT_INVALID"}}, status_code=422, headers={"Cache-Control": "no-store"})

        return handler


router = APIRouter(prefix="/data-connections", tags=["data-connections"], route_class=ConnectionRoute)


def configured():
    settings = get_settings()
    return bool(settings.polar_client_id and settings.polar_client_secret)


async def call(operation):
    try:
        return await operation
    except service.SyncRuleError as exc:
        code = str(exc)
        status = 404 if code.endswith("NOT_FOUND") else 503 if "STORAGE" in code else 409
        raise HTTPException(status, {"code": code}, headers={"Cache-Control": "no-store"}) from None
    except (IntegrityError, AuditArtifactConflictError):
        raise HTTPException(409, {"code": "DATA_SYNC_CONCURRENT_CONFLICT"}, headers={"Cache-Control": "no-store"}) from None
    except Exception:
        raise HTTPException(503, {"code": "DATA_SYNC_SOURCE_OR_STORAGE_UNAVAILABLE"}, headers={"Cache-Control": "no-store"}) from None


@router.get("/status")
async def status(db: DB, owner: Owner):
    _fresh(db)
    return await call(service.status(db, owner, configured=configured()))


@router.get("/runs/{request_id}")
async def run(request_id: UUID, db: DB, owner: Owner):
    _fresh(db)
    return await call(service.receipt(db, owner, str(request_id)))


@router.post("/sync")
async def synchronize(payload: DataSyncInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(service.synchronize(db, owner, payload.model_dump(mode="json"), configured=configured()))
    response.status_code = 202 if result["run"]["state"] == "running" else 200 if result["reused"] else 201
    return result
