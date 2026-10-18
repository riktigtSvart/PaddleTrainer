from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

from app.pft_engine.baseline.models import (
    BaselineKey,
    BaselineSnapshot,
    BaselineStatus,
)


class ComparisonStatus(StrEnum):
    NOT_READY = "not_ready"
    AVAILABLE = "available"


class ComparisonDirection(StrEnum):
    BELOW_BASELINE = "below_baseline"
    AT_BASELINE = "at_baseline"
    ABOVE_BASELINE = "above_baseline"


class ComparisonIssueCode(StrEnum):
    BASELINE_INSUFFICIENT = "baseline_insufficient"
    BASELINE_EMPTY = "baseline_empty"
    BASELINE_KEY_MISMATCH = "baseline_key_mismatch"
    CURRENT_VALUE_INVALID = "current_value_invalid"
    MAD_ZERO = "mad_zero"
    BASELINE_MEDIAN_ZERO = "baseline_median_zero"


@dataclass(frozen=True)
class ComparisonIssue:
    code: ComparisonIssueCode
    message: str


@dataclass(frozen=True)
class CurrentFeatureValue:
    key: BaselineKey
    recorded_at: datetime
    value: float


@dataclass(frozen=True)
class FeatureComparison:
    key: BaselineKey

    current_recorded_at: datetime
    baseline_as_of: datetime

    status: ComparisonStatus
    baseline_status: BaselineStatus
    baseline_n: int

    current_value: float
    baseline_median: float | None
    baseline_mad: float | None

    absolute_difference: float | None
    relative_difference_pct: float | None

    # Number of baseline MADs separating the current
    # value from the historical baseline median.
    deviation_mad_units: float | None

    direction: ComparisonDirection | None

    issues: tuple[ComparisonIssue, ...]


def _direction(
    difference: float,
) -> ComparisonDirection:
    if difference > 0.0:
        return ComparisonDirection.ABOVE_BASELINE

    if difference < 0.0:
        return ComparisonDirection.BELOW_BASELINE

    return ComparisonDirection.AT_BASELINE


def compare_to_baseline(
    *,
    current: CurrentFeatureValue,
    baseline: BaselineSnapshot,
) -> FeatureComparison:
    issues: list[ComparisonIssue] = []

    if current.key != baseline.key:
        issues.append(
            ComparisonIssue(
                code=ComparisonIssueCode.BASELINE_KEY_MISMATCH,
                message=(
                    "Current feature context does not match "
                    "the baseline context."
                ),
            )
        )

        return FeatureComparison(
            key=current.key,
            current_recorded_at=current.recorded_at,
            baseline_as_of=baseline.as_of,
            status=ComparisonStatus.NOT_READY,
            baseline_status=baseline.status,
            baseline_n=baseline.n,
            current_value=current.value,
            baseline_median=baseline.median,
            baseline_mad=baseline.mad,
            absolute_difference=None,
            relative_difference_pct=None,
            deviation_mad_units=None,
            direction=None,
            issues=tuple(issues),
        )

    if not isfinite(current.value):
        issues.append(
            ComparisonIssue(
                code=ComparisonIssueCode.CURRENT_VALUE_INVALID,
                message=(
                    "Current feature value is not finite."
                ),
            )
        )

        return FeatureComparison(
            key=current.key,
            current_recorded_at=current.recorded_at,
            baseline_as_of=baseline.as_of,
            status=ComparisonStatus.NOT_READY,
            baseline_status=baseline.status,
            baseline_n=baseline.n,
            current_value=current.value,
            baseline_median=baseline.median,
            baseline_mad=baseline.mad,
            absolute_difference=None,
            relative_difference_pct=None,
            deviation_mad_units=None,
            direction=None,
            issues=tuple(issues),
        )

    if (
        baseline.median is None
        or baseline.n == 0
    ):
        issues.append(
            ComparisonIssue(
                code=ComparisonIssueCode.BASELINE_EMPTY,
                message=(
                    "Baseline contains no usable observations."
                ),
            )
        )

        return FeatureComparison(
            key=current.key,
            current_recorded_at=current.recorded_at,
            baseline_as_of=baseline.as_of,
            status=ComparisonStatus.NOT_READY,
            baseline_status=baseline.status,
            baseline_n=baseline.n,
            current_value=current.value,
            baseline_median=baseline.median,
            baseline_mad=baseline.mad,
            absolute_difference=None,
            relative_difference_pct=None,
            deviation_mad_units=None,
            direction=None,
            issues=tuple(issues),
        )

    if baseline.status == BaselineStatus.INSUFFICIENT:
        issues.append(
            ComparisonIssue(
                code=(
                    ComparisonIssueCode
                    .BASELINE_INSUFFICIENT
                ),
                message=(
                    "Baseline does not yet contain enough "
                    "eligible observations for personal "
                    "comparison."
                ),
            )
        )

        return FeatureComparison(
            key=current.key,
            current_recorded_at=current.recorded_at,
            baseline_as_of=baseline.as_of,
            status=ComparisonStatus.NOT_READY,
            baseline_status=baseline.status,
            baseline_n=baseline.n,
            current_value=current.value,
            baseline_median=baseline.median,
            baseline_mad=baseline.mad,
            absolute_difference=None,
            relative_difference_pct=None,
            deviation_mad_units=None,
            direction=None,
            issues=tuple(issues),
        )

    difference = (
        current.value
        - baseline.median
    )

    relative_difference_pct: float | None

    if baseline.median == 0.0:
        relative_difference_pct = None

        issues.append(
            ComparisonIssue(
                code=(
                    ComparisonIssueCode
                    .BASELINE_MEDIAN_ZERO
                ),
                message=(
                    "Relative difference cannot be "
                    "calculated because baseline median "
                    "is zero."
                ),
            )
        )
    else:
        relative_difference_pct = (
            difference
            / abs(baseline.median)
            * 100.0
        )

    deviation_mad_units: float | None

    if (
        baseline.mad is None
        or baseline.mad == 0.0
    ):
        deviation_mad_units = None

        issues.append(
            ComparisonIssue(
                code=ComparisonIssueCode.MAD_ZERO,
                message=(
                    "MAD-based deviation cannot be "
                    "calculated because baseline MAD "
                    "is zero."
                ),
            )
        )
    else:
        deviation_mad_units = (
            difference
            / baseline.mad
        )

    return FeatureComparison(
        key=current.key,
        current_recorded_at=current.recorded_at,
        baseline_as_of=baseline.as_of,
        status=ComparisonStatus.AVAILABLE,
        baseline_status=baseline.status,
        baseline_n=baseline.n,
        current_value=current.value,
        baseline_median=baseline.median,
        baseline_mad=baseline.mad,
        absolute_difference=difference,
        relative_difference_pct=(
            relative_difference_pct
        ),
        deviation_mad_units=(
            deviation_mad_units
        ),
        direction=_direction(difference),
        issues=tuple(issues),
    )