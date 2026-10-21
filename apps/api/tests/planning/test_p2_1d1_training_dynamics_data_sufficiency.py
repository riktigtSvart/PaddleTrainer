from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics.descriptive import (
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
from app.planning.domain.training_dynamics.response_metrics import (
    build_response_metric_observation,
)
from app.planning.domain.training_dynamics.response_reference import (
    build_descriptive_response_metric_references,
)
from app.planning.domain.training_dynamics.sufficiency import (
    TrainingDynamicsDataSufficiencyComponentKind,
    TrainingDynamicsDataSufficiencyLimitationCode,
    TrainingDynamicsDataSufficiencyStatus,
    assess_training_dynamics_data_sufficiency,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"
SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"


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


def make_stimulus(
    *,
    session_id: str,
    day: int,
    hash_char: str,
    duration_known: bool = True,
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
        duration_status=(
            KnowledgeStatus.KNOWN
            if duration_known
            else KnowledgeStatus.UNKNOWN
        ),
        duration_s=3600 if duration_known else None,
        features=(),
        created_at=dt(day, 9),
    )


def make_association(
    stimulus,
    *,
    response_char: str,
    response_day: int,
    response_hour: int = 14,
    timing=TrainingResponseTiming.SAME_DAY,
):
    observed = dt(
        response_day,
        response_hour,
    )

    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"d1:{response_char}"
        ),
        stimulus=stimulus,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            f"{response_char * 64}"
        ),
        response_evidence_hash=(
            response_char * 64
        ),
        response_workout_session_id=(
            stimulus.workout_session_id
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


def make_history(
    entries,
    *,
    history_id="pt-training-dynamics-history:d1-test",
    stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
    response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
):
    source_ids = tuple(
        association.response_evidence_id
        for entry in entries
        for association in entry.responses
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


def make_observation(
    stimulus,
    association,
    *,
    metric_key="self_reported_fatigue_score",
    knowledge_status=KnowledgeStatus.KNOWN,
    value=6.0,
    unit="score_0_10",
):
    return build_response_metric_observation(
        stimulus=stimulus,
        association=association,
        measurement=TrainingResponseMeasurement(
            metric_key=metric_key,
            knowledge_status=knowledge_status,
            value=value,
            unit=unit,
        ),
        created_at=dt(23, 21),
    )


def build_sources(
    *,
    duration_known=True,
    measurement_status=KnowledgeStatus.KNOWN,
    measurement_value=6.0,
    stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
    response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
):
    stimulus = make_stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
        duration_known=duration_known,
    )

    association = make_association(
        stimulus,
        response_char="d",
        response_day=19,
    )

    history = make_history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=stimulus,
                responses=(association,),
            ),
        ),
        stimulus_coverage=stimulus_coverage,
        response_coverage=response_coverage,
    )

    summary = summarize_training_dynamics_history(
        history,
        created_at=dt(23, 22),
    )

    observation = make_observation(
        stimulus,
        association,
        knowledge_status=measurement_status,
        value=measurement_value,
    )

    references = build_descriptive_response_metric_references(
        history=history,
        observations=(observation,),
        created_at=dt(23, 22),
    )

    return (
        history,
        summary,
        references,
    )


def assess(
    history,
    summary,
    references,
    *,
    created_at=None,
):
    return assess_training_dynamics_data_sufficiency(
        history=history,
        summary=summary,
        references=tuple(references),
        created_at=created_at or dt(23, 23),
    )


def component(
    assessment,
    kind,
):
    return next(
        item
        for item in assessment.components
        if item.kind == kind
    )


def limitation_values(
    assessment,
):
    return {
        item.value
        for item in assessment.limitation_codes
    }


def test_complete_observed_data_supports_descriptive_components():
    history, summary, references = build_sources()

    result = assess(
        history,
        summary,
        references,
    )

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    assert all(
        item.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
        for item in result.components
    )

    assert result.reference_context_count == 1
    assert result.eligible_numeric_reference_context_count == 1
    assert result.eligible_numeric_response_sample_count == 1

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


