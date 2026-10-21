from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationEstimateLimitationCode,
    PersonalAssociationEstimateStatus,
    PersonalAssociationPairEligibility,
    PersonalAssociationPredictorKey,
    build_personal_association_estimate,
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


def pair(
    index: int,
    x: float | None,
    y: float | None,
    *,
    eligible: bool = True,
    hash_valid: bool = True,
) -> FakePair:
    eligibility = (
        PersonalAssociationPairEligibility
        .ELIGIBLE_NUMERIC_PAIR
        if eligible
        else PersonalAssociationPairEligibility
        .INELIGIBLE
    )

    return FakePair(
        pair_id=(
            f"pair-{index}"
        ),
        content_hash=(
            f"{index:x}" * 64
        )[:64],
        workout_session_id=(
            f"session-{index}"
        ),
        athlete_id=ATHLETE,
        predictor_key=PREDICTOR_KEY,
        response_key=RESPONSE_KEY,
        eligibility=eligibility,
        predictor_numeric_value=x,
        response_numeric_value=y,
        hash_valid=hash_valid,
    )


def dataset(
    numeric_pairs: tuple[
        tuple[float, float],
        ...,
    ],
    *,
    ineligible_count: int = 0,
) -> FakeDataset:
    built = [
        pair(
            index,
            x,
            y,
        )
        for index, (x, y) in enumerate(
            numeric_pairs,
            start=1,
        )
    ]

    for offset in range(
        ineligible_count
    ):
        built.append(
            pair(
                len(built) + 1,
                None,
                None,
                eligible=False,
            )
        )

    return FakeDataset(
        dataset_id="dataset-1",
        content_hash="a" * 64,
        schema_version=(
            PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_ASSOCIATION_DATASET_RULES_V01
        ),
        athlete_id=ATHLETE,
        predictor_key=PREDICTOR_KEY,
        response_key=RESPONSE_KEY,
        observed_pair_count=len(built),
        eligible_numeric_pair_count=(
            len(numeric_pairs)
        ),
        ineligible_pair_count=(
            ineligible_count
        ),
        pairs=tuple(built),
        evidence_level_ceiling=(
            EffectEvidenceLevel.DESCRIPTIVE
        ),
    )


def estimate(
    source,
    *,
    created_hour: int = 9,
):
    return build_personal_association_estimate(
        dataset=source,
        created_at=dt(
            created_hour
        ),
    )


def test_estimates_perfect_positive_monotonic_relationship():
    result = estimate(
        dataset(
            (
                (1.0, 2.0),
                (2.0, 4.0),
                (3.0, 6.0),
            )
        )
    )

    assert (
        result.estimate_status
        == PersonalAssociationEstimateStatus.ESTIMATED
    )

    assert result.spearman_rho == pytest.approx(
        1.0
    )

    assert result.pearson_r == pytest.approx(
        1.0
    )

    assert result.limitation_codes == ()

    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert result.association_supported is False
    assert result.planning_authorized is False


def test_spearman_primary_preserves_nonlinear_monotonic_relationship():
    result = estimate(
        dataset(
            (
                (1.0, 1.0),
                (2.0, 4.0),
                (3.0, 9.0),
            )
        )
    )

    assert result.spearman_rho == pytest.approx(
        1.0
    )

    assert result.pearson_r is not None
    assert 0.0 < result.pearson_r < 1.0


def test_spearman_uses_average_ranks_for_ties():
    result = estimate(
        dataset(
            (
                (1.0, 1.0),
                (1.0, 2.0),
                (2.0, 2.0),
                (3.0, 3.0),
            )
        )
    )

    assert result.spearman_rho == pytest.approx(
        5.0 / 6.0
    )

    assert (
        result.distinct_predictor_value_count
        == 3
    )

    assert (
        result.distinct_response_value_count
        == 3
    )


def test_zero_eligible_pairs_is_not_estimable():
    result = estimate(
        dataset(
            (),
            ineligible_count=2,
        )
    )

    assert (
        result.estimate_status
        == PersonalAssociationEstimateStatus
        .NOT_ESTIMABLE
    )

    assert result.spearman_rho is None
    assert result.pearson_r is None

    assert result.limitation_codes == (
        PersonalAssociationEstimateLimitationCode
        .NO_ELIGIBLE_NUMERIC_PAIRS,
    )

    assert result.predictor_min is None
    assert result.response_min is None


