from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

import pytest

from app.planning.domain.training_dynamics import (
    EffectEvidenceLevel,
    PersonalAssociationEvidenceStatus,
    PersonalAssociationPairEligibility,
    PersonalAssociationPredictorKey,
    PersonalAssociationSupportStatus,
    ResponseIsolationStatus,
    TrainingDynamicsHistoryCoverage,
    assess_personal_association_support,
    build_personal_association_estimate,
    build_personal_association_evidence,
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
    x: float | None,
    y: float | None,
    *,
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
        workout_session_id=f"session-{index}",
        athlete_id=ATHLETE,
        predictor_key=PREDICTOR_KEY,
        response_key=RESPONSE_KEY,
        isolation_status=isolation,
        intervening_stimulus_ids=intervening,
        eligibility=(
            PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
        ),
        predictor_numeric_value=x,
        response_numeric_value=y,
    )


def make_dataset(
    values,
    *,
    stimulus_coverage=(
        TrainingDynamicsHistoryCoverage.COMPLETE
    ),
    response_coverage=(
        TrainingDynamicsHistoryCoverage.COMPLETE
    ),
):
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
        repr(
            (
                values,
                stimulus_coverage.value,
                response_coverage.value,
            )
        ).encode("utf-8")
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
        stimulus_coverage=stimulus_coverage,
        response_coverage=response_coverage,
        observed_pair_count=len(pairs),
        eligible_numeric_pair_count=len(pairs),
        ineligible_pair_count=0,
        pairs=pairs,
        evidence_level_ceiling=(
            EffectEvidenceLevel.DESCRIPTIVE
        ),
    )


def source_chain(
    source,
):
    estimate = build_personal_association_estimate(
        dataset=source,
        created_at=dt(9),
    )

    support = assess_personal_association_support(
        dataset=source,
        estimate=estimate,
        created_at=dt(10),
    )

    return estimate, support


def build_evidence(
    source,
    estimate=None,
    support=None,
    *,
    hour=11,
):
    if (
        estimate is None
        or support is None
    ):
        estimate, support = source_chain(
            source
        )

    return build_personal_association_evidence(
        dataset=source,
        estimate=estimate,
        support=support,
        created_at=dt(hour),
    )


def perfect_five():
    return make_dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        )
    )


def perfect_four():
    return make_dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
        )
    )


def test_supported_c_promotes_to_association_supported():
    source = perfect_five()

    estimate, support = source_chain(
        source
    )

    assert (
        support.status
        == PersonalAssociationSupportStatus
        .SUPPORT_CRITERIA_MET
    )

    evidence = build_evidence(
        source,
        estimate,
        support,
    )

    assert (
        evidence.status
        == PersonalAssociationEvidenceStatus
        .ASSOCIATION_SUPPORTED
    )

    assert (
        evidence.evidence_level
        == EffectEvidenceLevel
        .ASSOCIATION_SUPPORTED
    )

    assert evidence.association_supported is True

    assert (
        evidence.source_dataset_id
        == source.dataset_id
    )

    assert (
        evidence.source_estimate_id
        == estimate.estimate_id
    )

    assert (
        evidence.source_support_assessment_id
        == support.assessment_id
    )

    assert evidence.verify_content_hash()


def test_insufficient_c_remains_descriptive():
    source = perfect_four()

    estimate, support = source_chain(
        source
    )

    assert (
        support.status
        == PersonalAssociationSupportStatus
        .INSUFFICIENT
    )

    evidence = build_evidence(
        source,
        estimate,
        support,
    )

    assert (
        evidence.status
        == PersonalAssociationEvidenceStatus
        .UNESTABLISHED
    )

    assert (
        evidence.evidence_level
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert evidence.association_supported is False

    assert evidence.support_limitation_codes


def test_not_assessable_c_remains_descriptive():
    source = make_dataset(
        (
            (1.0, 5.0),
            (2.0, 5.0),
            (3.0, 5.0),
            (4.0, 5.0),
            (5.0, 5.0),
        )
    )

    estimate, support = source_chain(
        source
    )

    assert (
        support.status
        == PersonalAssociationSupportStatus
        .NOT_ASSESSABLE
    )

    evidence = build_evidence(
        source,
        estimate,
        support,
    )

    assert (
        evidence.status
        == PersonalAssociationEvidenceStatus
        .UNESTABLISHED
    )

    assert (
        evidence.evidence_level
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert evidence.association_supported is False


def test_partial_coverage_cannot_be_promoted():
    source = make_dataset(
        (
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
            (4.0, 4.0),
            (5.0, 5.0),
        ),
        stimulus_coverage=(
            TrainingDynamicsHistoryCoverage.PARTIAL
        ),
    )

    estimate, support = source_chain(
        source
    )

    evidence = build_evidence(
        source,
        estimate,
        support,
    )

    assert (
        support.status
        == PersonalAssociationSupportStatus
        .INSUFFICIENT
    )

    assert (
        evidence.evidence_level
        == EffectEvidenceLevel.DESCRIPTIVE
    )

    assert evidence.association_supported is False


def test_tampered_dataset_fails_closed():
    source = perfect_five()

    estimate, support = source_chain(
        source
    )

    source = replace(
        source,
        hash_valid=False,
    )

    with pytest.raises(
        ValueError,
        match="dataset hash does not verify",
    ):
        build_evidence(
            source,
            estimate,
            support,
        )


def test_tampered_estimate_fails_closed():
    source = perfect_five()

    estimate, support = source_chain(
        source
    )

    estimate = replace(
        estimate,
        content_hash="bad",
    )

    with pytest.raises(
        ValueError,
        match="estimate hash does not verify",
    ):
        build_evidence(
            source,
            estimate,
            support,
        )


def test_tampered_support_fails_closed():
    source = perfect_five()

    estimate, support = source_chain(
        source
    )

    support = replace(
        support,
        content_hash="bad",
    )

    with pytest.raises(
        ValueError,
        match="support assessment hash does not verify",
    ):
        build_evidence(
            source,
            estimate,
            support,
        )


def test_cross_chain_support_is_rejected():
    source_a = perfect_five()

    estimate_a, _ = source_chain(
        source_a
    )

    source_b = make_dataset(
        (
            (10.0, 10.0),
            (20.0, 20.0),
            (30.0, 30.0),
            (40.0, 40.0),
            (50.0, 50.0),
        )
    )

    _, support_b = source_chain(
        source_b
    )

    with pytest.raises(
        ValueError,
        match=(
            "support assessment does not reference"
        ),
    ):
        build_evidence(
            source_a,
            estimate_a,
            support_b,
        )


def test_evidence_cannot_predate_support():
    source = perfect_five()

    estimate, support = source_chain(
        source
    )

    with pytest.raises(
        ValueError,
        match="cannot predate its sources",
    ):
        build_personal_association_evidence(
            dataset=source,
            estimate=estimate,
            support=support,
            created_at=dt(9),
        )


def test_identity_is_independent_of_materialization_time():
    source = perfect_five()

    estimate, support = source_chain(
        source
    )

    first = build_evidence(
        source,
        estimate,
        support,
        hour=11,
    )

    second = build_evidence(
        source,
        estimate,
        support,
        hour=12,
    )

    assert first.evidence_id == second.evidence_id
    assert first.content_hash == second.content_hash
    assert first.created_at != second.created_at

    assert first.verify_content_hash()
    assert second.verify_content_hash()

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
