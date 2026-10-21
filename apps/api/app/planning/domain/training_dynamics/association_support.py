from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import itertools
import json
import math
import random

from ..common.time import to_utc
from .association_dataset import (
    PERSONAL_ASSOCIATION_DATASET_RULES_V01,
    PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01,
    PersonalAssociationDataset,
    PersonalAssociationPairEligibility,
    PersonalAssociationPredictorKey,
)
from .association_estimate import (
    PERSONAL_ASSOCIATION_ESTIMATE_RULES_V01,
    PERSONAL_ASSOCIATION_ESTIMATE_SCHEMA_V01,
    PersonalAssociationEstimate,
    PersonalAssociationEstimateStatus,
)
from .history import TrainingDynamicsHistoryCoverage
from .models import (
    EffectEvidenceLevel,
    ResponseIsolationStatus,
)
from .response_reference import ResponseMetricReferenceKey


PERSONAL_ASSOCIATION_SUPPORT_SCHEMA_V01 = (
    "personal-association-support-v0.1"
)

PERSONAL_ASSOCIATION_SUPPORT_RULES_V01 = (
    "personal-association-support-rules-v0.1"
)

PERSONAL_ASSOCIATION_SUPPORT_ALPHA_V01 = 0.05

PERSONAL_ASSOCIATION_EXACT_PERMUTATION_MAX_PAIRS_V01 = 9

PERSONAL_ASSOCIATION_MONTE_CARLO_RESAMPLES_V01 = 20_000

_WILSON_Z_95 = 1.959963984540054


class PersonalAssociationSupportStatus(StrEnum):
    NOT_ASSESSABLE = "NOT_ASSESSABLE"
    INSUFFICIENT = "INSUFFICIENT"
    SUPPORT_CRITERIA_MET = "SUPPORT_CRITERIA_MET"


class PersonalAssociationPermutationMethod(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXACT = "EXACT"
    MONTE_CARLO = "MONTE_CARLO"


class PersonalAssociationSupportLimitationCode(StrEnum):
    ESTIMATE_NOT_ESTIMABLE = (
        "ESTIMATE_NOT_ESTIMABLE"
    )

    STIMULUS_SOURCE_COVERAGE_PARTIAL = (
        "STIMULUS_SOURCE_COVERAGE_PARTIAL"
    )
    STIMULUS_SOURCE_COVERAGE_UNKNOWN = (
        "STIMULUS_SOURCE_COVERAGE_UNKNOWN"
    )

    RESPONSE_SOURCE_COVERAGE_PARTIAL = (
        "RESPONSE_SOURCE_COVERAGE_PARTIAL"
    )
    RESPONSE_SOURCE_COVERAGE_UNKNOWN = (
        "RESPONSE_SOURCE_COVERAGE_UNKNOWN"
    )

    INELIGIBLE_PAIRS_PRESENT = (
        "INELIGIBLE_PAIRS_PRESENT"
    )

    DUPLICATE_WORKOUT_SESSION = (
        "DUPLICATE_WORKOUT_SESSION"
    )

    UNKNOWN_ISOLATION_PRESENT = (
        "UNKNOWN_ISOLATION_PRESENT"
    )
    INTERVENING_STIMULUS_PRESENT = (
        "INTERVENING_STIMULUS_PRESENT"
    )

    SPEARMAN_PEARSON_DIRECTION_DISAGREEMENT = (
        "SPEARMAN_PEARSON_DIRECTION_DISAGREEMENT"
    )

    JACKKNIFE_NOT_ESTIMABLE = (
        "JACKKNIFE_NOT_ESTIMABLE"
    )
    JACKKNIFE_DIRECTION_UNSTABLE = (
        "JACKKNIFE_DIRECTION_UNSTABLE"
    )

    PERMUTATION_SUPPORT_NOT_ESTABLISHED = (
        "PERMUTATION_SUPPORT_NOT_ESTABLISHED"
    )


@dataclass(frozen=True)
class PersonalAssociationSupportAssessment:
    """Fail-closed P2.2C support/robustness assessment.

    SUPPORT_CRITERIA_MET means only that this historical, within-person,
    exact-context dataset satisfied the v0.1 association-support gate.

    It does not itself promote the evidence level, establish causality,
    validate prediction, infer readiness, or authorize planning.

    P2.2D owns any explicit ASSOCIATION_SUPPORTED evidence artifact.
    """

    assessment_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_dataset_id: str
    source_dataset_content_hash: str

    source_estimate_id: str
    source_estimate_content_hash: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    stimulus_coverage: TrainingDynamicsHistoryCoverage
    response_coverage: TrainingDynamicsHistoryCoverage

    observed_pair_count: int
    eligible_numeric_pair_count: int
    ineligible_pair_count: int

    unique_workout_session_count: int

    clean_isolation_pair_count: int
    unknown_isolation_pair_count: int
    intervening_isolation_pair_count: int

    estimate_status: PersonalAssociationEstimateStatus

    spearman_rho: float | None
    pearson_r: float | None

    spearman_pearson_direction_consistent: bool | None

    jackknife_evaluated_count: int
    jackknife_min_spearman_rho: float | None
    jackknife_max_spearman_rho: float | None
    jackknife_direction_stable: bool | None

    permutation_method: PersonalAssociationPermutationMethod
    permutation_resample_count: int
    permutation_extreme_count: int | None

    permutation_p_value: float | None
    permutation_p_value_upper_bound_95: float | None

    support_alpha: float

    status: PersonalAssociationSupportStatus

    limitation_codes: tuple[
        PersonalAssociationSupportLimitationCode,
        ...,
    ]

    # C is still an assessment layer. Promotion belongs to D.
    evidence_level_ceiling: EffectEvidenceLevel

    association_supported: bool
    prospective_validation_established: bool
    causal_attribution_established: bool
    effect_inference_authorized: bool
    readiness_inference_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool
    planning_authorized: bool

    created_at: datetime
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            self.content_hash
            == _assessment_content_hash(self)
        )


