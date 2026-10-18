from dataclasses import dataclass
from enum import StrEnum

from app.pft_engine.pft.features import (
    PftFeatureExtractionResult,
    PftFeatureName,
)
from app.pft_engine.pft.protocol import (
    PftStage,
)
from app.pft_engine.pft.quality import (
    PftQualityAssessmentResult,
    PftQualityGrade,
)
from app.pft_engine.pft.transition_detection import (
    PftTransitionDetectionResult,
    RecoveryAnchorSource,
)


class FeatureQualityIssueCode(StrEnum):
    FEATURE_MISSING = "feature_missing"
    STAGE_QUALITY_LIMIT = "stage_quality_limit"
    TRANSITION_NOT_DETECTED = "transition_not_detected"
    RECOVERY_ANCHOR_FALLBACK = "recovery_anchor_fallback"


@dataclass(frozen=True)
class FeatureQualityRules:
    version: str = "feature_quality_v0.1"

    analysis_usable_grades: tuple[
        PftQualityGrade, ...
    ] = (
        PftQualityGrade.A,
        PftQualityGrade.B,
        PftQualityGrade.C,
    )

    baseline_eligible_grades: tuple[
        PftQualityGrade, ...
    ] = (
        PftQualityGrade.A,
        PftQualityGrade.B,
    )

    # If HR recovery is anchored only to the nominal
    # protocol boundary rather than an observed stop,
    # cap confidence at C.
    recovery_nominal_grade_cap: PftQualityGrade = (
        PftQualityGrade.C
    )


DEFAULT_FEATURE_QUALITY_RULES = FeatureQualityRules()


@dataclass(frozen=True)
class FeatureQualityIssue:
    code: FeatureQualityIssueCode
    message: str


@dataclass(frozen=True)
class FeatureQualityAssessment:
    feature: PftFeatureName
    source_stage: PftStage

    value_available: bool

    quality_grade: PftQualityGrade

    usable_for_analysis: bool
    baseline_eligible: bool

    issues: tuple[FeatureQualityIssue, ...]


@dataclass(frozen=True)
class PftFeatureQualityResult:
    rules_version: str

    feature_algorithm_version: str
    stage_quality_rules_version: str
    transition_rules_version: str

    features: tuple[FeatureQualityAssessment, ...]

    def get(
        self,
        feature: PftFeatureName,
    ) -> FeatureQualityAssessment:
        for item in self.features:
            if item.feature == feature:
                return item

        raise KeyError(
            f"Feature quality not found: {feature}"
        )


_GRADE_ORDER = {
    PftQualityGrade.A: 0,
    PftQualityGrade.B: 1,
    PftQualityGrade.C: 2,
    PftQualityGrade.X: 3,
}


P1_TRANSITION_FEATURES = {
    PftFeatureName.DELTA_HR30_P1,
    PftFeatureName.DELTA_HR60_P1,
}


P2_TRANSITION_FEATURES = {
    PftFeatureName.DELTA_HR30_P2,
    PftFeatureName.DELTA_HR60_P2,
}


RECOVERY_FEATURES = {
    PftFeatureName.HRR30,
    PftFeatureName.HRR60,
    PftFeatureName.HRR90,
    PftFeatureName.HRR120,
}


def _worst_grade(
    first: PftQualityGrade,
    second: PftQualityGrade,
) -> PftQualityGrade:
    if _GRADE_ORDER[first] >= _GRADE_ORDER[second]:
        return first

    return second


def _source_stage(
    feature: PftFeatureName,
) -> PftStage:
    if feature == PftFeatureName.HR_PRE_MEDIAN:
        return PftStage.PRE

    if feature in {
        PftFeatureName.HR_P1_MEDIAN,
        PftFeatureName.DELTA_HR30_P1,
        PftFeatureName.DELTA_HR60_P1,
    }:
        return PftStage.P1

    if feature in {
        PftFeatureName.HR_P2_MEDIAN,
        PftFeatureName.DELTA_HR30_P2,
        PftFeatureName.DELTA_HR60_P2,
    }:
        return PftStage.P2

    if feature in RECOVERY_FEATURES:
        return PftStage.RECOVERY

    raise ValueError(
        f"No quality source stage defined for feature: "
        f"{feature}"
    )


