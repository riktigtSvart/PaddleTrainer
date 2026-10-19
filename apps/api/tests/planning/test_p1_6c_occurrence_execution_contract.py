from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.planning.domain.execution_link import (
    ExecutionLinkBasis,
    finalize_authoritative_plan_execution_link,
)
from app.planning.domain.occurrence_execution import (
    OccurrenceExecutionCandidateEvidence,
    OccurrenceExecutionConfirmation,
    OccurrenceExecutionLinkBasis,
    OccurrenceExecutionNotEligible,
    finalize_authoritative_occurrence_execution_link,
)
from app.planning.domain.plan_revision.persistence_contract import (
    AdoptionSourceRef,
    OccurrenceLineageKind,
    PlanHistoryClaim,
    PlanRevisionOrigin,
    RevisionOccurrence,
    finalize_authoritative_plan_revision,
)


UTC = timezone.utc
ATHLETE_ID = str(uuid4())
SOURCE_ID = str(uuid4())
SESSION_ID = str(uuid4())
LOGICAL_PLAN_ID = f"planned-workout:{SOURCE_ID}"

REVISION_ID = "pt-plan-rev:p1-6c-observed"
OCCURRENCE_ID = "pt-occ:p1-6c-1"
CAPTURE_OCCURRENCE_ID = "occ_capture_p1_6c_1"


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        19,
        hour,
        tzinfo=UTC,
    )


def revision(
    *,
    source_capture_occurrence_id=(
        CAPTURE_OCCURRENCE_ID
    ),
):
    return finalize_authoritative_plan_revision(
        revision_id=REVISION_ID,
        logical_plan_id=LOGICAL_PLAN_ID,
        athlete_id=ATHLETE_ID,
        revision_number=1,
        previous_revision_id=None,
        origin=PlanRevisionOrigin.ADOPTED_CURRENT_STATE,
        history_claim=(
            PlanHistoryClaim.CURRENT_STATE_BASELINE_ONLY
        ),
        authority_established_at=dt(8),
        effective_from=dt(8),
        created_at=dt(8),
        contract_schema_version="0.1",
        contract_json="{}",
        occurrences=(
            RevisionOccurrence(
                occurrence_id=OCCURRENCE_ID,
                ordinal=0,
                lineage_kind=OccurrenceLineageKind.NEW,
                source_capture_occurrence_id=(
                    source_capture_occurrence_id
                ),
            ),
        ),
        adoption_source=AdoptionSourceRef(
            capture_id="capture-p1-6c",
            capture_content_hash="1" * 64,
            source_read_content_hash="2" * 64,
            source_content_sha256="3" * 64,
            external_contract_plan_id=(
                "polar-plan-p1-6c"
            ),
            external_contract_plan_revision=1,
        ),
        decision_lineage=None,
    )


def plan_execution_link(
    observed_revision,
    *,
    observed_revision_id=None,
):
    return finalize_authoritative_plan_execution_link(
        link_id="pt-exec-link:p1-6c",
        athlete_id=ATHLETE_ID,
        logical_plan_id=LOGICAL_PLAN_ID,
        observed_revision_id=(
            observed_revision_id
            or observed_revision.revision_id
        ),
        workout_session_id=SESSION_ID,
        source_workout_id=SOURCE_ID,
        link_basis=ExecutionLinkBasis.EXACT_PROVIDER_ID,
        provider_target_id="polar-target-p1-6c",
        source_workout_content_hash="a" * 64,
        session_source_content_hash="b" * 64,
        observed_revision_content_hash=(
            observed_revision.content_hash
        ),
        created_at=dt(12),
    )


def candidate(
    *,
    session_hash="b" * 64,
    plan_hash="a" * 64,
    captured_contract_occurrence_id=(
        CAPTURE_OCCURRENCE_ID
    ),
):
    return OccurrenceExecutionCandidateEvidence(
        phase_reconciliation_artifact_id=(
            "phase_reconciliation_" + "c" * 64
        ),
        phase_reconciliation_rules_version=(
            "phase-reconciliation-0.1-draft2"
        ),
        session_source_content_hash=session_hash,
        plan_source_content_hash=plan_hash,
        stable_source_occurrence_id=(
            "phase-source-occurrence_" + "d" * 64
        ),
        captured_contract_occurrence_id=(
            captured_contract_occurrence_id
        ),
        hypothesis_id="phase_path_" + "e" * 64,
        candidate_start_window_s=(10.0, 12.0),
        candidate_completion_window_s=(70.0, 72.0),
        clock_domain="NATIVE_INDEX_CANDIDATE",
    )


def confirmation(
    candidate_evidence,
    *,
    acknowledge_boundaries=True,
    acknowledge_provider_limit=True,
):
    return OccurrenceExecutionConfirmation(
        confirmation_id=(
            "pt-occ-exec-confirmation:p1-6c"
        ),
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
        authoritative_occurrence_id=OCCURRENCE_ID,
        phase_reconciliation_artifact_id=(
            candidate_evidence
            .phase_reconciliation_artifact_id
        ),
        hypothesis_id=(
            candidate_evidence.hypothesis_id
        ),
        stable_source_occurrence_id=(
            candidate_evidence
            .stable_source_occurrence_id
        ),
        submitted_at=dt(13),
        acknowledges_candidate_boundaries=(
            acknowledge_boundaries
        ),
        acknowledges_not_provider_verified=(
            acknowledge_provider_limit
        ),
    )


