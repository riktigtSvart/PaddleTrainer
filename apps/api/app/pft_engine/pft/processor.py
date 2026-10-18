from dataclasses import dataclass, field

from app.pft_engine.contracts.input import (
    ImportedSession,
)
from app.pft_engine.pft.feature_quality import (
    FeatureQualityRules,
    PftFeatureQualityResult,
    assess_feature_quality,
)
from app.pft_engine.pft.features import (
    FeatureExtractionRules,
    FeatureValue,
    PftFeatureExtractionResult,
    PftFeatureName,
    extract_pft_features,
)
from app.pft_engine.pft.protocol import (
    PftProtocol,
)
from app.pft_engine.pft.quality import (
    PftQualityAssessmentResult,
    PftQualityGrade,
    QualityRules,
    assess_pft_quality,
)
from app.pft_engine.pft.segmentation import (
    PftSegmentationResult,
    segment_session,
)
from app.pft_engine.pft.stage_statistics import (
    PftStageStatisticsResult,
    calculate_all_stage_statistics,
)
from app.pft_engine.pft.transition_detection import (
    PftTransitionDetectionResult,
    TransitionDetectionRules,
    detect_pft_transitions,
)
from app.pft_engine.pft.rhri import (
    PftRhriLocalResult,
    RhriLocalRules,
    calculate_rhri_local,
)
from app.pft_engine.pft.rhri_sig import (
    PftRhriSigResult,
    RhriSigRules,
    calculate_rhri_sig,
)
from app.pft_engine.pft.rhri_diagnostics import (
    PftRhriDiagnosticsResult,
    RhriDiagnosticsRules,
    calculate_rhri_diagnostics,
)


@dataclass(frozen=True)
class PftProcessingRules:
    version: str = "processor_v0.5"

    quality: QualityRules = field(
        default_factory=QualityRules
    )

    transitions: TransitionDetectionRules = field(
        default_factory=TransitionDetectionRules
    )

    features: FeatureExtractionRules = field(
        default_factory=FeatureExtractionRules
    )

    feature_quality: FeatureQualityRules = field(
        default_factory=FeatureQualityRules
    )

    rhri_local: RhriLocalRules = field(
        default_factory=RhriLocalRules
    )

    rhri_sig: RhriSigRules = field(
        default_factory=RhriSigRules
    )

    rhri_diagnostics: RhriDiagnosticsRules = field(
        default_factory=RhriDiagnosticsRules
    )


DEFAULT_PROCESSING_RULES = PftProcessingRules()


@dataclass(frozen=True)
class PftExperimentalResult:
    rhri_local: PftRhriLocalResult
    rhri_sig: PftRhriSigResult
    rhri_diagnostics: PftRhriDiagnosticsResult


@dataclass(frozen=True)
class PftProcessingResult:
    processor_version: str

    protocol: PftProtocol

    segmentation: PftSegmentationResult

    stage_statistics: PftStageStatisticsResult

    stage_quality: PftQualityAssessmentResult

    transitions: PftTransitionDetectionResult

    features: PftFeatureExtractionResult

    feature_quality: PftFeatureQualityResult

    experimental: PftExperimentalResult

    def get_feature(
        self,
        name: PftFeatureName,
    ) -> FeatureValue:
        return self.features.get(name)

    def get_feature_grade(
        self,
        name: PftFeatureName,
    ) -> PftQualityGrade:
        return self.feature_quality.get(
            name
        ).quality_grade


def process_pft(
    *,
    session: ImportedSession,
    protocol: PftProtocol,
    rules: PftProcessingRules = (
        DEFAULT_PROCESSING_RULES
    ),
) -> PftProcessingResult:
    """
    Execute the complete PFT physiological processing pipeline.

    This function performs orchestration only.
    Scientific calculations remain in their dedicated modules.
    """

    segmentation = segment_session(
        session=session,
        protocol=protocol,
    )

    stage_statistics = (
        calculate_all_stage_statistics(
            segmentation
        )
    )

    stage_quality = assess_pft_quality(
        segmentation,
        rules=rules.quality,
    )

    transitions = detect_pft_transitions(
        session=session,
        protocol=protocol,
        rules=rules.transitions,
    )

    rhri_local = calculate_rhri_local(
        session=session,
        transitions=transitions,
        rules=rules.rhri_local,
    )

    rhri_sig = calculate_rhri_sig(
        session=session,
        protocol=protocol,
        transitions=transitions,
        rules=rules.rhri_sig,
    )

    rhri_diagnostics = calculate_rhri_diagnostics(
        session=session,
        transitions=transitions,
        rhri_local=rhri_local,
        rhri_sig=rhri_sig,
        local_rules=rules.rhri_local,
        rules=rules.rhri_diagnostics,
    )

    features = extract_pft_features(
        session=session,
        segmentation=segmentation,
        transitions=transitions,
        rules=rules.features,
    )

    feature_quality = assess_feature_quality(
        features=features,
        stage_quality=stage_quality,
        transitions=transitions,
        rules=rules.feature_quality,
    )

    return PftProcessingResult(
        processor_version=rules.version,
        protocol=protocol,
        segmentation=segmentation,
        stage_statistics=stage_statistics,
        stage_quality=stage_quality,
        transitions=transitions,
        features=features,
        feature_quality=feature_quality,
        experimental=PftExperimentalResult(
            rhri_local=rhri_local,
            rhri_sig=rhri_sig,
            rhri_diagnostics=rhri_diagnostics,
        ),
    )