def _enum_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value

    return getattr(
        value,
        "value",
        value,
    )


def _predictor_key_payload(
    key: PersonalAssociationPredictorKey,
) -> dict[str, object]:
    return {
        "metric_key": key.metric_key,
        "unit": key.unit,
    }


def _response_key_payload(
    key: ResponseMetricReferenceKey,
) -> dict[str, object]:
    return {
        "metric_key": key.metric_key,
        "unit": key.unit,
        "response_timing": _enum_value(
            key.response_timing
        ),
        "stimulus_modality_key": (
            key.stimulus_modality_key
        ),
    }


def _assessment_payload(
    assessment: PersonalAssociationSupportAssessment,
) -> dict[str, object]:
    return {
        "schema_version": assessment.schema_version,
        "rules_version": assessment.rules_version,

        "athlete_id": assessment.athlete_id,

        "source_dataset_id": (
            assessment.source_dataset_id
        ),
        "source_dataset_content_hash": (
            assessment.source_dataset_content_hash
        ),

        "source_estimate_id": (
            assessment.source_estimate_id
        ),
        "source_estimate_content_hash": (
            assessment.source_estimate_content_hash
        ),

        "predictor_key": _predictor_key_payload(
            assessment.predictor_key
        ),
        "response_key": _response_key_payload(
            assessment.response_key
        ),

        "stimulus_coverage": (
            assessment.stimulus_coverage.value
        ),
        "response_coverage": (
            assessment.response_coverage.value
        ),

        "observed_pair_count": (
            assessment.observed_pair_count
        ),
        "eligible_numeric_pair_count": (
            assessment.eligible_numeric_pair_count
        ),
        "ineligible_pair_count": (
            assessment.ineligible_pair_count
        ),

        "unique_workout_session_count": (
            assessment.unique_workout_session_count
        ),

        "clean_isolation_pair_count": (
            assessment.clean_isolation_pair_count
        ),
        "unknown_isolation_pair_count": (
            assessment.unknown_isolation_pair_count
        ),
        "intervening_isolation_pair_count": (
            assessment.intervening_isolation_pair_count
        ),

        "estimate_status": (
            assessment.estimate_status.value
        ),

        "spearman_rho": assessment.spearman_rho,
        "pearson_r": assessment.pearson_r,

        "spearman_pearson_direction_consistent": (
            assessment
            .spearman_pearson_direction_consistent
        ),

        "jackknife_evaluated_count": (
            assessment.jackknife_evaluated_count
        ),
        "jackknife_min_spearman_rho": (
            assessment.jackknife_min_spearman_rho
        ),
        "jackknife_max_spearman_rho": (
            assessment.jackknife_max_spearman_rho
        ),
        "jackknife_direction_stable": (
            assessment.jackknife_direction_stable
        ),

        "permutation_method": (
            assessment.permutation_method.value
        ),
        "permutation_resample_count": (
            assessment.permutation_resample_count
        ),
        "permutation_extreme_count": (
            assessment.permutation_extreme_count
        ),
        "permutation_p_value": (
            assessment.permutation_p_value
        ),
        "permutation_p_value_upper_bound_95": (
            assessment
            .permutation_p_value_upper_bound_95
        ),

        "support_alpha": assessment.support_alpha,

        "status": assessment.status.value,

        "limitation_codes": [
            item.value
            for item in assessment.limitation_codes
        ],

        "evidence_level_ceiling": (
            assessment.evidence_level_ceiling.value
        ),

        "association_supported": (
            assessment.association_supported
        ),
        "prospective_validation_established": (
            assessment.prospective_validation_established
        ),
        "causal_attribution_established": (
            assessment.causal_attribution_established
        ),
        "effect_inference_authorized": (
            assessment.effect_inference_authorized
        ),
        "readiness_inference_authorized": (
            assessment.readiness_inference_authorized
        ),
        "performance_prediction_authorized": (
            assessment.performance_prediction_authorized
        ),
        "prescription_change_authorized": (
            assessment.prescription_change_authorized
        ),
        "planning_authorized": (
            assessment.planning_authorized
        ),
    }