def test_single_eligible_pair_is_not_estimable_but_is_described():
    result = estimate(
        dataset(
            (
                (0.0, 7.0),
            )
        )
    )

    assert (
        result.estimate_status
        == PersonalAssociationEstimateStatus
        .NOT_ESTIMABLE
    )

    assert result.predictor_min == 0.0
    assert result.predictor_max == 0.0
    assert result.predictor_range == 0.0

    assert result.response_min == 7.0
    assert result.response_max == 7.0
    assert result.response_range == 0.0

    assert result.limitation_codes == (
        PersonalAssociationEstimateLimitationCode
        .SINGLE_ELIGIBLE_NUMERIC_PAIR,
    )


def test_no_predictor_variation_is_not_estimable():
    result = estimate(
        dataset(
            (
                (4.0, 2.0),
                (4.0, 5.0),
                (4.0, 9.0),
            )
        )
    )

    assert (
        result.estimate_status
        == PersonalAssociationEstimateStatus
        .NOT_ESTIMABLE
    )

    assert result.spearman_rho is None
    assert result.pearson_r is None

    assert result.limitation_codes == (
        PersonalAssociationEstimateLimitationCode
        .NO_PREDICTOR_VARIATION,
    )


def test_no_response_variation_is_not_estimable():
    result = estimate(
        dataset(
            (
                (1.0, 5.0),
                (2.0, 5.0),
                (3.0, 5.0),
            )
        )
    )

    assert result.limitation_codes == (
        PersonalAssociationEstimateLimitationCode
        .NO_RESPONSE_VARIATION,
    )

    assert result.spearman_rho is None
    assert result.pearson_r is None


def test_ineligible_pairs_are_retained_in_counts_but_not_estimated():
    result = estimate(
        dataset(
            (
                (1.0, 3.0),
                (2.0, 6.0),
            ),
            ineligible_count=2,
        )
    )

    assert result.observed_pair_count == 4
    assert result.eligible_numeric_pair_count == 2
    assert result.ineligible_pair_count == 2

    assert len(
        result.source_pairs
    ) == 2

    assert result.spearman_rho == pytest.approx(
        1.0
    )


def test_invalid_source_dataset_hash_fails_closed():
    source = replace(
        dataset(
            (
                (1.0, 2.0),
                (2.0, 3.0),
            )
        ),
        hash_valid=False,
    )

    with pytest.raises(
        ValueError,
        match="dataset hash does not verify",
    ):
        estimate(
            source
        )


def test_invalid_source_pair_hash_fails_closed():
    source = dataset(
        (
            (1.0, 2.0),
            (2.0, 3.0),
        )
    )

    bad_pair = replace(
        source.pairs[0],
        hash_valid=False,
    )

    source = replace(
        source,
        pairs=(
            bad_pair,
            source.pairs[1],
        ),
    )

    with pytest.raises(
        ValueError,
        match="pair hash does not verify",
    ):
        estimate(
            source
        )


def test_stronger_source_authority_fails_closed():
    source = replace(
        dataset(
            (
                (1.0, 2.0),
                (2.0, 3.0),
            )
        ),
        association_supported=True,
    )

    with pytest.raises(
        ValueError,
        match="stronger authority",
    ):
        estimate(
            source
        )


def test_identity_and_hash_do_not_depend_on_materialization_time():
    source = dataset(
        (
            (1.0, 3.0),
            (2.0, 7.0),
            (4.0, 9.0),
        )
    )

    first = estimate(
        source,
        created_hour=9,
    )

    second = estimate(
        source,
        created_hour=10,
    )

    assert (
        first.estimate_id
        == second.estimate_id
    )

    assert (
        first.content_hash
        == second.content_hash
    )

    assert first.created_at != second.created_at

    assert first.verify_content_hash()
    assert second.verify_content_hash()

    assert first.association_supported is False
    assert (
        first.prospective_validation_established
        is False
    )
    assert (
        first.causal_attribution_established
        is False
    )
    assert (
        first.effect_inference_authorized
        is False
    )
    assert (
        first.readiness_inference_authorized
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
