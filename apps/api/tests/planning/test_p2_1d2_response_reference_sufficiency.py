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
from app.planning.domain.training_dynamics.reference_sufficiency import (
    ResponseMetricReferenceContextDimension,
    assess_response_metric_reference_sufficiency,
)
from app.planning.domain.training_dynamics.response_metrics import (
    build_response_metric_observation,
)
from app.planning.domain.training_dynamics.response_reference import (
    build_descriptive_response_metric_references,
)
from app.planning.domain.training_dynamics.sufficiency import (
    TrainingDynamicsDataSufficiencyStatus,
    assess_training_dynamics_data_sufficiency,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"

SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"
SESSION_C = "44444444-4444-4444-8444-444444444444"


def dt(
    day: int,
    hour: int,
) -> datetime:
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
    modality: str = "RUNNING",
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
        executed_training_evidence_hash=(
            hash_char * 64
        ),
        exposure_observed_at=dt(day, 8),
        modality_key=modality,
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
    timing: TrainingResponseTiming = (
        TrainingResponseTiming.SAME_DAY
    ),
):
    observed = dt(
        day,
        hour,
    )

    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"d2:{response_char}"
        ),
        stimulus=source_stimulus,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            f"{response_char * 64}"
        ),
        response_evidence_hash=(
            response_char * 64
        ),
        response_workout_session_id=(
            source_stimulus.workout_session_id
        ),
        response_timing=timing,
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
    metric_key="self_reported_fatigue_score",
    knowledge_status=KnowledgeStatus.KNOWN,
    value=6.0,
    unit="score_0_10",
):
    return build_response_metric_observation(
        stimulus=source_stimulus,
        association=source_association,
        measurement=TrainingResponseMeasurement(
            metric_key=metric_key,
            knowledge_status=knowledge_status,
            value=value,
            unit=unit,
        ),
        created_at=dt(23, 21),
    )


def history(
    entries,
    *,
    history_id="pt-training-dynamics-history:d2-test",
    stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
    response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
):
    source_ids = tuple(
        response.response_evidence_id
        for entry in entries
        for response in entry.responses
    )

    return build_training_dynamics_history(
        history_id=history_id,
        athlete_id=ATHLETE,
        window_start_at=dt(18, 0),
        as_of=dt(23, 20),
        information_cutoff_at=dt(23, 20),
        stimulus_coverage=stimulus_coverage,
        response_coverage=response_coverage,
        entries=tuple(entries),
        source_evidence_ids=source_ids,
        created_at=dt(23, 21),
    )


def build_context(
    *,
    observations_builder=None,
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

    h = history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=s1,
                responses=(a1,),
            ),
        ),
        response_coverage=response_coverage,
    )

    summary = summarize_training_dynamics_history(
        h,
        created_at=dt(23, 22),
    )

    if observations_builder is None:
        observations = (
            observation(
                s1,
                a1,
            ),
        )
    else:
        observations = tuple(
            observations_builder(
                s1,
                a1,
            )
        )

    references = build_descriptive_response_metric_references(
        history=h,
        observations=observations,
        created_at=dt(23, 22),
    )

    d1 = assess_training_dynamics_data_sufficiency(
        history=h,
        summary=summary,
        references=references,
        created_at=dt(23, 23),
    )

    return (
        h,
        d1,
        references,
    )


def assess(
    h,
    d1,
    references,
    *,
    created_at=None,
):
    return assess_response_metric_reference_sufficiency(
        history=h,
        data_sufficiency=d1,
        references=tuple(references),
        created_at=created_at or dt(24, 0),
    )


def limitation_values(
    result,
):
    return {
        item.value
        for item in result.limitation_codes
    }