def _assessment_content_hash(
    assessment: PersonalAssociationSupportAssessment,
) -> str:
    canonical = json.dumps(
        _assessment_payload(assessment),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _finite_numeric(
    value: object,
    *,
    field_name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise ValueError(
            f"{field_name} must be numeric."
        )

    numeric = float(value)

    if not math.isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite."
        )

    if numeric == 0.0:
        return 0.0

    return numeric


def _average_ranks(
    values: tuple[float, ...],
) -> tuple[float, ...]:
    ordered = sorted(
        enumerate(values),
        key=lambda item: (
            item[1],
            item[0],
        ),
    )

    ranks = [
        0.0
        for _ in values
    ]

    index = 0

    while index < len(ordered):
        end = index + 1

        while (
            end < len(ordered)
            and ordered[end][1]
            == ordered[index][1]
        ):
            end += 1

        average_rank = (
            (index + 1)
            + end
        ) / 2.0

        for position in range(
            index,
            end,
        ):
            ranks[
                ordered[position][0]
            ] = average_rank

        index = end

    return tuple(ranks)


def _pearson(
    x: tuple[float, ...],
    y: tuple[float, ...],
) -> float | None:
    if len(x) != len(y):
        raise ValueError(
            "Correlation inputs must have equal length."
        )

    if len(x) < 2:
        return None

    x_scale = max(
        abs(value)
        for value in x
    )

    y_scale = max(
        abs(value)
        for value in y
    )

    if (
        x_scale == 0.0
        or y_scale == 0.0
    ):
        return None

    xs = tuple(
        value / x_scale
        for value in x
    )

    ys = tuple(
        value / y_scale
        for value in y
    )

    x_mean = math.fsum(xs) / len(xs)
    y_mean = math.fsum(ys) / len(ys)

    xc = tuple(
        value - x_mean
        for value in xs
    )

    yc = tuple(
        value - y_mean
        for value in ys
    )

    x_ss = math.fsum(
        value * value
        for value in xc
    )

    y_ss = math.fsum(
        value * value
        for value in yc
    )

    if (
        x_ss <= 0.0
        or y_ss <= 0.0
    ):
        return None

    numerator = math.fsum(
        xv * yv
        for xv, yv in zip(
            xc,
            yc,
        )
    )

    result = numerator / math.sqrt(
        x_ss * y_ss
    )

    result = max(
        -1.0,
        min(
            1.0,
            result,
        ),
    )

    if result == 0.0:
        return 0.0

    return result


def _spearman(
    x: tuple[float, ...],
    y: tuple[float, ...],
) -> float | None:
    if len(x) != len(y):
        raise ValueError(
            "Correlation inputs must have equal length."
        )

    if len(x) < 2:
        return None

    return _pearson(
        _average_ranks(x),
        _average_ranks(y),
    )


def _sign(value: float) -> int:
    if abs(value) <= 1e-15:
        return 0

    return 1 if value > 0.0 else -1


def _ordered_limitations(
    values,
) -> tuple[
    PersonalAssociationSupportLimitationCode,
    ...,
]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: item.value,
        )
    )


