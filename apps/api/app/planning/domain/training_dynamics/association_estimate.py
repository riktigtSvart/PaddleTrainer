from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math
from datetime import datetime

from ..common.time import to_utc
from .association_dataset import (
    PERSONAL_ASSOCIATION_DATASET_RULES_V01,
    PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01,
    PersonalAssociationDataset,
    PersonalAssociationPairEligibility,
    PersonalAssociationPredictorKey,
)
from .models import EffectEvidenceLevel
from .response_reference import (
    ResponseMetricReferenceKey,
)


PERSONAL_ASSOCIATION_ESTIMATE_SCHEMA_V01 = (
    "personal-association-estimate-v0.1"
)

PERSONAL_ASSOCIATION_ESTIMATE_RULES_V01 = (
    "personal-association-estimate-rules-v0.1"
)


class PersonalAssociationEstimateStatus(StrEnum):
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    ESTIMATED = "ESTIMATED"


class PersonalAssociationEstimateLimitationCode(StrEnum):
    NO_ELIGIBLE_NUMERIC_PAIRS = (
        "NO_ELIGIBLE_NUMERIC_PAIRS"
    )
    SINGLE_ELIGIBLE_NUMERIC_PAIR = (
        "SINGLE_ELIGIBLE_NUMERIC_PAIR"
    )
    NO_PREDICTOR_VARIATION = (
        "NO_PREDICTOR_VARIATION"
    )
    NO_RESPONSE_VARIATION = (
        "NO_RESPONSE_VARIATION"
    )


@dataclass(frozen=True)
class PersonalAssociationEstimateSourcePair:
    pair_id: str
    pair_content_hash: str
    workout_session_id: str

    predictor_value: float
    response_value: float


@dataclass(frozen=True)
class PersonalAssociationEstimate:
    """Deterministic descriptive P2.2B association estimate.

    ESTIMATED means only that the mathematical correlation coefficients
    can be computed from the eligible numeric pairs.

    It does not establish adequate support, causality, prediction,
    physiological effect, readiness interpretation, or planning authority.
    """

    estimate_id: str
    schema_version: str
    rules_version: str

    athlete_id: str

    source_dataset_id: str
    source_dataset_content_hash: str
    source_dataset_schema_version: str
    source_dataset_rules_version: str

    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey

    observed_pair_count: int
    eligible_numeric_pair_count: int
    ineligible_pair_count: int

    distinct_predictor_value_count: int
    distinct_response_value_count: int

    predictor_min: float | None
    predictor_max: float | None
    predictor_range: float | None

    response_min: float | None
    response_max: float | None
    response_range: float | None

    estimate_status: PersonalAssociationEstimateStatus

    limitation_codes: tuple[
        PersonalAssociationEstimateLimitationCode,
        ...,
    ]

    # Primary P2.2B estimator.
    spearman_rho: float | None

    # Descriptive diagnostic only.
    pearson_r: float | None

    source_pairs: tuple[
        PersonalAssociationEstimateSourcePair,
        ...,
    ]

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
            == _estimate_content_hash(self)
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


def _source_pair_payload(
    pair: PersonalAssociationEstimateSourcePair,
) -> dict[str, object]:
    return {
        "pair_id": pair.pair_id,
        "pair_content_hash": (
            pair.pair_content_hash
        ),
        "workout_session_id": (
            pair.workout_session_id
        ),
        "predictor_value": (
            pair.predictor_value
        ),
        "response_value": (
            pair.response_value
        ),
    }


