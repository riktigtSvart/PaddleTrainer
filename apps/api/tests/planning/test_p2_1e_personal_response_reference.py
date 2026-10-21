from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics.descriptive import (
    DescriptiveSampleSupport,
    summarize_training_dynamics_history,
)
from app.planning.domain.training_dynamics.history import (
    TrainingDynamicsHistoryCoverage,
    TrainingDynamicsHistoryEntry,
    build_training_dynamics_history,
)
from app.planning.domain.training_dynamics.models import (
    EffectEvidenceLevel,
    ResponseIsolationStatus,
    build_observed_response_association,
    build_realized_training_stimulus,
)
from app.planning.domain.training_dynamics.personal_reference import (
    PersonalResponseReferenceStatus,
    build_personal_response_reference_assessment,
)
from app.planning.domain.training_dynamics.reference_sufficiency import (
    assess_response_metric_reference_sufficiency,
)
from app.planning.domain.training_dynamics.response_metrics import (
    build_response_metric_observation,
)
from app.planning.domain.training_dynamics.response_reference import (
    build_descriptive_response_metric_references,
)
from app.planning.domain.training_dynamics.sufficiency import (
    assess_training_dynamics_data_sufficiency,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"


def dt(day: int, hour: int) -> datetime:
    return datetime(
        2026,
        10,
        day,
        hour,
        tzinfo=UTC,
    )


def stimulus(
    *,
    session_id: str,
    day: int,
    hash_char: str,
):
    return build_realized_training_stimulus(
        stimulus_id=(
            "pt-training-stimulus:"
            f"session:{session_id}"
        ),
        athlete_id=ATHLETE,
        workout_session_id=session_id,
        executed_training_evidence_id=(
            "pt-executed-training-evidence:"
            f"session:{session_id}"
        ),
        executed_training_evidence_hash=hash_char * 64,
        exposure_observed_at=dt(day, 8),
        modality_key="RUNNING",
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        features=(),
        created_at=dt(day, 9),
    )


def association(
    source_stimulus,
    *,
    response_char: str,
    day: int,
    hour: int = 14,
):
    observed = dt(day, hour)

    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"e:{response_char}"
        ),
        stimulus=source_stimulus,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            f"{response_char * 64}"
        ),
        response_evidence_hash=response_char * 64,
        response_workout_session_id=(
            source_stimulus.workout_session_id
        ),
        response_timing=TrainingResponseTiming.SAME_DAY,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        response_observed_at=observed,
        response_available_at=observed,
        isolation_status=ResponseIsolationStatus.UNKNOWN,
        intervening_stimulus_ids=(),
        created_at=observed,
    )


def observation(
    source_stimulus,
    source_association,
    *,
    knowledge_status=KnowledgeStatus.KNOWN,
    value=6.0,
):
    return build_response_metric_observation(
        stimulus=source_stimulus,
        association=source_association,
        measurement=TrainingResponseMeasurement(
            metric_key="self_reported_fatigue_score",
            knowledge_status=knowledge_status,
            value=value,
            unit="score_0_10",
        ),
        created_at=dt(23, 21),
    )


def build_context(
    *,
    two_numeric=False,
    knowledge_status=KnowledgeStatus.KNOWN,
    value=6.0,
    response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
):
    s1 = stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
    )

    a1 = association(
        s1,
        response_char="d",
        day=19,
    )

    entries = [
        TrainingDynamicsHistoryEntry(
            stimulus=s1,
            responses=(a1,),
        )
    ]

    observations = [
        observation(
            s1,
            a1,
            knowledge_status=knowledge_status,
            value=value,
        )
    ]

    if two_numeric:
        s2 = stimulus(
            session_id=SESSION_B,
            day=21,
            hash_char="b",
        )

        a2 = association(
            s2,
            response_char="e",
            day=21,
        )

        entries.append(
            TrainingDynamicsHistoryEntry(
                stimulus=s2,
                responses=(a2,),
            )
        )

        observations.append(
            observation(
                s2,
                a2,
                value=8.0,
            )
        )

    source_ids = tuple(
        response.response_evidence_id
        for entry in entries
        for response in entry.responses
    )

    history = build_training_dynamics_history(
        history_id="pt-training-dynamics-history:e-test",
        athlete_id=ATHLETE,
        window_start_at=dt(18, 0),
        as_of=dt(23, 20),
        information_cutoff_at=dt(23, 20),
        stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
        response_coverage=response_coverage,
        entries=tuple(entries),
        source_evidence_ids=source_ids,
        created_at=dt(23, 21),
    )

    summary = summarize_training_dynamics_history(
        history,
        created_at=dt(23, 22),
    )

    references = build_descriptive_response_metric_references(
        history=history,
        observations=tuple(observations),
        created_at=dt(23, 22),
    )

    d1 = assess_training_dynamics_data_sufficiency(
        history=history,
        summary=summary,
        references=references,
        created_at=dt(23, 23),
    )

    d2 = assess_response_metric_reference_sufficiency(
        history=history,
        data_sufficiency=d1,
        references=references,
        created_at=dt(24, 0),
    )

    assert len(references) == 1
    assert len(d2) == 1

    return references[0], d2[0]


