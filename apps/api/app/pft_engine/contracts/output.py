from dataclasses import dataclass


PFT_OUTPUT_SCHEMA_VERSION = "pft_processing_output_v2"


@dataclass(frozen=True)
class SessionOutput:
    started_at: str
    duration_s: float
    sample_count: int
    unassigned_sample_count: int


@dataclass(frozen=True)
class ProtocolOutput:
    name: str
    version: str
    duration_s: float


@dataclass(frozen=True)
class AlgorithmLineageOutput:
    processor: str
    stage_quality: str
    transition_detection: str
    feature_extraction: str
    feature_quality: str
    rhri_local: str
    rhri_sig: str
    rhri_diagnostics: str


@dataclass(frozen=True)
class MetricStatisticsOutput:
    count: int

    mean: float | None
    median: float | None

    minimum: float | None
    maximum: float | None

    sd: float | None
    cv_pct: float | None


@dataclass(frozen=True)
class StageStatisticsOutput:
    stage: str

    sample_count: int
    observed_span_s: float

    distance_delta_m: float | None

    hr: MetricStatisticsOutput
    power: MetricStatisticsOutput
    cadence: MetricStatisticsOutput
    speed: MetricStatisticsOutput


@dataclass(frozen=True)
class StageQualityOutput:
    stage: str
    grade: str

    duration_completeness: float
    hr_coverage: float

    power_coverage: float | None

    steady_power_mean: float | None
    steady_power_cv_pct: float | None

    issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class TransitionOutput:
    from_stage: str
    to_stage: str

    signal: str
    direction: str

    nominal_transition_s: float

    pre_load_w: float
    post_load_w: float
    delta_load_w: float

    ramp_start_s: float
    midpoint_s: float
    steady_start_s: float

    ramp_duration_s: float
    nominal_to_midpoint_delay_s: float


@dataclass(frozen=True)
class RecoveryAnchorOutput:
    nominal_s: float
    observed_s: float
    source: str


@dataclass(frozen=True)
class FeatureOutput:
    name: str

    value: float | None
    unit: str | None

    quality_grade: str

    usable_for_analysis: bool
    baseline_eligible: bool

    issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class RhriLocalOutput:
    stage: str

    value_bpm_per_s: float
    peak_elapsed_s: float

    search_start_s: float
    search_end_s: float

    sampling_interval_s: float

    window_length: int
    polyorder: int


@dataclass(frozen=True)
class RhriSigOutput:
    stage: str

    value_bpm_per_s: float

    lower_plateau_bpm: float
    response_range_bpm: float

    upper_curvature_per_s: float
    lower_curvature_per_s: float

    midpoint_s_from_ramp: float
    midpoint_elapsed_s: float
    midpoint_slope_bpm_per_s: float
    peak_elapsed_s: float
    search_start_s: float
    search_end_s: float
    peak_at_search_boundary: bool

    fit_start_s: float
    fit_end_s: float

    sample_count: int
    pre_sample_count: int
    post_sample_count: int

    mse_bpm2: float
    r_squared: float


@dataclass(frozen=True)
class RhriMethodComparisonOutput:
    stage: str

    local_bpm_per_s: float
    sig_bpm_per_s: float

    absolute_difference_bpm_per_s: float
    relative_difference_pct: float

    local_to_sig_ratio: float

    local_peak_elapsed_s: float
    sig_midpoint_elapsed_s: float
    sig_peak_elapsed_s: float
    peak_timing_difference_s: float
    timing_difference_s: float

    sig_r_squared: float
    sig_mse_bpm2: float


@dataclass(frozen=True)
class RhriWindowPointOutput:
    window_length: int
    value_bpm_per_s: float


@dataclass(frozen=True)
class RhriWindowSensitivityOutput:
    stage: str

    points: tuple[
        RhriWindowPointOutput, ...
    ]

    minimum_bpm_per_s: float
    maximum_bpm_per_s: float
    range_bpm_per_s: float

    mean_bpm_per_s: float
    cv_pct: float | None


@dataclass(frozen=True)
class RhriDiagnosticsOutput:
    local_p2_minus_p1_bpm_per_s: float | None
    sig_p2_minus_p1_bpm_per_s: float | None

    p1_p2_direction_agreement: bool | None

    local_to_sig_ratio_spread: float | None

    comparisons: tuple[
        RhriMethodComparisonOutput, ...
    ]

    window_sensitivity: tuple[
        RhriWindowSensitivityOutput, ...
    ]


@dataclass(frozen=True)
class ExperimentalOutput:
    rhri_local: tuple[
        RhriLocalOutput, ...
    ]

    rhri_sig: tuple[
        RhriSigOutput, ...
    ]

    rhri_diagnostics: RhriDiagnosticsOutput


@dataclass(frozen=True)
class PftProcessingOutputV2:
    schema_version: str

    session: SessionOutput
    protocol: ProtocolOutput

    algorithm_lineage: AlgorithmLineageOutput

    session_quality_grade: str

    stage_statistics: tuple[
        StageStatisticsOutput, ...
    ]

    stage_quality: tuple[
        StageQualityOutput, ...
    ]

    transitions: tuple[
        TransitionOutput, ...
    ]

    recovery_anchor: RecoveryAnchorOutput

    features: tuple[
        FeatureOutput, ...
    ]

    experimental: ExperimentalOutput
