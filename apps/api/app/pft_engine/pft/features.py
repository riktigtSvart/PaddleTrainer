from dataclasses import dataclass
from enum import StrEnum
from statistics import median

from app.pft_engine.contracts.input import (
    ImportedSession,
    RawSample,
)
from app.pft_engine.pft.protocol import (
    PftProtocol,
    PftStage,
)
from app.pft_engine.pft.segmentation import (
    PftSegmentationResult,
)
from app.pft_engine.pft.transition_detection import (
    DetectedLoadTransition,
    PftTransitionDetectionResult,
    RecoveryAnchorSource,
)


class PftFeatureName(StrEnum):
    HR_PRE_MEDIAN = "HR_PRE_MEDIAN"

    HR_P1_MEDIAN = "HR_P1_MEDIAN"
    HR_P2_MEDIAN = "HR_P2_MEDIAN"

    DELTA_HR30_P1 = "DELTA_HR30_P1"
    DELTA_HR60_P1 = "DELTA_HR60_P1"

    DELTA_HR30_P2 = "DELTA_HR30_P2"
    DELTA_HR60_P2 = "DELTA_HR60_P2"

    HRR30 = "HRR30"
    HRR60 = "HRR60"
    HRR90 = "HRR90"
    HRR120 = "HRR120"


@dataclass(frozen=True)
class FeatureExtractionRules:
    version: str = "features_v0.2"

    # Steady HR is represented by the final part
    # of the nominal protocol stage.
    steady_hr_window_s: float = 60.0

    # Baseline immediately before the observed
    # external-load ramp starts.
    transition_baseline_window_s: float = 10.0

    # HR around +30 / +60 etc. is represented
    # by a small median window rather than one sample.
    point_window_s: float = 5.0

    # End-exercise HR immediately before the
    # observed recovery anchor.
    recovery_end_hr_window_s: float = 5.0

    minimum_point_hr_samples: int = 3


DEFAULT_FEATURE_RULES = FeatureExtractionRules()


@dataclass(frozen=True)
class FeatureValue:
    name: PftFeatureName
    value: float
    unit: str


@dataclass(frozen=True)
class PftFeatureExtractionResult:
    algorithm_version: str
    transition_rules_version: str

    features: tuple[FeatureValue, ...]

    recovery_anchor_s: float
    recovery_anchor_source: RecoveryAnchorSource

    def get(
        self,
        name: PftFeatureName,
    ) -> FeatureValue:
        for feature in self.features:
            if feature.name == name:
                return feature

        raise KeyError(f"Feature not found: {name}")


def _protocol_window(
    protocol: PftProtocol,
    stage: PftStage,
):
    for window in protocol.stages:
        if window.stage == stage:
            return window

    raise KeyError(
        f"Protocol does not contain stage: {stage}"
    )


def _hr_values(
    samples: tuple[RawSample, ...],
    start_s: float,
    end_s: float,
) -> list[float]:
    return [
        float(sample.hr_bpm)
        for sample in samples
        if (
            start_s <= sample.elapsed_s < end_s
            and sample.hr_bpm is not None
        )
    ]


def _median_hr(
    samples: tuple[RawSample, ...],
    start_s: float,
    end_s: float,
    *,
    minimum_samples: int = 1,
) -> float | None:
    values = _hr_values(
        samples,
        start_s,
        end_s,
    )

    if len(values) < minimum_samples:
        return None

    return float(median(values))


def _centered_hr(
    samples: tuple[RawSample, ...],
    target_s: float,
    window_s: float,
    minimum_samples: int,
) -> float | None:
    half = window_s / 2.0

    return _median_hr(
        samples,
        target_s - half,
        target_s + half,
        minimum_samples=minimum_samples,
    )


def _steady_stage_hr(
    session: ImportedSession,
    protocol: PftProtocol,
    stage: PftStage,
    window_s: float,
) -> float | None:
    stage_window = _protocol_window(
        protocol,
        stage,
    )

    start_s = max(
        stage_window.start_s,
        stage_window.end_s - window_s,
    )

    return _median_hr(
        session.samples,
        start_s,
        stage_window.end_s,
    )