def finalize(
    observed_revision,
    candidate_evidence,
    explicit_confirmation,
    *,
    execution_link=None,
):
    return (
        finalize_authoritative_occurrence_execution_link(
            link_id="pt-occ-exec-link:p1-6c",
            plan_execution_link=(
                execution_link
                or plan_execution_link(
                    observed_revision
                )
            ),
            observed_revision=observed_revision,
            candidate=candidate_evidence,
            confirmation=explicit_confirmation,
            created_at=dt(14),
        )
    )


def test_explicit_user_confirmation_creates_bounded_link():
    observed = revision()
    evidence = candidate()

    result = finalize(
        observed,
        evidence,
        confirmation(evidence),
    )

    assert (
        result.link_basis
        == OccurrenceExecutionLinkBasis
        .USER_CONFIRMED_CANDIDATE_SEGMENT
    )
    assert (
        result.authoritative_occurrence_id
        == OCCURRENCE_ID
    )
    assert (
        result.observed_revision_id
        == REVISION_ID
    )
    assert (
        result.captured_contract_occurrence_id
        == CAPTURE_OCCURRENCE_ID
    )
    assert result.occurrence_alignment_status == (
        "user_confirmed_candidate_segment"
    )

    # P1.6C confirmation is deliberately narrower than
    # provider/boundary verification.
    assert result.provider_event_verified is False
    assert result.clock_alignment_verified is False
    assert result.actual_boundary_verified is False
    assert result.temporal_match_used is False

    # P1.6C must not strengthen the historical-plan claim.
    assert (
        result.plan_content_at_execution_status
        == "unverified"
    )
    assert result.verify_content_hash()


def test_candidate_without_explicit_confirmation_fails_closed():
    observed = revision()
    evidence = candidate()

    with pytest.raises(
        OccurrenceExecutionNotEligible,
        match="Explicit occurrence execution confirmation",
    ):
        finalize(
            observed,
            evidence,
            None,
        )


def test_must_use_revision_frozen_by_session_execution_link():
    observed = revision()
    evidence = candidate()
    mismatched_link = plan_execution_link(
        observed,
        observed_revision_id="pt-plan-rev:later",
    )

    with pytest.raises(
        OccurrenceExecutionNotEligible,
        match="revision frozen",
    ):
        finalize(
            observed,
            evidence,
            confirmation(evidence),
            execution_link=mismatched_link,
        )


def test_session_source_drift_blocks_occurrence_promotion():
    observed = revision()
    evidence = candidate(
        session_hash="f" * 64,
    )

    with pytest.raises(
        OccurrenceExecutionNotEligible,
        match="Session source changed",
    ):
        finalize(
            observed,
            evidence,
            confirmation(evidence),
        )


def test_source_capture_occurrence_mapping_must_match():
    observed = revision(
        source_capture_occurrence_id=(
            "different-source-occurrence"
        )
    )
    evidence = candidate()

    with pytest.raises(
        OccurrenceExecutionNotEligible,
        match="does not map",
    ):
        finalize(
            observed,
            evidence,
            confirmation(evidence),
        )


def test_confirmation_must_acknowledge_candidate_limits():
    observed = revision()
    evidence = candidate()

    with pytest.raises(
        OccurrenceExecutionNotEligible,
        match="Candidate-boundary acknowledgement",
    ):
        finalize(
            observed,
            evidence,
            confirmation(
                evidence,
                acknowledge_boundaries=False,
            ),
        )

    with pytest.raises(
        OccurrenceExecutionNotEligible,
        match="Non-provider-verification acknowledgement",
    ):
        finalize(
            observed,
            evidence,
            confirmation(
                evidence,
                acknowledge_provider_limit=False,
            ),
        )


def test_candidate_cannot_claim_provider_or_boundary_verification():
    with pytest.raises(
        ValueError,
        match="cannot claim provider",
    ):
        OccurrenceExecutionCandidateEvidence(
            phase_reconciliation_artifact_id=(
                "phase_reconciliation_" + "c" * 64
            ),
            phase_reconciliation_rules_version=(
                "phase-reconciliation-0.1-draft2"
            ),
            session_source_content_hash="b" * 64,
            plan_source_content_hash="a" * 64,
            stable_source_occurrence_id=(
                "phase-source-occurrence_" + "d" * 64
            ),
            captured_contract_occurrence_id=(
                CAPTURE_OCCURRENCE_ID
            ),
            hypothesis_id="phase_path_" + "e" * 64,
            candidate_start_window_s=(10.0, 12.0),
            candidate_completion_window_s=(70.0, 72.0),
            clock_domain="NATIVE_INDEX_CANDIDATE",
            provider_event_verified=True,
        )