def _coverage_limitations(
    *,
    stimulus_coverage: TrainingDynamicsHistoryCoverage,
    response_coverage: TrainingDynamicsHistoryCoverage,
) -> list[
    PersonalAssociationSupportLimitationCode
]:
    limitations: list[
        PersonalAssociationSupportLimitationCode
    ] = []

    if (
        stimulus_coverage
        == TrainingDynamicsHistoryCoverage.PARTIAL
    ):
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .STIMULUS_SOURCE_COVERAGE_PARTIAL
        )

    elif (
        stimulus_coverage
        == TrainingDynamicsHistoryCoverage.UNKNOWN
    ):
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .STIMULUS_SOURCE_COVERAGE_UNKNOWN
        )

    if (
        response_coverage
        == TrainingDynamicsHistoryCoverage.PARTIAL
    ):
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .RESPONSE_SOURCE_COVERAGE_PARTIAL
        )

    elif (
        response_coverage
        == TrainingDynamicsHistoryCoverage.UNKNOWN
    ):
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .RESPONSE_SOURCE_COVERAGE_UNKNOWN
        )

    return limitations


def _wilson_upper_bound_95(
    *,
    successes: int,
    trials: int,
) -> float:
    if trials <= 0:
        raise ValueError(
            "Wilson interval requires positive trials."
        )

    if (
        successes < 0
        or successes > trials
    ):
        raise ValueError(
            "Invalid Wilson success count."
        )

    p_hat = successes / trials
    z2 = _WILSON_Z_95 * _WILSON_Z_95

    denominator = (
        1.0
        + z2 / trials
    )

    center = (
        p_hat
        + z2 / (2.0 * trials)
    )

    margin = (
        _WILSON_Z_95
        * math.sqrt(
            (
                p_hat
                * (1.0 - p_hat)
                / trials
            )
            + (
                z2
                / (
                    4.0
                    * trials
                    * trials
                )
            )
        )
    )

    return min(
        1.0,
        (
            center + margin
        ) / denominator,
    )


def _rank_permutation_inputs(
    x: tuple[float, ...],
    y: tuple[float, ...],
):
    x_ranks = _average_ranks(x)
    y_ranks = _average_ranks(y)

    x_mean = math.fsum(
        x_ranks
    ) / len(x_ranks)

    y_mean = math.fsum(
        y_ranks
    ) / len(y_ranks)

    xc = tuple(
        value - x_mean
        for value in x_ranks
    )

    yc = tuple(
        value - y_mean
        for value in y_ranks
    )

    denominator = math.sqrt(
        math.fsum(
            value * value
            for value in xc
        )
        * math.fsum(
            value * value
            for value in yc
        )
    )

    if denominator <= 0.0:
        raise ValueError(
            "Permutation test requires rank variation."
        )

    return xc, yc, denominator


def _permuted_rho(
    *,
    xc: tuple[float, ...],
    yc: tuple[float, ...],
    denominator: float,
    permutation: tuple[int, ...],
) -> float:
    numerator = math.fsum(
        xc[index]
        * yc[permutation[index]]
        for index in range(
            len(permutation)
        )
    )

    result = numerator / denominator

    return max(
        -1.0,
        min(
            1.0,
            result,
        ),
    )


