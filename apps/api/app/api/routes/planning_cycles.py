"""Owned cycle onboarding, exact retry receipts and append-only event refinement."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Path, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.planning_goals import DB, GoalRoute, Owner, _finish_read, _fresh
from app.planning.application import create_cycle_program as service
from app.planning.domain import cycle_program as domain
from app.planning.domain.common.serialization import compute_content_hash
from app.planning.domain.persistence.audit import AuditArtifactConflictError
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.planning_cycles import (
    BoundaryRevisionInput,
    CompetitionRevisionInput,
    CycleProgramInput,
)


class CycleRoute(GoalRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def closed_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    {"detail": {"code": "CYCLE_INPUT_INVALID"}},
                    status_code=422,
                    headers={"Cache-Control": "no-store"},
                )

        return closed_handler


router = APIRouter(prefix="/planning/cycles", tags=["planning-cycles"], route_class=CycleRoute)
Identity = Annotated[str, Path(pattern=r"^pt-cycle:[0-9a-f]{64}$")]


def error(status, code):
    return HTTPException(status, {"code": code}, headers={"Cache-Control": "no-store"})


async def call(operation):
    try:
        return await operation
    except service.CycleNotFound:
        raise error(404, "CYCLE_PROGRAM_NOT_FOUND") from None
    except domain.CycleRuleError as exc:
        raise error(409, exc.code) from None
    except (IntegrityError, AuditArtifactConflictError):
        raise error(409, "CYCLE_REQUEST_IDENTITY_CONFLICT") from None
    except (
        service.CycleStorageError,
        SQLAlchemyError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
    ):
        raise error(503, "CYCLE_PERSISTENCE_UNAVAILABLE") from None


@router.get("/catalog")
async def catalog(db: DB, owner: Owner):
    _fresh(db)
    try:
        timezone_name = await service.timezone_for(db, owner)
        today = datetime.now(UTC).astimezone(ZoneInfo(timezone_name)).date().isoformat()
        return {
            "schema_version": "cycle-creation-catalog-v0.1",
            "rules_version": domain.RULES,
            "timezone_name": timezone_name,
            "local_today": today,
            "olympics": domain.OLYMPICS,
            "calendar_version": domain.CALENDAR_VERSION,
            "calendar_source": domain.CALENDAR_SOURCE,
            "goals": domain.GOALS,
            "planning_context_version": "cycle-planning-basis-v0.1",
            "boundary_revision_schema": "cycle-mesocycle-boundary-revision-v0.1",
            "race_min_days": 28,
            "race_max_calendar_months": 12,
            "default_recreation_weeks": 12,
            "default_mesocycle_days": 28,
            "limits_are_product_policy": True,
        }
    finally:
        await _finish_read(db)


@router.post("/preview")
async def preview(payload: CycleProgramInput, db: DB, owner: Owner):
    _fresh(db)
    proposal = payload.model_dump()
    try:
        repository = SqlAlchemyPlanningAuditRepository(db)
        continuation = None
        if proposal["continued_from"] is not None:
            continuation, _ = await call(
                service._load(
                    repository,
                    owner,
                    service.PROGRAM,
                    proposal["continued_from"]["artifact_id"],
                )
            )
            if domain.reference(continuation) != proposal["continued_from"]:
                raise error(409, "CYCLE_REFERENCE_DIFFERS")
        created_at = datetime.now(UTC).isoformat()
        timezone_name = await service.timezone_for(db, owner)
        snapshot = await call(
            service.athlete_snapshot(
                repository,
                session=db,
                owner=owner,
                proposal=proposal,
                created_at=created_at,
                timezone_name=timezone_name,
                validate_latest=True,
            )
        )
        try:
            artifact = domain.build_registration(
                proposal,
                athlete_id=owner,
                timezone_name=timezone_name,
                created_at=created_at,
                continuation=continuation,
                athlete_snapshot=snapshot,
            )
        except domain.CycleRuleError as exc:
            raise error(409, exc.code) from None
        return {
            "proposal_hash": compute_content_hash(proposal, exclude_fields=frozenset()),
            "periods": artifact["periods"],
            "timezone_name": artifact["timezone_name"],
            "calendar_snapshot": artifact["calendar_snapshot"],
            **(
                {"athlete_context_snapshot": artifact["athlete_context_snapshot"]}
                if "athlete_context_snapshot" in artifact
                else {}
            ),
            "committed": False,
            "planning_authorized": False,
        }
    finally:
        await _finish_read(db)


@router.post("/programs", status_code=201)
async def create(payload: CycleProgramInput, response: Response, db: DB, owner: Owner):
    result = await call(
        service.create_program(
            owner=owner,
            proposal=payload.model_dump(),
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result


@router.get("/programs")
async def programs(
    db: DB,
    owner: Owner,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    _fresh(db)
    try:
        result = await db.execute(
            select(PlanningAuditArtifactRow.artifact_id)
            .where(
                PlanningAuditArtifactRow.athlete_id == UUID(owner),
                PlanningAuditArtifactRow.artifact_kind == service.PROGRAM.value,
            )
            .order_by(
                PlanningAuditArtifactRow.persisted_at.desc(), PlanningAuditArtifactRow.artifact_id
            )
            .offset(offset)
            .limit(limit + 1)
        )
        identities = result.scalars().all()
        repository = SqlAlchemyPlanningAuditRepository(db)
        items = []
        cache = {}
        for identity in identities[:limit]:
            artifact, record = await call(
                service._load(repository, owner, service.PROGRAM, identity, cache=cache)
            )
            items.append(service.receipt(artifact, record, reused=True))
        return {
            "items": items,
            "limit": limit,
            "offset": offset,
            "has_more": len(identities) > limit,
        }
    finally:
        await _finish_read(db)


@router.get("/programs/{identity}")
async def program(identity: Identity, db: DB, owner: Owner):
    return await call(
        service.load_program(
            owner=owner,
            identity=identity,
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )


@router.post("/competition-revisions", status_code=201)
async def revise(payload: CompetitionRevisionInput, response: Response, db: DB, owner: Owner):
    result = await call(
        service.revise_competitions(
            owner=owner,
            proposal=payload.model_dump(),
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result


@router.post("/boundary-revisions", status_code=201)
async def revise_boundary(payload: BoundaryRevisionInput, response: Response, db: DB, owner: Owner):
    from app.planning.application.revise_cycle_boundary import revise

    result = await call(
        revise(
            owner=owner,
            proposal=payload.model_dump(),
            repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    response.status_code = 200 if result["reused"] else 201
    return result
