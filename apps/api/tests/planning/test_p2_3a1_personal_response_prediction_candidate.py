from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

import pytest

from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPairEligibility,
    PersonalAssociationPredictorKey,
    PersonalResponsePredictionDirection,
    PersonalResponsePredictionLimitationCode,
    PersonalResponsePredictionStatus,
    ResponseIsolationStatus,
    TrainingDynamicsHistoryCoverage,
    assess_personal_association_support,
    build_personal_association_estimate,
    build_personal_association_evidence,
    build_personal_response_prediction_candidate,
    create_prediction_target_predictor_observation,
)
from app.planning.domain.training_dynamics.association_dataset import (
    PERSONAL_ASSOCIATION_DATASET_RULES_V01,
    PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01,
)


UTC = timezone.utc

ATHLETE = (
    "11111111-1111-4111-8111-111111111111"
)


def dt(hour: int) -> datetime:
    return datetime(
        2026,
        10,
        21,
        hour,
        tzinfo=UTC,
    )


PREDICTOR_KEY = PersonalAssociationPredictorKey(
    metric_key="training_load_index",
    unit="au",
)

RESPONSE_KEY = SimpleNamespace(
    metric_key="self_reported_fatigue_score",
    unit="score_0_10",
    response_timing="SAME_DAY",
    stimulus_modality_key="RUNNING",
)


@dataclass(frozen=True)
class FakePair:
    pair_id: str
    content_hash: str
    workout_session_id: str

    athlete_id: str
    predictor_key: object
    response_key: object

    isolation_status: ResponseIsolationStatus
    intervening_stimulus_ids: tuple[str, ...]

    eligibility: PersonalAssociationPairEligibility

    predictor_numeric_value: float | None
    response_numeric_value: float | None

    association_supported: bool = False
    causal_attribution_established: bool = False
    effect_inference_authorized: bool = False
    prediction_authorized: bool = False
    planning_authorized: bool = False

    hash_valid: bool = True

    def verify_content_hash(self) -> bool:
        return self.hash_valid


@dataclass(frozen=True)
class FakeDataset:
    dataset_id: str
    content_hash: str

    schema_version: str
    rules_version: str

    athlete_id: str

    predictor_key: object
    response_key: object

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    observed_pair_count: int
    eligible_numeric_pair_count: int
    ineligible_pair_count: int

    pairs: tuple[FakePair, ...]

    evidence_level_ceiling: EffectEvidenceLevel

    association_supported: bool = False
    prospective_validation_established: bool = False
    causal_attribution_established: bool = False
    effect_inference_authorized: bool = False
    readiness_inference_authorized: bool = False
    performance_prediction_authorized: bool = False
    prescription_change_authorized: bool = False
    planning_authorized: bool = False

    created_at: datetime = dt(8)

    hash_valid: bool = True

    def verify_content_hash(self) -> bool:
        return self.hash_valid


def make_pair(
    index: int,
    x: float,
    y: float,
) -> FakePair:
    return FakePair(
        pair_id=f"pair-{index}",
        content_hash=(
            f"{index:x}" * 64
        )[:64],
        workout_session_id=f"session-{index}",
        athlete_id=ATHLETE,
        predictor_key=PREDICTOR_KEY,
        response_key=RESPONSE_KEY,
        isolation_status=(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
        ),
        intervening_stimulus_ids=(),
        eligibility=(
            PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
        ),
        predictor_numeric_value=x,
        response_numeric_value=y,
    )


def make_dataset(values):
    values = tuple(values)

    pairs = tuple(
        make_pair(
            index,
            x,
            y,
        )
        for index, (x, y)
        in enumerate(
            values,
            start=1,
        )
    )

    digest = hashlib.sha256(
        repr(values).encode("utf-8")
    ).hexdigest()

    return FakeDataset(
        dataset_id=(
            "dataset-"
            + digest[:16]
        ),
        content_hash=digest,
        schema_version=(
            PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_ASSOCIATION_DATASET_RULES_V01
        ),
        athlete_id=ATHLETE,
        predictor_key=PREDICTOR_KEY,
        response_key=RESPONSE_KEY,
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.COMPLETE
        ),
        response_coverage=(
            TrainingDynamicsHistoryCoverage.COMPLETE
        ),
        observed_pair_count=len(pairs),
        eligible_numeric_pair_count=len(pairs),
        ineligible_pair_count=0,
        pairs=pairs,
        evidence_level_ceiling=(
            EffectEvidenceLevel.DESCRIPTIVE
        ),
    )


def positive_source():
    return make_dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        )
    )


def negative_source():
    return make_dataset(
        (
            (1.0, 5.0),
            (2.0, 4.0),
            (3.0, 3.0),
            (4.0, 2.0),
            (5.0, 1.0),
        )
    )


def insufficient_source():
    return make_dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
        )
    )


def source_chain(source):
    estimate = build_personal_association_estimate(
        dataset=source,
        created_at=dt(9),
    )

    support = assess_personal_association_support(
        dataset=source,
        estimate=estimate,
        created_at=dt(10),
    )

    evidence = build_personal_association_evidence(
        dataset=source,
        estimate=estimate,
        support=support,
        created_at=dt(11),
    )

    return estimate, support, evidence


