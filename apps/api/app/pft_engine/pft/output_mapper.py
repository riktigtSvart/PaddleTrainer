from app.pft_engine.contracts.input import (
    ImportedSession,
)
from app.pft_engine.contracts.output import (
    AlgorithmLineageOutput,
    ExperimentalOutput,
    FeatureOutput,
    MetricStatisticsOutput,
    PFT_OUTPUT_SCHEMA_VERSION,
    PftProcessingOutputV2,
    ProtocolOutput,
    RecoveryAnchorOutput,
    RhriDiagnosticsOutput,
    RhriLocalOutput,
    RhriMethodComparisonOutput,
    RhriSigOutput,
    RhriWindowPointOutput,
    RhriWindowSensitivityOutput,
    SessionOutput,
    StageQualityOutput,
    StageStatisticsOutput,
    TransitionOutput,
)
from app.pft_engine.pft.features import (
    PftFeatureName,
)
from app.pft_engine.pft.processor import (
    PftProcessingResult,
)


def _metric(metric) -> MetricStatisticsOutput:
    return MetricStatisticsOutput(
        count=metric.count,
        mean=metric.mean,
        median=metric.median,
        minimum=metric.minimum,
        maximum=metric.maximum,
        sd=metric.sd,
        cv_pct=metric.cv_pct,
    )


