from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api.routes import planning_adoption
from app.planning.application.link_authoritative_occurrence_execution import (
    AuthoritativeOccurrenceExecutionPlanLinkNotFound,
    AuthoritativeOccurrenceExecutionStateError,
)
from app.planning.domain.occurrence_execution import (
    OccurrenceExecutionConflictError,
    OccurrenceExecutionNotEligible,
)
from app.planning.infrastructure.adapters.current_phase_occurrence_candidate import (
    CurrentPhaseOccurrenceCandidateNotFound,
)
from app.planning.infrastructure.adapters.phase_occurrence_candidate import (
    PhaseOccurrenceCandidateAdapterError,
)


API_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PATH = (
    API_ROOT
    / "app"
    / "api"
    / "routes"
    / "planning_adoption.py"
)

ATHLETE_ID = UUID(
    "11111111-1111-4111-8111-111111111111"
)
WORKOUT_ID = UUID(
    "22222222-2222-4222-8222-222222222222"
)
SESSION_ID = UUID(
    "33333333-3333-4333-8333-333333333333"
)

OCCURRENCE_ID = "pt-occ:api-1"
HYPOTHESIS_ID = "phase_path_api_1"
STABLE_ID = "phase-source-occurrence_api_1"


def request():
    return planning_adoption.AuthoritativeOccurrenceExecutionRequest(
        hypothesis_id=HYPOTHESIS_ID,
        stable_source_occurrence_id=STABLE_ID,
        acknowledge_candidate_boundaries=True,
        acknowledge_not_provider_verified=True,
    )


def link():
    return SimpleNamespace(
        link_id="pt-occ-exec-link:api",
        schema_version=(
            "authoritative-occurrence-execution-link-v0.1"
        ),
        athlete_id=str(ATHLETE_ID),
        plan_execution_link_id="pt-exec-link:api",
        logical_plan_id=f"planned-workout:{WORKOUT_ID}",
        observed_revision_id="pt-plan-rev:api",
        authoritative_occurrence_id=OCCURRENCE_ID,
        workout_session_id=str(SESSION_ID),
        link_basis=SimpleNamespace(
            value="user_confirmed_candidate_segment"
        ),
        phase_reconciliation_artifact_id=(
            "phase_reconciliation_api"
        ),
        phase_reconciliation_rules_version=(
            "phase-reconciliation-0.1-draft2"
        ),
        hypothesis_id=HYPOTHESIS_ID,
        stable_source_occurrence_id=STABLE_ID,
        captured_contract_occurrence_id="capture-occ-api",
        candidate_start_window_s=(10.0, 12.0),
        candidate_completion_window_s=(70.0, 72.0),
        clock_domain="NATIVE_INDEX_CANDIDATE",
        confirmation_id="pt-occ-exec-confirmation:api",
        confirmation_submitted_at=datetime(
            2026, 10, 19, 12, 0, tzinfo=timezone.utc
        ),
        occurrence_alignment_status=(
            "user_confirmed_candidate_segment"
        ),
        plan_content_at_execution_status="unverified",
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
        temporal_match_used=False,
        created_at=datetime(
            2026, 10, 19, 12, 0, tzinfo=timezone.utc
        ),
        content_hash="d" * 64,
    )


def test_request_schema_exposes_only_selection_and_acknowledgements():
    assert set(
        planning_adoption
        .AuthoritativeOccurrenceExecutionRequest
        .model_fields
    ) == {
        "hypothesis_id",
        "stable_source_occurrence_id",
        "acknowledge_candidate_boundaries",
        "acknowledge_not_provider_verified",
    }


def test_request_schema_forbids_client_evidence_fields():
    with pytest.raises(ValidationError):
        planning_adoption.AuthoritativeOccurrenceExecutionRequest(
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_ID,
            acknowledge_candidate_boundaries=True,
            acknowledge_not_provider_verified=True,
            session_source_content_hash="a" * 64,
        )


def test_occurrence_api_uses_server_side_candidate_provider():
    source = ROUTE_PATH.read_text(encoding="utf-8")

    start = source.index(
        '@router.post(\n'
        '    "/workouts/{workout_id}/authoritative-plan/"\n'
        '    "executions/{session_id}/occurrences/'
        '{authoritative_occurrence_id}",'
    )
    end = source.index(
        '@router.get("/workouts/{workout_id}/authoritative-plan")'
    )
    endpoint = source[start:end]

    assert (
        "CurrentAppPhaseOccurrenceCandidateProvider(" in endpoint
    )
    assert (
        "build_production_authoritative_occurrence_execution_repository"
        in endpoint
    )
    assert (
        "link_authoritative_occurrence_execution_with_repository"
        in endpoint
    )

    assert "logical_plan_id=logical_plan_id" in endpoint
    assert "candidate_provider=candidate_provider" in endpoint

    # Evidence values may be returned to the client after server
    # derivation, but they must never be read from payload.
    for forbidden in (
        "payload.session_source_content_hash",
        "payload.plan_source_content_hash",
        "payload.candidate_start_window_s",
        "payload.candidate_completion_window_s",
        "payload.captured_contract_occurrence_id",
        "payload.clock_domain",
        "payload.provider_event_verified",
    ):
        assert forbidden not in endpoint


