from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean, median, pstdev

from app.pft_engine.pft.protocol import (
    PftProtocol,
    PftStage,
)
from app.pft_engine.pft.segmentation import (
    PftSegmentationResult,
    StageSegment,
)


class PftQualityGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    X = "X"


class QualityIssueCode(StrEnum):
    EMPTY_STAGE = "empty_stage"
    DURATION_INCOMPLETE = "duration_incomplete"
    HR_COVERAGE_LOW = "hr_coverage_low"
    POWER_COVERAGE_LOW = "power_coverage_low"
    POWER_VARIABILITY_HIGH = "power_variability_high"
    POWER_NOT_POSITIVE = "power_not_positive"


@dataclass(frozen=True)
class QualityRules:
    version: str = "quality_v0.1"

    # Stage completeness
    completeness_a: float = 0.98
    completeness_b: float = 0.95
    completeness_c: float = 0.80

    # Signal coverage
    coverage_a: float = 0.98
    coverage_b: float = 0.95
    coverage_c: float = 0.80

    # Power stability
    power_cv_a_pct: float = 5.0
    power_cv_b_pct: float = 10.0
    power_cv_c_pct: float = 20.0

    # Ignore the transition/start of the stage and assess
    # external-load stability near the end.
    steady_window_s: float = 60.0


DEFAULT_QUALITY_RULES = QualityRules()


@dataclass(frozen=True)
class QualityIssue:
    code: QualityIssueCode
    measured_value: float | None
    reference_value: float | None
    message: str


@dataclass(frozen=True)
class StageQualityAssessment:
    stage: PftStage
    grade: PftQualityGrade

    duration_completeness: float

    hr_coverage: float

    power_coverage: float | None
    steady_power_mean: float | None
    steady_power_cv_pct: float | None

    issues: tuple[QualityIssue, ...]


@dataclass(frozen=True)
class PftQualityAssessmentResult:
    rules_version: str
    session_grade: PftQualityGrade
    stages: tuple[StageQualityAssessment, ...]

    def get_stage(
        self,
        stage: PftStage,
    ) -> StageQualityAssessment:
        for assessment in self.stages:
            if assessment.stage == stage:
                return assessment

        raise KeyError(f"Stage quality not found: {stage}")


_GRADE_ORDER = {
    PftQualityGrade.A: 0,
    PftQualityGrade.B: 1,
    PftQualityGrade.C: 2,
    PftQualityGrade.X: 3,
}


LOAD_STAGES = {
    PftStage.P0,
    PftStage.P1,
    PftStage.P2,
}


def _worst_grade(
    grades: list[PftQualityGrade],
) -> PftQualityGrade:
    return max(
        grades,
        key=lambda grade: _GRADE_ORDER[grade],
    )


def _grade_minimum(
    value: float,
    *,
    a: float,
    b: float,
    c: float,
) -> PftQualityGrade:
    if value >= a:
        return PftQualityGrade.A

    if value >= b:
        return PftQualityGrade.B

    if value >= c:
        return PftQualityGrade.C

    return PftQualityGrade.X


def _grade_maximum(
    value: float,
    *,
    a: float,
    b: float,
    c: float,
) -> PftQualityGrade:
    if value <= a:
        return PftQualityGrade.A

    if value <= b:
        return PftQualityGrade.B

    if value <= c:
        return PftQualityGrade.C

    return PftQualityGrade.X


def _signal_coverage(
    values: list[float | None],
) -> float:
    if not values:
        return 0.0

    valid = sum(
        value is not None
        for value in values
    )

    return valid / len(values)


def _sampling_interval_s(
    segment: StageSegment,
) -> float | None:
    if len(segment.samples) < 2:
        return None

    deltas = [
        current.elapsed_s - previous.elapsed_s
        for previous, current in zip(
            segment.samples,
            segment.samples[1:],
        )
        if current.elapsed_s > previous.elapsed_s
    ]

    if not deltas:
        return None

    return float(median(deltas))


def _duration_completeness(
    segment: StageSegment,
    nominal_duration_s: float,
) -> float:
    if not segment.samples:
        return 0.0

    sampling_interval = _sampling_interval_s(segment)

    if sampling_interval is None:
        observed_duration = 0.0
    else:
        observed_duration = (
            segment.duration_s
            + sampling_interval
        )

    if nominal_duration_s <= 0.0:
        return 0.0

    return min(
        observed_duration / nominal_duration_s,
        1.0,
    )


def _steady_power_values(
    segment: StageSegment,
    window_s: float,
) -> list[float]:
    if not segment.samples:
        return []

    stage_end_s = segment.samples[-1].elapsed_s

    window_start_s = (
        stage_end_s
        - window_s
        + 1.0
    )

    return [
        float(sample.power_w)
        for sample in segment.samples
        if (
            sample.elapsed_s >= window_start_s
            and sample.power_w is not None
        )
    ]


def _cv_pct(
    values: list[float],
) -> tuple[float | None, float | None]:
    if not values:
        return None, None

    mean_value = fmean(values)

    if mean_value <= 0.0:
        return mean_value, None

    if len(values) < 2:
        return mean_value, 0.0

    sd_value = pstdev(values)

    return (
        mean_value,
        sd_value / mean_value * 100.0,
    )


def _nominal_stage_duration(
    protocol: PftProtocol,
    stage: PftStage,
) -> float:
    for window in protocol.stages:
        if window.stage == stage:
            return window.duration_s

    raise KeyError(
        f"Protocol does not contain stage: {stage}"
    )


