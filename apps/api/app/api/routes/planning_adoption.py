from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import User
from app.planning.application.apply_plan_revision import (
    AuthoritativePlanRevisionNoChange,
    AuthoritativePlanRevisionStaleCurrent,
    apply_authoritative_plan_revision_with_repository,
)
from app.planning.application.audited_plan_mutation import (
    AuditedPlanMutationInstructionError,
    AuditedPlanMutationInstructionNotFound,
    load_audited_plan_mutation_instruction,
)
from app.planning.application.link_authoritative_execution import (
    AuthoritativeExecutionPlanNotFound,
    AuthoritativeExecutionPlanStateError,
    link_authoritative_execution_with_repository,
)
from app.planning.application.polar_source_reconciliation import (
    build_polar_source_reconciliation,
)
from app.planning.application.plan_adoption import (
    PlanAdoptionNotEligibleError,
    PlanAdoptionStalePreviewError,
    PlanAlreadyAdoptedError,
    adopt_with_repository,
    preview_with_repository,
)
from app.planning.domain.execution_link import (
    AuthoritativeExecutionLinkConflictError,
    AuthoritativeExecutionLinkNotEligible,
)
from app.planning.domain.integration.polar_reconciliation import (
    PolarSourceReconciliationError,
)
from app.planning.domain.plan_revision.persistence_contract import (
    AuthoritativePlanConflictError,
)
from app.planning.infrastructure.adapters.current_app_plan_read import (
    CurrentAppPlanReadAdapterError,
    capture_current_app_plan,
)
from app.planning.infrastructure.adapters.locked_execution_source import (
    CurrentAppLockedExecutionSource,
)
from app.planning.infrastructure.repositories.postgres_authoritative_plan_execution import (
    build_production_authoritative_plan_execution_repository,
)
from app.planning.infrastructure.repositories.postgres_authoritative_plan_revision import (
    build_production_authoritative_plan_revision_repository,
)
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    build_production_planning_audit_repository,
)
from app.planning.infrastructure.repositories.postgres_plan_reconciliation_audit import (
    PlanReconciliationAuditPersistenceError,
    build_production_plan_reconciliation_audit_repository,
)
from app.planning.ports.execution_source import (
    ExecutionSourceNotFound,
)
from app.planning.application.link_authoritative_occurrence_execution import (
    AuthoritativeOccurrenceExecutionPlanLinkNotFound,
    AuthoritativeOccurrenceExecutionStateError,
    link_authoritative_occurrence_execution_with_repository,
)
from app.planning.domain.occurrence_execution import (
    OccurrenceExecutionConflictError,
    OccurrenceExecutionNotEligible,
)
from app.planning.infrastructure.adapters.current_phase_occurrence_candidate import (
    CurrentAppPhaseOccurrenceCandidateProvider,
    CurrentPhaseOccurrenceCandidateNotFound,
)
from app.planning.infrastructure.adapters.phase_occurrence_candidate import (
    PhaseOccurrenceCandidateAdapterError,
)
from app.planning.infrastructure.repositories.postgres_authoritative_occurrence_execution import (
    build_production_authoritative_occurrence_execution_repository,
)
from app.services.phase_reconciliation_read import (
    PhaseReconciliationReadError,
)
from app.services.plan_contract_read import PlanReadError


router = APIRouter(tags=["planning-adoption"])


class PlanAdoptionRequest(BaseModel):
    expected_source_content_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    acknowledge_current_state_baseline_only: Literal[True]



class AuthoritativePlanRevisionRequest(BaseModel):
    instruction_id: str = Field(min_length=1)


class AuthoritativeOccurrenceExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(
        min_length=12,
        max_length=256,
        pattern=r"^phase_path_.+$",
    )
    stable_source_occurrence_id: str = Field(
        min_length=25,
        max_length=256,
        pattern=r"^phase-source-occurrence_.+$",
    )
    acknowledge_candidate_boundaries: Literal[True]
    acknowledge_not_provider_verified: Literal[True]


