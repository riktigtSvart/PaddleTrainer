from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.application.assemble_training_dynamics import (
    assemble_observed_response_association,
    assemble_realized_training_stimulus,
)
from app.planning.application.project_authoritative_training_response import (
    project_authoritative_training_response_evidence,
)
from app.planning.domain.common.enums import (
    KnowledgeStatus,
    ProvenanceKind,
)
from app.planning.domain.common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    create_evidence_item,
)
from app.planning.domain.executed_training import (
    AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION,
    AuthoritativeExecutedTrainingEvidence,
)
from app.planning.domain.executed_training.models import (
    AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS,
)
from app.planning.domain.response_evidence import (
    TrainingResponseKind,
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
    build_authoritative_training_response_evidence,
)
from app.planning.domain.training_dynamics import (
    ExposureReferenceEndBasis,
    ResponseIsolationStatus,
)
from app.planning.domain.training_state.evidence import (
    SESSION_FEEDBACK,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
OTHER_ATHLETE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

SESSION = "22222222-2222-4222-8222-222222222222"
OTHER_SESSION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

RESPONSE_SOURCE_ID = "33333333-3333-4333-8333-333333333333"


def dt(
    hour: int,
    minute: int = 0,
) -> datetime:
    return datetime(
        2026,
        10,
        20,
        hour,
        minute,
        tzinfo=UTC,
    )


def executed_artifact(
    *,
    athlete_id: str = ATHLETE,
    session_id: str = SESSION,
    observed_at: datetime | None = None,
    duration_status: KnowledgeStatus = KnowledgeStatus.KNOWN,
    duration_s: int | None = 3600,
    actual_boundary_verified: bool = False,
):
    observed = observed_at or dt(8)

    provisional = AuthoritativeExecutedTrainingEvidence(
        artifact_id=(
            "pt-executed-training-evidence:"
            f"session:{session_id}"
        ),
        schema_version=(
            AUTHORITATIVE_EXECUTED_TRAINING_SCHEMA_VERSION
        ),
        athlete_id=athlete_id,
        workout_session_id=session_id,
        observed_at=observed,
        modality_key="RUNNING",
        duration_status=duration_status,
        duration_s=duration_s,
        plan_execution_link_id=(
            f"pt-exec-link:{session_id}"
        ),
        plan_execution_link_content_hash="1" * 64,
        logical_plan_id=f"logical-plan:{session_id}",
        observed_revision_id=f"revision:{session_id}",
        observed_revision_content_hash="2" * 64,
        source_workout_id=f"source-workout:{session_id}",
        source_workout_content_hash="3" * 64,
        session_source_content_hash="4" * 64,
        execution_link_basis="exact_provider_id",
        provider_target_id=None,
        plan_identity_linked=True,
        plan_content_at_execution_status="unverified",
        occurrence_associations=(),
        occurrence_alignment_verified=False,
        phase_alignment_verified=False,
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=actual_boundary_verified,
        temporal_match_used=False,
        created_at=dt(10),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            AUTHORITATIVE_EXECUTED_TRAINING_HASH_EXCLUDE_FIELDS
        ),
    )

    return AuthoritativeExecutedTrainingEvidence(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )


def stimulus(
    *,
    source=None,
    created_at=None,
):
    return assemble_realized_training_stimulus(
        source or executed_artifact(),
        created_at=created_at or dt(11),
    )


def response_evidence(
    *,
    source_execution=None,
):
    execution = source_execution or executed_artifact()

    authoritative = build_authoritative_training_response_evidence(
        artifact_id=(
            "pt-training-response-evidence:"
            f"athlete-response:{RESPONSE_SOURCE_ID}"
        ),
        athlete_id=execution.athlete_id,
        workout_session_id=execution.workout_session_id,
        executed_training_evidence_id=execution.artifact_id,
        executed_training_evidence_hash=execution.content_hash,
        response_kind=TrainingResponseKind.SESSION_FEEDBACK,
        response_timing=TrainingResponseTiming.SAME_DAY,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        observed_at=dt(14),
        available_at=dt(14, 30),
        source_system="current_app_athlete_response",
        source_record_id=RESPONSE_SOURCE_ID,
        source_record_version=(
            "current-app-athlete-response-source-v0.1"
        ),
        source_content_hash="5" * 64,
        provenance=ProvenanceKind.SOURCE,
        quality=EvidenceQuality.MODERATE,
        measurements=(
            TrainingResponseMeasurement(
                metric_key="self_reported_fatigue_score",
                knowledge_status=KnowledgeStatus.KNOWN,
                value=6.0,
                unit=None,
            ),
        ),
        created_at=dt(15),
    )

    return project_authoritative_training_response_evidence(
        authoritative,
        created_at=dt(16),
    )


