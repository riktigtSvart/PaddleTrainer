from dataclasses import dataclass
from datetime import datetime
from math import floor, isfinite
from statistics import median

from app.pft_engine.baseline.models import (
    BaselineKey,
    BaselineObservation,
    BaselineSnapshot,
    BaselineStatus,
)


@dataclass(frozen=True)
class BaselineRules:
    version: str = "baseline_v0.1"

    provisional_min_n: int = 5
    established_min_n: int = 8


DEFAULT_BASELINE_RULES = BaselineRules()


def _percentile(
    values: list[float],
    probability: float,
) -> float | None:
    """
    Linear-interpolated percentile using position:

        (n - 1) * p

    Works deterministically even for very small samples.
    """

    if not values:
        return None

    if not 0.0 <= probability <= 1.0:
        raise ValueError(
            "Probability must be between 0 and 1."
        )

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (
        len(ordered) - 1
    ) * probability

    lower_index = floor(position)
    upper_index = min(
        lower_index + 1,
        len(ordered) - 1,
    )

    fraction = position - lower_index

    lower = ordered[lower_index]
    upper = ordered[upper_index]

    return (
        lower
        + (upper - lower) * fraction
    )


def _mad(
    values: list[float],
    median_value: float,
) -> float:
    deviations = [
        abs(value - median_value)
        for value in values
    ]

    return float(median(deviations))


def _baseline_status(
    n: int,
    rules: BaselineRules,
) -> BaselineStatus:
    if n >= rules.established_min_n:
        return BaselineStatus.ESTABLISHED

    if n >= rules.provisional_min_n:
        return BaselineStatus.PROVISIONAL

    return BaselineStatus.INSUFFICIENT


def calculate_baseline(
    *,
    key: BaselineKey,
    observations: tuple[
        BaselineObservation, ...
    ],
    as_of:datetime,
    rules: BaselineRules = DEFAULT_BASELINE_RULES,
) -> BaselineSnapshot:

    # First isolate the exact baseline context.
    matching = [
        observation
        for observation in observations
        if (
            observation.key == key
            and observation.recorded_at < as_of
        )
    ]

    eligible = [
        observation
        for observation in matching
        if (
            observation.baseline_eligible
            and isfinite(observation.value)
        )
    ]

    values = [
        float(observation.value)
        for observation in eligible
    ]

    n = len(values)

    status = _baseline_status(
        n,
        rules,
    )

    excluded_ineligible = (
        len(matching) - n
    )

    if not values:
        return BaselineSnapshot(
            key=key,
            as_of=as_of,
            status=status,
            n=0,
            median=None,
            mad=None,
            q25=None,
            q75=None,
            minimum=None,
            maximum=None,
            total_matching_observations=len(
                matching
            ),
            excluded_ineligible_observations=(
                excluded_ineligible
            ),
            rules_version=rules.version,
        )

    median_value = float(
        median(values)
    )

    return BaselineSnapshot(
        key=key,
        as_of=as_of,
        status=status,
        n=n,
        median=median_value,
        mad=_mad(
            values,
            median_value,
        ),
        q25=_percentile(
            values,
            0.25,
        ),
        q75=_percentile(
            values,
            0.75,
        ),
        minimum=min(values),
        maximum=max(values),
        total_matching_observations=len(
            matching
        ),
        excluded_ineligible_observations=(
            excluded_ineligible
        ),
        rules_version=rules.version,
    )