async def _existing_owner_id(db: AsyncSession):
    with db.no_autoflush:
        return await db.scalar(
            select(User.id).where(User.email == get_settings().demo_user_email)
        )


def _preview_payload(preview) -> dict:
    return {
        "status": preview.status.value,
        "logical_plan_id": preview.logical_plan_id,
        "athlete_id": preview.athlete_id,
        "source_workout_id": preview.source_workout_id,
        "source_kind": preview.source_kind,
        "source_content_sha256": preview.source_content_sha256,
        "capture_id": preview.capture_id,
        "capture_content_hash": preview.capture_content_hash,
        "source_read_content_hash": preview.source_read_content_hash,
        "external_contract_plan_id": preview.external_contract_plan_id,
        "external_contract_plan_revision": preview.external_contract_plan_revision,
        "external_occurrence_count": preview.external_occurrence_count,
        "history_claim": preview.history_claim.value,
        "direct_external_id_promotion_allowed": (
            preview.direct_external_id_promotion_allowed
        ),
        "baseline_adoption_allowed": preview.baseline_adoption_allowed,
        "external_plan_id_promoted": preview.external_plan_id_promoted,
        "external_occurrence_ids_promoted": (
            preview.external_occurrence_ids_promoted
        ),
        "source_workout_mutated": preview.source_workout_mutated,
        "existing_current_revision_id": preview.existing_current_revision_id,
        "polar_reconciliation_status": preview.polar_reconciliation_status,
        "polar_reconciliation_rules_version": preview.polar_reconciliation_rules_version,
        "polar_reconciliation_content_hash": preview.polar_reconciliation_content_hash,
        "polar_reconciliation_gate_satisfied": preview.polar_reconciliation_gate_satisfied,
        "polar_reconciliation_audit_persistence_ready": (
            preview.polar_reconciliation_audit_persistence_ready
        ),
        "actual_execution_timing_in_scope": False,
        "blockers": list(preview.blockers),
        "database_writes": 0,
        "provider_calls": 0,
    }



def _reconciliation_payload(artifact) -> dict:
    return {
        "schema_version": artifact.schema_version,
        "rules_version": artifact.rules_version,
        "capture_id": artifact.capture_id,
        "captured_at": artifact.captured_at.isoformat(),
        "logical_plan_id": artifact.logical_plan_id,
        "athlete_id": artifact.athlete_id,
        "source_workout_id": artifact.source_workout_id,
        "source_content_sha256": artifact.source_content_sha256,
        "source_read_content_hash": artifact.source_read_content_hash,
        "external_contract_plan_id": artifact.external_contract_plan_id,
        "external_contract_plan_revision": artifact.external_contract_plan_revision,
        "timezone_context_name": artifact.timezone_context_name,
        "timezone_context_source": artifact.timezone_context_source,
        "status": artifact.status.value,
        "future_baseline_adoption_support": artifact.future_baseline_adoption_support.value,
        "semantic_equivalence_claimed": artifact.semantic_equivalence_claimed,
        "current_orm_edit_detected": artifact.current_orm_edit_detected,
        "provider_snapshot_selected_as_future_authority_candidate": (
            artifact.provider_snapshot_selected_as_future_authority_candidate
        ),
        "adoption_gate_integrated": artifact.adoption_gate_integrated,
        "compared_fields": list(artifact.compared_fields),
        "differences": [
            {
                "field_path": item.field_path,
                "code": item.code,
                "materiality": item.materiality.value,
                "expected_value": item.expected_value,
                "actual_value": item.actual_value,
            }
            for item in artifact.differences
        ],
        "normalization_notes": list(artifact.normalization_notes),
        "excluded_fields": list(artifact.excluded_fields),
        "blockers": list(artifact.blockers),
        "content_hash_algorithm": artifact.content_hash_algorithm,
        "content_hash": artifact.content_hash,
        "database_writes": 0,
        "provider_calls": 0,
        "source_workout_mutated": False,
        "actual_execution_timing_in_scope": False,
    }