def rebuild_evidence(
    item,
    *,
    athlete_id=None,
    payload=None,
):
    return create_evidence_item(
        evidence_id=item.evidence_id,
        athlete_id=athlete_id or item.athlete_id,
        evidence_type=item.evidence_type,
        observed_at=item.observed_at,
        available_at=item.available_at,
        created_at=item.created_at,
        source_ref=item.source_ref,
        provenance=item.provenance,
        knowledge_status=item.knowledge_status,
        quality=item.quality,
        payload=payload or dict(item.payload),
    )


def test_execution_artifact_assembles_realized_stimulus_without_authority_upgrade():
    source = executed_artifact()

    item = stimulus(source=source)

    assert item.athlete_id == ATHLETE
    assert item.workout_session_id == SESSION

    assert (
        item.executed_training_evidence_id
        == source.artifact_id
    )
    assert (
        item.executed_training_evidence_hash
        == source.content_hash
    )

    assert item.exposure_observed_at == dt(8)
    assert item.duration_status == KnowledgeStatus.KNOWN
    assert item.duration_s == 3600

    assert item.reference_end_at == dt(9)
    assert (
        item.reference_end_basis
        == ExposureReferenceEndBasis
        .OBSERVED_AT_PLUS_KNOWN_DURATION
    )

    assert item.features == ()

    assert item.actual_start_boundary_verified is False
    assert item.actual_end_boundary_verified is False
    assert item.causal_effect_established is False
    assert item.planning_authorized is False

    assert item.verify_content_hash()


def test_stimulus_identity_and_hash_are_stable_across_retry_created_at():
    source = executed_artifact()

    first = stimulus(
        source=source,
        created_at=dt(11),
    )

    second = stimulus(
        source=source,
        created_at=dt(12),
    )

    assert first.stimulus_id == second.stimulus_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at


def test_stimulus_rejects_invalid_authoritative_hash():
    source = replace(
        executed_artifact(),
        content_hash="f" * 64,
    )

    with pytest.raises(
        ValueError,
        match="hash",
    ):
        stimulus(source=source)


def test_stimulus_rejects_stronger_execution_boundary_claim():
    source = executed_artifact(
        actual_boundary_verified=True,
    )

    with pytest.raises(
        ValueError,
        match="actual_boundary_verified must remain false",
    ):
        stimulus(source=source)


def test_response_evidence_assembles_descriptive_association():
    execution = executed_artifact()
    realized = stimulus(source=execution)
    response = response_evidence(
        source_execution=execution
    )

    association = assemble_observed_response_association(
        stimulus=realized,
        response_evidence=response,
        intervening_history_complete=True,
        created_at=dt(17),
    )

    assert association.athlete_id == ATHLETE
    assert association.workout_session_id == SESSION

    assert association.stimulus_id == realized.stimulus_id
    assert (
        association.response_evidence_id
        == response.evidence_id
    )
    assert (
        association.response_evidence_hash
        == response.content_hash
    )

    assert (
        association.response_timing
        == TrainingResponseTiming.SAME_DAY
    )
    assert (
        association.session_link_basis
        == TrainingResponseLinkBasis
        .SOURCE_EXPLICIT_SESSION_ID
    )

    assert (
        association.lag_from_reference_end_status
        == KnowledgeStatus.KNOWN
    )
    assert association.lag_from_reference_end_s == 5 * 3600

    assert (
        association.isolation_status
        == ResponseIsolationStatus
        .NO_INTERVENING_STIMULUS_OBSERVED
    )

    assert association.causal_attribution_established is False
    assert association.effect_inference_authorized is False
    assert association.planning_authorized is False

    assert association.verify_content_hash()


def test_no_intervening_claim_requires_explicit_history_completeness():
    execution = executed_artifact()

    association = assemble_observed_response_association(
        stimulus=stimulus(source=execution),
        response_evidence=response_evidence(
            source_execution=execution
        ),
        created_at=dt(17),
    )

    assert (
        association.isolation_status
        == ResponseIsolationStatus.UNKNOWN
    )
    assert association.intervening_stimulus_ids == ()