def test_complete_empty_history_is_insufficient_not_zero_evidence():
    history = make_history(
        (),
        stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
        response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
    )

    summary = summarize_training_dynamics_history(
        history,
        created_at=dt(23, 22),
    )

    result = assess(
        history,
        summary,
        (),
    )

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    assert (
        component(
            result,
            TrainingDynamicsDataSufficiencyComponentKind
            .STRUCTURAL_HISTORY,
        ).status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    assert (
        "no_observed_stimuli"
        in limitation_values(result)
    )

    assert (
        "no_observed_responses"
        in limitation_values(result)
    )


def test_unknown_empty_source_coverage_stays_unknown():
    history = make_history(
        (),
        stimulus_coverage=TrainingDynamicsHistoryCoverage.UNKNOWN,
        response_coverage=TrainingDynamicsHistoryCoverage.UNKNOWN,
    )

    summary = summarize_training_dynamics_history(
        history,
        created_at=dt(23, 22),
    )

    result = assess(
        history,
        summary,
        (),
    )

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus.UNKNOWN
    )

    assert (
        component(
            result,
            TrainingDynamicsDataSufficiencyComponentKind
            .STRUCTURAL_HISTORY,
        ).status
        == TrainingDynamicsDataSufficiencyStatus.UNKNOWN
    )

    assert (
        "stimulus_source_coverage_unknown"
        in limitation_values(result)
    )
    assert (
        "response_source_coverage_unknown"
        in limitation_values(result)
    )


def test_partial_coverage_preserves_descriptive_support_with_limits():
    history, summary, references = build_sources(
        stimulus_coverage=TrainingDynamicsHistoryCoverage.PARTIAL,
        response_coverage=TrainingDynamicsHistoryCoverage.PARTIAL,
    )

    result = assess(
        history,
        summary,
        references,
    )

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    values = limitation_values(
        result
    )

    assert (
        "stimulus_source_coverage_partial"
        in values
    )
    assert (
        "response_source_coverage_partial"
        in values
    )