def _reconciliation_audit_payload(record) -> dict | None:
    if record is None:
        return None
    return {
        "audit_schema_version": record.audit_schema_version,
        "revision_id": record.revision_id,
        "capture_id": record.capture_id,
        "reconciliation_schema_version": record.reconciliation_schema_version,
        "reconciliation_rules_version": record.reconciliation_rules_version,
        "reconciliation_content_hash": record.reconciliation_content_hash,
        "source_content_sha256": record.source_content_sha256,
        "source_read_content_hash": record.source_read_content_hash,
        "timezone_context_name": record.timezone_context_name,
        "timezone_context_source": record.timezone_context_source,
        "reconciliation_status": record.reconciliation_status,
        "created_at": record.created_at.isoformat(),
        "audit_content_hash": record.content_hash,
    }


def _revision_payload(revision) -> dict:
    return {
        "revision_id": revision.revision_id,
        "logical_plan_id": revision.logical_plan_id,
        "athlete_id": revision.athlete_id,
        "revision_number": revision.revision_number,
        "previous_revision_id": revision.previous_revision_id,
        "origin": revision.origin.value,
        "history_claim": revision.history_claim.value,
        "authority_established_at": revision.authority_established_at.isoformat(),
        "effective_from": revision.effective_from.isoformat(),
        "created_at": revision.created_at.isoformat(),
        "contract_schema_version": revision.contract_schema_version,
        "contract_content_hash": revision.contract_content_hash,
        "revision_content_hash": revision.content_hash,
        "contract": json.loads(revision.canonical_contract_json),
        "occurrences": [
            {
                "occurrence_id": item.occurrence_id,
                "ordinal": item.ordinal,
                "lineage_kind": item.lineage_kind.value,
                "source_capture_occurrence_id": item.source_capture_occurrence_id,
            }
            for item in revision.occurrences
        ],
        "adoption_source": (
            None
            if revision.adoption_source is None
            else asdict(revision.adoption_source)
        ),
        "decision_lineage": (
            None
            if revision.decision_lineage is None
            else asdict(revision.decision_lineage)
        ),
    }


async def _owner_or_404(db: AsyncSession):
    owner_id = await _existing_owner_id(db)
    if owner_id is None:
        raise HTTPException(404, "PLAN_ADOPTION_CONFIGURED_OWNER_NOT_FOUND")
    return owner_id


async def _polar_reconciliation_for_capture(
    *,
    db: AsyncSession,
    owner_id,
    capture,
):
    if capture.source_kind != "STORED_POLAR_TARGET":
        return None
    with db.no_autoflush:
        athlete_timezone = await db.scalar(
            select(User.timezone).where(User.id == owner_id)
        )
    return build_polar_source_reconciliation(
        capture=capture,
        athlete_timezone=athlete_timezone,
    )


def _capture_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PlanReadError):
        return HTTPException(exc.status_code, {"code": exc.code})
    if isinstance(exc, CurrentAppPlanReadAdapterError):
        return HTTPException(409, {"code": str(exc)})
    return HTTPException(409, {"code": "PLAN_ADOPTION_CAPTURE_FAILED"})