def test_explicit_intervening_stimulus_is_preserved():
    execution = executed_artifact()
    realized = stimulus(source=execution)

    intervening_execution = executed_artifact(
        session_id=OTHER_SESSION,
        observed_at=dt(11),
    )

    intervening = stimulus(
        source=intervening_execution,
        created_at=dt(12),
    )

    association = assemble_observed_response_association(
        stimulus=realized,
        response_evidence=response_evidence(
            source_execution=execution
        ),
        intervening_stimuli=(intervening,),
        created_at=dt(17),
    )

    assert (
        association.isolation_status
        == ResponseIsolationStatus
        .INTERVENING_STIMULUS_OBSERVED
    )

    assert (
        association.intervening_stimulus_ids
        == (intervening.stimulus_id,)
    )

    assert association.causal_attribution_established is False


def test_unknown_duration_keeps_response_lag_unknown():
    execution = executed_artifact(
        duration_status=KnowledgeStatus.UNKNOWN,
        duration_s=None,
    )

    association = assemble_observed_response_association(
        stimulus=stimulus(source=execution),
        response_evidence=response_evidence(
            source_execution=execution
        ),
        created_at=dt(17),
    )

    assert (
        association.lag_from_reference_end_status
        == KnowledgeStatus.UNKNOWN
    )
    assert association.lag_from_reference_end_s is None


def test_response_association_rejects_wrong_athlete():
    execution = executed_artifact()
    response = response_evidence(
        source_execution=execution
    )

    wrong_athlete = rebuild_evidence(
        response,
        athlete_id=OTHER_ATHLETE,
    )

    with pytest.raises(
        ValueError,
        match="athlete",
    ):
        assemble_observed_response_association(
            stimulus=stimulus(source=execution),
            response_evidence=wrong_athlete,
            created_at=dt(17),
        )


def test_response_association_rejects_wrong_execution_reference():
    execution = executed_artifact()
    response = response_evidence(
        source_execution=execution
    )

    payload = dict(response.payload)
    payload["executed_training_evidence_hash"] = "e" * 64

    malformed = rebuild_evidence(
        response,
        payload=payload,
    )

    with pytest.raises(
        ValueError,
        match="execution reference",
    ):
        assemble_observed_response_association(
            stimulus=stimulus(source=execution),
            response_evidence=malformed,
            created_at=dt(17),
        )


def test_response_association_rejects_tampered_response_hash():
    execution = executed_artifact()

    tampered = replace(
        response_evidence(
            source_execution=execution
        ),
        content_hash="f" * 64,
    )

    with pytest.raises(
        ValueError,
        match="hash",
    ):
        assemble_observed_response_association(
            stimulus=stimulus(source=execution),
            response_evidence=tampered,
            created_at=dt(17),
        )


def test_response_association_rejects_authority_upgrade():
    execution = executed_artifact()
    response = response_evidence(
        source_execution=execution
    )

    payload = dict(response.payload)
    payload["causal_attribution_established"] = True

    stronger = rebuild_evidence(
        response,
        payload=payload,
    )

    assert stronger.verify_content_hash()

    with pytest.raises(
        ValueError,
        match="causal_attribution_established must remain false",
    ):
        assemble_observed_response_association(
            stimulus=stimulus(source=execution),
            response_evidence=stronger,
            created_at=dt(17),
        )


def test_intervening_stimulus_must_be_inside_response_interval():
    execution = executed_artifact()

    too_late_execution = executed_artifact(
        session_id=OTHER_SESSION,
        observed_at=dt(15),
    )

    too_late = stimulus(
        source=too_late_execution,
        created_at=dt(16),
    )

    with pytest.raises(
        ValueError,
        match="before the response",
    ):
        assemble_observed_response_association(
            stimulus=stimulus(source=execution),
            response_evidence=response_evidence(
                source_execution=execution
            ),
            intervening_stimuli=(too_late,),
            created_at=dt(17),
        )


def test_response_association_identity_and_hash_stable_across_retry():
    execution = executed_artifact()
    realized = stimulus(source=execution)
    response = response_evidence(
        source_execution=execution
    )

    first = assemble_observed_response_association(
        stimulus=realized,
        response_evidence=response,
        created_at=dt(17),
    )

    second = assemble_observed_response_association(
        stimulus=realized,
        response_evidence=response,
        created_at=dt(18),
    )

    assert first.association_id == second.association_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at
