from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import KnowledgeStatus
from app.planning.domain.response_evidence import (
    TrainingResponseLinkBasis,
    TrainingResponseMeasurement,
    TrainingResponseTiming,
)
from app.planning.domain.training_dynamics.association_dataset import (
    PersonalAssociationPairEligibility,
    PersonalAssociationPairExclusionReason,
    PersonalAssociationPredictorKey,
    build_personal_association_dataset,
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
    StimulusFeature,
    build_observed_response_association,
    build_realized_training_stimulus,
)
from app.planning.domain.training_dynamics.personal_reference import (
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

PREDICTOR_KEY = "training_load_index"
PREDICTOR_UNIT = "au"


def dt(day: int, hour: int) -> datetime:
    return datetime(
        2026,
        10,
        day,
        hour,
        tzinfo=UTC,
    )


def predictor_feature(
    *,
    knowledge_status=KnowledgeStatus.KNOWN,
    value=100.0,
    unit=PREDICTOR_UNIT,
):
    return StimulusFeature(
        metric_key=PREDICTOR_KEY,
        knowledge_status=knowledge_status,
        value=value,
        unit=unit,
    )


def stimulus(
    *,
    session_id: str,
    day: int,
    hash_char: str,
    features=(),
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
        features=tuple(features),
        created_at=dt(day, 9),
    )


def association(
    source_stimulus,
    *,
    response_char: str,
    day: int,
):
    observed = dt(day, 14)

    return build_observed_response_association(
        association_id=(
            "pt-response-association:"
            f"a1:{response_char}"
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


def response_observation(
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
    feature_a=None,
    feature_b=None,
    response_status=KnowledgeStatus.KNOWN,
    response_value=6.0,
    two_sessions=False,
):
    if feature_a is None:
        feature_a = predictor_feature()

    s1 = stimulus(
        session_id=SESSION_A,
        day=19,
        hash_char="a",
        features=(
            ()
            if feature_a is False
            else (feature_a,)
        ),
    )

    a1 = association(
        s1,
        response_char="d",
        day=19,
    )

    o1 = response_observation(
        s1,
        a1,
        knowledge_status=response_status,
        value=response_value,
    )

    entries = [
        TrainingDynamicsHistoryEntry(
            stimulus=s1,
            responses=(a1,),
        )
    ]

    observations = [o1]

    if two_sessions:
        if feature_b is None:
            feature_b = predictor_feature(
                value=200.0,
            )

        s2 = stimulus(
            session_id=SESSION_B,
            day=21,
            hash_char="b",
            features=(
                ()
                if feature_b is False
                else (feature_b,)
            ),
        )

        a2 = association(
            s2,
            response_char="e",
            day=21,
        )

        o2 = response_observation(
            s2,
            a2,
            value=8.0,
        )

        entries.append(
            TrainingDynamicsHistoryEntry(
                stimulus=s2,
                responses=(a2,),
            )
        )

        observations.append(o2)

    history = build_training_dynamics_history(
        history_id="pt-training-dynamics-history:p2-2a1",
        athlete_id=ATHLETE,
        window_start_at=dt(18, 0),
        as_of=dt(23, 20),
        information_cutoff_at=dt(23, 20),
        stimulus_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
        response_coverage=TrainingDynamicsHistoryCoverage.COMPLETE,
        entries=tuple(entries),
        source_evidence_ids=tuple(
            response.response_evidence_id
            for entry in entries
            for response in entry.responses
        ),
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

    assert len(references) == 1

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

    personal = build_personal_response_reference_assessment(
        reference=references[0],
        sufficiency=d2[0],
        created_at=dt(24, 1),
    )

    return (
        history,
        references[0],
        personal,
        tuple(observations),
    )


def build_dataset(
    history,
    reference,
    personal,
    observations,
    *,
    predictor_unit=PREDICTOR_UNIT,
    created_at=None,
):
    return build_personal_association_dataset(
        history=history,
        response_reference=reference,
        personal_reference=personal,
        observations=tuple(observations),
        predictor_key=PersonalAssociationPredictorKey(
            metric_key=PREDICTOR_KEY,
            unit=predictor_unit,
        ),
        created_at=created_at or dt(24, 2),
    )


def reasons(pair):
    return set(
        pair.exclusion_reasons
    )


def test_numeric_stimulus_and_response_create_eligible_pair():
    h, reference, personal, observations = build_context()

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    assert dataset.observed_pair_count == 1
    assert dataset.eligible_numeric_pair_count == 1
    assert dataset.ineligible_pair_count == 0

    pair = dataset.pairs[0]

    assert (
        pair.eligibility
        == PersonalAssociationPairEligibility
        .ELIGIBLE_NUMERIC_PAIR
    )

    assert pair.predictor_numeric_value == 100.0
    assert pair.response_numeric_value == 6.0
    assert pair.exclusion_reasons == ()

    assert dataset.verify_content_hash()
    assert pair.verify_content_hash()


def test_numeric_zero_is_preserved_as_real_predictor_value():
    h, reference, personal, observations = build_context(
        feature_a=predictor_feature(
            value=0.0,
        )
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    pair = dataset.pairs[0]

    assert pair.predictor_numeric_value == 0.0
    assert (
        pair.eligibility
        == PersonalAssociationPairEligibility
        .ELIGIBLE_NUMERIC_PAIR
    )


def test_non_known_response_is_not_silently_zero():
    h, reference, personal, observations = build_context(
        response_status=KnowledgeStatus.UNKNOWN,
        response_value=None,
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    pair = dataset.pairs[0]

    assert pair.response_numeric_value is None

    assert (
        PersonalAssociationPairExclusionReason
        .RESPONSE_NON_KNOWN
        in reasons(pair)
    )

    assert (
        pair.eligibility
        == PersonalAssociationPairEligibility.INELIGIBLE
    )


def test_missing_predictor_is_explicit_exclusion():
    h, reference, personal, observations = build_context(
        feature_a=False,
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    pair = dataset.pairs[0]

    assert pair.predictor_knowledge_status is None
    assert pair.predictor_numeric_value is None

    assert reasons(pair) == {
        PersonalAssociationPairExclusionReason
        .PREDICTOR_MISSING
    }


def test_non_known_predictor_is_explicit_exclusion():
    h, reference, personal, observations = build_context(
        feature_a=predictor_feature(
            knowledge_status=KnowledgeStatus.UNKNOWN,
            value=None,
        )
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    pair = dataset.pairs[0]

    assert (
        PersonalAssociationPairExclusionReason
        .PREDICTOR_NON_KNOWN
        in reasons(pair)
    )

    assert pair.predictor_numeric_value is None


def test_known_non_numeric_predictor_is_explicit_exclusion():
    h, reference, personal, observations = build_context(
        feature_a=predictor_feature(
            value="high",
        )
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    pair = dataset.pairs[0]

    assert (
        PersonalAssociationPairExclusionReason
        .PREDICTOR_KNOWN_NON_NUMERIC
        in reasons(pair)
    )


def test_predictor_unit_mismatch_is_not_coerced():
    h, reference, personal, observations = build_context(
        feature_a=predictor_feature(
            value=100.0,
            unit="other_unit",
        )
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    pair = dataset.pairs[0]

    assert pair.predictor_observed_unit == "other_unit"
    assert pair.predictor_numeric_value is None

    assert (
        PersonalAssociationPairExclusionReason
        .PREDICTOR_UNIT_MISMATCH
        in reasons(pair)
    )


def test_multiple_exclusion_reasons_are_preserved():
    h, reference, personal, observations = build_context(
        feature_a=False,
        response_status=KnowledgeStatus.UNKNOWN,
        response_value=None,
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    assert reasons(dataset.pairs[0]) == {
        PersonalAssociationPairExclusionReason
        .PREDICTOR_MISSING,
        PersonalAssociationPairExclusionReason
        .RESPONSE_NON_KNOWN,
    }


def test_response_subset_is_rejected_to_prevent_cherry_picking():
    h, reference, personal, observations = build_context(
        two_sessions=True,
    )

    with pytest.raises(
        ValueError,
        match="exactly match",
    ):
        build_dataset(
            h,
            reference,
            personal,
            observations[:1],
        )


def test_tampered_observation_fails_closed():
    h, reference, personal, observations = build_context()

    tampered = replace(
        observations[0],
        value=999.0,
    )

    with pytest.raises(
        ValueError,
        match="hash does not verify",
    ):
        build_dataset(
            h,
            reference,
            personal,
            (tampered,),
        )


def test_mismatched_personal_reference_fails_closed():
    h1, reference1, _, observations1 = build_context()

    h2, reference2, personal2, _ = build_context(
        two_sessions=True,
    )

    assert reference1.content_hash != reference2.content_hash
    assert h1.content_hash != h2.content_hash

    with pytest.raises(
        ValueError,
        match="does not belong",
    ):
        build_dataset(
            h1,
            reference1,
            personal2,
            observations1,
        )


def test_a1_never_claims_association_even_with_multiple_eligible_pairs():
    h, reference, personal, observations = build_context(
        two_sessions=True,
    )

    dataset = build_dataset(
        h,
        reference,
        personal,
        observations,
    )

    assert dataset.eligible_numeric_pair_count == 2

    assert (
        dataset.evidence_level_ceiling
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert dataset.association_supported is False
    assert dataset.prospective_validation_established is False
    assert dataset.causal_attribution_established is False
    assert dataset.effect_inference_authorized is False
    assert dataset.readiness_inference_authorized is False
    assert dataset.performance_prediction_authorized is False
    assert dataset.prescription_change_authorized is False
    assert dataset.planning_authorized is False

    for pair in dataset.pairs:
        assert pair.association_supported is False
        assert pair.causal_attribution_established is False
        assert pair.effect_inference_authorized is False
        assert pair.prediction_authorized is False
        assert pair.planning_authorized is False


def test_identity_and_hash_are_stable_across_materialization_time():
    h, reference, personal, observations = build_context(
        two_sessions=True,
    )

    first = build_dataset(
        h,
        reference,
        personal,
        observations,
        created_at=dt(24, 2),
    )

    second = build_dataset(
        h,
        reference,
        personal,
        tuple(
            reversed(
                observations
            )
        ),
        created_at=dt(24, 3),
    )

    assert first.dataset_id == second.dataset_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at

    assert tuple(
        pair.pair_id
        for pair in first.pairs
    ) == tuple(
        pair.pair_id
        for pair in second.pairs
    )
