from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import (
    KnowledgeStatus,
)
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics.descriptive import (
    DescriptiveSampleSupport,
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
from app.planning.domain.training_dynamics.response_metrics import (
    build_response_metric_observation,
)
from app.planning.domain.training_dynamics.response_reference import (
    DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01,
    ResponseMetricReferenceEligibility,
    build_descriptive_response_metric_references,
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
    observed_at: datetime,
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
        exposure_observed_at=observed_at,
        modality_key=modality,
        duration_status=KnowledgeStatus.KNOWN,
        duration_s=3600,
        features=(),
        created_at=observed_at,
    )


def association(
    source_stimulus,
    *,
    response_char: str,
    observed_at: datetime,
    timing: TrainingResponseTiming = (
        TrainingResponseTiming.SAME_DAY
    ),
    isolation: ResponseIsolationStatus = (
        ResponseIsolationStatus.UNKNOWN
    ),
):
    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"test:{response_char}"
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
        response_observed_at=observed_at,
        response_available_at=observed_at,
        isolation_status=isolation,
        intervening_stimulus_ids=(),
        created_at=observed_at,
    )


def observation(
    source_stimulus,
    source_association,
    *,
    metric_key: str = "self_reported_fatigue_score",
    knowledge_status: KnowledgeStatus = KnowledgeStatus.KNOWN,
    value=6.0,
    unit: str | None = "score_0_10",
):
    measurement = TrainingResponseMeasurement(
        metric_key=metric_key,
        knowledge_status=knowledge_status,
        value=value,
        unit=unit,
    )

    return build_response_metric_observation(
        stimulus=source_stimulus,
        association=source_association,
        measurement=measurement,
        created_at=dt(23, 0),
    )


