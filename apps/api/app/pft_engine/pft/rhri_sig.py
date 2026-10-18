from dataclasses import dataclass
from statistics import fmean, pstdev

import numpy as np
from scipy.optimize import least_squares, minimize_scalar

from app.pft_engine.contracts.input import (
    ImportedSession,
)
from app.pft_engine.pft.protocol import (
    PftProtocol,
    PftStage,
)
from app.pft_engine.pft.transition_detection import (
    DetectedLoadTransition,
    PftTransitionDetectionResult,
)


@dataclass(frozen=True)
class RhriSigRules:
    version: str = "rhri_sig_v0.2"

    # Research protocols commonly include pre-transition
    # HR in the sigmoid fit.
    pre_window_s: float = 30.0

    # PFT stages are 3 minutes long.
    post_window_s: float = 180.0

    steady_reference_window_s: float = 60.0

    minimum_pre_samples: int = 15
    minimum_post_samples: int = 60

    minimum_response_range_bpm: float = 5.0

    # Published work constrained baseline HR when needed.
    baseline_sd_multiplier: float = 1.96

    # SciPy requires lower < upper bounds even when
    # pre-transition HR variance is zero.
    minimum_baseline_half_width_bpm: float = 0.5

    minimum_curvature_per_s: float = 0.001
    maximum_curvature_per_s: float = 2.0

    maximum_response_range_bpm: float = 100.0

    max_nfev: int = 50_000

    # Curvature is bounded by 2 / s by default. Bracket every
    # sampled local slope maximum, rather than assuming unimodality.
    peak_grid_step_s: float = 0.05
    peak_time_tolerance_s: float = 1e-9


DEFAULT_RHRI_SIG_RULES = RhriSigRules()


@dataclass(frozen=True)
class RhriSigValue:
    stage: PftStage

    value_bpm_per_s: float

    # Published five-component sigmoid parameters.
    lower_plateau_bpm: float       # a
    response_range_bpm: float      # b
    upper_curvature_per_s: float   # c
    midpoint_s_from_ramp: float    # d
    lower_curvature_per_s: float   # e

    midpoint_elapsed_s: float

    # v0.1 exported this midpoint slope as the maximum.
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
class PftRhriSigResult:
    rules_version: str
    model_name: str
    values: tuple[RhriSigValue, ...]

    def get_stage(
        self,
        stage: PftStage,
    ) -> RhriSigValue:
        for value in self.values:
            if value.stage == stage:
                return value

        raise KeyError(
            f"RHRI_SIG not found for stage: {stage}"
        )


def _protocol_stage_end(
    protocol: PftProtocol,
    stage: PftStage,
) -> float:
    for window in protocol.stages:
        if window.stage == stage:
            return window.end_s

    raise KeyError(
        f"Protocol does not contain stage: {stage}"
    )


def _sigmoid_5_component(
    time_s: np.ndarray,
    a: float,
    b: float,
    c: float,
    d: float,
    e: float,
) -> np.ndarray:
    """
    Five-component sigmoid used in published rHRI work.

    a = lower HR plateau
    b = HR response range
    c = upper curvature parameter
    d = time at half response
    e = lower curvature parameter
    """

    curvature_mean = (
        2.0 * c * e
        / (c + e)
    )

    z = d - time_s

    weight = 1.0 / (
        1.0
        + np.exp(
            np.clip(
                -curvature_mean * z,
                -60.0,
                60.0,
            )
        )
    )

    upper_term = np.exp(
        np.clip(
            c * z,
            -60.0,
            60.0,
        )
    )

    lower_term = np.exp(
        np.clip(
            e * z,
            -60.0,
            60.0,
        )
    )

    denominator = (
        1.0
        + weight * upper_term
        + (1.0 - weight) * lower_term
    )

    return (
        a
        + b / denominator
    )


