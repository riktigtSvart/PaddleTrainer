from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationPairEligibility,
    PersonalAssociationPermutationMethod,
    PersonalAssociationPredictorKey,
    PersonalAssociationSupportLimitationCode,
    PersonalAssociationSupportStatus,
    ResponseIsolationStatus,
    TrainingDynamicsHistoryCoverage,
    assess_personal_association_support,
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


def pair(
    index: int,
    x: float | None,
    y: float | None,
    *,
    session_id: str | None = None,
    eligibility=(
        PersonalAssociationPairEligibility
        .ELIGIBLE_NUMERIC_PAIR
    ),
    isolation=(
        ResponseIsolationStatus
        .NO_INTERVENING_STIMULUS_OBSERVED
    ),
) -> FakePair:
    intervening = (
        (f"intervening-{index}",)
        if (
            isolation
            == ResponseIsolationStatus
            .INTERVENING_STIMULUS_OBSERVED
        )
        else ()
    )

    return FakePair(
        pair_id=f"pair-{index}",
        content_hash=(
            f"{index:x}" * 64
        )[:64],
        workout_session_id=(
            session_id
            or f"session-{index}"
        ),
        athlete_id=ATHLETE,
        predictor_key=PREDICTOR_KEY,
        response_key=RESPONSE_KEY,
        isolation_status=isolation,
        intervening_stimulus_ids=intervening,
        eligibility=eligibility,
        predictor_numeric_value=x,
        response_numeric_value=y,
    )


def dataset(
    values,
    *,
    stimulus_coverage=(
        TrainingDynamicsHistoryCoverage.COMPLETE
    ),
    response_coverage=(
        TrainingDynamicsHistoryCoverage.COMPLETE
    ),
    isolations=None,
    duplicate_session=False,
    add_ineligible=False,
):
    values = tuple(values)

    if isolations is None:
        isolations = tuple(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
            for _ in values
        )

    built = []

    for index, (
        (x, y),
        isolation,
    ) in enumerate(
        zip(
            values,
            isolations,
        ),
        start=1,
    ):
        session_id = (
            "session-1"
            if (
                duplicate_session
                and index == 2
            )
            else f"session-{index}"
        )

        built.append(
            pair(
                index,
                x,
                y,
                session_id=session_id,
                isolation=isolation,
            )
        )

    if add_ineligible:
        built.append(
            pair(
                len(built) + 1,
                None,
                None,
                eligibility=(
                    PersonalAssociationPairEligibility
                    .INELIGIBLE
                ),
            )
        )

    eligible_count = sum(
        1
        for item in built
        if (
            item.eligibility
            == PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
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
        stimulus_coverage=stimulus_coverage,
        response_coverage=response_coverage,
        observed_pair_count=len(built),
        eligible_numeric_pair_count=eligible_count,
        ineligible_pair_count=(
            len(built) - eligible_count
        ),
        pairs=tuple(built),
        evidence_level_ceiling=(
            EffectEvidenceLevel.DESCRIPTIVE
        ),
    )


def estimate(source):
    return build_personal_association_estimate(
        dataset=source,
        created_at=dt(9),
    )


def assess(source, source_estimate=None, hour=10):
    if source_estimate is None:
        source_estimate = estimate(source)

    return assess_personal_association_support(
        dataset=source,
        estimate=source_estimate,
        created_at=dt(hour),
    )


def perfect_five():
    return dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        )
    )


def test_perfect_five_pair_exact_association_meets_c_criteria():
    result = assess(
        perfect_five()
    )

    assert (
        result.status
        == PersonalAssociationSupportStatus
        .SUPPORT_CRITERIA_MET
    )

    assert (
        result.permutation_method
        == PersonalAssociationPermutationMethod.EXACT
    )

    assert result.permutation_resample_count == 120
    assert result.permutation_extreme_count == 2

    assert result.permutation_p_value == pytest.approx(
        2.0 / 120.0
    )

    assert (
        result.permutation_p_value_upper_bound_95
        == pytest.approx(
            2.0 / 120.0
        )
    )

    assert result.jackknife_direction_stable is True

    assert result.limitation_codes == ()

    assert (
        result.evidence_level_ceiling
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert result.association_supported is False
    assert result.planning_authorized is False


def test_four_perfect_pairs_are_not_supported_by_exact_permutation_gate():
    source = dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
        )
    )

    result = assess(
        source
    )

    assert (
        result.status
        == PersonalAssociationSupportStatus
        .INSUFFICIENT
    )

    assert result.permutation_resample_count == 24

    assert result.permutation_p_value == pytest.approx(
        2.0 / 24.0
    )

    assert (
        PersonalAssociationSupportLimitationCode
        .PERMUTATION_SUPPORT_NOT_ESTABLISHED
        in result.limitation_codes
    )


def test_partial_coverage_blocks_support():
    source = replace(
        perfect_five(),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
    )

    result = assess(
        source
    )

    assert (
        result.status
        == PersonalAssociationSupportStatus
        .INSUFFICIENT
    )

    assert (
        PersonalAssociationSupportLimitationCode
        .STIMULUS_SOURCE_COVERAGE_PARTIAL
        in result.limitation_codes
    )


def test_unknown_isolation_blocks_support():
    source = dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        ),
        isolations=(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus.UNKNOWN,
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
        ),
    )

    result = assess(
        source
    )

    assert (
        PersonalAssociationSupportLimitationCode
        .UNKNOWN_ISOLATION_PRESENT
        in result.limitation_codes
    )

    assert (
        result.status
        == PersonalAssociationSupportStatus
        .INSUFFICIENT
    )


def test_intervening_stimulus_blocks_support():
    source = dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        ),
        isolations=(
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus
            .INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
            ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED,
        ),
    )

    result = assess(
        source
    )

    assert (
        PersonalAssociationSupportLimitationCode
        .INTERVENING_STIMULUS_PRESENT
        in result.limitation_codes
    )


def test_duplicate_workout_session_blocks_support():
    source = dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        ),
        duplicate_session=True,
    )

    result = assess(
        source
    )

    assert result.unique_workout_session_count == 4

    assert (
        PersonalAssociationSupportLimitationCode
        .DUPLICATE_WORKOUT_SESSION
        in result.limitation_codes
    )


def test_ineligible_pair_blocks_support_without_hiding_it():
    source = dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        ),
        add_ineligible=True,
    )

    result = assess(
        source
    )

    assert result.observed_pair_count == 6
    assert result.eligible_numeric_pair_count == 5
    assert result.ineligible_pair_count == 1

    assert (
        PersonalAssociationSupportLimitationCode
        .INELIGIBLE_PAIRS_PRESENT
        in result.limitation_codes
    )

    assert (
        result.status
        == PersonalAssociationSupportStatus
        .INSUFFICIENT
    )


def test_tampered_estimate_fails_closed():
    source = perfect_five()
    source_estimate = estimate(
        source
    )

    source_estimate = replace(
        source_estimate,
        content_hash="bad",
    )

    with pytest.raises(
        ValueError,
        match="estimate hash does not verify",
    ):
        assess(
            source,
            source_estimate,
        )


def test_assessment_identity_is_independent_of_materialization_time():
    source = perfect_five()
    source_estimate = estimate(
        source
    )

    first = assess(
        source,
        source_estimate,
        hour=10,
    )

    second = assess(
        source,
        source_estimate,
        hour=11,
    )

    assert (
        first.assessment_id
        == second.assessment_id
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