def _observed_transition_delta_hr(
    session: ImportedSession,
    transition: DetectedLoadTransition,
    offset_s: float,
    rules: FeatureExtractionRules,
) -> float | None:
    # Baseline belongs entirely before the observed
    # external-load ramp.
    baseline = _median_hr(
        session.samples,
        transition.ramp_start_s
        - rules.transition_baseline_window_s,
        transition.ramp_start_s,
        minimum_samples=rules.minimum_point_hr_samples,
    )

    # Response timing is anchored to the midpoint of the
    # observed external-load transition.
    response_target_s = (
        transition.midpoint_s
        + offset_s
    )

    response = _centered_hr(
        session.samples,
        response_target_s,
        rules.point_window_s,
        rules.minimum_point_hr_samples,
    )

    if baseline is None or response is None:
        return None

    return response - baseline


def _recovery_feature(
    session: ImportedSession,
    recovery_anchor_s: float,
    offset_s: float,
    rules: FeatureExtractionRules,
) -> float | None:
    end_hr = _median_hr(
        session.samples,
        recovery_anchor_s
        - rules.recovery_end_hr_window_s,
        recovery_anchor_s,
        minimum_samples=rules.minimum_point_hr_samples,
    )

    recovery_hr = _centered_hr(
        session.samples,
        recovery_anchor_s + offset_s,
        rules.point_window_s,
        rules.minimum_point_hr_samples,
    )

    if end_hr is None or recovery_hr is None:
        return None

    return end_hr - recovery_hr


def _try_transition_to(
    transitions: PftTransitionDetectionResult,
    stage: PftStage,
) -> DetectedLoadTransition | None:
    try:
        return transitions.get_transition_to(stage)
    except KeyError:
        return None


def extract_pft_features(
    session: ImportedSession,
    segmentation: PftSegmentationResult,
    transitions: PftTransitionDetectionResult,
    rules: FeatureExtractionRules = DEFAULT_FEATURE_RULES,
) -> PftFeatureExtractionResult:
    protocol = segmentation.protocol

    result: list[FeatureValue] = []

    def add(
        name: PftFeatureName,
        value: float | None,
        unit: str = "bpm",
    ) -> None:
        if value is None:
            return

        result.append(
            FeatureValue(
                name=name,
                value=float(value),
                unit=unit,
            )
        )

    # --------------------------------------------------
    # Steady / baseline HR
    # --------------------------------------------------

    add(
        PftFeatureName.HR_PRE_MEDIAN,
        _steady_stage_hr(
            session,
            protocol,
            PftStage.PRE,
            rules.steady_hr_window_s,
        ),
    )

    add(
        PftFeatureName.HR_P1_MEDIAN,
        _steady_stage_hr(
            session,
            protocol,
            PftStage.P1,
            rules.steady_hr_window_s,
        ),
    )

    add(
        PftFeatureName.HR_P2_MEDIAN,
        _steady_stage_hr(
            session,
            protocol,
            PftStage.P2,
            rules.steady_hr_window_s,
        ),
    )

    # --------------------------------------------------
    # HR response to OBSERVED external-load transitions
    # --------------------------------------------------

    p1_transition = _try_transition_to(
        transitions,
        PftStage.P1,
    )

    if p1_transition is not None:
        add(
            PftFeatureName.DELTA_HR30_P1,
            _observed_transition_delta_hr(
                session,
                p1_transition,
                30.0,
                rules,
            ),
        )

        add(
            PftFeatureName.DELTA_HR60_P1,
            _observed_transition_delta_hr(
                session,
                p1_transition,
                60.0,
                rules,
            ),
        )

    p2_transition = _try_transition_to(
        transitions,
        PftStage.P2,
    )

    if p2_transition is not None:
        add(
            PftFeatureName.DELTA_HR30_P2,
            _observed_transition_delta_hr(
                session,
                p2_transition,
                30.0,
                rules,
            ),
        )

        add(
            PftFeatureName.DELTA_HR60_P2,
            _observed_transition_delta_hr(
                session,
                p2_transition,
                60.0,
                rules,
            ),
        )

    # --------------------------------------------------
    # Recovery
    # --------------------------------------------------

    recovery = transitions.recovery_anchor

    for name, offset_s in (
        (PftFeatureName.HRR30, 30.0),
        (PftFeatureName.HRR60, 60.0),
        (PftFeatureName.HRR90, 90.0),
        (PftFeatureName.HRR120, 120.0),
    ):
        add(
            name,
            _recovery_feature(
                session,
                recovery.observed_s,
                offset_s,
                rules,
            ),
        )

    return PftFeatureExtractionResult(
        algorithm_version=rules.version,
        transition_rules_version=(
            transitions.rules_version
        ),
        features=tuple(result),
        recovery_anchor_s=recovery.observed_s,
        recovery_anchor_source=recovery.source,
    )