def target(
    value: float,
    *,
    session_id="future-session",
    athlete_id=ATHLETE,
    modality="RUNNING",
):
    return create_prediction_target_predictor_observation(
        athlete_id=athlete_id,
        workout_session_id=session_id,
        source_evidence_id="future-execution-evidence",
        source_evidence_content_hash="f" * 64,
        predictor_key=PREDICTOR_KEY,
        stimulus_modality_key=modality,
        predictor_value=value,
        observed_at=dt(12),
        available_at=dt(12),
        created_at=dt(12),
    )


def prediction(
    source,
    target_observation,
    *,
    estimate=None,
    support=None,
    evidence=None,
    created_hour=13,
):
    if (
        estimate is None
        or support is None
        or evidence is None
    ):
        estimate, support, evidence = source_chain(
            source
        )

    return build_personal_response_prediction_candidate(
        dataset=source,
        estimate=estimate,
        support=support,
        association_evidence=evidence,
        target_predictor=target_observation,
        information_cutoff_at=dt(12),
        prediction_at=dt(13),
        created_at=dt(created_hour),
    )


def test_positive_association_predicts_above_reference():
    source = positive_source()

    result = prediction(
        source,
        target(4.5),
    )

    assert (
        result.status
        == PersonalResponsePredictionStatus
        .PREDICTION_AVAILABLE
    )

    assert (
        result.predicted_response_direction
        == PersonalResponsePredictionDirection
        .ABOVE_HISTORICAL_MEDIAN
    )

    assert result.historical_predictor_median == 3.0
    assert result.historical_response_median == 3.0
    assert result.target_predictor_value == 4.5

    assert result.response_prediction_available is True

    assert result.issuance_proof_established is False

    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.ASSOCIATION_SUPPORTED
    )

    assert result.association_supported is True

    assert (
        result.prospective_validation_established
        is False
    )

    assert result.planning_authorized is False
    assert result.verify_content_hash()


def test_negative_association_reverses_direction():
    source = negative_source()

    result = prediction(
        source,
        target(4.5),
    )

    assert result.source_spearman_rho < 0.0

    assert (
        result.predicted_response_direction
        == PersonalResponsePredictionDirection
        .BELOW_HISTORICAL_MEDIAN
    )


def test_predictor_below_median_uses_association_sign():
    source = positive_source()

    result = prediction(
        source,
        target(1.5),
    )

    assert (
        result.predicted_response_direction
        == PersonalResponsePredictionDirection
        .BELOW_HISTORICAL_MEDIAN
    )


def test_predictor_equal_to_median_is_withheld():
    source = positive_source()

    result = prediction(
        source,
        target(3.0),
    )

    assert (
        result.status
        == PersonalResponsePredictionStatus.WITHHELD
    )

    assert result.predicted_response_direction is None

    assert (
        PersonalResponsePredictionLimitationCode
        .TARGET_PREDICTOR_EQUALS_HISTORICAL_MEDIAN
        in result.limitation_codes
    )


def test_extrapolation_outside_historical_range_is_withheld():
    source = positive_source()

    result = prediction(
        source,
        target(6.0),
    )

    assert (
        result.status
        == PersonalResponsePredictionStatus.WITHHELD
    )

    assert result.predicted_response_direction is None

    assert (
        PersonalResponsePredictionLimitationCode
        .TARGET_PREDICTOR_OUTSIDE_HISTORICAL_RANGE
        in result.limitation_codes
    )


def test_historical_session_cannot_be_prediction_target():
    source = positive_source()

    with pytest.raises(
        ValueError,
        match="already present in historical model sources",
    ):
        prediction(
            source,
            target(
                4.5,
                session_id="session-1",
            ),
        )


def test_context_mismatch_fails_closed():
    source = positive_source()

    with pytest.raises(
        ValueError,
        match="modality does not match",
    ):
        prediction(
            source,
            target(
                4.5,
                modality="CYCLING",
            ),
        )


def test_unestablished_association_cannot_generate_prediction():
    source = insufficient_source()

    estimate, support, evidence = source_chain(
        source
    )

    with pytest.raises(
        ValueError,
        match="requires ASSOCIATION_SUPPORTED evidence",
    ):
        prediction(
            source,
            target(3.5),
            estimate=estimate,
            support=support,
            evidence=evidence,
        )


def test_tampered_association_evidence_fails_closed():
    source = positive_source()

    estimate, support, evidence = source_chain(
        source
    )

    evidence = replace(
        evidence,
        content_hash="bad",
    )

    with pytest.raises(
        ValueError,
        match="evidence hash does not verify",
    ):
        prediction(
            source,
            target(4.5),
            estimate=estimate,
            support=support,
            evidence=evidence,
        )


def test_candidate_identity_ignores_materialization_time():
    source = positive_source()

    estimate, support, evidence = source_chain(
        source
    )

    target_observation = target(
        4.5
    )

    first = prediction(
        source,
        target_observation,
        estimate=estimate,
        support=support,
        evidence=evidence,
        created_hour=13,
    )

    second = prediction(
        source,
        target_observation,
        estimate=estimate,
        support=support,
        evidence=evidence,
        created_hour=14,
    )

    assert first.candidate_id == second.candidate_id
    assert first.content_hash == second.content_hash

    assert first.created_at != second.created_at

    assert first.verify_content_hash()
    assert second.verify_content_hash()

    assert first.issuance_proof_established is False
    assert (
        first.prospective_validation_established
        is False
    )
    assert (
        first.performance_prediction_authorized
        is False
    )
    assert (
        first.prescription_change_authorized
        is False
    )
    assert first.planning_authorized is False
