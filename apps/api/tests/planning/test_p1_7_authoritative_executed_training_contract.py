from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
    build_authoritative_executed_training_evidence,
)
from app.planning.domain.occurrence_execution import (
    OccurrenceExecutionLinkBasis,
)


UTC = timezone.utc

ATHLETE_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_WORKOUT_ID = "33333333-3333-4333-8333-333333333333"

LOGICAL_PLAN_ID = f"planned-workout:{SOURCE_WORKOUT_ID}"
REVISION_ID = "pt-plan-rev:observed"
PLAN_LINK_ID = "pt-exec-link:observed"

OBSERVED_AT = datetime(
    2026, 10, 19, 12, 0, tzinfo=UTC
)
PLAN_LINK_CREATED_AT = datetime(
    2026, 10, 19, 13, 0, tzinfo=UTC
)
OCCURRENCE_LINK_CREATED_AT = datetime(
    2026, 10, 19, 13, 5, tzinfo=UTC
)
CREATED_AT = datetime(
    2026, 10, 19, 13, 10, tzinfo=UTC
)

PLAN_HASH = "a" * 64
SESSION_HASH = "b" * 64
REVISION_HASH = "c" * 64
PLAN_LINK_HASH = "d" * 64


def plan_link(*, valid_hash=True, temporal_match_used=False):
    return SimpleNamespace(
        link_id=PLAN_LINK_ID,
        athlete_id=ATHLETE_ID,
        logical_plan_id=LOGICAL_PLAN_ID,
        observed_revision_id=REVISION_ID,
        workout_session_id=SESSION_ID,
        source_workout_id=SOURCE_WORKOUT_ID,
        link_basis=SimpleNamespace(
            value="exact_provider_id"
        ),
        provider_target_id="provider-target-1",
        source_workout_content_hash=PLAN_HASH,
        session_source_content_hash=SESSION_HASH,
        observed_revision_content_hash=REVISION_HASH,
        plan_content_at_execution_status="unverified",
        temporal_match_used=temporal_match_used,
        created_at=PLAN_LINK_CREATED_AT,
        content_hash=PLAN_LINK_HASH,
        verify_content_hash=lambda: valid_hash,
    )


def occurrence_link(
    *,
    occurrence_id="pt-occ:1",
    link_id="pt-occ-exec-link:1",
    stable_id="phase-source-occurrence_1",
    content_hash="e" * 64,
    plan_execution_link_id=PLAN_LINK_ID,
    session_source_content_hash=SESSION_HASH,
    plan_source_content_hash=PLAN_HASH,
    provider_event_verified=False,
    clock_alignment_verified=False,
    actual_boundary_verified=False,
    temporal_match_used=False,
):
    return SimpleNamespace(
        link_id=link_id,
        athlete_id=ATHLETE_ID,
        plan_execution_link_id=plan_execution_link_id,
        logical_plan_id=LOGICAL_PLAN_ID,
        observed_revision_id=REVISION_ID,
        authoritative_occurrence_id=occurrence_id,
        workout_session_id=SESSION_ID,
        link_basis=(
            OccurrenceExecutionLinkBasis
            .USER_CONFIRMED_CANDIDATE_SEGMENT
        ),
        phase_reconciliation_artifact_id=(
            f"phase_reconciliation_{occurrence_id}"
        ),
        phase_reconciliation_rules_version=(
            "phase-reconciliation-0.1-draft2"
        ),
        session_source_content_hash=(
            session_source_content_hash
        ),
        plan_source_content_hash=(
            plan_source_content_hash
        ),
        stable_source_occurrence_id=stable_id,
        captured_contract_occurrence_id=(
            f"capture-{occurrence_id}"
        ),
        hypothesis_id=f"phase_path_{occurrence_id}",
        candidate_start_window_s=(10.0, 12.0),
        candidate_completion_window_s=(70.0, 72.0),
        clock_domain="NATIVE_INDEX_CANDIDATE",
        confirmation_id=(
            f"pt-occ-exec-confirmation:{occurrence_id}"
        ),
        confirmation_submitted_at=(
            OCCURRENCE_LINK_CREATED_AT
        ),
        occurrence_alignment_status=(
            "user_confirmed_candidate_segment"
        ),
        plan_content_at_execution_status="unverified",
        provider_event_verified=provider_event_verified,
        clock_alignment_verified=clock_alignment_verified,
        actual_boundary_verified=actual_boundary_verified,
        temporal_match_used=temporal_match_used,
        created_at=OCCURRENCE_LINK_CREATED_AT,
        content_hash=content_hash,
        verify_content_hash=lambda: True,
    )


def build(*, occurrences=(), artifact_id="pt-executed-training-evidence:1"):
    return build_authoritative_executed_training_evidence(
        artifact_id=artifact_id,
        plan_execution_link=plan_link(),
        occurrence_execution_links=tuple(occurrences),
        observed_at=OBSERVED_AT,
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        created_at=CREATED_AT,
    )