def build_assessment(
    reference,
    sufficiency,
    *,
    created_at=None,
):
    return build_personal_response_reference_assessment(
        reference=reference,
        sufficiency=sufficiency,
        created_at=created_at or dt(24, 1),
    )


def test_single_numeric_sample_creates_descriptive_reference_availability():
    reference, sufficiency = build_context()

    result = build_assessment(
        reference,
        sufficiency,
    )

    assert (
        result.status
        == PersonalResponseReferenceStatus
        .DESCRIPTIVE_REFERENCE_AVAILABLE
    )

    assert (
        result.sample_support
        == DescriptiveSampleSupport.SINGLE_SAMPLE
    )

    assert result.eligible_numeric_sample_count == 1
    assert result.reference_median == 6.0

    assert result.first_eligible_observed_at == dt(19, 14)
    assert result.last_eligible_observed_at == dt(19, 14)
    assert result.eligible_observation_span_s == 0.0

    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert result.stability_established is False
    assert result.representativeness_established is False
    assert result.validated_baseline_established is False

    assert result.comparison_interpretation_authorized is False
    assert result.association_inference_authorized is False
    assert result.effect_inference_authorized is False
    assert result.causal_attribution_established is False
    assert result.readiness_inference_authorized is False
    assert result.performance_prediction_authorized is False
    assert result.prescription_change_authorized is False
    assert result.planning_authorized is False

    assert result.verify_content_hash()


def test_multiple_samples_preserve_descriptive_statistics_and_span():
    reference, sufficiency = build_context(
        two_numeric=True,
    )

    result = build_assessment(
        reference,
        sufficiency,
    )

    assert (
        result.sample_support
        == DescriptiveSampleSupport.MULTIPLE_SAMPLES
    )

    assert result.eligible_numeric_sample_count == 2

    assert result.reference_minimum == 6.0
    assert result.reference_median == 7.0
    assert result.reference_maximum == 8.0
    assert (
        result.reference_median_absolute_deviation
        == 1.0
    )

    assert result.first_eligible_observed_at == dt(19, 14)
    assert result.last_eligible_observed_at == dt(21, 14)

    assert result.eligible_observation_span_s == 172800.0

    assert result.stability_established is False
    assert result.representativeness_established is False


def test_unknown_measurement_remains_unestablished():
    reference, sufficiency = build_context(
        knowledge_status=KnowledgeStatus.UNKNOWN,
        value=None,
    )

    result = build_assessment(
        reference,
        sufficiency,
    )

    assert (
        result.status
        == PersonalResponseReferenceStatus.UNESTABLISHED
    )

    assert result.eligible_numeric_sample_count == 0
    assert result.reference_median is None

    assert result.first_eligible_observed_at is None
    assert result.last_eligible_observed_at is None
    assert result.eligible_observation_span_s is None


def test_known_non_numeric_measurement_remains_unestablished():
    reference, sufficiency = build_context(
        value="controlled",
    )

    result = build_assessment(
        reference,
        sufficiency,
    )

    assert (
        result.status
        == PersonalResponseReferenceStatus.UNESTABLISHED
    )

    assert result.eligible_numeric_sample_count == 0
    assert result.excluded_known_non_numeric_count == 1


def test_partial_coverage_does_not_hide_available_descriptive_reference():
    reference, sufficiency = build_context(
        response_coverage=TrainingDynamicsHistoryCoverage.PARTIAL,
    )

    result = build_assessment(
        reference,
        sufficiency,
    )

    assert (
        result.status
        == PersonalResponseReferenceStatus
        .DESCRIPTIVE_REFERENCE_AVAILABLE
    )

    assert (
        result.response_coverage
        == TrainingDynamicsHistoryCoverage.PARTIAL
    )

    assert {
        code.value
        for code in result.limitation_codes
    } == {
        "response_source_coverage_partial",
    }

    assert result.representativeness_established is False


def test_reference_and_sufficiency_mismatch_fails_closed():
    reference_a, _ = build_context()

    reference_b, sufficiency_b = build_context(
        two_numeric=True,
    )

    assert reference_a.content_hash != reference_b.content_hash

    with pytest.raises(
        ValueError,
        match="does not belong",
    ):
        build_assessment(
            reference_a,
            sufficiency_b,
        )


def test_tampered_reference_fails_closed():
    reference, sufficiency = build_context()

    tampered = replace(
        reference,
        median=999.0,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        build_assessment(
            tampered,
            sufficiency,
        )


def test_tampered_sufficiency_fails_closed():
    reference, sufficiency = build_context()

    tampered = replace(
        sufficiency,
        eligible_numeric_sample_count=0,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        build_assessment(
            reference,
            tampered,
        )


def test_assessment_cannot_predate_source_sufficiency():
    reference, sufficiency = build_context()

    with pytest.raises(
        ValueError,
        match="cannot predate",
    ):
        build_assessment(
            reference,
            sufficiency,
            created_at=dt(23, 23),
        )


def test_identity_and_hash_are_stable_across_materialization_time():
    reference, sufficiency = build_context()

    first = build_assessment(
        reference,
        sufficiency,
        created_at=dt(24, 1),
    )

    second = build_assessment(
        reference,
        sufficiency,
        created_at=dt(24, 2),
    )

    assert first.assessment_id == second.assessment_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at
