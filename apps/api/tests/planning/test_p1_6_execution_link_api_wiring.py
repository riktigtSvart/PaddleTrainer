from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException, Response

from app.api.routes import planning_adoption
from app.planning.application.link_authoritative_execution import (
    AuthoritativeExecutionPlanNotFound,
    AuthoritativeExecutionPlanStateError,
)
from app.planning.domain.execution_link import (
    AuthoritativeExecutionLinkConflictError,
    AuthoritativeExecutionLinkNotEligible,
)
from app.planning.ports.execution_source import (
    ExecutionSourceNotFound,
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


def test_execution_link_api_is_identity_only_server_trust_boundary():
    source = ROUTE_PATH.read_text(encoding="utf-8")

    start = source.index(
        '@router.post(\n'
        '    "/workouts/{workout_id}/authoritative-plan/'
        'executions/{session_id}",'
    )
    end = source.index(
        '@router.post(\n'
        '    "/workouts/{workout_id}/authoritative-plan/"\n'
        '    "executions/{session_id}/occurrences/'
        '{authoritative_occurrence_id}",'
    )
    endpoint = source[start:end]

    assert "payload:" not in endpoint
    assert "workout_id: UUID" in endpoint
    assert "session_id: UUID" in endpoint

    assert (
        "build_production_authoritative_plan_revision_repository"
        in endpoint
    )
    assert (
        "build_production_authoritative_plan_execution_repository"
        in endpoint
    )
    assert "CurrentAppLockedExecutionSource()" in endpoint
    assert (
        "link_authoritative_execution_with_repository"
        in endpoint
    )

    # These inputs must be derived server-side, never accepted from
    # a client request body.
    assert "expected_current_revision_id" not in endpoint
    assert "expected_source_content_sha256" not in endpoint
    assert "instruction_id" not in endpoint


@pytest.mark.asyncio
async def test_execution_link_api_passes_only_server_resolved_state(
    monkeypatch,
):
    revision_repository = object()
    link_repository = object()
    execution_source = object()
    captured = {}

    async def owner(_db):
        return ATHLETE_ID

    async def link_service(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            link_id="pt-exec-link:api-test",
            schema_version=(
                "authoritative-plan-execution-link-v0.1"
            ),
            athlete_id=str(ATHLETE_ID),
            logical_plan_id=(
                f"planned-workout:{WORKOUT_ID}"
            ),
            observed_revision_id="pt-plan-rev:observed",
            workout_session_id=str(SESSION_ID),
            source_workout_id=str(WORKOUT_ID),
            link_basis=SimpleNamespace(
                value="exact_provider_id"
            ),
            provider_target_id="target-1",
            source_workout_content_hash="a" * 64,
            session_source_content_hash="b" * 64,
            observed_revision_content_hash="c" * 64,
            plan_content_at_execution_status="unverified",
            temporal_match_used=False,
            created_at=datetime(
                2026,
                10,
                19,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            content_hash_algorithm="sha256",
            content_hash="d" * 64,
        )

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
        lambda db: link_repository,
    )
    monkeypatch.setattr(
        planning_adoption,
        "CurrentAppLockedExecutionSource",
        lambda: execution_source,
    )
    monkeypatch.setattr(
        planning_adoption,
        "link_authoritative_execution_with_repository",
        link_service,
    )

    db = object()
    response = Response()

    result = await planning_adoption.link_authoritative_execution_api(
        workout_id=WORKOUT_ID,
        session_id=SESSION_ID,
        response=response,
        db=db,
    )

    assert captured == {
        "athlete_id": str(ATHLETE_ID),
        "logical_plan_id": (
            f"planned-workout:{WORKOUT_ID}"
        ),
        "workout_session_id": str(SESSION_ID),
        "revision_repository": revision_repository,
        "execution_link_repository": link_repository,
        "execution_source": execution_source,
        "session": db,
    }

    assert result["status"] == (
        "authoritative_plan_execution_link"
    )
    assert result["link"]["link_basis"] == (
        "exact_provider_id"
    )
    assert result["link"]["provider_target_id"] == (
        "target-1"
    )
    assert (
        result["link"]["plan_content_at_execution_status"]
        == "unverified"
    )
    assert result["claims"] == {
        "plan_identity_linked": True,
        "plan_content_at_execution_status": "unverified",
        "occurrence_alignment_verified": False,
        "phase_alignment_verified": False,
        "temporal_match_used": False,
    }
    assert result["source_workout_mutated"] is False
    assert result["workout_session_mutated"] is False
    assert result["authoritative_revision_mutated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            AuthoritativeExecutionPlanNotFound(),
            404,
            "AUTHORITATIVE_PLAN_NOT_FOUND",
        ),
        (
            ExecutionSourceNotFound(),
            404,
            "EXECUTION_SOURCE_NOT_FOUND",
        ),
        (
            AuthoritativeExecutionLinkNotEligible(),
            409,
            "AUTHORITATIVE_EXECUTION_LINK_NOT_ELIGIBLE",
        ),
        (
            AuthoritativeExecutionLinkConflictError(),
            409,
            "AUTHORITATIVE_EXECUTION_LINK_CONFLICT",
        ),
        (
            AuthoritativeExecutionPlanStateError(),
            409,
            "AUTHORITATIVE_PLAN_EXECUTION_STATE_INVALID",
        ),
        (
            ValueError(),
            409,
            "AUTHORITATIVE_EXECUTION_LINK_INVALID",
        ),
    ],
)
async def test_execution_link_api_maps_fail_closed_errors(
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
        "CurrentAppLockedExecutionSource",
        lambda: object(),
    )
    monkeypatch.setattr(
        planning_adoption,
        "link_authoritative_execution_with_repository",
        link_service,
    )

    with pytest.raises(HTTPException) as caught:
        await planning_adoption.link_authoritative_execution_api(
            workout_id=WORKOUT_ID,
            session_id=SESSION_ID,
            response=Response(),
            db=object(),
        )

    assert caught.value.status_code == status_code
    assert caught.value.detail == {"code": code}