def test_session_level_authority_does_not_require_occurrence_mapping():
    evidence = build()

    assert evidence.schema_version == (
        AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
    )
    assert evidence.plan_identity_linked is True
    assert evidence.logical_plan_id == LOGICAL_PLAN_ID
    assert evidence.observed_revision_id == REVISION_ID

    # Missing occurrence association remains missing/unknown.
    assert evidence.occurrence_associations == ()

    assert evidence.occurrence_alignment_verified is False
    assert evidence.phase_alignment_verified is False
    assert evidence.provider_event_verified is False
    assert evidence.clock_alignment_verified is False
    assert evidence.actual_boundary_verified is False
    assert evidence.temporal_match_used is False

    assert evidence.duration_status == KnowledgeStatus.KNOWN
    assert evidence.duration_s == 3600
    assert evidence.verify_content_hash() is True


def test_user_confirmed_occurrence_is_preserved_without_stronger_claim():
    evidence = build(
        occurrences=(occurrence_link(),)
    )

    assert len(evidence.occurrence_associations) == 1
    association = evidence.occurrence_associations[0]

    assert association.authoritative_occurrence_id == "pt-occ:1"
    assert association.link_basis == (
        "user_confirmed_candidate_segment"
    )
    assert association.occurrence_alignment_status == (
        "user_confirmed_candidate_segment"
    )

    assert association.provider_event_verified is False
    assert association.clock_alignment_verified is False
    assert association.actual_boundary_verified is False
    assert association.temporal_match_used is False

    # Even an explicit user association is not promoted to verified
    # actual occurrence/phase alignment.
    assert evidence.occurrence_alignment_verified is False
    assert evidence.phase_alignment_verified is False


def test_occurrence_must_belong_to_same_plan_execution_link():
    with pytest.raises(
        ValueError,
        match="another plan execution link",
    ):
        build(
            occurrences=(
                occurrence_link(
                    plan_execution_link_id=(
                        "pt-exec-link:different"
                    )
                ),
            )
        )


@pytest.mark.parametrize(
    "field",
    [
        "provider_event_verified",
        "clock_alignment_verified",
        "actual_boundary_verified",
        "temporal_match_used",
    ],
)
def test_stronger_occurrence_claims_fail_closed(field):
    kwargs = {field: True}

    with pytest.raises(
        ValueError,
        match="stronger execution claim",
    ):
        build(
            occurrences=(
                occurrence_link(**kwargs),
            )
        )


def test_duplicate_authoritative_occurrence_fails_closed():
    with pytest.raises(
        ValueError,
        match="Duplicate authoritative occurrence",
    ):
        build(
            occurrences=(
                occurrence_link(
                    link_id="pt-occ-exec-link:a",
                    content_hash="e" * 64,
                ),
                occurrence_link(
                    link_id="pt-occ-exec-link:b",
                    stable_id="phase-source-occurrence_2",
                    content_hash="f" * 64,
                ),
            )
        )


def test_known_duration_requires_real_non_negative_value():
    with pytest.raises(
        ValueError,
        match="Known duration requires",
    ):
        build_authoritative_executed_training_evidence(
            artifact_id="pt-executed-training-evidence:duration",
            plan_execution_link=plan_link(),
            observed_at=OBSERVED_AT,
            modality_key="RUNNING",
            duration_status=KnowledgeStatus.KNOWN,
            duration_s=None,
            created_at=CREATED_AT,
        )


def test_temporal_matching_cannot_be_promoted_into_evidence():
    with pytest.raises(
        ValueError,
        match="Temporal proximity",
    ):
        build_authoritative_executed_training_evidence(
            artifact_id="pt-executed-training-evidence:temporal",
            plan_execution_link=plan_link(
                temporal_match_used=True
            ),
            observed_at=OBSERVED_AT,
            modality_key="RUNNING",
            duration_status=KnowledgeStatus.KNOWN,
            duration_s=3600,
            created_at=CREATED_AT,
        )


def test_association_order_does_not_change_semantic_hash():
    first = occurrence_link(
        occurrence_id="pt-occ:1",
        link_id="pt-occ-exec-link:1",
        stable_id="phase-source-occurrence_1",
        content_hash="e" * 64,
    )
    second = occurrence_link(
        occurrence_id="pt-occ:2",
        link_id="pt-occ-exec-link:2",
        stable_id="phase-source-occurrence_2",
        content_hash="f" * 64,
    )

    one = build(
        occurrences=(first, second),
        artifact_id="pt-executed-training-evidence:a",
    )

    two = build_authoritative_executed_training_evidence(
        artifact_id="pt-executed-training-evidence:b",
        plan_execution_link=plan_link(),
        occurrence_execution_links=(second, first),
        observed_at=OBSERVED_AT,
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert one.content_hash == two.content_hash
    assert one.verify_content_hash() is True
    assert two.verify_content_hash() is True