def test_response_absence_is_component_insufficient_not_global_failure():
    stimulus = make_stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
    )

    history = make_history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=stimulus,
                responses=(),
            ),
        ),
        response_coverage=TrainingDynamicsHistoryCoverage.PARTIAL,
    )

    summary = summarize_training_dynamics_history(
        history,
        created_at=dt(23, 22),
    )

    result = assess(
        history,
        summary,
        (),
    )

    assert (
        result.status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    assert (
        component(
            result,
            TrainingDynamicsDataSufficiencyComponentKind
            .STRUCTURAL_HISTORY,
        ).status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )

    assert (
        component(
            result,
            TrainingDynamicsDataSufficiencyComponentKind
            .RESPONSE_OBSERVATION,
        ).status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )


def test_unknown_response_lag_is_insufficient_for_lag_only():
    history, summary, references = build_sources(
        duration_known=False,
    )

    result = assess(
        history,
        summary,
        references,
    )

    lag = component(
        result,
        TrainingDynamicsDataSufficiencyComponentKind.RESPONSE_LAG,
    )

    assert lag.observed_count == 1
    assert lag.usable_count == 0

    assert (
        lag.status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    assert (
        TrainingDynamicsDataSufficiencyLimitationCode
        .NO_KNOWN_RESPONSE_LAGS
        in lag.limitation_codes
    )


def test_single_numeric_reference_is_descriptively_supported_without_threshold():
    history, summary, references = build_sources()

    result = assess(
        history,
        summary,
        references,
    )

    metric = component(
        result,
        TrainingDynamicsDataSufficiencyComponentKind
        .PERSONAL_METRIC_REFERENCE,
    )

    assert metric.observed_count == 1
    assert metric.usable_count == 1

    assert (
        metric.status
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


def test_known_non_numeric_reference_is_not_numeric_support():
    history, summary, references = build_sources(
        measurement_value="controlled",
    )

    result = assess(
        history,
        summary,
        references,
    )

    metric = component(
        result,
        TrainingDynamicsDataSufficiencyComponentKind
        .PERSONAL_METRIC_REFERENCE,
    )

    assert metric.usable_count == 0
    assert (
        metric.status
        == TrainingDynamicsDataSufficiencyStatus.INSUFFICIENT
    )

    assert (
        result.excluded_known_non_numeric_response_sample_count
        == 1
    )

    assert (
        "known_non_numeric_response_samples_present"
        in limitation_values(result)
    )


def test_non_known_reference_is_excluded_not_converted_to_zero():
    history, summary, references = build_sources(
        measurement_status=KnowledgeStatus.UNKNOWN,
        measurement_value=None,
    )

    result = assess(
        history,
        summary,
        references,
    )

    metric = component(
        result,
        TrainingDynamicsDataSufficiencyComponentKind
        .PERSONAL_METRIC_REFERENCE,
    )

    assert metric.usable_count == 0

    assert (
        result.excluded_non_known_response_sample_count
        == 1
    )

    assert (
        "non_known_response_samples_present"
        in limitation_values(result)
    )


def test_context_fragmentation_is_warning_not_support_failure():
    stimulus_a = make_stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
    )
    stimulus_b = make_stimulus(
        session_id=SESSION_B,
        day=20,
        hash_char="b",
    )

    association_a = make_association(
        stimulus_a,
        response_char="d",
        response_day=19,
        timing=TrainingResponseTiming.SAME_DAY,
    )

    association_b = make_association(
        stimulus_b,
        response_char="e",
        response_day=21,
        response_hour=8,
        timing=TrainingResponseTiming.NEXT_MORNING,
    )

    history = make_history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=stimulus_a,
                responses=(association_a,),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=stimulus_b,
                responses=(association_b,),
            ),
        )
    )

    summary = summarize_training_dynamics_history(
        history,
        created_at=dt(23, 22),
    )

    observations = (
        make_observation(
            stimulus_a,
            association_a,
            value=5.0,
        ),
        make_observation(
            stimulus_b,
            association_b,
            value=7.0,
        ),
    )

    references = build_descriptive_response_metric_references(
        history=history,
        observations=observations,
        created_at=dt(23, 22),
    )

    result = assess(
        history,
        summary,
        references,
    )

    assert result.reference_context_count == 2
    assert result.fragmented_metric_keys == (
        "self_reported_fatigue_score",
    )

    assert (
        "context_fragmentation_present"
        in limitation_values(result)
    )

    assert (
        component(
            result,
            TrainingDynamicsDataSufficiencyComponentKind
            .PERSONAL_METRIC_REFERENCE,
        ).status
        == TrainingDynamicsDataSufficiencyStatus
        .DESCRIPTIVE_SUPPORTED
    )


def test_summary_from_another_history_fails_closed():
    history, summary, references = build_sources()

    other = make_history(
        (),
        history_id="pt-training-dynamics-history:other",
    )

    other_summary = summarize_training_dynamics_history(
        other,
        created_at=dt(23, 22),
    )

    with pytest.raises(
        ValueError,
        match="does not belong",
    ):
        assess(
            history,
            other_summary,
            references,
        )


def test_reference_from_another_history_fails_closed():
    history, summary, references = build_sources()

    other_stimulus = make_stimulus(
        session_id=SESSION_B,
        day=20,
        hash_char="b",
    )

    other_association = make_association(
        other_stimulus,
        response_char="e",
        response_day=20,
    )

    other_history = make_history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=other_stimulus,
                responses=(other_association,),
            ),
        ),
        history_id="pt-training-dynamics-history:other",
    )

    other_observation = make_observation(
        other_stimulus,
        other_association,
    )

    other_references = build_descriptive_response_metric_references(
        history=other_history,
        observations=(other_observation,),
        created_at=dt(23, 22),
    )

    with pytest.raises(
        ValueError,
        match="does not belong",
    ):
        assess(
            history,
            summary,
            other_references,
        )


def test_assessment_hash_is_stable_across_materialization_time():
    history, summary, references = build_sources()

    first = assess_training_dynamics_data_sufficiency(
        history=history,
        summary=summary,
        references=references,
        created_at=dt(23, 23),
    )

    second = assess_training_dynamics_data_sufficiency(
        history=history,
        summary=summary,
        references=tuple(reversed(references)),
        created_at=dt(24, 0),
    )

    assert first.assessment_id == second.assessment_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at