def build_pft_output_contract(
    *,
    session: ImportedSession,
    result: PftProcessingResult,
) -> PftProcessingOutputV2:

    stage_statistics = tuple(
        StageStatisticsOutput(
            stage=stage.stage.value,
            sample_count=stage.sample_count,
            observed_span_s=stage.observed_span_s,
            distance_delta_m=stage.distance_delta_m,
            hr=_metric(stage.hr),
            power=_metric(stage.power),
            cadence=_metric(stage.cadence),
            speed=_metric(stage.speed),
        )
        for stage in result.stage_statistics.stages
    )

    stage_quality = tuple(
        StageQualityOutput(
            stage=stage.stage.value,
            grade=stage.grade.value,
            duration_completeness=(
                stage.duration_completeness
            ),
            hr_coverage=stage.hr_coverage,
            power_coverage=stage.power_coverage,
            steady_power_mean=(
                stage.steady_power_mean
            ),
            steady_power_cv_pct=(
                stage.steady_power_cv_pct
            ),
            issue_codes=tuple(
                issue.code.value
                for issue in stage.issues
            ),
        )
        for stage in result.stage_quality.stages
    )

    transitions = tuple(
        TransitionOutput(
            from_stage=transition.from_stage.value,
            to_stage=transition.to_stage.value,
            signal=transition.signal.value,
            direction=transition.direction.value,
            nominal_transition_s=(
                transition.nominal_transition_s
            ),
            pre_load_w=transition.pre_load_w,
            post_load_w=transition.post_load_w,
            delta_load_w=transition.delta_load_w,
            ramp_start_s=transition.ramp_start_s,
            midpoint_s=transition.midpoint_s,
            steady_start_s=transition.steady_start_s,
            ramp_duration_s=(
                transition.ramp_duration_s
            ),
            nominal_to_midpoint_delay_s=(
                transition.nominal_to_midpoint_delay_s
            ),
        )
        for transition in (
            result.transitions.load_transitions
        )
    )

    recovery = result.transitions.recovery_anchor

    feature_outputs: list[FeatureOutput] = []

    for feature_name in PftFeatureName:
        quality = result.feature_quality.get(
            feature_name
        )

        try:
            feature = result.features.get(
                feature_name
            )
        except KeyError:
            feature = None

        feature_outputs.append(
            FeatureOutput(
                name=feature_name.value,
                value=(
                    feature.value
                    if feature is not None
                    else None
                ),
                unit=(
                    feature.unit
                    if feature is not None
                    else None
                ),
                quality_grade=(
                    quality.quality_grade.value
                ),
                usable_for_analysis=(
                    quality.usable_for_analysis
                ),
                baseline_eligible=(
                    quality.baseline_eligible
                ),
                issue_codes=tuple(
                    issue.code.value
                    for issue in quality.issues
                ),
            )
        )

    rhri_local = tuple(
        RhriLocalOutput(
            stage=value.stage.value,
            value_bpm_per_s=(
                value.value_bpm_per_s
            ),
            peak_elapsed_s=(
                value.peak_elapsed_s
            ),
            search_start_s=(
                value.search_start_s
            ),
            search_end_s=(
                value.search_end_s
            ),
            sampling_interval_s=(
                value.sampling_interval_s
            ),
            window_length=value.window_length,
            polyorder=value.polyorder,
        )
        for value in (
            result.experimental
            .rhri_local
            .values
        )
    )

    rhri_sig = tuple(
        RhriSigOutput(
            stage=value.stage.value,
            value_bpm_per_s=(
                value.value_bpm_per_s
            ),
            lower_plateau_bpm=(
                value.lower_plateau_bpm
            ),
            response_range_bpm=(
                value.response_range_bpm
            ),
            upper_curvature_per_s=(
                value.upper_curvature_per_s
            ),
            lower_curvature_per_s=(
                value.lower_curvature_per_s
            ),
            midpoint_s_from_ramp=(
                value.midpoint_s_from_ramp
            ),
            midpoint_elapsed_s=(
                value.midpoint_elapsed_s
            ),
            midpoint_slope_bpm_per_s=value.midpoint_slope_bpm_per_s,
            peak_elapsed_s=value.peak_elapsed_s,
            search_start_s=value.search_start_s,
            search_end_s=value.search_end_s,
            peak_at_search_boundary=value.peak_at_search_boundary,
            fit_start_s=value.fit_start_s,
            fit_end_s=value.fit_end_s,
            sample_count=value.sample_count,
            pre_sample_count=(
                value.pre_sample_count
            ),
            post_sample_count=(
                value.post_sample_count
            ),
            mse_bpm2=value.mse_bpm2,
            r_squared=value.r_squared,
        )
        for value in (
            result.experimental
            .rhri_sig
            .values
        )
    )

    diagnostics = (
        result.experimental.rhri_diagnostics
    )

    diagnostic_comparisons = tuple(
        RhriMethodComparisonOutput(
            stage=value.stage.value,
            local_bpm_per_s=(
                value.local_bpm_per_s
            ),
            sig_bpm_per_s=(
                value.sig_bpm_per_s
            ),
            absolute_difference_bpm_per_s=(
                value.absolute_difference_bpm_per_s
            ),
            relative_difference_pct=(
                value.relative_difference_pct
            ),
            local_to_sig_ratio=(
                value.local_to_sig_ratio
            ),
            local_peak_elapsed_s=(
                value.local_peak_elapsed_s
            ),
            sig_midpoint_elapsed_s=(
                value.sig_midpoint_elapsed_s
            ),
            sig_peak_elapsed_s=value.sig_peak_elapsed_s,
            peak_timing_difference_s=value.peak_timing_difference_s,
            timing_difference_s=(
                value.timing_difference_s
            ),
            sig_r_squared=(
                value.sig_r_squared
            ),
            sig_mse_bpm2=value.sig_mse_bpm2,
        )
        for value in diagnostics.comparisons
    )

    sensitivity = tuple(
        RhriWindowSensitivityOutput(
            stage=value.stage.value,
            points=tuple(
                RhriWindowPointOutput(
                    window_length=point.window_length,
                    value_bpm_per_s=(
                        point.value_bpm_per_s
                    ),
                )
                for point in value.points
            ),
            minimum_bpm_per_s=(
                value.minimum_bpm_per_s
            ),
            maximum_bpm_per_s=(
                value.maximum_bpm_per_s
            ),
            range_bpm_per_s=(
                value.range_bpm_per_s
            ),
            mean_bpm_per_s=(
                value.mean_bpm_per_s
            ),
            cv_pct=value.cv_pct,
        )
        for value in (
            diagnostics.window_sensitivity
        )
    )

    return PftProcessingOutputV2(
        schema_version=PFT_OUTPUT_SCHEMA_VERSION,
        session=SessionOutput(
            started_at=(
                session.started_at.isoformat()
            ),
            duration_s=session.duration_s,
            sample_count=len(session.samples),
            unassigned_sample_count=len(
                result.segmentation.unassigned_samples
            ),
        ),
        protocol=ProtocolOutput(
            name=result.protocol.name,
            version=result.protocol.version,
            duration_s=result.protocol.duration_s,
        ),
        algorithm_lineage=AlgorithmLineageOutput(
            processor=result.processor_version,
            stage_quality=(
                result.stage_quality.rules_version
            ),
            transition_detection=(
                result.transitions.rules_version
            ),
            feature_extraction=(
                result.features.algorithm_version
            ),
            feature_quality=(
                result.feature_quality.rules_version
            ),
            rhri_local=(
                result.experimental
                .rhri_local
                .rules_version
            ),
            rhri_sig=(
                result.experimental
                .rhri_sig
                .rules_version
            ),
            rhri_diagnostics=(
                diagnostics.rules_version
            ),
        ),
        session_quality_grade=(
            result.stage_quality
            .session_grade
            .value
        ),
        stage_statistics=stage_statistics,
        stage_quality=stage_quality,
        transitions=transitions,
        recovery_anchor=RecoveryAnchorOutput(
            nominal_s=recovery.nominal_s,
            observed_s=recovery.observed_s,
            source=recovery.source.value,
        ),
        features=tuple(feature_outputs),
        experimental=ExperimentalOutput(
            rhri_local=rhri_local,
            rhri_sig=rhri_sig,
            rhri_diagnostics=(
                RhriDiagnosticsOutput(
                    local_p2_minus_p1_bpm_per_s=(
                        diagnostics
                        .local_p2_minus_p1_bpm_per_s
                    ),
                    sig_p2_minus_p1_bpm_per_s=(
                        diagnostics
                        .sig_p2_minus_p1_bpm_per_s
                    ),
                    p1_p2_direction_agreement=(
                        diagnostics
                        .p1_p2_direction_agreement
                    ),
                    local_to_sig_ratio_spread=(
                        diagnostics
                        .local_to_sig_ratio_spread
                    ),
                    comparisons=(
                        diagnostic_comparisons
                    ),
                    window_sensitivity=sensitivity,
                )
            ),
        ),
    )