def _permutation_support(
    *,
    x: tuple[float, ...],
    y: tuple[float, ...],
    observed_rho: float,
    seed_source: str,
):
    count = len(x)

    xc, yc, denominator = (
        _rank_permutation_inputs(
            x,
            y,
        )
    )

    observed_abs = abs(
        observed_rho
    )

    epsilon = 1e-12

    if (
        count
        <= PERSONAL_ASSOCIATION_EXACT_PERMUTATION_MAX_PAIRS_V01
    ):
        total = math.factorial(
            count
        )

        extreme = 0

        for permutation in itertools.permutations(
            range(count)
        ):
            rho = _permuted_rho(
                xc=xc,
                yc=yc,
                denominator=denominator,
                permutation=permutation,
            )

            if (
                abs(rho)
                >= observed_abs - epsilon
            ):
                extreme += 1

        p_value = (
            extreme / total
        )

        return (
            PersonalAssociationPermutationMethod.EXACT,
            total,
            extreme,
            p_value,
            p_value,
        )

    resamples = (
        PERSONAL_ASSOCIATION_MONTE_CARLO_RESAMPLES_V01
    )

    seed_digest = hashlib.sha256(
        (
            PERSONAL_ASSOCIATION_SUPPORT_RULES_V01
            + ":"
            + seed_source
        ).encode("utf-8")
    ).hexdigest()

    rng = random.Random(
        int(
            seed_digest[:16],
            16,
        )
    )

    extreme = 0
    base = list(
        range(count)
    )

    for _ in range(
        resamples
    ):
        permutation = list(
            base
        )

        rng.shuffle(
            permutation
        )

        rho = _permuted_rho(
            xc=xc,
            yc=yc,
            denominator=denominator,
            permutation=tuple(
                permutation
            ),
        )

        if (
            abs(rho)
            >= observed_abs - epsilon
        ):
            extreme += 1

    # Plus-one correction for a finite Monte Carlo randomization test.
    p_value = (
        extreme + 1
    ) / (
        resamples + 1
    )

    upper_bound = (
        _wilson_upper_bound_95(
            successes=extreme,
            trials=resamples,
        )
    )

    return (
        PersonalAssociationPermutationMethod
        .MONTE_CARLO,
        resamples,
        extreme,
        p_value,
        upper_bound,
    )


def _validate_authority(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
) -> None:
    if (
        dataset.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
        or estimate.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
    ):
        raise ValueError(
            "P2.2C sources exceed DESCRIPTIVE authority."
        )

    dataset_fields = (
        "association_supported",
        "prospective_validation_established",
        "causal_attribution_established",
        "effect_inference_authorized",
        "readiness_inference_authorized",
        "performance_prediction_authorized",
        "prescription_change_authorized",
        "planning_authorized",
    )

    for field_name in dataset_fields:
        if getattr(
            dataset,
            field_name,
        ) is not False:
            raise ValueError(
                "Association dataset contains "
                "unsupported stronger authority: "
                f"{field_name}."
            )

    estimate_fields = (
        "association_supported",
        "prospective_validation_established",
        "causal_attribution_established",
        "effect_inference_authorized",
        "readiness_inference_authorized",
        "performance_prediction_authorized",
        "prescription_change_authorized",
        "planning_authorized",
    )

    for field_name in estimate_fields:
        if getattr(
            estimate,
            field_name,
        ) is not False:
            raise ValueError(
                "Association estimate contains "
                "unsupported stronger authority: "
                f"{field_name}."
            )


