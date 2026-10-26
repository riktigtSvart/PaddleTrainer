"""Configured-owner intake, availability and historical source review; no implicit imports."""

from datetime import date
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.planning_goals import DB, GoalRoute, Owner, _fresh
from app.integrations.polar.client import PolarAPIError
from app.planning.application import register_athlete_setup as service
from app.planning.application.create_cycle_program import timezone_for
from app.planning.domain import athlete_setup as domain
from app.planning.domain.persistence.audit import AuditArtifactConflictError
from app.planning.infrastructure.adapters.athlete_history import historical_candidates
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.athlete_setup import AvailabilityInput, PolarImportInput, ProfileInput


class SetupRoute(GoalRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    {"detail": {"code": "ATHLETE_INPUT_INVALID"}},
                    status_code=422,
                    headers={"Cache-Control": "no-store"},
                )

        return handler


router = APIRouter(prefix="/planning/athlete", tags=["athlete-setup"], route_class=SetupRoute)
Identity = Annotated[str, Path(pattern=r"^pt-athlete:[0-9a-f]{64}$")]
DayQuery = Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]


def error(status, code):
    return HTTPException(status, {"code": code}, headers={"Cache-Control": "no-store"})


async def call(operation):
    try:
        return await operation
    except service.SetupNotFound:
        raise error(404, "ATHLETE_RECORD_NOT_FOUND") from None
    except domain.SetupRuleError as exc:
        raise error(409, exc.code) from None
    except (IntegrityError, AuditArtifactConflictError):
        raise error(409, "ATHLETE_REQUEST_IDENTITY_CONFLICT") from None
    except (PolarAPIError, httpx.HTTPError):
        raise error(502, "ATHLETE_POLAR_UNAVAILABLE_OR_REJECTED") from None
    except (
        SQLAlchemyError,
        service.SetupStorageError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
    ):
        raise error(503, "ATHLETE_STORAGE_OR_SOURCE_UNAVAILABLE") from None


def valid_range(start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if (
            first.isoformat() != start
            or last.isoformat() != end
            or not ("1900-01-01" <= start <= end <= "2100-12-31")
            or not (0 <= (last - first).days < 366)
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise error(422, "ATHLETE_DATE_RANGE_INVALID") from None


@router.get("/context")
async def context(
    db: DB, owner: Owner, start_date: DayQuery | None = None, end_date: DayQuery | None = None
):
    _fresh(db)
    if (start_date is None) != (end_date is None):
        raise error(422, "ATHLETE_DATE_RANGE_INVALID")
    if start_date is not None:
        valid_range(start_date, end_date)
    return await call(
        service.get_context(
            owner=owner,
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
            start=start_date,
            end=end_date,
        )
    )


@router.post("/profiles", status_code=201)
async def profile(payload: ProfileInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(
        service.save(
            owner=owner,
            kind="profile",
            proposal=payload.model_dump(),
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result


@router.post("/availability", status_code=201)
async def availability(payload: AvailabilityInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(
        service.save(
            owner=owner,
            kind="availability",
            proposal=payload.model_dump(),
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result


@router.post("/availability/preview")
async def availability_preview(payload: AvailabilityInput, db: DB, owner: Owner):
    _fresh(db)
    try:
        timezone_name = await timezone_for(db, owner)
        domain.require(
            payload.data.timezone_name == timezone_name, "ATHLETE_CALENDAR_TIMEZONE_DIFFERS"
        )
        return {
            "schema_version": domain.SCHEMA,
            "calendar": domain.resolve_calendar(payload.data.model_dump()),
            "proposal_hash": domain.digest(payload.model_dump()),
            "committed": False,
            "planning_authorized": False,
        }
    except domain.SetupRuleError as exc:
        raise error(409, exc.code) from None
    finally:
        await service.rollback(db)


@router.get("/history")
async def history(db: DB, owner: Owner, start_date: DayQuery, end_date: DayQuery):
    _fresh(db)
    valid_range(start_date, end_date)
    try:
        candidates = await call(
            historical_candidates(
                db,
                owner,
                first=start_date,
                last=end_date,
                timezone_name=await timezone_for(db, owner),
            )
        )
        return {
            "schema_version": "athlete-history-candidates-v0.1",
            "start_date": start_date,
            "end_date": end_date,
            "items": candidates,
            "has_more": False,
            "absence_means_zero": False,
            "profile_changed": False,
        }
    finally:
        await service.rollback(db)


@router.get("/{kind}/{identity}")
async def record(
    kind: Literal["profiles", "availability"], identity: Identity, db: DB, owner: Owner
):
    _fresh(db)
    try:
        artifact, stored = await call(
            service.load(
                SqlAlchemyPlanningAuditRepository(db),
                owner,
                "profile" if kind == "profiles" else "availability",
                identity,
            )
        )
        return service.receipt(artifact, stored, True)
    finally:
        await service.rollback(db)


@router.post("/polar-imports", status_code=201)
async def polar_import(payload: PolarImportInput, response: Response, db: DB, owner: Owner):
    _fresh(db)
    result = await call(
        service.polar_import(
            owner=owner,
            proposal=payload.model_dump(),
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result