def _estimate_payload(
    estimate: PersonalAssociationEstimate,
) -> dict[str, object]:
    return {
        "schema_version": estimate.schema_version,
        "rules_version": estimate.rules_version,

        "athlete_id": estimate.athlete_id,

        "source_dataset_id": (
            estimate.source_dataset_id
        ),
        "source_dataset_content_hash": (
            estimate.source_dataset_content_hash
        ),
        "source_dataset_schema_version": (
            estimate.source_dataset_schema_version
        ),
        "source_dataset_rules_version": (
            estimate.source_dataset_rules_version
        ),

        "predictor_key": _predictor_key_payload(
            estimate.predictor_key
        ),
        "response_key": _response_key_payload(
            estimate.response_key
        ),

        "observed_pair_count": (
            estimate.observed_pair_count
        ),
        "eligible_numeric_pair_count": (
            estimate.eligible_numeric_pair_count
        ),
        "ineligible_pair_count": (
            estimate.ineligible_pair_count
        ),

        "distinct_predictor_value_count": (
            estimate.distinct_predictor_value_count
        ),
        "distinct_response_value_count": (
            estimate.distinct_response_value_count
        ),

        "predictor_min": estimate.predictor_min,
        "predictor_max": estimate.predictor_max,
        "predictor_range": estimate.predictor_range,

        "response_min": estimate.response_min,
        "response_max": estimate.response_max,
        "response_range": estimate.response_range,

        "estimate_status": (
            estimate.estimate_status.value
        ),

        "limitation_codes": [
            item.value
            for item in estimate.limitation_codes
        ],

        "spearman_rho": estimate.spearman_rho,
        "pearson_r": estimate.pearson_r,

        "source_pairs": [
            _source_pair_payload(pair)
            for pair in estimate.source_pairs
        ],

        "evidence_level_ceiling": (
            estimate.evidence_level_ceiling.value
        ),

        "association_supported": (
            estimate.association_supported
        ),
        "prospective_validation_established": (
            estimate.prospective_validation_established
        ),
        "causal_attribution_established": (
            estimate.causal_attribution_established
        ),
        "effect_inference_authorized": (
            estimate.effect_inference_authorized
        ),
        "readiness_inference_authorized": (
            estimate.readiness_inference_authorized
        ),
        "performance_prediction_authorized": (
            estimate.performance_prediction_authorized
        ),
        "prescription_change_authorized": (
            estimate.prescription_change_authorized
        ),
        "planning_authorized": (
            estimate.planning_authorized
        ),
    }