def history(
    entries,
    *,
    stimulus_coverage=(
        TrainingDynamicsHistoryCoverage.PARTIAL
    ),
    response_coverage=(
        TrainingDynamicsHistoryCoverage.PARTIAL
    ),
):
    source_ids = tuple(
        association.response_evidence_id
        for entry in entries
        for association in entry.responses
    )

    return build_training_dynamics_history(
        history_id=(
            "pt-training-dynamics-history:"
            "c2b-test"
        ),
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


def build_refs(
    source_history,
    observations,
    *,
    created_at=None,
):
    return build_descriptive_response_metric_references(
        history=source_history,
        observations=tuple(observations),
        created_at=created_at or dt(23, 22),
    )


def isolation_counts(reference):
    return {
        item.category_key: item.observed_count
        for item in reference.response_isolation_counts
    }


def three_numeric_context():
    s1 = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )
    s2 = stimulus(
        session_id=SESSION_B,
        observed_at=dt(20, 8),
        hash_char="b",
    )
    s3 = stimulus(
        session_id=SESSION_C,
        observed_at=dt(21, 8),
        hash_char="c",
    )

    a1 = association(
        s1,
        response_char="d",
        observed_at=dt(19, 14),
    )
    a2 = association(
        s2,
        response_char="e",
        observed_at=dt(20, 14),
    )
    a3 = association(
        s3,
        response_char="f",
        observed_at=dt(21, 14),
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

    return (
        h,
        (
            observation(
                s1,
                a1,
                value=4.0,
            ),
            observation(
                s2,
                a2,
                value=6.0,
            ),
            observation(
                s3,
                a3,
                value=10.0,
            ),
        ),
    )


def test_builds_personal_descriptive_median_and_mad():
    h, observations = three_numeric_context()

    references = build_refs(
        h,
        observations,
    )

    assert len(references) == 1

    reference = references[0]

    assert (
        reference.schema_version
        == DESCRIPTIVE_RESPONSE_METRIC_REFERENCE_SCHEMA_V01
    )

    assert (
        reference.key.metric_key
        == "self_reported_fatigue_score"
    )
    assert reference.key.unit == "score_0_10"
    assert (
        reference.key.response_timing
        == TrainingResponseTiming.SAME_DAY
    )
    assert (
        reference.key.stimulus_modality_key
        == "RUNNING"
    )

    assert reference.observed_observation_count == 3
    assert reference.eligible_numeric_sample_count == 3

    assert reference.minimum == 4.0
    assert reference.median == 6.0
    assert reference.maximum == 10.0
    assert reference.median_absolute_deviation == 2.0

    assert (
        reference.sample_support
        == DescriptiveSampleSupport.MULTIPLE_SAMPLES
    )

    assert len(
        reference.source_observations
    ) == 3

    assert reference.verify_content_hash()


def test_zero_is_valid_numeric_sample():
    h, observations = three_numeric_context()

    adjusted = (
        replace(
            observations[0],
            value=0.0,
            content_hash="",
        ),
    )

    # Rebuild correctly rather than accepting a tampered hash.
    first_entry = h.entries[0]

    zero_observation = observation(
        first_entry.stimulus,
        first_entry.responses[0],
        value=0.0,
    )

    second_entry = h.entries[1]

    two_observation = observation(
        second_entry.stimulus,
        second_entry.responses[0],
        value=2.0,
    )

    references = build_refs(
        h,
        (
            zero_observation,
            two_observation,
        ),
    )

    reference = references[0]

    assert reference.eligible_numeric_sample_count == 2
    assert reference.minimum == 0.0
    assert reference.median == 1.0
    assert reference.maximum == 2.0
    assert reference.median_absolute_deviation == 1.0


def test_unknown_is_excluded_not_converted_to_zero():
    h, observations = three_numeric_context()

    first_entry = h.entries[0]
    second_entry = h.entries[1]

    known = observation(
        first_entry.stimulus,
        first_entry.responses[0],
        value=6.0,
    )

    unknown = observation(
        second_entry.stimulus,
        second_entry.responses[0],
        knowledge_status=KnowledgeStatus.UNKNOWN,
        value=None,
    )

    reference = build_refs(
        h,
        (
            known,
            unknown,
        ),
    )[0]

    assert reference.observed_observation_count == 2
    assert reference.eligible_numeric_sample_count == 1
    assert reference.excluded_non_known_count == 1

    assert reference.minimum == 6.0
    assert reference.median == 6.0
    assert reference.maximum == 6.0
    assert reference.median_absolute_deviation is None

    assert (
        reference.sample_support
        == DescriptiveSampleSupport.SINGLE_SAMPLE
    )

    eligibility = {
        source.eligibility
        for source in reference.source_observations
    }

    assert (
        ResponseMetricReferenceEligibility.NON_KNOWN
        in eligibility
    )


def test_known_string_and_bool_are_not_numeric_samples():
    h, observations = three_numeric_context()

    first_entry = h.entries[0]
    second_entry = h.entries[1]

    label = observation(
        first_entry.stimulus,
        first_entry.responses[0],
        metric_key="subjective_label",
        value="controlled",
        unit=None,
    )

    completed = observation(
        second_entry.stimulus,
        second_entry.responses[0],
        metric_key="subjective_label",
        value=True,
        unit=None,
    )

    reference = build_refs(
        h,
        (
            label,
            completed,
        ),
    )[0]

    assert reference.observed_observation_count == 2
    assert reference.eligible_numeric_sample_count == 0
    assert (
        reference.excluded_known_non_numeric_count
        == 2
    )

    assert (
        reference.sample_support
        == DescriptiveSampleSupport.NO_SAMPLES
    )

    assert reference.minimum is None
    assert reference.median is None
    assert reference.maximum is None
    assert reference.median_absolute_deviation is None


def test_response_timing_is_part_of_reference_key():
    h, observations = three_numeric_context()

    first_entry = h.entries[0]
    second_entry = h.entries[1]

    same_day = observation(
        first_entry.stimulus,
        first_entry.responses[0],
        value=6.0,
    )

    next_morning_association = association(
        second_entry.stimulus,
        response_char="9",
        observed_at=dt(20, 18),
        timing=TrainingResponseTiming.NEXT_MORNING,
    )

    h2 = history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=first_entry.stimulus,
                responses=(first_entry.responses[0],),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=second_entry.stimulus,
                responses=(next_morning_association,),
            ),
        )
    )

    next_morning = observation(
        second_entry.stimulus,
        next_morning_association,
        value=7.0,
    )

    references = build_refs(
        h2,
        (
            same_day,
            next_morning,
        ),
    )

    assert len(references) == 2

    assert {
        reference.key.response_timing
        for reference in references
    } == {
        TrainingResponseTiming.SAME_DAY,
        TrainingResponseTiming.NEXT_MORNING,
    }


def test_modality_is_part_of_reference_key():
    running = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
        modality="RUNNING",
    )

    kayak = stimulus(
        session_id=SESSION_B,
        observed_at=dt(20, 8),
        hash_char="b",
        modality="KAYAK",
    )

    running_response = association(
        running,
        response_char="d",
        observed_at=dt(19, 14),
    )

    kayak_response = association(
        kayak,
        response_char="e",
        observed_at=dt(20, 14),
    )

    h = history(
        (
            TrainingDynamicsHistoryEntry(
                stimulus=running,
                responses=(running_response,),
            ),
            TrainingDynamicsHistoryEntry(
                stimulus=kayak,
                responses=(kayak_response,),
            ),
        )
    )

    references = build_refs(
        h,
        (
            observation(
                running,
                running_response,
                value=6.0,
            ),
            observation(
                kayak,
                kayak_response,
                value=6.0,
            ),
        ),
    )

    assert len(references) == 2

    assert {
        reference.key.stimulus_modality_key
        for reference in references
    } == {
        "RUNNING",
        "KAYAK",
    }