@router.get("/workouts/{workout_id}/plan-adoption-preview")
async def preview_plan_adoption(
    workout_id: UUID,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"
    owner_id = await _owner_or_404(db)
    try:
        capture = await capture_current_app_plan(
            db,
            source_workout_id=str(workout_id),
            athlete_id=str(owner_id),
        )
    except (PlanReadError, CurrentAppPlanReadAdapterError, ValueError) as exc:
        raise _capture_error(exc) from None

    try:
        polar_reconciliation = await _polar_reconciliation_for_capture(
            db=db,
            owner_id=owner_id,
            capture=capture,
        )
    except PolarSourceReconciliationError:
        raise HTTPException(
            409,
            {"code": "POLAR_SOURCE_RECONCILIATION_CAPTURE_INTEGRITY_FAILED"},
        ) from None

    repository = build_production_authoritative_plan_revision_repository(db)
    audit_repository = build_production_plan_reconciliation_audit_repository(db)
    preview = await preview_with_repository(
        capture=capture,
        repository=repository,
        polar_reconciliation=polar_reconciliation,
        polar_reconciliation_audit_persistence_ready=(
            audit_repository is not None
        ),
    )
    return _preview_payload(preview)



@router.get("/workouts/{workout_id}/polar-source-reconciliation")
async def get_polar_source_reconciliation(
    workout_id: UUID,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"
    owner_id = await _owner_or_404(db)
    with db.no_autoflush:
        athlete_timezone = await db.scalar(
            select(User.timezone).where(User.id == owner_id)
        )
    if not athlete_timezone:
        raise HTTPException(
            409,
            {"code": "POLAR_SOURCE_RECONCILIATION_TIMEZONE_CONTEXT_MISSING"},
        )
    try:
        capture = await capture_current_app_plan(
            db,
            source_workout_id=str(workout_id),
            athlete_id=str(owner_id),
        )
        artifact = build_polar_source_reconciliation(
            capture=capture,
            athlete_timezone=athlete_timezone,
        )
    except PolarSourceReconciliationError:
        raise HTTPException(
            409,
            {"code": "POLAR_SOURCE_RECONCILIATION_CAPTURE_INTEGRITY_FAILED"},
        ) from None
    except (PlanReadError, CurrentAppPlanReadAdapterError, ValueError) as exc:
        raise _capture_error(exc) from None

    return _reconciliation_payload(artifact)

@router.post("/workouts/{workout_id}/plan-adoption", status_code=201)
async def adopt_plan_current_state(
    workout_id: UUID,
    payload: PlanAdoptionRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"
    owner_id = await _owner_or_404(db)
    try:
        capture = await capture_current_app_plan(
            db,
            source_workout_id=str(workout_id),
            athlete_id=str(owner_id),
        )
        polar_reconciliation = await _polar_reconciliation_for_capture(
            db=db,
            owner_id=owner_id,
            capture=capture,
        )
        repository = build_production_authoritative_plan_revision_repository(db)
        audit_repository = build_production_plan_reconciliation_audit_repository(db)
        result = await adopt_with_repository(
            capture=capture,
            expected_source_content_sha256=(
                payload.expected_source_content_sha256
            ),
            repository=repository,
            session=db,
            polar_reconciliation=polar_reconciliation,
            reconciliation_audit_repository=audit_repository,
        )
    except PolarSourceReconciliationError:
        raise HTTPException(
            409,
            {"code": "POLAR_SOURCE_RECONCILIATION_CAPTURE_INTEGRITY_FAILED"},
        ) from None
    except PlanAdoptionStalePreviewError:
        raise HTTPException(
            409,
            {"code": "PLAN_ADOPTION_STALE_PREVIEW"},
        ) from None
    except PlanAlreadyAdoptedError:
        raise HTTPException(
            409,
            {"code": "PLAN_ALREADY_AUTHORITATIVE"},
        ) from None
    except PlanAdoptionNotEligibleError as exc:
        raise HTTPException(
            409,
            {
                "code": "PLAN_ADOPTION_NOT_ELIGIBLE",
                "blockers": list(exc.blockers),
            },
        ) from None
    except AuthoritativePlanConflictError:
        raise HTTPException(
            409,
            {"code": "PLAN_ADOPTION_CONFLICT"},
        ) from None
    except PlanReconciliationAuditPersistenceError:
        raise HTTPException(
            503,
            {"code": "POLAR_RECONCILIATION_AUDIT_STORAGE_UNAVAILABLE"},
        ) from None
    except (PlanReadError, CurrentAppPlanReadAdapterError, ValueError) as exc:
        raise _capture_error(exc) from None

    return {
        "status": result.status.value,
        "identity": {
            "logical_plan_id": result.identity.logical_plan_id,
            "athlete_id": result.identity.athlete_id,
            "source_workout_id": result.identity.source_workout_id,
            "current_revision_id": result.identity.current_revision_id,
            "current_revision_number": result.identity.current_revision_number,
            "authority_established_at": (
                None
                if result.identity.authority_established_at is None
                else result.identity.authority_established_at.isoformat()
            ),
            "content_hash": result.identity.content_hash,
        },
        "revision": _revision_payload(result.revision),
        "polar_reconciliation_audit": _reconciliation_audit_payload(
            result.polar_reconciliation_audit
        ),
        "source_workout_mutated": False,
        "external_plan_id_promoted": False,
        "external_occurrence_ids_promoted": False,
    }


@router.post(
    "/workouts/{workout_id}/authoritative-plan/revisions",
    status_code=201,
)
async def create_authoritative_plan_revision(
    workout_id: UUID,
    payload: AuthoritativePlanRevisionRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"

    owner_id = await _owner_or_404(db)
    logical_plan_id = f"planned-workout:{workout_id}"

    revision_repository = (
        build_production_authoritative_plan_revision_repository(
            db
        )
    )

    identity = await revision_repository.get_plan(
        logical_plan_id=logical_plan_id
    )
    if (
        identity is None
        or identity.current_revision_id is None
        or identity.athlete_id != str(owner_id)
    ):
        raise HTTPException(
            404,
            {"code": "AUTHORITATIVE_PLAN_NOT_FOUND"},
        )

    audit_repository = (
        build_production_planning_audit_repository(db)
    )

    try:
        instruction = (
            await load_audited_plan_mutation_instruction(
                instruction_id=payload.instruction_id,
                expected_athlete_id=str(owner_id),
                expected_plan_id=logical_plan_id,
                audit_repository=audit_repository,
            )
        )

        applied = (
            await apply_authoritative_plan_revision_with_repository(
                instruction=instruction,
                revision_id=f"pt-plan-rev:{uuid4()}",
                repository=revision_repository,
                session=db,
            )
        )
    except AuditedPlanMutationInstructionNotFound:
        raise HTTPException(
            404,
            {
                "code": (
                    "PLAN_MUTATION_INSTRUCTION_NOT_FOUND"
                )
            },
        ) from None
    except AuditedPlanMutationInstructionError:
        raise HTTPException(
            409,
            {
                "code": (
                    "PLAN_MUTATION_INSTRUCTION_INVALID"
                )
            },
        ) from None
    except AuthoritativePlanRevisionNoChange:
        raise HTTPException(
            409,
            {"code": "PLAN_REVISION_NO_CHANGE"},
        ) from None
    except (
        AuthoritativePlanRevisionStaleCurrent,
        AuthoritativePlanConflictError,
    ):
        raise HTTPException(
            409,
            {"code": "PLAN_REVISION_STALE_CURRENT"},
        ) from None
    except ValueError:
        raise HTTPException(
            409,
            {"code": "PLAN_REVISION_NOT_ELIGIBLE"},
        ) from None

    return {
        "status": "authoritative_plan_revision_created",
        "identity": {
            "logical_plan_id": (
                applied.identity.logical_plan_id
            ),
            "athlete_id": applied.identity.athlete_id,
            "source_workout_id": (
                applied.identity.source_workout_id
            ),
            "current_revision_id": (
                applied.identity.current_revision_id
            ),
            "current_revision_number": (
                applied.identity.current_revision_number
            ),
            "authority_established_at": (
                None
                if applied.identity.authority_established_at
                is None
                else applied.identity.authority_established_at.isoformat()
            ),
            "content_hash": applied.identity.content_hash,
        },
        "revision": _revision_payload(applied.revision),
    }


@router.post(
    "/workouts/{workout_id}/authoritative-plan/executions/{session_id}",
    status_code=201,
)
async def link_authoritative_execution_api(
    workout_id: UUID,
    session_id: UUID,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Establish one immutable authoritative plan/execution link.

    The client supplies only resource identities. Revision identity,
    provider evidence, source hashes, and eligibility are resolved
    server-side from locked authoritative/current application state.
    """
    response.headers["Cache-Control"] = "no-store"

    owner_id = await _owner_or_404(db)
    logical_plan_id = f"planned-workout:{workout_id}"

    revision_repository = (
        build_production_authoritative_plan_revision_repository(
            db
        )
    )
    execution_link_repository = (
        build_production_authoritative_plan_execution_repository(
            db
        )
    )

    try:
        link = (
            await link_authoritative_execution_with_repository(
                athlete_id=str(owner_id),
                logical_plan_id=logical_plan_id,
                workout_session_id=str(session_id),
                revision_repository=revision_repository,
                execution_link_repository=(
                    execution_link_repository
                ),
                execution_source=(
                    CurrentAppLockedExecutionSource()
                ),
                session=db,
            )
        )
    except AuthoritativeExecutionPlanNotFound:
        raise HTTPException(
            404,
            {"code": "AUTHORITATIVE_PLAN_NOT_FOUND"},
        ) from None
    except ExecutionSourceNotFound:
        raise HTTPException(
            404,
            {"code": "EXECUTION_SOURCE_NOT_FOUND"},
        ) from None
    except PlanReadError as exc:
        raise HTTPException(
            exc.status_code,
            {"code": exc.code},
        ) from None
    except AuthoritativeExecutionLinkNotEligible:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_EXECUTION_LINK_NOT_ELIGIBLE"
                )
            },
        ) from None
    except AuthoritativeExecutionLinkConflictError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_EXECUTION_LINK_CONFLICT"
                )
            },
        ) from None
    except AuthoritativeExecutionPlanStateError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_PLAN_EXECUTION_STATE_INVALID"
                )
            },
        ) from None
    except ValueError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_EXECUTION_LINK_INVALID"
                )
            },
        ) from None

    return {
        "status": "authoritative_plan_execution_link",
        "link": {
            "link_id": link.link_id,
            "schema_version": link.schema_version,
            "athlete_id": link.athlete_id,
            "logical_plan_id": link.logical_plan_id,
            "observed_revision_id": (
                link.observed_revision_id
            ),
            "workout_session_id": (
                link.workout_session_id
            ),
            "source_workout_id": link.source_workout_id,
            "link_basis": link.link_basis.value,
            "provider_target_id": link.provider_target_id,
            "source_workout_content_hash": (
                link.source_workout_content_hash
            ),
            "session_source_content_hash": (
                link.session_source_content_hash
            ),
            "observed_revision_content_hash": (
                link.observed_revision_content_hash
            ),
            "plan_content_at_execution_status": (
                link.plan_content_at_execution_status
            ),
            "temporal_match_used": (
                link.temporal_match_used
            ),
            "created_at": link.created_at.isoformat(),
            "content_hash_algorithm": (
                link.content_hash_algorithm
            ),
            "content_hash": link.content_hash,
        },
        "claims": {
            "plan_identity_linked": True,
            "plan_content_at_execution_status": (
                link.plan_content_at_execution_status
            ),
            "occurrence_alignment_verified": False,
            "phase_alignment_verified": False,
            "temporal_match_used": (
                link.temporal_match_used
            ),
        },
        "source_workout_mutated": False,
        "workout_session_mutated": False,
        "authoritative_revision_mutated": False,
    }


@router.post(
    "/workouts/{workout_id}/authoritative-plan/"
    "executions/{session_id}/occurrences/{authoritative_occurrence_id}",
    status_code=201,
)
async def link_authoritative_occurrence_execution_api(
    workout_id: UUID,
    session_id: UUID,
    authoritative_occurrence_id: str,
    payload: AuthoritativeOccurrenceExecutionRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Confirm one authoritative occurrence against a server candidate.

    The caller selects only identities already exposed by reconciliation
    plus two explicit acknowledgements. Hashes, candidate windows,
    captured occurrence provenance, clock domain, and evidence authority
    are re-derived server-side.
    """
    response.headers["Cache-Control"] = "no-store"

    owner_id = await _owner_or_404(db)
    logical_plan_id = f"planned-workout:{workout_id}"

    revision_repository = (
        build_production_authoritative_plan_revision_repository(
            db
        )
    )
    execution_link_repository = (
        build_production_authoritative_plan_execution_repository(
            db
        )
    )
    occurrence_execution_repository = (
        build_production_authoritative_occurrence_execution_repository(
            db
        )
    )

    candidate_provider = (
        CurrentAppPhaseOccurrenceCandidateProvider(
            db,
            athlete_id=str(owner_id),
            workout_session_id=str(session_id),
        )
    )

    try:
        link = (
            await link_authoritative_occurrence_execution_with_repository(
                athlete_id=str(owner_id),
                logical_plan_id=logical_plan_id,
                workout_session_id=str(session_id),
                authoritative_occurrence_id=(
                    authoritative_occurrence_id
                ),
                hypothesis_id=payload.hypothesis_id,
                stable_source_occurrence_id=(
                    payload.stable_source_occurrence_id
                ),
                acknowledges_candidate_boundaries=(
                    payload.acknowledge_candidate_boundaries
                ),
                acknowledges_not_provider_verified=(
                    payload.acknowledge_not_provider_verified
                ),
                execution_link_repository=(
                    execution_link_repository
                ),
                revision_repository=revision_repository,
                occurrence_execution_repository=(
                    occurrence_execution_repository
                ),
                candidate_provider=candidate_provider,
                session=db,
            )
        )
    except AuthoritativeOccurrenceExecutionPlanLinkNotFound:
        raise HTTPException(
            404,
            {
                "code": (
                    "AUTHORITATIVE_PLAN_EXECUTION_LINK_NOT_FOUND"
                )
            },
        ) from None
    except CurrentPhaseOccurrenceCandidateNotFound:
        raise HTTPException(
            404,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_SESSION_NOT_FOUND"
                )
            },
        ) from None
    except PhaseReconciliationReadError as exc:
        raise HTTPException(
            exc.status_code,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_"
                    "RECONCILIATION_UNAVAILABLE"
                ),
                "blocking_reason": exc.code,
            },
        ) from None
    except PhaseOccurrenceCandidateAdapterError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_"
                    "CANDIDATE_NOT_ELIGIBLE"
                )
            },
        ) from None
    except OccurrenceExecutionNotEligible:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_"
                    "EXECUTION_NOT_ELIGIBLE"
                )
            },
        ) from None
    except OccurrenceExecutionConflictError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_"
                    "EXECUTION_CONFLICT"
                )
            },
        ) from None
    except AuthoritativeOccurrenceExecutionStateError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_"
                    "EXECUTION_STATE_INVALID"
                )
            },
        ) from None
    except ValueError:
        raise HTTPException(
            409,
            {
                "code": (
                    "AUTHORITATIVE_OCCURRENCE_"
                    "EXECUTION_INVALID"
                )
            },
        ) from None

    return {
        "status": "authoritative_occurrence_execution_link",
        "link": {
            "link_id": link.link_id,
            "schema_version": link.schema_version,
            "athlete_id": link.athlete_id,
            "plan_execution_link_id": (
                link.plan_execution_link_id
            ),
            "logical_plan_id": link.logical_plan_id,
            "observed_revision_id": (
                link.observed_revision_id
            ),
            "authoritative_occurrence_id": (
                link.authoritative_occurrence_id
            ),
            "workout_session_id": link.workout_session_id,
            "link_basis": link.link_basis.value,
            "phase_reconciliation_artifact_id": (
                link.phase_reconciliation_artifact_id
            ),
            "phase_reconciliation_rules_version": (
                link.phase_reconciliation_rules_version
            ),
            "hypothesis_id": link.hypothesis_id,
            "stable_source_occurrence_id": (
                link.stable_source_occurrence_id
            ),
            "captured_contract_occurrence_id": (
                link.captured_contract_occurrence_id
            ),
            "candidate_start_window_s": list(
                link.candidate_start_window_s
            ),
            "candidate_completion_window_s": list(
                link.candidate_completion_window_s
            ),
            "clock_domain": link.clock_domain,
            "confirmation_id": link.confirmation_id,
            "confirmation_submitted_at": (
                link.confirmation_submitted_at.isoformat()
            ),
            "occurrence_alignment_status": (
                link.occurrence_alignment_status
            ),
            "plan_content_at_execution_status": (
                link.plan_content_at_execution_status
            ),
            "provider_event_verified": (
                link.provider_event_verified
            ),
            "clock_alignment_verified": (
                link.clock_alignment_verified
            ),
            "actual_boundary_verified": (
                link.actual_boundary_verified
            ),
            "temporal_match_used": link.temporal_match_used,
            "created_at": link.created_at.isoformat(),
            "content_hash": link.content_hash,
        },
        "claims": {
            "plan_identity_linked": True,
            "occurrence_candidate_association_confirmed": True,
            "occurrence_alignment_verified": False,
            "occurrence_alignment_status": (
                link.occurrence_alignment_status
            ),
            "plan_content_at_execution_status": (
                link.plan_content_at_execution_status
            ),
            "phase_alignment_verified": False,
            "provider_event_verified": False,
            "clock_alignment_verified": False,
            "actual_boundary_verified": False,
            "temporal_match_used": False,
        },
        "source_workout_mutated": False,
        "workout_session_mutated": False,
        "authoritative_revision_mutated": False,
    }