def _estimate_content_hash(
    estimate: PersonalAssociationEstimate,
) -> str:
    canonical = json.dumps(
        _estimate_payload(estimate),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _require_non_empty_string(
    value: object,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _require_finite_numeric(
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


def _scaled_pearson(
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

    x_centered = tuple(
        value - x_mean
        for value in xs
    )

    y_centered = tuple(
        value - y_mean
        for value in ys
    )

    x_ss = math.fsum(
        value * value
        for value in x_centered
    )

    y_ss = math.fsum(
        value * value
        for value in y_centered
    )

    if (
        x_ss <= 0.0
        or y_ss <= 0.0
    ):
        return None

    numerator = math.fsum(
        x_value * y_value
        for x_value, y_value in zip(
            x_centered,
            y_centered,
        )
    )

    result = numerator / math.sqrt(
        x_ss * y_ss
    )

    # Round-off can very slightly exceed the mathematical bounds.
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

        # Rank positions are one-based.
        first_rank = index + 1
        last_rank = end

        average_rank = (
            first_rank + last_rank
        ) / 2.0

        for position in range(
            index,
            end,
        ):
            original_index = (
                ordered[position][0]
            )

            ranks[
                original_index
            ] = average_rank

        index = end

    return tuple(ranks)


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

    return _scaled_pearson(
        _average_ranks(x),
        _average_ranks(y),
    )


def _validate_dataset_authority(
    dataset: PersonalAssociationDataset,
) -> None:
    if (
        dataset.evidence_level_ceiling
        != EffectEvidenceLevel.DESCRIPTIVE
    ):
        raise ValueError(
            "Personal association source dataset "
            "exceeds DESCRIPTIVE authority."
        )

    stronger_fields = (
        "association_supported",
        "prospective_validation_established",
        "causal_attribution_established",
        "effect_inference_authorized",
        "readiness_inference_authorized",
        "performance_prediction_authorized",
        "prescription_change_authorized",
        "planning_authorized",
    )

    for field_name in stronger_fields:
        if getattr(
            dataset,
            field_name,
        ) is not False:
            raise ValueError(
                "Personal association source dataset "
                "contains unsupported stronger authority: "
                f"{field_name}."
            )


def _validate_pair_authority(
    pair: object,
) -> None:
    stronger_fields = (
        "association_supported",
        "causal_attribution_established",
        "effect_inference_authorized",
        "prediction_authorized",
        "planning_authorized",
    )

    for field_name in stronger_fields:
        if getattr(
            pair,
            field_name,
        ) is not False:
            raise ValueError(
                "Personal association source pair "
                "contains unsupported stronger authority: "
                f"{field_name}."
            )


def build_personal_association_estimate(
    *,
    dataset: PersonalAssociationDataset,
    created_at: datetime,
) -> PersonalAssociationEstimate:
    """Compute deterministic descriptive correlation estimates.

    P2.2B intentionally does not decide whether the observed association
    has sufficient scientific support. That decision belongs to P2.2C.
    """

    if not dataset.verify_content_hash():
        raise ValueError(
            "Personal association dataset hash "
            "does not verify."
        )

    if (
        dataset.schema_version
        != PERSONAL_ASSOCIATION_DATASET_SCHEMA_V01
    ):
        raise ValueError(
            "Unsupported personal association "
            "dataset schema."
        )

    if (
        dataset.rules_version
        != PERSONAL_ASSOCIATION_DATASET_RULES_V01
    ):
        raise ValueError(
            "Unsupported personal association "
            "dataset rules."
        )

    _validate_dataset_authority(
        dataset
    )

    materialized = to_utc(
        created_at,
        field_name="created_at",
    )

    dataset_created = to_utc(
        dataset.created_at,
        field_name="dataset.created_at",
    )

    if materialized < dataset_created:
        raise ValueError(
            "Personal association estimate cannot "
            "predate its source dataset."
        )

    pairs = tuple(
        dataset.pairs
    )

    if (
        dataset.observed_pair_count
        != len(pairs)
    ):
        raise ValueError(
            "Source dataset observed pair count "
            "does not match materialized pairs."
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

    if (
        dataset.eligible_numeric_pair_count
        != len(eligible_pairs)
    ):
        raise ValueError(
            "Source dataset eligible pair count "
            "does not match materialized pairs."
        )

    expected_ineligible = (
        len(pairs)
        - len(eligible_pairs)
    )

    if (
        dataset.ineligible_pair_count
        != expected_ineligible
    ):
        raise ValueError(
            "Source dataset ineligible pair count "
            "does not match materialized pairs."
        )

    seen_pair_ids: set[str] = set()

    sources: list[
        PersonalAssociationEstimateSourcePair
    ] = []

    for pair in pairs:
        if not pair.verify_content_hash():
            raise ValueError(
                "Personal association pair hash "
                "does not verify."
            )

        pair_id = _require_non_empty_string(
            pair.pair_id,
            field_name="pair.pair_id",
        )

        if pair_id in seen_pair_ids:
            raise ValueError(
                "Duplicate personal association "
                "pair identity."
            )

        seen_pair_ids.add(
            pair_id
        )

        _require_non_empty_string(
            pair.content_hash,
            field_name="pair.content_hash",
        )

        _require_non_empty_string(
            pair.workout_session_id,
            field_name=(
                "pair.workout_session_id"
            ),
        )

        if (
            pair.athlete_id
            != dataset.athlete_id
        ):
            raise ValueError(
                "Association pair athlete differs "
                "from source dataset athlete."
            )

        if (
            pair.predictor_key
            != dataset.predictor_key
        ):
            raise ValueError(
                "Association pair predictor context "
                "differs from source dataset."
            )

        if (
            pair.response_key
            != dataset.response_key
        ):
            raise ValueError(
                "Association pair response context "
                "differs from source dataset."
            )

        _validate_pair_authority(
            pair
        )

        if (
            pair.eligibility
            != PersonalAssociationPairEligibility
            .ELIGIBLE_NUMERIC_PAIR
        ):
            continue

        predictor_value = (
            _require_finite_numeric(
                pair.predictor_numeric_value,
                field_name=(
                    "pair.predictor_numeric_value"
                ),
            )
        )

        response_value = (
            _require_finite_numeric(
                pair.response_numeric_value,
                field_name=(
                    "pair.response_numeric_value"
                ),
            )
        )

        sources.append(
            PersonalAssociationEstimateSourcePair(
                pair_id=pair_id,
                pair_content_hash=(
                    pair.content_hash
                ),
                workout_session_id=(
                    pair.workout_session_id
                ),
                predictor_value=(
                    predictor_value
                ),
                response_value=(
                    response_value
                ),
            )
        )

    ordered_sources = tuple(
        sorted(
            sources,
            key=lambda item: (
                item.workout_session_id,
                item.pair_id,
            ),
        )
    )

    predictor_values = tuple(
        item.predictor_value
        for item in ordered_sources
    )

    response_values = tuple(
        item.response_value
        for item in ordered_sources
    )

    eligible_count = len(
        ordered_sources
    )

    predictor_distinct = len(
        set(
            predictor_values
        )
    )

    response_distinct = len(
        set(
            response_values
        )
    )

    if predictor_values:
        predictor_min = min(
            predictor_values
        )
        predictor_max = max(
            predictor_values
        )
        predictor_range = (
            predictor_max
            - predictor_min
        )

        response_min = min(
            response_values
        )
        response_max = max(
            response_values
        )
        response_range = (
            response_max
            - response_min
        )

    else:
        predictor_min = None
        predictor_max = None
        predictor_range = None

        response_min = None
        response_max = None
        response_range = None

    limitations: list[
        PersonalAssociationEstimateLimitationCode
    ] = []

    if eligible_count == 0:
        limitations.append(
            PersonalAssociationEstimateLimitationCode
            .NO_ELIGIBLE_NUMERIC_PAIRS
        )

    elif eligible_count == 1:
        limitations.append(
            PersonalAssociationEstimateLimitationCode
            .SINGLE_ELIGIBLE_NUMERIC_PAIR
        )

    else:
        if predictor_distinct < 2:
            limitations.append(
                PersonalAssociationEstimateLimitationCode
                .NO_PREDICTOR_VARIATION
            )

        if response_distinct < 2:
            limitations.append(
                PersonalAssociationEstimateLimitationCode
                .NO_RESPONSE_VARIATION
            )

    if limitations:
        estimate_status = (
            PersonalAssociationEstimateStatus
            .NOT_ESTIMABLE
        )

        spearman_rho = None
        pearson_r = None

    else:
        spearman_rho = _spearman(
            predictor_values,
            response_values,
        )

        pearson_r = _scaled_pearson(
            predictor_values,
            response_values,
        )

        if (
            spearman_rho is None
            or pearson_r is None
        ):
            raise ValueError(
                "Association estimator became undefined "
                "despite validated numeric variation."
            )

        estimate_status = (
            PersonalAssociationEstimateStatus
            .ESTIMATED
        )

    provisional = PersonalAssociationEstimate(
        estimate_id="PENDING",
        schema_version=(
            PERSONAL_ASSOCIATION_ESTIMATE_SCHEMA_V01
        ),
        rules_version=(
            PERSONAL_ASSOCIATION_ESTIMATE_RULES_V01
        ),

        athlete_id=dataset.athlete_id,

        source_dataset_id=dataset.dataset_id,
        source_dataset_content_hash=(
            dataset.content_hash
        ),
        source_dataset_schema_version=(
            dataset.schema_version
        ),
        source_dataset_rules_version=(
            dataset.rules_version
        ),

        predictor_key=dataset.predictor_key,
        response_key=dataset.response_key,

        observed_pair_count=(
            dataset.observed_pair_count
        ),
        eligible_numeric_pair_count=(
            eligible_count
        ),
        ineligible_pair_count=(
            dataset.ineligible_pair_count
        ),

        distinct_predictor_value_count=(
            predictor_distinct
        ),
        distinct_response_value_count=(
            response_distinct
        ),

        predictor_min=predictor_min,
        predictor_max=predictor_max,
        predictor_range=predictor_range,

        response_min=response_min,
        response_max=response_max,
        response_range=response_range,

        estimate_status=estimate_status,

        limitation_codes=tuple(
            limitations
        ),

        spearman_rho=spearman_rho,
        pearson_r=pearson_r,

        source_pairs=ordered_sources,

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

    content_hash = _estimate_content_hash(
        provisional
    )

    return PersonalAssociationEstimate(
        estimate_id=(
            "pt-personal-association-estimate:"
            f"{content_hash}"
        ),
        schema_version=(
            provisional.schema_version
        ),
        rules_version=(
            provisional.rules_version
        ),

        athlete_id=provisional.athlete_id,

        source_dataset_id=(
            provisional.source_dataset_id
        ),
        source_dataset_content_hash=(
            provisional.source_dataset_content_hash
        ),
        source_dataset_schema_version=(
            provisional.source_dataset_schema_version
        ),
        source_dataset_rules_version=(
            provisional.source_dataset_rules_version
        ),

        predictor_key=(
            provisional.predictor_key
        ),
        response_key=(
            provisional.response_key
        ),

        observed_pair_count=(
            provisional.observed_pair_count
        ),
        eligible_numeric_pair_count=(
            provisional.eligible_numeric_pair_count
        ),
        ineligible_pair_count=(
            provisional.ineligible_pair_count
        ),

        distinct_predictor_value_count=(
            provisional.distinct_predictor_value_count
        ),
        distinct_response_value_count=(
            provisional.distinct_response_value_count
        ),

        predictor_min=provisional.predictor_min,
        predictor_max=provisional.predictor_max,
        predictor_range=provisional.predictor_range,

        response_min=provisional.response_min,
        response_max=provisional.response_max,
        response_range=provisional.response_range,

        estimate_status=(
            provisional.estimate_status
        ),
        limitation_codes=(
            provisional.limitation_codes
        ),

        spearman_rho=(
            provisional.spearman_rho
        ),
        pearson_r=(
            provisional.pearson_r
        ),

        source_pairs=(
            provisional.source_pairs
        ),

        evidence_level_ceiling=(
            provisional.evidence_level_ceiling
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
        content_hash=content_hash,
    )