def test_single_numeric_reference_is_descriptively_supported():
    h, d1, references = build_context()

    results = assess(
        h,
        d1,
        references,
    )

    assert len(results) == 1

    result = results[0]

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    assert (
        result.sample_support
        == DescriptiveSampleSupport.SINGLE_SAMPLE
    )

    assert result.observed_observation_count == 1
    assert result.eligible_numeric_sample_count == 1

    assert result.metric_context_count == 1
    assert result.sibling_reference_ids == ()
    assert result.fragmented_dimensions == ()
    assert result.limitation_codes == ()

    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert result.association_inference_authorized is False
    assert result.effect_inference_authorized is False
    assert result.causal_attribution_established is False
    assert result.readiness_inference_authorized is False
    assert result.performance_prediction_authorized is False
    assert result.prescription_change_authorized is False
    assert result.planning_authorized is False

    assert result.verify_content_hash()


def test_single_sample_does_not_require_arbitrary_minimum_n():
    h, d1, references = build_context()

    result = assess(
        h,
        d1,
        references,
    )[0]

    assert result.eligible_numeric_sample_count == 1

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    assert not hasattr(
        result,
        "minimum_samples",
    )
    assert not hasattr(
        result,
        "baseline_established",
    )


def test_unknown_measurement_is_insufficient_not_zero():
    def observations_builder(
        source_stimulus,
        source_association,
    ):
        return (
            observation(
                source_stimulus,
                source_association,
                knowledge_status=KnowledgeStatus.UNKNOWN,
                value=None,
            ),
        )

    h, d1, references = build_context(
        observations_builder=observations_builder,
    )

    result = assess(
        h,
        d1,
        references,
    )[0]

    assert result.observed_observation_count == 1
    assert result.eligible_numeric_sample_count == 0
    assert result.excluded_non_known_count == 1

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    assert (
        "no_eligible_numeric_response_samples"
        in limitation_values(result)
    )

    assert (
        "non_known_response_samples_present"
        in limitation_values(result)
    )


def test_known_non_numeric_measurement_is_insufficient():
    def observations_builder(
        source_stimulus,
        source_association,
    ):
        return (
            observation(
                source_stimulus,
                source_association,
                value="controlled",
                unit=None,
            ),
        )

    h, d1, references = build_context(
        observations_builder=observations_builder,
    )

    result = assess(
        h,
        d1,
        references,
    )[0]

    assert result.eligible_numeric_sample_count == 0
    assert result.excluded_known_non_numeric_count == 1

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    assert (
        "known_non_numeric_response_samples_present"
        in limitation_values(result)
    )


def test_partial_response_coverage_is_limitation_not_support_failure():
    h, d1, references = build_context(
        response_coverage=TrainingDynamicsHistoryCoverage.PARTIAL,
    )

    result = assess(
        h,
        d1,
        references,
    )[0]

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    assert (
        "response_source_coverage_partial"
        in limitation_values(result)
    )


def test_fragmentation_reports_exact_changed_dimensions():
    s1 = stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
        modality="RUNNING",
    )

    s2 = stimulus(
        session_id=SESSION_B,
        day=20,
        hash_char="b",
        modality="KAYAK",
    )

    s3 = stimulus(
        session_id=SESSION_C,
        day=21,
        hash_char="c",
        modality="RUNNING",
    )

    a1 = association(
        s1,
        response_char="d",
        day=19,
        timing=TrainingResponseTiming.SAME_DAY,
    )

    a2 = association(
        s2,
        response_char="e",
        day=20,
        timing=TrainingResponseTiming.SAME_DAY,
    )

    a3 = association(
        s3,
        response_char="f",
        day=22,
        hour=8,
        timing=TrainingResponseTiming.NEXT_MORNING,
    )

    h = history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=s1,
                responses=(a1,),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=s2,
                responses=(a2,),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=s3,
                responses=(a3,),
            ),
        )
    )

    summary = summarize_training_dynamics_history(
        h,
        created_at=dt(23, 22),
    )

    observations = (
        observation(
            s1,
            a1,
            value=5.0,
            unit="score_0_10",
        ),
        observation(
            s2,
            a2,
            value=6.0,
            unit="score_0_10",
        ),
        observation(
            s3,
            a3,
            value=7.0,
            unit=None,
        ),
    )

    references = build_descriptive_response_metric_references(
        history=h,
        observations=observations,
        created_at=dt(23, 22),
    )

    d1 = assess_training_dynamics_data_sufficiency(
        history=h,
        summary=summary,
        references=references,
        created_at=dt(23, 23),
    )

    results = assess(
        h,
        d1,
        references,
    )

    assert len(results) == 3

    expected = {
        ResponseMetricReferenceContextDimension.UNIT,
        ResponseMetricReferenceContextDimension.RESPONSE_TIMING,
        ResponseMetricReferenceContextDimension.STIMULUS_MODALITY,
    }

    for result in results:
        assert result.metric_context_count == 3

        assert set(
            result.fragmented_dimensions
        ) == expected

        assert len(
            result.sibling_reference_ids
        ) == 2

        assert (
            "context_fragmentation_present"
            in limitation_values(result)
        )

        assert (
            result.status
            == TrainingDynamicsDataSufficiencyStatus
            .DESCRIPTIVE_SUPPORTED
        )