def _sigmoid_5_component_derivative(
    time_s: np.ndarray,
    a: float,
    b: float,
    c: float,
    d: float,
    e: float,
) -> np.ndarray:
    """Analytical derivative of the implemented, exponent-clipped curve."""
    del a  # A constant offset has no effect on the slope.
    z = d - np.asarray(time_s, dtype=float)
    k = 2.0 * c * e / (c + e)
    weight_exponent = -k * z
    upper_exponent = c * z
    lower_exponent = e * z
    weight = 1.0 / (1.0 + np.exp(np.clip(weight_exponent, -60.0, 60.0)))
    upper = np.exp(np.clip(upper_exponent, -60.0, 60.0))
    lower = np.exp(np.clip(lower_exponent, -60.0, 60.0))
    # Clipped terms are constant outside their active interval.
    weight_active = np.abs(weight_exponent) < 60.0
    upper_active = np.abs(upper_exponent) < 60.0
    lower_active = np.abs(lower_exponent) < 60.0
    weight_z = k * weight * (1.0 - weight) * weight_active
    denominator = 1.0 + weight * upper + (1.0 - weight) * lower
    denominator_z = (
        weight_z * (upper - lower)
        + weight * c * upper * upper_active
        + (1.0 - weight) * e * lower * lower_active
    )
    return b * denominator_z / denominator**2


def _maximum_sigmoid_slope(
    parameters: tuple[float, float, float, float, float],
    *,
    search_start_s: float,
    search_end_s: float,
    rules: RhriSigRules,
) -> tuple[float, float, bool]:
    """Return the largest slope and its time inside the observed post window.

    A deterministic fine grid brackets all sampled local maxima. Each bracket
    is refined independently, and endpoints are retained as candidates.
    This is a bounded numerical estimate, not a global-maximisation theorem.
    """
    if (
        not np.all(np.isfinite(parameters))
        or not np.isfinite(search_start_s)
        or not np.isfinite(search_end_s)
        or search_end_s <= search_start_s
        or not np.isfinite(rules.peak_grid_step_s)
        or rules.peak_grid_step_s <= 0.0
        or not np.isfinite(rules.peak_time_tolerance_s)
        or rules.peak_time_tolerance_s <= 0.0
    ):
        raise ValueError("Invalid sigmoid peak parameters or assessment interval.")
    _, b, c, d, e = parameters
    if b <= 0.0 or c <= 0.0 or e <= 0.0:
        raise ValueError("Sigmoid response and curvatures must be positive.")
    # Respect the shortest curvature scale even with custom fit bounds.
    step_s = min(rules.peak_grid_step_s, 0.1 / max(c, e))
    intervals = max(2, int(np.ceil((search_end_s - search_start_s) / step_s)))
    if intervals > 1_000_000:
        raise ValueError("Sigmoid peak search exceeds the numerical grid budget.")
    grid = np.linspace(search_start_s, search_end_s, intervals + 1)
    slopes = _sigmoid_5_component_derivative(grid, *parameters)
    if not np.all(np.isfinite(slopes)):
        raise ValueError("Non-finite sigmoid derivative.")
    candidates = [
        (float(slopes[0]), float(grid[0])),
        (float(slopes[-1]), float(grid[-1])),
    ]
    # Retain the midpoint as an explicit comparison candidate when observed.
    if search_start_s <= d <= search_end_s:
        candidates.append((float(_sigmoid_5_component_derivative(np.asarray(d), *parameters)), d))
    for i in np.flatnonzero(
        (slopes[1:-1] >= slopes[:-2])
        & (slopes[1:-1] >= slopes[2:])
        & ((slopes[1:-1] > slopes[:-2]) | (slopes[1:-1] > slopes[2:]))
    ) + 1:
        candidates.append((float(slopes[i]), float(grid[i])))
        refined = minimize_scalar(
            lambda t: -float(_sigmoid_5_component_derivative(np.asarray(t), *parameters)),
            bounds=(float(grid[i - 1]), float(grid[i + 1])),
            method="bounded",
            options={"xatol": rules.peak_time_tolerance_s},
        )
        if refined.success and np.isfinite(refined.fun):
            candidates.append((-float(refined.fun), float(refined.x)))
    value, time = max(candidates, key=lambda item: (item[0], -item[1]))
    at_boundary = (
        abs(time - search_start_s) <= 1e-6
        or abs(time - search_end_s) <= 1e-6
    )
    return value, time, at_boundary