def test_unit_is_part_of_reference_key():
    h, observations = three_numeric_context()

    first_entry = h.entries[0]
    second_entry = h.entries[1]

    scored = observation(
        first_entry.stimulus,
        first_entry.responses[0],
        value=6.0,
        unit="score_0_10",
    )

    unitless = observation(
        second_entry.stimulus,
        second_entry.responses[0],
        value=6.0,
        unit=None,
    )

    references = build_refs(
        h,
        (
            scored,
            unitless,
        ),
    )

    assert len(references) == 2

    assert {
        reference.key.unit
        for reference in references
    } == {
        "score_0_10",
        None,
    }


def test_isolation_status_does_not_fragment_reference_key():
    s1 = stimulus(
        session_id=SESSION_A,
        observed_at=dt(19, 8),
        hash_char="a",
    )

    s2 = stimulus(
        session_id=SESSION_B,
        observed_at=dt(20, 8),
        hash_char="b",
    )

    a1 = association(
        s1,
        response_char="d",
        observed_at=dt(19, 14),
        isolation=ResponseIsolationStatus.UNKNOWN,
    )

    a2 = association(
        s2,
        response_char="e",
        observed_at=dt(20, 14),
        isolation=(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
        ),
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
        )
    )

    reference = build_refs(
        h,
        (
            observation(
                s1,
                a1,
                value=5.0,
            ),
            observation(
                s2,
                a2,
                value=7.0,
            ),
        ),
    )[0]

    assert reference.observed_observation_count == 2

    counts = isolation_counts(
        reference
    )

    assert counts["unknown"] == 1
    assert (
        counts[
            "no_intervening_stimulus_observed"
        ]
        == 1
    )

    assert (
        counts["intervening_stimulus_observed"]
        == 0
    )


def test_observation_not_present_in_history_fails_closed():
    h, observations = three_numeric_context()

    outside_stimulus = stimulus(
        session_id=(
            "55555555-5555-4555-8555-555555555555"
        ),
        observed_at=dt(22, 8),
        hash_char="8",
    )

    outside_association = association(
        outside_stimulus,
        response_char="7",
        observed_at=dt(22, 14),
    )

    outside_observation = observation(
        outside_stimulus,
        outside_association,
        value=5.0,
    )

    with pytest.raises(
        ValueError,
        match="not present",
    ):
        build_refs(
            h,
            (
                outside_observation,
            ),
        )


def test_tampered_observation_fails_closed():
    h, observations = three_numeric_context()

    tampered = replace(
        observations[0],
        value=9.0,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        build_refs(
            h,
            (
                tampered,
            ),
        )


def test_duplicate_observation_identity_fails_closed():
    h, observations = three_numeric_context()

    with pytest.raises(
        ValueError,
        match="Duplicate response metric observation",
    ):
        build_refs(
            h,
            (
                observations[0],
                observations[0],
            ),
        )


def test_reference_preserves_coverage_and_has_no_stronger_authority():
    h, observations = three_numeric_context()

    reference = build_refs(
        h,
        observations,
    )[0]

    assert (
        reference.stimulus_coverage
        == TrainingDynamicsHistoryCoverage.PARTIAL
    )

    assert (
        reference.response_coverage
        == TrainingDynamicsHistoryCoverage.PARTIAL
    )

    assert reference.causal_attribution_established is False
    assert reference.effect_inference_authorized is False
    assert reference.readiness_inference_authorized is False
    assert reference.performance_prediction_authorized is False
    assert reference.prescription_change_authorized is False

    assert not hasattr(
        reference,
        "baseline_established",
    )
    assert not hasattr(
        reference,
        "planning_authorized",
    )


def test_reference_is_deterministic_across_input_order_and_created_at():
    h, observations = three_numeric_context()

    first = build_descriptive_response_metric_references(
        history=h,
        observations=observations,
        created_at=dt(23, 22),
    )

    second = build_descriptive_response_metric_references(
        history=h,
        observations=tuple(
            reversed(
                observations
            )
        ),
        created_at=dt(23, 23),
    )

    assert len(first) == 1
    assert len(second) == 1

    assert (
        first[0].reference_id
        == second[0].reference_id
    )

    assert (
        first[0].content_hash
        == second[0].content_hash
    )

    assert (
        first[0].created_at
        != second[0].created_at
    )