@router.get("/workouts/{workout_id}/authoritative-plan")
async def get_authoritative_plan(
    workout_id: UUID,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response.headers["Cache-Control"] = "no-store"
    owner_id = await _owner_or_404(db)
    logical_plan_id = f"planned-workout:{workout_id}"
    repository = build_production_authoritative_plan_revision_repository(db)
    identity = await repository.get_plan(logical_plan_id=logical_plan_id)
    if identity is None or identity.current_revision_id is None:
        raise HTTPException(404, "AUTHORITATIVE_PLAN_NOT_FOUND")
    if identity.athlete_id != str(owner_id):
        # Owner-scoped API: do not disclose another athlete's plan existence.
        raise HTTPException(404, "AUTHORITATIVE_PLAN_NOT_FOUND")
    revision = await repository.get_current_revision(logical_plan_id=logical_plan_id)
    if revision is None:
        raise HTTPException(409, "AUTHORITATIVE_PLAN_POINTER_UNRESOLVED")
    audit_repository = build_production_plan_reconciliation_audit_repository(db)
    try:
        reconciliation_audit = await audit_repository.get_polar_audit(
            revision_id=revision.revision_id,
        )
    except PlanReconciliationAuditPersistenceError:
        raise HTTPException(
            503,
            {"code": "POLAR_RECONCILIATION_AUDIT_STORAGE_UNAVAILABLE"},
        ) from None
    return {
        "status": "authoritative_plan",
        "identity": {
            "logical_plan_id": identity.logical_plan_id,
            "athlete_id": identity.athlete_id,
            "source_workout_id": identity.source_workout_id,
            "current_revision_id": identity.current_revision_id,
            "current_revision_number": identity.current_revision_number,
            "authority_established_at": (
                None
                if identity.authority_established_at is None
                else identity.authority_established_at.isoformat()
            ),
            "content_hash": identity.content_hash,
        },
        "revision": _revision_payload(revision),
        "polar_reconciliation_audit": _reconciliation_audit_payload(
            reconciliation_audit
        ),
        "database_writes": 0,
        "provider_calls": 0,
    }