def _initial_midpoint(
    time_s: np.ndarray,
    heart_rate: np.ndarray,
    *,
    baseline_hr: float,
    response_range_bpm: float,
) -> float:
    target_hr = (
        baseline_hr
        + response_range_bpm / 2.0
    )

    post_mask = time_s >= 0.0

    post_time = time_s[post_mask]
    post_hr = heart_rate[post_mask]

    index = int(
        np.argmin(
            np.abs(
                post_hr - target_hr
            )
        )
    )

    return float(post_time[index])


def _fit_transition(
    *,
    session: ImportedSession,
    protocol: PftProtocol,
    transition: DetectedLoadTransition,
    rules: RhriSigRules,
) -> RhriSigValue | None:

    stage_end_s = _protocol_stage_end(
        protocol,
        transition.to_stage,
    )

    fit_start_s = (
        transition.ramp_start_s
        - rules.pre_window_s
    )

    fit_end_s = min(
        stage_end_s,
        transition.ramp_start_s
        + rules.post_window_s,
    )

    selected = [
        sample
        for sample in session.samples
        if (
            fit_start_s
            <= sample.elapsed_s
            < fit_end_s
            and sample.hr_bpm is not None
            and np.isfinite(sample.hr_bpm)
        )
    ]

    if not selected:
        return None

    time_s = np.asarray(
        [
            sample.elapsed_s
            - transition.ramp_start_s
            for sample in selected
        ],
        dtype=float,
    )

    heart_rate = np.asarray(
        [
            float(sample.hr_bpm)
            for sample in selected
        ],
        dtype=float,
    )

    pre_mask = time_s < 0.0
    post_mask = time_s >= 0.0

    pre_count = int(
        np.count_nonzero(pre_mask)
    )

    post_count = int(
        np.count_nonzero(post_mask)
    )

    if pre_count < rules.minimum_pre_samples:
        return None

    if post_count < rules.minimum_post_samples:
        return None

    pre_hr = heart_rate[pre_mask]

    baseline_mean = float(
        fmean(pre_hr)
    )

    if len(pre_hr) >= 2:
        baseline_sd = float(
            pstdev(pre_hr)
        )
    else:
        baseline_sd = 0.0

    post_duration_s = (
        fit_end_s
        - transition.ramp_start_s
    )

    steady_start_relative_s = max(
        0.0,
        post_duration_s
        - rules.steady_reference_window_s,
    )

    steady_mask = (
        time_s >= steady_start_relative_s
    )

    steady_hr = heart_rate[
        steady_mask
    ]

    if len(steady_hr) == 0:
        return None

    steady_mean = float(
        fmean(steady_hr)
    )

    response_range_guess = (
        steady_mean
        - baseline_mean
    )

    if (
        response_range_guess
        < rules.minimum_response_range_bpm
    ):
        return None

    midpoint_guess = _initial_midpoint(
        time_s,
        heart_rate,
        baseline_hr=baseline_mean,
        response_range_bpm=response_range_guess,
    )

    baseline_half_width = max(
        rules.minimum_baseline_half_width_bpm,
        (
            rules.baseline_sd_multiplier
            * baseline_sd
        ),
    )

    lower_bounds = np.asarray(
        [
            baseline_mean
            - baseline_half_width,
            0.1,
            rules.minimum_curvature_per_s,
            0.0,
            rules.minimum_curvature_per_s,
        ],
        dtype=float,
    )

    upper_bounds = np.asarray(
        [
            baseline_mean
            + baseline_half_width,
            rules.maximum_response_range_bpm,
            rules.maximum_curvature_per_s,
            post_duration_s,
            rules.maximum_curvature_per_s,
        ],
        dtype=float,
    )

    # Multiple deterministic starting points reduce
    # sensitivity to a local nonlinear optimum.
    curvature_starts = (
        (0.15, 0.03),
        (0.08, 0.04),
        (0.04, 0.08),
        (0.03, 0.15),
        (0.10, 0.10),
    )

    best_solution = None
    best_sse = None

    for c_start, e_start in curvature_starts:
        initial = np.asarray(
            [
                baseline_mean,
                response_range_guess,
                c_start,
                midpoint_guess,
                e_start,
            ],
            dtype=float,
        )

        epsilon = 1e-9

        initial = np.minimum(
            np.maximum(
                initial,
                lower_bounds + epsilon,
            ),
            upper_bounds - epsilon,
        )

        try:
            solution = least_squares(
                lambda parameters: (
                    _sigmoid_5_component(
                        time_s,
                        *parameters,
                    )
                    - heart_rate
                ),
                x0=initial,
                bounds=(
                    lower_bounds,
                    upper_bounds,
                ),
                max_nfev=rules.max_nfev,
            )
        except ValueError:
            continue

        if not solution.success:
            continue

        sse = float(
            2.0 * solution.cost
        )

        if not np.isfinite(sse):
            continue

        if (
            best_sse is None
            or sse < best_sse
        ):
            best_sse = sse
            best_solution = solution

    if (
        best_solution is None
        or best_sse is None
    ):
        return None

    (
        a,
        b,
        c,
        d,
        e,
    ) = (
        float(value)
        for value in best_solution.x
    )

    predicted = _sigmoid_5_component(
        time_s,
        a,
        b,
        c,
        d,
        e,
    )

    residuals = (
        heart_rate
        - predicted
    )

    mse = float(
        np.mean(
            residuals ** 2
        )
    )

    total_variation = float(
        np.sum(
            (
                heart_rate
                - np.mean(heart_rate)
            ) ** 2
        )
    )

    if total_variation <= 0.0:
        return None

    r_squared = (
        1.0
        - best_sse / total_variation
    )

    # For this curve, b(c+e)/8 is the slope at t=d. With
    # unequal curvatures it is generally not the maximum.
    # Preserve it as a legacy diagnostic, and search only
    # the post-transition interval supported by HR samples.
    search_start = float(np.min(time_s[post_mask]))
    search_end = float(np.max(time_s[post_mask]))
    rhri, peak_time, at_boundary = _maximum_sigmoid_slope(
        (a, b, c, d, e),
        search_start_s=search_start,
        search_end_s=search_end,
        rules=rules,
    )

    if (
        not np.isfinite(rhri)
        or rhri <= 0.0
    ):
        return None

    return RhriSigValue(
        stage=transition.to_stage,
        value_bpm_per_s=rhri,
        lower_plateau_bpm=a,
        response_range_bpm=b,
        upper_curvature_per_s=c,
        midpoint_s_from_ramp=d,
        lower_curvature_per_s=e,
        midpoint_elapsed_s=(
            transition.ramp_start_s
            + d
        ),
        midpoint_slope_bpm_per_s=b * (c + e) / 8.0,
        peak_elapsed_s=transition.ramp_start_s + peak_time,
        search_start_s=transition.ramp_start_s + search_start,
        search_end_s=transition.ramp_start_s + search_end,
        peak_at_search_boundary=at_boundary,
        fit_start_s=fit_start_s,
        fit_end_s=fit_end_s,
        sample_count=len(selected),
        pre_sample_count=pre_count,
        post_sample_count=post_count,
        mse_bpm2=mse,
        r_squared=r_squared,
    )


def calculate_rhri_sig(
    *,
    session: ImportedSession,
    protocol: PftProtocol,
    transitions: PftTransitionDetectionResult,
    rules: RhriSigRules = (
        DEFAULT_RHRI_SIG_RULES
    ),
) -> PftRhriSigResult:

    values: list[RhriSigValue] = []

    for stage in (
        PftStage.P1,
        PftStage.P2,
    ):
        try:
            transition = (
                transitions.get_transition_to(
                    stage
                )
            )
        except KeyError:
            continue

        value = _fit_transition(
            session=session,
            protocol=protocol,
            transition=transition,
            rules=rules,
        )

        if value is not None:
            values.append(value)

    return PftRhriSigResult(
        rules_version=rules.version,
        model_name=(
            "five_component_sigmoid"
        ),
        values=tuple(values),
    )
