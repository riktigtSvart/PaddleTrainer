"""Owned, versioned cycle-goal and measurement workflow over the C1/C2 services."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import PeriodType, TrainingPeriod, User
from app.planning.application import assess_mesocycle_goals as assessments
from app.planning.application import register_goal_measurement as measurements
from app.planning.application import register_goal_protocol as goals
from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.goals.catalog import (
    GOAL_CATALOG_HASH,
    GOAL_CATALOG_VERSION,
    GOAL_METRICS,
    CapabilityKey,
)
from app.planning.domain.goals.protocol import (
    CapabilityGoalRole,
    GoalVersionReference,
    goal_artifact_id,
)
from app.planning.domain.persistence.audit import AuditArtifactConflictError, AuditArtifactKind
from app.planning.infrastructure.adapters.current_goal_measurements import (
    SqlAlchemyGoalMeasurementSource,
)
from app.planning.infrastructure.adapters.current_training_period_goals import (
    SqlAlchemyTrainingGoalSource,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_goal_measurement import (
    SqlAlchemyGoalMeasurementWriter,
)
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.planning.ports.goal_measurement_write import GoalMeasurementWriteConflict
from app.schemas.planning_goals import (
    GoalArtifactListResponse,
    GoalArtifactResponse,
    GoalAssessmentInput,
    GoalMeasurementInput,
    MacrocyclePlanInput,
    MesocycleProtocolInput,
    UtcTimestamp,
)

GOAL_HTTP_BODY_LIMIT = 1024 * 1024
IDENTITY_SCOPE = "APPLICATION_DEMO_USER"
KIND = AuditArtifactKind


def _now():
    return datetime.now(UTC)


def _error(status, code):
    return HTTPException(status, {"code": code}, headers={"Cache-Control": "no-store"})


class GoalRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        allowed_query = {field.alias for field in self.dependant.query_params}

        async def handler(request: Request):
            names = [key for key, _ in request.query_params.multi_items()]
            if len(names) != len(set(names)) or set(names) - allowed_query:
                raise _error(422, "GOAL_QUERY_FIELDS_INVALID")
            if request.method == "POST":
                body, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > GOAL_HTTP_BODY_LIMIT:
                        raise _error(413, "GOAL_REQUEST_SIZE_LIMIT")
                    body.append(chunk)
                request._body = b"".join(body)
            try:
                result = await original(request)
            except SQLAlchemyError:
                raise _error(503, "GOAL_PERSISTENCE_UNAVAILABLE") from None
            result.headers["Cache-Control"] = "no-store"
            return result

        return handler


router = APIRouter(prefix="/planning/goals", tags=["planning-goals"], route_class=GoalRoute)
DB = Annotated[AsyncSession, Depends(get_db)]
ArtifactPath = Annotated[str, Path(pattern=r"^pt-goal(?:-assessment|-measurement)?:[0-9a-f]{64}$")]
Limit = Annotated[int, Query(ge=1, le=50)]
Offset = Annotated[int, Query(ge=0, le=100000)]


async def _finish_read(db):
    await db.rollback()
    if db.in_transaction() is not False:
        raise _error(503, "GOAL_TRANSACTION_NOT_CLOSED")


def _fresh(db):
    if db.in_transaction() is not False:
        raise _error(409, "GOAL_FRESH_SESSION_REQUIRED")


async def goal_owner(db: DB):
    """Existing configured owner only; never create a user as a read side effect."""
    _fresh(db)
    try:
        result = await db.execute(
            select(User.id).where(User.email == get_settings().demo_user_email)
        )
        owner = result.scalar_one_or_none()
    finally:
        await _finish_read(db)
    if owner is None:
        raise _error(404, "GOAL_CONFIGURED_OWNER_NOT_FOUND")
    return str(owner)


Owner = Annotated[str, Depends(goal_owner)]


async def _preflight(db, owner, *, period=None, references=(), retry_slot=None):
    _fresh(db)
    try:
        if retry_slot is not None:
            kind, identity = retry_slot
            existing = await db.execute(
                select(PlanningAuditArtifactRow.artifact_id).where(
                    PlanningAuditArtifactRow.artifact_kind == kind.value,
                    PlanningAuditArtifactRow.artifact_id == identity,
                    PlanningAuditArtifactRow.athlete_id == UUID(owner),
                )
            )
            if existing.scalar_one_or_none() is not None:
                return  # The domain service replays original immutable inputs.
        if period is not None:
            identity, period_type = period
            found = await db.execute(
                select(TrainingPeriod.id).where(
                    TrainingPeriod.id == UUID(identity),
                    TrainingPeriod.user_id == UUID(owner),
                    TrainingPeriod.period_type == period_type,
                )
            )
            if found.scalar_one_or_none() is None:
                raise _error(404, "GOAL_PERIOD_NOT_FOUND")
        for kind, identity in references:
            found = await db.execute(
                select(PlanningAuditArtifactRow.artifact_id).where(
                    PlanningAuditArtifactRow.artifact_kind == kind.value,
                    PlanningAuditArtifactRow.artifact_id == identity,
                    PlanningAuditArtifactRow.athlete_id == UUID(owner),
                )
            )
            if found.scalar_one_or_none() is None:
                raise _error(404, "GOAL_ARTIFACT_NOT_FOUND")
    finally:
        await _finish_read(db)


async def _call(operation):
    try:
        return await operation
    except (
        goals.CycleGoalArtifactNotFound,
        measurements.GoalMeasurementRegistrationNotFound,
        assessments.GoalAssessmentNotFound,
    ):
        raise _error(404, "GOAL_ARTIFACT_NOT_FOUND") from None
    except (AuditArtifactConflictError, GoalMeasurementWriteConflict, IntegrityError):
        raise _error(409, "GOAL_IMMUTABLE_IDENTITY_CONFLICT") from None
    except (
        ValueError,
        TypeError,
        KeyError,
        goals.CycleGoalProtocolError,
        measurements.GoalMeasurementRegistrationError,
        assessments.GoalAssessmentError,
    ):
        raise _error(409, "GOAL_CONTRACT_REJECTED") from None
    except (SQLAlchemyError, RuntimeError):
        raise _error(503, "GOAL_PERSISTENCE_UNAVAILABLE") from None


def _payload(receipt):
    committed = getattr(
        receipt, "registration_committed", getattr(receipt, "assessment_committed", False)
    )
    if committed is not True:
        raise _error(503, "GOAL_COMMIT_NOT_CONFIRMED")
    reused = getattr(receipt, "reused_registration", getattr(receipt, "reused_assessment", False))
    return {
        "identity_scope": IDENTITY_SCOPE,
        "artifact": json.loads(canonical_json(receipt.artifact)),
        "durable_available_at": receipt.durable_available_at,
        "reused": reused,
        "committed": True,
        "measurement_schedule_preregistered": receipt.measurement_schedule_preregistered,
        "physiological_adaptation_established": False,
        "planning_utility_supported": False,
        "planning_authorized": False,
    }


def _post_payload(receipt, response):
    response.status_code = (
        200
        if getattr(receipt, "reused_registration", getattr(receipt, "reused_assessment", False))
        else 201
    )
    return _payload(receipt)


async def _load(db, owner, kind, identity, available_by):
    available = available_by or _now()
    if available > _now():
        raise _error(422, "GOAL_FUTURE_AVAILABILITY_CUTOFF")
    audit = SqlAlchemyPlanningAuditRepository(db)
    if kind in {goals.MACRO_KIND, goals.MESO_KIND}:
        operation = goals.load_cycle_goal_artifact(
            athlete_id=owner,
            artifact_kind=kind,
            artifact_id=identity,
            available_by=available,
            audit_repository=audit,
            session=db,
        )
    elif kind == measurements.MEASUREMENT_KIND:
        operation = measurements.load_goal_measurement(
            athlete_id=owner,
            artifact_id=identity,
            available_by=available,
            audit_repository=audit,
            session=db,
        )
    else:
        operation = assessments.load_mesocycle_goal_assessment(
            athlete_id=owner,
            artifact_id=identity,
            available_by=available,
            audit_repository=audit,
            session=db,
        )
    return await _call(operation)


async def _detail(db, owner, kind, identity, available_by):
    await _preflight(db, owner, references=((kind, identity),))
    return _payload(await _load(db, owner, kind, identity, available_by))


async def _list(db, owner, kind, limit, offset):
    _fresh(db)
    try:
        result = await db.execute(
            select(PlanningAuditArtifactRow.artifact_id)
            .where(
                PlanningAuditArtifactRow.athlete_id == UUID(owner),
                PlanningAuditArtifactRow.artifact_kind == kind.value,
            )
            .order_by(
                PlanningAuditArtifactRow.persisted_at.desc(), PlanningAuditArtifactRow.artifact_id
            )
            .offset(offset)
            .limit(limit + 1)
        )
        identities = tuple(result.scalars().all())
    finally:
        await _finish_read(db)
    items = [
        _payload(await _load(db, owner, kind, identity, None)) for identity in identities[:limit]
    ]
    return {
        "identity_scope": IDENTITY_SCOPE,
        "items": items,
        "limit": limit,
        "offset": offset,
        "has_more": len(identities) > limit,
    }


@router.get("/catalog")
async def catalog():
    return json.loads(
        canonical_json(
            {
                "catalog_version": GOAL_CATALOG_VERSION,
                "catalog_content_hash": GOAL_CATALOG_HASH,
                "capabilities": tuple(CapabilityKey),
                "goal_roles": tuple(CapabilityGoalRole),
                "metrics": GOAL_METRICS,
                "scientific_protocol_validity_established": False,
                "identity_scope": IDENTITY_SCOPE,
            }
        )
    )


@router.post("/macrocycle-plans", response_model=GoalArtifactResponse, status_code=201)
async def register_macrocycle(
    payload: MacrocyclePlanInput, response: Response, db: DB, owner: Owner
):
    proposal = payload.to_domain()
    references = (
        ((goals.MACRO_KIND, proposal.supersedes.artifact_id),) if proposal.supersedes else ()
    )
    await _preflight(
        db,
        owner,
        period=(proposal.macrocycle_period_id, PeriodType.MACROCYCLE),
        references=references,
        retry_slot=(
            goals.MACRO_KIND,
            goal_artifact_id(
                goals.MACRO_KIND, owner, proposal.macrocycle_period_id, proposal.revision
            ),
        ),
    )
    receipt = await _call(
        goals.register_macrocycle_capability_plan(
            athlete_id=owner,
            proposal=proposal,
            source_repository=SqlAlchemyTrainingGoalSource(db),
            audit_repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    return _post_payload(receipt, response)


@router.post("/mesocycle-protocols", response_model=GoalArtifactResponse, status_code=201)
async def register_mesocycle(
    payload: MesocycleProtocolInput, response: Response, db: DB, owner: Owner
):
    proposal = payload.to_domain()
    references = ((goals.MACRO_KIND, proposal.macrocycle_plan.artifact_id),)
    if proposal.supersedes:
        references += ((goals.MESO_KIND, proposal.supersedes.artifact_id),)
    await _preflight(
        db,
        owner,
        period=(proposal.mesocycle_period_id, PeriodType.MESOCYCLE),
        references=references,
        retry_slot=(
            goals.MESO_KIND,
            goal_artifact_id(
                goals.MESO_KIND, owner, proposal.mesocycle_period_id, proposal.revision
            ),
        ),
    )
    receipt = await _call(
        goals.register_mesocycle_goal_protocol(
            athlete_id=owner,
            proposal=proposal,
            source_repository=SqlAlchemyTrainingGoalSource(db),
            audit_repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    return _post_payload(receipt, response)


@router.post("/measurements", response_model=GoalArtifactResponse, status_code=201)
async def register_measurement(
    payload: GoalMeasurementInput, response: Response, db: DB, owner: Owner
):
    proposal = payload.to_domain()
    await _preflight(
        db, owner, references=((goals.MESO_KIND, proposal.protocol_reference.artifact_id),)
    )
    receipt = await _call(
        measurements.register_goal_measurement(
            athlete_id=owner,
            proposal=proposal,
            measurement_repository=SqlAlchemyGoalMeasurementWriter(db),
            audit_repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    return _post_payload(receipt, response)


@router.post("/assessments", response_model=GoalArtifactResponse, status_code=201)
async def assess_goals(payload: GoalAssessmentInput, response: Response, db: DB, owner: Owner):
    if payload.activity_cutoff_at > _now():
        raise _error(422, "GOAL_FUTURE_ACTIVITY_CUTOFF")
    await _preflight(
        db, owner, references=((goals.MESO_KIND, payload.protocol_reference.artifact_id),)
    )
    receipt = await _call(
        assessments.assess_mesocycle_goal_protocol(
            athlete_id=owner,
            protocol_reference=GoalVersionReference(**payload.protocol_reference.model_dump()),
            activity_cutoff_at=payload.activity_cutoff_at,
            source_repository=SqlAlchemyGoalMeasurementSource(db),
            audit_repository=SqlAlchemyPlanningAuditRepository(db),
            session=db,
        )
    )
    return _post_payload(receipt, response)


def _add_reads(resource, kind):
    async def listing(db: DB, owner: Owner, limit: Limit = 25, offset: Offset = 0):
        return await _list(db, owner, kind, limit, offset)

    async def detail(
        artifact_id: ArtifactPath, db: DB, owner: Owner, available_by: UtcTimestamp | None = None
    ):
        return await _detail(db, owner, kind, artifact_id, available_by)

    listing.__name__ = "list_goal_" + resource.replace("-", "_")
    detail.__name__ = "get_goal_" + resource.replace("-", "_")
    router.add_api_route(
        "/" + resource, listing, methods=["GET"], response_model=GoalArtifactListResponse
    )
    router.add_api_route(
        "/" + resource + "/{artifact_id}",
        detail,
        methods=["GET"],
        response_model=GoalArtifactResponse,
    )


for _resource, _kind in (
    ("macrocycle-plans", goals.MACRO_KIND),
    ("mesocycle-protocols", goals.MESO_KIND),
    ("measurements", measurements.MEASUREMENT_KIND),
    ("assessments", assessments.ASSESSMENT_KIND),
):
    _add_reads(_resource, _kind)