@pytest.mark.asyncio
async def test_occurrence_api_passes_only_selection_to_service(
    monkeypatch,
):
    revision_repository = object()
    execution_repository = object()
    occurrence_repository = object()
    candidate_provider = object()
    captured = {}

    async def owner(_db):
        return ATHLETE_ID

    async def link_service(**kwargs):
        captured.update(kwargs)
        return link()

    monkeypatch.setattr(
        planning_adoption,
        "_owner_or_404",
        owner,
    )
    monkeypatch.setattr(
        planning_adoption,
        "build_production_authoritative_plan_revision_repository",
        lambda db: revision_repository,
    )
    monkeypatch.setattr(
        planning_adoption,
        "build_production_authoritative_plan_execution_repository",
        lambda db: execution_repository,
    )
    monkeypatch.setattr(
        planning_adoption,
        "build_production_authoritative_occurrence_execution_repository",
        lambda db: occurrence_repository,
    )
    monkeypatch.setattr(
        planning_adoption,
        "CurrentAppPhaseOccurrenceCandidateProvider",
        lambda db, **kwargs: candidate_provider,
    )
    monkeypatch.setattr(
        planning_adoption,
        "link_authoritative_occurrence_execution_with_repository",
        link_service,
    )

    db = object()
    response = Response()

    result = (
        await planning_adoption
        .link_authoritative_occurrence_execution_api(
            workout_id=WORKOUT_ID,
            session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            payload=request(),
            response=response,
            db=db,
        )
    )

    assert captured == {
        "athlete_id": str(ATHLETE_ID),
        "logical_plan_id": f"planned-workout:{WORKOUT_ID}",
        "workout_session_id": str(SESSION_ID),
        "authoritative_occurrence_id": OCCURRENCE_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "stable_source_occurrence_id": STABLE_ID,
        "acknowledges_candidate_boundaries": True,
        "acknowledges_not_provider_verified": True,
        "execution_link_repository": execution_repository,
        "revision_repository": revision_repository,
        "occurrence_execution_repository": occurrence_repository,
        "candidate_provider": candidate_provider,
        "session": db,
    }

    assert response.headers["Cache-Control"] == "no-store"
    assert result["status"] == (
        "authoritative_occurrence_execution_link"
    )
    assert result["claims"] == {
        "plan_identity_linked": True,
        "occurrence_candidate_association_confirmed": True,
        "occurrence_alignment_verified": False,
        "occurrence_alignment_status": (
            "user_confirmed_candidate_segment"
        ),
        "plan_content_at_execution_status": "unverified",
        "phase_alignment_verified": False,
        "provider_event_verified": False,
        "clock_alignment_verified": False,
        "actual_boundary_verified": False,
        "temporal_match_used": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            AuthoritativeOccurrenceExecutionPlanLinkNotFound(),
            404,
            "AUTHORITATIVE_PLAN_EXECUTION_LINK_NOT_FOUND",
        ),
        (
            CurrentPhaseOccurrenceCandidateNotFound(),
            404,
            "AUTHORITATIVE_OCCURRENCE_SESSION_NOT_FOUND",
        ),
        (
            PhaseOccurrenceCandidateAdapterError("x"),
            409,
            "AUTHORITATIVE_OCCURRENCE_CANDIDATE_NOT_ELIGIBLE",
        ),
        (
            OccurrenceExecutionNotEligible(),
            409,
            "AUTHORITATIVE_OCCURRENCE_EXECUTION_NOT_ELIGIBLE",
        ),
        (
            OccurrenceExecutionConflictError(),
            409,
            "AUTHORITATIVE_OCCURRENCE_EXECUTION_CONFLICT",
        ),
        (
            AuthoritativeOccurrenceExecutionStateError(),
            409,
            "AUTHORITATIVE_OCCURRENCE_EXECUTION_STATE_INVALID",
        ),
        (
            ValueError(),
            409,
            "AUTHORITATIVE_OCCURRENCE_EXECUTION_INVALID",
        ),
    ],
)
async def test_occurrence_api_maps_fail_closed_errors(
    monkeypatch,
    error,
    status_code,
    code,
):
    async def owner(_db):
        return ATHLETE_ID

    async def link_service(**kwargs):
        raise error

    monkeypatch.setattr(
        planning_adoption,
        "_owner_or_404",
        owner,
    )
    monkeypatch.setattr(
        planning_adoption,
        "build_production_authoritative_plan_revision_repository",
        lambda db: object(),
    )
    monkeypatch.setattr(
        planning_adoption,
        "build_production_authoritative_plan_execution_repository",
        lambda db: object(),
    )
    monkeypatch.setattr(
        planning_adoption,
        "build_production_authoritative_occurrence_execution_repository",
        lambda db: object(),
    )
    monkeypatch.setattr(
        planning_adoption,
        "CurrentAppPhaseOccurrenceCandidateProvider",
        lambda db, **kwargs: object(),
    )
    monkeypatch.setattr(
        planning_adoption,
        "link_authoritative_occurrence_execution_with_repository",
        link_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await planning_adoption.link_authoritative_occurrence_execution_api(
            workout_id=WORKOUT_ID,
            session_id=SESSION_ID,
            authoritative_occurrence_id=OCCURRENCE_ID,
            payload=request(),
            response=Response(),
            db=object(),
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail["code"] == code
