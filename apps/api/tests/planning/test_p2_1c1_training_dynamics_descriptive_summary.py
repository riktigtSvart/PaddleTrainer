from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics.descriptive import (
    DescriptiveSampleSupport,
    TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_SCHEMA_V01,
    summarize_training_dynamics_history,
)
from app.planning.domain.training_dynamics.history import (
    TrainingDynamicsHistoryCoverage,
    TrainingDynamicsHistoryEntry,
    build_training_dynamics_history,
)
from app.planning.domain.training_dynamics.models import (
    ResponseIsolationStatus,
    build_observed_response_association,
    build_realized_training_stimulus,
)


UTC = timezone.utc

ATHLETE = "11111111-1111-4111-8111-111111111111"

SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"


def dt(
    day: int,
    hour: int,
    minute: int = 0,
) -> datetime:
    return datetime(
        2026,
        10,
        day,
        hour,
        minute,
        tzinfo=UTC,
    )


def stimulus(
    *,
    session_id: str,
    observed_at: datetime,
    hash_char: str,
    modality: str = "RUNNING",
    duration_status: KnowledgeStatus = KnowledgeStatus.KNOWN,
    duration_s: int | None = 3600,
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
        exposure_observed_at=observed_at,
        modality_key=modality,
        duration_status=duration_status,
        duration_s=duration_s,
        features=(),
        created_at=observed_at,
    )


def response(
    *,
    source_stimulus,
    observed_at: datetime,
    hash_char: str,
    timing: TrainingResponseTiming,
    isolation: ResponseIsolationStatus,
):
    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"test:{hash_char}"
        ),
        stimulus=source_stimulus,
        response_evidence_id=(
            "pt-evidence:session-feedback:"
            f"{hash_char * 64}"
        ),
        response_evidence_hash=(
            hash_char * 64
        ),
        response_workout_session_id=(
            source_stimulus.workout_session_id
        ),
        response_timing=timing,
        session_link_basis=(
            TrainingResponseLinkBasis
            .SOURCE_EXPLICIT_SESSION_ID
        ),
        response_observed_at=observed_at,
        response_available_at=observed_at,
        isolation_status=isolation,
        intervening_stimulus_ids=(),
        created_at=observed_at,
    )


def history(
    *,
    entries,
    stimulus_coverage=(
        TrainingDynamicsHistoryCoverage.PARTIAL
    ),
    response_coverage=(
        TrainingDynamicsHistoryCoverage.PARTIAL
    ),
):
    return build_training_dynamics_history(
        history_id="pt-training-dynamics-history:c1-test",
        athlete_id=ATHLETE,
        window_start_at=dt(18, 0),
        as_of=dt(21, 23),
        information_cutoff_at=dt(21, 23),
        stimulus_coverage=stimulus_coverage,
        response_coverage=response_coverage,
        entries=tuple(entries),
        source_evidence_ids=(
            "source:a",
            "source:b",
        ),
        created_at=dt(22, 0),
    )


def counts_as_dict(items):
    return {
        item.category_key: item.observed_count
        for item in items
    }


def test_builds_structural_descriptive_summary():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    b = stimulus(
        session_id=SESSION_B,
        observed_at=dt(20, 8),
        hash_char="b",
        modality="KAYAK",
    )

    a_response = response(
        source_stimulus=a,
        observed_at=dt(19, 14),
        hash_char="c",
        timing=TrainingResponseTiming.SAME_DAY,
        isolation=(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
        ),
    )

    b_response = response(
        source_stimulus=b,
        observed_at=dt(21, 8),
        hash_char="d",
        timing=TrainingResponseTiming.NEXT_MORNING,
        isolation=ResponseIsolationStatus.UNKNOWN,
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=b,
                responses=(b_response,),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(a_response,),
            ),
        )
    )

    summary = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 1),
    )

    assert (
        summary.schema_version
        == TRAINING_DYNAMICS_DESCRIPTIVE_SUMMARY_SCHEMA_V01
    )

    assert summary.observed_stimulus_count == 2
    assert summary.known_duration_stimulus_count == 2

    assert summary.observed_response_count == 2
    assert (
        summary.stimuli_with_observed_response_count
        == 2
    )

    assert counts_as_dict(
        summary.modality_stimulus_counts
    ) == {
        "KAYAK": 1,
        "RUNNING": 1,
    }

    timing = counts_as_dict(
        summary.response_timing_counts
    )

    assert timing["same_day"] == 1
    assert timing["next_morning"] == 1
    assert timing["immediate"] == 0
    assert timing["follow_up"] == 0

    isolation = counts_as_dict(
        summary.response_isolation_counts
    )

    assert (
        isolation[
            "no_intervening_stimulus_observed"
        ]
        == 1
    )
    assert isolation["unknown"] == 1

    spacing = summary.observed_stimulus_spacing_s

    assert spacing.sample_count == 1
    assert (
        spacing.sample_support
        == DescriptiveSampleSupport.SINGLE_SAMPLE
    )
    assert spacing.minimum == 86400.0
    assert spacing.median == 86400.0
    assert spacing.maximum == 86400.0
    assert spacing.median_absolute_deviation is None

    lag = (
        summary.response_lag_from_reference_end_s
    )

    assert lag.sample_count == 2
    assert (
        lag.sample_support
        == DescriptiveSampleSupport.MULTIPLE_SAMPLES
    )
    assert lag.minimum == 18000.0
    assert lag.median == 50400.0
    assert lag.maximum == 82800.0
    assert lag.median_absolute_deviation == 32400.0

    assert summary.verify_content_hash()


