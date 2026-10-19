from datetime import datetime, timezone

import pytest

from app.planning.domain.execution_link import (
    AuthoritativeExecutionLinkNotEligible,
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
    resolve_execution_link_basis,
)


ATHLETE_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
WORKOUT_ID = "33333333-3333-4333-8333-333333333333"


def _session(
    *,
    stored_plan=WORKOUT_ID,
    link_source=None,
    target_id="polar-target-1",
):
    return {
        "id": SESSION_ID,
        "user_id": ATHLETE_ID,
        "planned_workout_id": stored_plan,
        "planned_workout_link_source": link_source,
        "external_provider": "POLAR",
        "external_id": "polar-session-1",
        "sport": "RUNNING",
        # Deliberately unrelated to planned clock.
        "started_at": "2026-10-19T18:47:00+00:00",
        "raw_data": {
            "trainingTarget": (
                {}
                if target_id is None
                else {"id": target_id}
            )
        },
    }


def _workout(*, target_id="polar-target-1"):
    return {
        "id": WORKOUT_ID,
        "user_id": ATHLETE_ID,
        "sport": "RUNNING",
        "source": "POLAR",
        "polar_target_id": target_id,
        # Deliberately unrelated to actual clock.
        "planned_start_time": "2026-10-19T06:00:00+00:00",
    }


def test_exact_provider_identity_is_authoritative_without_time_matching():
    basis, provider_id = resolve_execution_link_basis(
        session_snapshot=_session(),
        source_workout_snapshot=_workout(),
    )

    assert basis == ExecutionLinkBasis.EXACT_PROVIDER_ID
    assert provider_id == "polar-target-1"


def test_explicit_manual_confirmation_is_authoritative():
    basis, provider_id = resolve_execution_link_basis(
        session_snapshot=_session(
            link_source="MANUAL_CONFIRMED",
            target_id=None,
        ),
        source_workout_snapshot=_workout(target_id=None),
    )

    assert basis == ExecutionLinkBasis.MANUAL_CONFIRMED
    assert provider_id is None


def test_auto_matched_stored_link_is_not_authoritative():
    with pytest.raises(AuthoritativeExecutionLinkNotEligible):
        resolve_execution_link_basis(
            session_snapshot=_session(
                link_source="AUTO_MATCHED",
                target_id=None,
            ),
            source_workout_snapshot=_workout(target_id=None),
        )


def test_stored_link_without_provenance_is_not_authoritative():
    with pytest.raises(AuthoritativeExecutionLinkNotEligible):
        resolve_execution_link_basis(
            session_snapshot=_session(target_id=None),
            source_workout_snapshot=_workout(target_id=None),
        )


def test_provider_target_conflict_is_rejected_even_with_stored_link():
    with pytest.raises(
        AuthoritativeExecutionLinkNotEligible,
        match="Provider target identity conflicts",
    ):
        resolve_execution_link_basis(
            session_snapshot=_session(target_id="different"),
            source_workout_snapshot=_workout(),
        )


def test_finalized_link_is_hash_verified_and_explicitly_non_temporal():
    link = finalize_authoritative_plan_execution_link(
        link_id="pt-exec-link:test-1",
        athlete_id=ATHLETE_ID,
        logical_plan_id=f"planned-workout:{WORKOUT_ID}",
        observed_revision_id="pt-plan-rev:test-1",
        workout_session_id=SESSION_ID,
        source_workout_id=WORKOUT_ID,
        link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
        provider_target_id="polar-target-1",
        source_workout_content_hash="a" * 64,
        session_source_content_hash="b" * 64,
        observed_revision_content_hash="c" * 64,
        created_at=datetime(
            2026, 10, 19, 12, 0, tzinfo=timezone.utc
        ),
    )

    assert link.verify_content_hash()
    assert link.temporal_match_used is False
    assert link.plan_content_at_execution_status == "unverified"