def _feature_exists(
    features: PftFeatureExtractionResult,
    name: PftFeatureName,
) -> bool:
    try:
        features.get(name)
    except KeyError:
        return False

    return True


def _transition_exists(
    transitions: PftTransitionDetectionResult,
    stage: PftStage,
) -> bool:
    try:
        transitions.get_transition_to(stage)
    except KeyError:
        return False

    return True


def _required_transition_stage(
    feature: PftFeatureName,
) -> PftStage | None:
    if feature in P1_TRANSITION_FEATURES:
        return PftStage.P1

    if feature in P2_TRANSITION_FEATURES:
        return PftStage.P2

    return None


def _assess_feature(
    *,
    feature: PftFeatureName,
    features: PftFeatureExtractionResult,
    stage_quality: PftQualityAssessmentResult,
    transitions: PftTransitionDetectionResult,
    rules: FeatureQualityRules,
) -> FeatureQualityAssessment:
    source_stage = _source_stage(feature)

    available = _feature_exists(
        features,
        feature,
    )

    issues: list[FeatureQualityIssue] = []

    required_transition = _required_transition_stage(
        feature
    )

    transition_available = True

    if required_transition is not None:
        transition_available = _transition_exists(
            transitions,
            required_transition,
        )

        if not transition_available:
            issues.append(
                FeatureQualityIssue(
                    code=(
                        FeatureQualityIssueCode
                        .TRANSITION_NOT_DETECTED
                    ),
                    message=(
                        "Required observed external-load "
                        "transition was not detected."
                    ),
                )
            )

    if not available:
        issues.append(
            FeatureQualityIssue(
                code=FeatureQualityIssueCode.FEATURE_MISSING,
                message=(
                    "Feature value could not be calculated."
                ),
            )
        )

    if not available or not transition_available:
        return FeatureQualityAssessment(
            feature=feature,
            source_stage=source_stage,
            value_available=available,
            quality_grade=PftQualityGrade.X,
            usable_for_analysis=False,
            baseline_eligible=False,
            issues=tuple(issues),
        )

    stage_assessment = stage_quality.get_stage(
        source_stage
    )

    grade = stage_assessment.grade

    if grade != PftQualityGrade.A:
        issues.append(
            FeatureQualityIssue(
                code=(
                    FeatureQualityIssueCode
                    .STAGE_QUALITY_LIMIT
                ),
                message=(
                    f"Feature quality is limited by "
                    f"{source_stage.value} stage quality "
                    f"{grade.value}."
                ),
            )
        )

    if (
        feature in RECOVERY_FEATURES
        and features.recovery_anchor_source
        == RecoveryAnchorSource.NOMINAL
    ):
        grade = _worst_grade(
            grade,
            rules.recovery_nominal_grade_cap,
        )

        issues.append(
            FeatureQualityIssue(
                code=(
                    FeatureQualityIssueCode
                    .RECOVERY_ANCHOR_FALLBACK
                ),
                message=(
                    "Recovery feature uses nominal protocol "
                    "timing because an observed stop was not "
                    "available."
                ),
            )
        )

    usable_for_analysis = (
        grade in rules.analysis_usable_grades
    )

    baseline_eligible = (
        grade in rules.baseline_eligible_grades
    )

    return FeatureQualityAssessment(
        feature=feature,
        source_stage=source_stage,
        value_available=True,
        quality_grade=grade,
        usable_for_analysis=usable_for_analysis,
        baseline_eligible=baseline_eligible,
        issues=tuple(issues),
    )


def assess_feature_quality(
    *,
    features: PftFeatureExtractionResult,
    stage_quality: PftQualityAssessmentResult,
    transitions: PftTransitionDetectionResult,
    rules: FeatureQualityRules = (
        DEFAULT_FEATURE_QUALITY_RULES
    ),
) -> PftFeatureQualityResult:
    assessments = tuple(
        _assess_feature(
            feature=feature,
            features=features,
            stage_quality=stage_quality,
            transitions=transitions,
            rules=rules,
        )
        for feature in PftFeatureName
    )

    return PftFeatureQualityResult(
        rules_version=rules.version,
        feature_algorithm_version=(
            features.algorithm_version
        ),
        stage_quality_rules_version=(
            stage_quality.rules_version
        ),
        transition_rules_version=(
            transitions.rules_version
        ),
        features=assessments,
    )