def test_empty_observed_numeric_samples_remain_explicit():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(),
            ),
        )
    )

    summary = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 1),
    )

    spacing = summary.observed_stimulus_spacing_s

    assert spacing.sample_count == 0
    assert (
        spacing.sample_support
        == DescriptiveSampleSupport.NO_SAMPLES
    )
    assert spacing.minimum is None
    assert spacing.median is None
    assert spacing.maximum is None
    assert spacing.median_absolute_deviation is None

    lag = summary.response_lag_from_reference_end_s

    assert lag.sample_count == 0
    assert lag.median is None


def test_unknown_response_lag_is_not_promoted_to_zero():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
        duration_status=KnowledgeStatus.UNKNOWN,
        duration_s=None,
    )

    r = response(
        source_stimulus=a,
        observed_at=dt(19, 14),
        hash_char="c",
        timing=TrainingResponseTiming.SAME_DAY,
        isolation=ResponseIsolationStatus.UNKNOWN,
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(r,),
            ),
        )
    )

    summary = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 1),
    )

    lag = summary.response_lag_from_reference_end_s

    assert lag.sample_count == 0
    assert lag.median is None


def test_history_coverage_is_preserved_not_inferred():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(),
            ),
        ),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.COMPLETE
        ),
        response_coverage=(
            TrainingDynamicsHistoryCoverage.UNKNOWN
        ),
    )

    summary = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 1),
    )

    assert (
        summary.stimulus_coverage
        == TrainingDynamicsHistoryCoverage.COMPLETE
    )

    assert (
        summary.response_coverage
        == TrainingDynamicsHistoryCoverage.UNKNOWN
    )


def test_summary_rejects_tampered_history():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(),
            ),
        )
    )

    tampered = replace(
        source,
        content_hash="f" * 64,
    )

    with pytest.raises(
        ValueError,
        match="history hash",
    ):
        summarize_training_dynamics_history(
            tampered,
            created_at=dt(22, 1),
        )


def test_summary_cannot_predate_source_history():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(),
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="cannot predate",
    ):
        summarize_training_dynamics_history(
            source,
            created_at=dt(21, 23),
        )


def test_summary_hash_is_stable_across_materialization_time():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(),
            ),
        )
    )

    first = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 1),
    )

    second = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 2),
    )

    assert first.summary_id == second.summary_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at


def test_summary_contains_no_effect_or_metric_baseline_claim():
    a = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    source = history(
        entries=(
            TrainingDynamicsHistoryEntry(
                stimulus=a,
                responses=(),
            ),
        )
    )

    summary = summarize_training_dynamics_history(
        source,
        created_at=dt(22, 1),
    )

    assert summary.causal_attribution_established is False
    assert summary.effect_inference_authorized is False
    assert summary.readiness_inference_authorized is False
    assert summary.performance_prediction_authorized is False
    assert summary.prescription_change_authorized is False

    assert not hasattr(summary, "fatigue_effect")
    assert not hasattr(summary, "adaptation_effect")
    assert not hasattr(summary, "metric_baselines")
    assert not hasattr(summary, "response_rate")