def test_different_metric_keys_do_not_fragment_each_other():
    def observations_builder(
        source_stimulus,
        source_association,
    ):
        return (
            observation(
                source_stimulus,
                source_association,
                metric_key="self_reported_fatigue_score",
                value=6.0,
            ),
            observation(
                source_stimulus,
                source_association,
                metric_key="self_reported_energy_score",
                value=7.0,
            ),
        )

    h, d1, references = build_context(
        observations_builder=observations_builder,
    )

    results = assess(
        h,
        d1,
        references,
    )

    assert len(results) == 2

    for result in results:
        assert result.metric_context_count == 1
        assert result.sibling_reference_ids == ()
        assert result.fragmented_dimensions == ()

        assert (
            "context_fragmentation_present"
            not in limitation_values(result)
        )


def test_reference_subset_is_rejected_to_prevent_cherry_picking():
    def observations_builder(
        source_stimulus,
        source_association,
    ):
        return (
            observation(
                source_stimulus,
                source_association,
                metric_key="self_reported_fatigue_score",
                value=6.0,
            ),
            observation(
                source_stimulus,
                source_association,
                metric_key="self_reported_energy_score",
                value=7.0,
            ),
        )

    h, d1, references = build_context(
        observations_builder=observations_builder,
    )

    with pytest.raises(
        ValueError,
        match="exactly match",
    ):
        assess(
            h,
            d1,
            references[:1],
        )


def test_tampered_reference_fails_closed():
    h, d1, references = build_context()

    tampered = replace(
        references[0],
        eligible_numeric_sample_count=0,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        assess(
            h,
            d1,
            (tampered,),
        )


def test_tampered_d1_assessment_fails_closed():
    h, d1, references = build_context()

    tampered = replace(
        d1,
        eligible_numeric_response_sample_count=0,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        assess(
            h,
            tampered,
            references,
        )


def test_empty_reference_set_produces_no_fabricated_context_assessment():
    h = history(
        (),
        stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
        response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
    )

    summary = summarize_training_dynamics_history(
        h,
        created_at=dt(23, 22),
    )

    d1 = assess_training_dynamics_data_sufficiency(
        history=h,
        summary=summary,
        references=(),
        created_at=dt(23, 23),
    )

    results = assess(
        h,
        d1,
        (),
    )

    assert results == ()


def test_identity_and_hash_are_deterministic_across_materialization_time():
    h, d1, references = build_context()

    first = assess_response_metric_reference_sufficiency(
        history=h,
        data_sufficiency=d1,
        references=references,
        created_at=dt(24, 0),
    )

    second = assess_response_metric_reference_sufficiency(
        history=h,
        data_sufficiency=d1,
        references=tuple(
            reversed(
                references
            )
        ),
        created_at=dt(24, 1),
    )

    assert len(first) == len(second) == 1

    assert (
        first[0].assessment_id
        == second[0].assessment_id
    )

    assert (
        first[0].content_hash
        == second[0].content_hash
    )

    assert (
        first[0].created_at
        != second[0].created_at
    )