def assess_stage_quality(
    segment: StageSegment,
    protocol: PftProtocol,
    rules: QualityRules = DEFAULT_QUALITY_RULES,
) -> StageQualityAssessment:
    issues: list[QualityIssue] = []
    component_grades: list[PftQualityGrade] = []

    if not segment.samples:
        return StageQualityAssessment(
            stage=segment.stage,
            grade=PftQualityGrade.X,
            duration_completeness=0.0,
            hr_coverage=0.0,
            power_coverage=None,
            steady_power_mean=None,
            steady_power_cv_pct=None,
            issues=(
                QualityIssue(
                    code=QualityIssueCode.EMPTY_STAGE,
                    measured_value=0.0,
                    reference_value=None,
                    message="Stage contains no samples.",
                ),
            ),
        )

    nominal_duration = _nominal_stage_duration(
        protocol,
        segment.stage,
    )

    completeness = _duration_completeness(
        segment,
        nominal_duration,
    )

    completeness_grade = _grade_minimum(
        completeness,
        a=rules.completeness_a,
        b=rules.completeness_b,
        c=rules.completeness_c,
    )

    component_grades.append(completeness_grade)

    if completeness_grade != PftQualityGrade.A:
        issues.append(
            QualityIssue(
                code=QualityIssueCode.DURATION_INCOMPLETE,
                measured_value=completeness,
                reference_value=rules.completeness_a,
                message=(
                    "Stage duration completeness "
                    "does not meet grade A."
                ),
            )
        )

    hr_values = [
        sample.hr_bpm
        for sample in segment.samples
    ]

    hr_coverage = _signal_coverage(hr_values)

    hr_grade = _grade_minimum(
        hr_coverage,
        a=rules.coverage_a,
        b=rules.coverage_b,
        c=rules.coverage_c,
    )

    component_grades.append(hr_grade)

    if hr_grade != PftQualityGrade.A:
        issues.append(
            QualityIssue(
                code=QualityIssueCode.HR_COVERAGE_LOW,
                measured_value=hr_coverage,
                reference_value=rules.coverage_a,
                message=(
                    "Heart-rate signal coverage "
                    "does not meet grade A."
                ),
            )
        )

    power_coverage: float | None = None
    steady_power_mean: float | None = None
    steady_power_cv_pct: float | None = None

    if segment.stage in LOAD_STAGES:
        power_values = [
            sample.power_w
            for sample in segment.samples
        ]

        power_coverage = _signal_coverage(
            power_values
        )

        power_coverage_grade = _grade_minimum(
            power_coverage,
            a=rules.coverage_a,
            b=rules.coverage_b,
            c=rules.coverage_c,
        )

        component_grades.append(
            power_coverage_grade
        )

        if (
            power_coverage_grade
            != PftQualityGrade.A
        ):
            issues.append(
                QualityIssue(
                    code=(
                        QualityIssueCode
                        .POWER_COVERAGE_LOW
                    ),
                    measured_value=power_coverage,
                    reference_value=rules.coverage_a,
                    message=(
                        "Power signal coverage "
                        "does not meet grade A."
                    ),
                )
            )

        steady_power = _steady_power_values(
            segment,
            rules.steady_window_s,
        )

        (
            steady_power_mean,
            steady_power_cv_pct,
        ) = _cv_pct(steady_power)

        if (
            steady_power_mean is None
            or steady_power_mean <= 0.0
        ):
            component_grades.append(
                PftQualityGrade.X
            )

            issues.append(
                QualityIssue(
                    code=(
                        QualityIssueCode
                        .POWER_NOT_POSITIVE
                    ),
                    measured_value=steady_power_mean,
                    reference_value=0.0,
                    message=(
                        "Steady-stage power is not "
                        "positive."
                    ),
                )
            )

        elif steady_power_cv_pct is not None:
            power_cv_grade = _grade_maximum(
                steady_power_cv_pct,
                a=rules.power_cv_a_pct,
                b=rules.power_cv_b_pct,
                c=rules.power_cv_c_pct,
            )

            component_grades.append(
                power_cv_grade
            )

            if power_cv_grade != PftQualityGrade.A:
                issues.append(
                    QualityIssue(
                        code=(
                            QualityIssueCode
                            .POWER_VARIABILITY_HIGH
                        ),
                        measured_value=(
                            steady_power_cv_pct
                        ),
                        reference_value=(
                            rules.power_cv_a_pct
                        ),
                        message=(
                            "Steady-stage power "
                            "variability does not "
                            "meet grade A."
                        ),
                    )
                )

    grade = _worst_grade(component_grades)

    return StageQualityAssessment(
        stage=segment.stage,
        grade=grade,
        duration_completeness=completeness,
        hr_coverage=hr_coverage,
        power_coverage=power_coverage,
        steady_power_mean=steady_power_mean,
        steady_power_cv_pct=steady_power_cv_pct,
        issues=tuple(issues),
    )


def assess_pft_quality(
    segmentation: PftSegmentationResult,
    rules: QualityRules = DEFAULT_QUALITY_RULES,
) -> PftQualityAssessmentResult:
    assessments = tuple(
        assess_stage_quality(
            segment=segment,
            protocol=segmentation.protocol,
            rules=rules,
        )
        for segment in segmentation.segments
    )

    session_grade = _worst_grade(
        [
            assessment.grade
            for assessment in assessments
        ]
    )

    return PftQualityAssessmentResult(
        rules_version=rules.version,
        session_grade=session_grade,
        stages=assessments,
    )