def assess_personal_association_support(
    *,
    dataset: PersonalAssociationDataset,
    estimate: PersonalAssociationEstimate,
    created_at: datetime,
) -> PersonalAssociationSupportAssessment:
    """Assess P2.2C support and robustness without authority promotion."""

    if not dataset.verify_content_hash():
        raise ValueError(
            "Personal association dataset hash "
            "does not verify."
        )

    if not estimate.verify_content_hash():
        raise ValueError(
            "Personal association estimate hash "
            "does not verify."
        )

    if (
        dataset.schema_version
        != PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01
        or dataset.rules_version
        != PERSONAL_ASSOCIATION_DATASET_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal association dataset contract."
        )

    if (
        estimate.schema_version
        != PERSONAL_ASSOCIATION_ESTIMATE_SCHEMA_V01
        or estimate.rules_version
        != PERSONAL_ASSOCIATION_ESTIMATE_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal association estimate contract."
        )

    _validate_authority(
        dataset=dataset,
        estimate=estimate,
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    dataset_created = to_utc(
        dataset.created_at,
        field_name="dataset.created_at",
    )

    estimate_created = to_utc(
        estimate.created_at,
        field_name="estimate.created_at",
    )

    if (
        materialized < dataset_created
        or materialized < estimate_created
    ):
        raise ValueError(
            "P2.2C assessment cannot predate its sources."
        )

    if (
        estimate.source_dataset_id
        != dataset.dataset_id
        or estimate.source_dataset_content_hash
        != dataset.content_hash
    ):
        raise ValueError(
            "Association estimate does not reference "
            "the supplied source dataset."
        )

    if (
        estimate.athlete_id
        != dataset.athlete_id
        or estimate.predictor_key
        != dataset.predictor_key
        or estimate.response_key
        != dataset.response_key
    ):
        raise ValueError(
            "Association estimate context does not "
            "match source dataset."
        )

    pairs = tuple(
        dataset.pairs
    )

    if (
        dataset.observed_pair_count
        != len(pairs)
        or estimate.observed_pair_count
        != len(pairs)
    ):
        raise ValueError(
            "Observed pair counts do not replay."
        )

    eligible_pairs = tuple(
        pair
        for pair in pairs
        if (
            pair.eligibility
            == PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
        )
    )

    eligible_count = len(
        eligible_pairs
    )

    if (
        dataset.eligible_numeric_pair_count
        != eligible_count
        or estimate.eligible_numeric_pair_count
        != eligible_count
    ):
        raise ValueError(
            "Eligible pair counts do not replay."
        )

    ineligible_count = (
        len(pairs)
        - eligible_count
    )

    if (
        dataset.ineligible_pair_count
        != ineligible_count
        or estimate.ineligible_pair_count
        != ineligible_count
    ):
        raise ValueError(
            "Ineligible pair counts do not replay."
        )

    dataset_sources = {}

    for pair in pairs:
        if not pair.verify_content_hash():
            raise ValueError(
                "Personal association pair hash "
                "does not verify."
            )

        if pair.pair_id in dataset_sources:
            raise ValueError(
                "Duplicate association pair identity."
            )

        if (
            pair.athlete_id
            != dataset.athlete_id
            or pair.predictor_key
            != dataset.predictor_key
            or pair.response_key
            != dataset.response_key
        ):
            raise ValueError(
                "Association pair context differs "
                "from dataset context."
            )

        for field_name in (
            "association_supported",
            "causal_attribution_established",
            "effect_inference_authorized",
            "prediction_authorized",
            "planning_authorized",
        ):
            if getattr(
                pair,
                field_name,
            ) is not False:
                raise ValueError(
                    "Association pair contains "
                    "unsupported stronger authority."
                )

        if (
            pair.eligibility
            != PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
        ):
            continue

        predictor_value = _finite_numeric(
            pair.predictor_numeric_value,
            field_name=(
                "pair.predictor_numeric_value"
            ),
        )

        response_value = _finite_numeric(
            pair.response_numeric_value,
            field_name=(
                "pair.response_numeric_value"
            ),
        )

        dataset_sources[
            pair.pair_id
        ] = (
            pair,
            predictor_value,
            response_value,
        )

    estimate_sources = {}

    for source in tuple(
        estimate.source_pairs
    ):
        if source.pair_id in estimate_sources:
            raise ValueError(
                "Duplicate estimate source pair identity."
            )

        estimate_sources[
            source.pair_id
        ] = source

    if (
        set(dataset_sources)
        != set(estimate_sources)
    ):
        raise ValueError(
            "Estimate source pair set differs "
            "from eligible dataset pair set."
        )

    for pair_id, (
        pair,
        predictor_value,
        response_value,
    ) in dataset_sources.items():
        source = estimate_sources[
            pair_id
        ]

        if (
            source.pair_content_hash
            != pair.content_hash
            or source.workout_session_id
            != pair.workout_session_id
            or source.predictor_value
            != predictor_value
            or source.response_value
            != response_value
        ):
            raise ValueError(
                "Estimate source pair replay mismatch."
            )

    ordered_sources = tuple(
        estimate.source_pairs
    )

    predictor_values = tuple(
        _finite_numeric(
            source.predictor_value,
            field_name="source.predictor_value",
        )
        for source in ordered_sources
    )

    response_values = tuple(
        _finite_numeric(
            source.response_value,
            field_name="source.response_value",
        )
        for source in ordered_sources
    )

    limitations = _coverage_limitations(
        stimulus_coverage=(
            dataset.stimulus_coverage
        ),
        response_coverage=(
            dataset.response_coverage
        ),
    )

    if ineligible_count > 0:
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .INELIGIBLE_PAIRS_PRESENT
        )

    workout_session_ids = tuple(
        source.workout_session_id
        for source in ordered_sources
    )

    unique_workout_session_count = len(
        set(
            workout_session_ids
        )
    )

    if (
        unique_workout_session_count
        != eligible_count
    ):
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .DUPLICATE_WORKOUT_SESSION
        )

    clean_isolation_count = 0
    unknown_isolation_count = 0
    intervening_isolation_count = 0

    for pair, _, _ in dataset_sources.values():
        if (
            pair.isolation_status
            == ResponseIsolationStatus
            .NO_INTERVENING_STIMULUS_OBSERVED
        ):
            clean_isolation_count += 1

            if pair.intervening_stimulus_ids:
                raise ValueError(
                    "Clean isolation pair cannot contain "
                    "intervening stimulus IDs."
                )

        elif (
            pair.isolation_status
            == ResponseIsolationStatus.UNKNOWN
        ):
            unknown_isolation_count += 1

            if pair.intervening_stimulus_ids:
                raise ValueError(
                    "UNKNOWN isolation pair cannot contain "
                    "intervening stimulus IDs."
                )

        elif (
            pair.isolation_status
            == ResponseIsolationStatus
            .INTERVENING_STIMULUS_OBSERVED
        ):
            intervening_isolation_count += 1

            if not pair.intervening_stimulus_ids:
                raise ValueError(
                    "Observed intervening isolation requires "
                    "intervening stimulus IDs."
                )

        else:
            raise ValueError(
                "Unsupported response isolation status."
            )

    if unknown_isolation_count > 0:
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .UNKNOWN_ISOLATION_PRESENT
        )

    if intervening_isolation_count > 0:
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .INTERVENING_STIMULUS_PRESENT
        )

    direction_consistent = None
    jackknife_values: list[float] = []
    jackknife_stable = None

    permutation_method = (
        PersonalAssociationPermutationMethod
        .NOT_APPLICABLE
    )
    permutation_resample_count = 0
    permutation_extreme_count = None
    permutation_p_value = None
    permutation_upper = None

    if (
        estimate.estimate_status
        != PersonalAssociationEstimateStatus.ESTIMATED
    ):
        limitations.append(
            PersonalAssociationSupportLimitationCode
            .ESTIMATE_NOT_ESTIMABLE
        )

        status = (
            PersonalAssociationSupportStatus
            .NOT_ASSESSABLE
        )

    else:
        if (
            estimate.spearman_rho is None
            or estimate.pearson_r is None
        ):
            raise ValueError(
                "ESTIMATED association requires "
                "both correlation diagnostics."
            )

        replay_spearman = _spearman(
            predictor_values,
            response_values,
        )

        replay_pearson = _pearson(
            predictor_values,
            response_values,
        )

        if (
            replay_spearman is None
            or replay_pearson is None
        ):
            raise ValueError(
                "ESTIMATED association cannot be replayed."
            )

        if not math.isclose(
            replay_spearman,
            estimate.spearman_rho,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "Spearman estimate does not replay."
            )

        if not math.isclose(
            replay_pearson,
            estimate.pearson_r,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "Pearson diagnostic does not replay."
            )

        spearman_sign = _sign(
            estimate.spearman_rho
        )

        pearson_sign = _sign(
            estimate.pearson_r
        )

        direction_consistent = (
            spearman_sign != 0
            and spearman_sign
            == pearson_sign
        )

        if not direction_consistent:
            limitations.append(
                PersonalAssociationSupportLimitationCode
                .SPEARMAN_PEARSON_DIRECTION_DISAGREEMENT
            )

        jackknife_estimable = True

        for omitted_index in range(
            eligible_count
        ):
            x_subset = tuple(
                value
                for index, value
                in enumerate(
                    predictor_values
                )
                if index != omitted_index
            )

            y_subset = tuple(
                value
                for index, value
                in enumerate(
                    response_values
                )
                if index != omitted_index
            )

            rho = _spearman(
                x_subset,
                y_subset,
            )

            if rho is None:
                jackknife_estimable = False
                continue

            jackknife_values.append(
                rho
            )

        if (
            not jackknife_estimable
            or len(jackknife_values)
            != eligible_count
        ):
            jackknife_stable = False

            limitations.append(
                PersonalAssociationSupportLimitationCode
                .JACKKNIFE_NOT_ESTIMABLE
            )

        else:
            jackknife_stable = (
                spearman_sign != 0
                and all(
                    _sign(rho)
                    == spearman_sign
                    for rho in jackknife_values
                )
            )

            if not jackknife_stable:
                limitations.append(
                    PersonalAssociationSupportLimitationCode
                    .JACKKNIFE_DIRECTION_UNSTABLE
                )

        (
            permutation_method,
            permutation_resample_count,
            permutation_extreme_count,
            permutation_p_value,
            permutation_upper,
        ) = _permutation_support(
            x=predictor_values,
            y=response_values,
            observed_rho=estimate.spearman_rho,
            seed_source=estimate.content_hash,
        )

        if (
            permutation_upper
            > PERSONAL_ASSOCIATION_SUPPORT_ALPHA_V01
        ):
            limitations.append(
                PersonalAssociationSupportLimitationCode
                .PERMUTATION_SUPPORT_NOT_ESTABLISHED
            )

        status = (
            PersonalAssociationSupportStatus
            .SUPPORT_CRITERIA_MET
            if not limitations
            else PersonalAssociationSupportStatus
            .INSUFFICIENT
        )

    ordered_limitations = _ordered_limitations(
        limitations
    )

    provisional = PersonalAssociationSupportAssessment(
        assessment_id="PENDING",
        schema_version=(
            PERSONAL_ASSOCIATION_SUPPORT_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_ASSOCIATION_SUPPORT_RULES_V01
        ),

        athlete_id=dataset.athlete_id,

        source_dataset_id=dataset.dataset_id,
        source_dataset_content_hash=(
            dataset.content_hash
        ),

        source_estimate_id=estimate.estimate_id,
        source_estimate_content_hash=(
            estimate.content_hash
        ),

        predictor_key=dataset.predictor_key,
        response_key=dataset.response_key,

        stimulus_coverage=(
            dataset.stimulus_coverage
        ),
        response_coverage=(
            dataset.response_coverage
        ),

        observed_pair_count=(
            dataset.observed_pair_count
        ),
        eligible_numeric_pair_count=(
            eligible_count
        ),
        ineligible_pair_count=(
            ineligible_count
        ),

        unique_workout_session_count=(
            unique_workout_session_count
        ),

        clean_isolation_pair_count=(
            clean_isolation_count
        ),
        unknown_isolation_pair_count=(
            unknown_isolation_count
        ),
        intervening_isolation_pair_count=(
            intervening_isolation_count
        ),

        estimate_status=(
            estimate.estimate_status
        ),

        spearman_rho=(
            estimate.spearman_rho
        ),
        pearson_r=(
            estimate.pearson_r
        ),

        spearman_pearson_direction_consistent=(
            direction_consistent
        ),

        jackknife_evaluated_count=len(
            jackknife_values
        ),
        jackknife_min_spearman_rho=(
            min(jackknife_values)
            if jackknife_values
            else None
        ),
        jackknife_max_spearman_rho=(
            max(jackknife_values)
            if jackknife_values
            else None
        ),
        jackknife_direction_stable=(
            jackknife_stable
        ),

        permutation_method=(
            permutation_method
        ),
        permutation_resample_count=(
            permutation_resample_count
        ),
        permutation_extreme_count=(
            permutation_extreme_count
        ),

        permutation_p_value=(
            permutation_p_value
        ),
        permutation_p_value_upper_bound_95=(
            permutation_upper
        ),

        support_alpha=(
            PERSONAL_ASSOCIATION_SUPPORT_ALPHA_V01
        ),

        status=status,
        limitation_codes=(
            ordered_limitations
        ),

        evidence_level_ceiling=(
            EffectEvidenceLevel.DESCRIPTIVE
        ),

        association_supported=False,
        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        created_at=materialized,
        content_hash="PENDING",
    )

    digest = _assessment_content_hash(
        provisional
    )

    return PersonalAssociationSupportAssessment(
        **{
            **provisional.__dict__,
            "assessment_id": (
                "pt-personal-association-support:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
