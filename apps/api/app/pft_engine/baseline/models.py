from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.pft_engine.pft.features import (
    PftFeatureName,
)
from app.pft_engine.pft.quality import (
    PftQualityGrade,
)


class BaselineStatus(StrEnum):
    INSUFFICIENT = "insufficient"
    PROVISIONAL = "provisional"
    ESTABLISHED = "established"


@dataclass(frozen=True)
class BaselineKey:
    """
    Defines which observations are allowed to belong
    to the same personal baseline.

    Athlete identity intentionally does not live here.
    The integration layer is responsible for selecting
    observations belonging to the same athlete.
    """

    feature: PftFeatureName

    modality: str

    protocol_name: str
    protocol_version: str

    stimulus_key: str

    unit: str

    # Prevents silent mixing of feature values produced
    # by different processing algorithms.
    algorithm_key: str


@dataclass(frozen=True)
class BaselineObservation:
    key: BaselineKey

    recorded_at: datetime

    value: float

    quality_grade: PftQualityGrade

    baseline_eligible: bool


@dataclass(frozen=True)
class BaselineSnapshot:
    key: BaselineKey

    as_of: datetime

    status: BaselineStatus

    n: int

    median: float | None
    mad: float | None

    q25: float | None
    q75: float | None

    minimum: float | None
    maximum: float | None

    total_matching_observations: int
    excluded_ineligible_observations: int

    rules_version: str