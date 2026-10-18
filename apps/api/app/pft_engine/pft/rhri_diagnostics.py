from dataclasses import dataclass, replace
from statistics import fmean, pstdev

from app.pft_engine.contracts.input import (
    ImportedSession,
)
from app.pft_engine.pft.protocol import (
    PftStage,
)
from app.pft_engine.pft.rhri import (
    PftRhriLocalResult,
    RhriLocalRules,
    calculate_rhri_local,
)
from app.pft_engine.pft.rhri_sig import (
    PftRhriSigResult,
)
from app.pft_engine.pft.transition_detection import (
    PftTransitionDetectionResult,
)


@dataclass(frozen=True)
class RhriDiagnosticsRules:
    version: str = "rhri_diagnostics_v0.2"

    # Used only to quantify numerical window sensitivity.
    local_sensitivity_windows: tuple[int, ...] = (
        5,
        11,
        21,
    )


DEFAULT_RHRI_DIAGNOSTICS_RULES = RhriDiagnosticsRules()


@dataclass(frozen=True)
class RhriMethodComparison:
    stage: PftStage

    local_bpm_per_s: float
    sig_bpm_per_s: float

    # LOCAL - SIG
    absolute_difference_bpm_per_s: float

    # Difference relative to SIG.
    relative_difference_pct: float

    local_to_sig_ratio: float

    local_peak_elapsed_s: float
    sig_midpoint_elapsed_s: float
    sig_peak_elapsed_s: float
    peak_timing_difference_s: float

    # Positive means LOCAL derivative maximum occurs
    # after the sigmoid midpoint.
    timing_difference_s: float

    sig_r_squared: float
    sig_mse_bpm2: float


@dataclass(frozen=True)
class RhriWindowPoint:
    window_length: int
    value_bpm_per_s: float


@dataclass(frozen=True)
class RhriWindowSensitivity:
    stage: PftStage

    points: tuple[RhriWindowPoint, ...]

    minimum_bpm_per_s: float
    maximum_bpm_per_s: float
    range_bpm_per_s: float

    mean_bpm_per_s: float
    cv_pct: float | None

    def get_window(
        self,
        window_length: int,
    ) -> RhriWindowPoint:
        for point in self.points:
            if point.window_length == window_length:
                return point

        raise KeyError(
            f"RHRI_LOCAL sensitivity window "
            f"not found: {window_length}"
        )


@dataclass(frozen=True)
class PftRhriDiagnosticsResult:
    rules_version: str

    local_rules_version: str
    sig_rules_version: str

    comparisons: tuple[RhriMethodComparison, ...]
    window_sensitivity: tuple[
        RhriWindowSensitivity, ...
    ]

    local_p2_minus_p1_bpm_per_s: float | None
    sig_p2_minus_p1_bpm_per_s: float | None

    p1_p2_direction_agreement: bool | None

    local_to_sig_ratio_spread: float | None

    def get_stage(
        self,
        stage: PftStage,
    ) -> RhriMethodComparison:
        for comparison in self.comparisons:
            if comparison.stage == stage:
                return comparison

        raise KeyError(
            f"RHRI diagnostic comparison not found: {stage}"
        )

    def get_sensitivity(
        self,
        stage: PftStage,
    ) -> RhriWindowSensitivity:
        for sensitivity in self.window_sensitivity:
            if sensitivity.stage == stage:
                return sensitivity

        raise KeyError(
            f"RHRI window sensitivity not found: {stage}"
        )


def _try_local(
    result: PftRhriLocalResult,
    stage: PftStage,
):
    try:
        return result.get_stage(stage)
    except KeyError:
        return None


def _try_sig(
    result: PftRhriSigResult,
    stage: PftStage,
):
    try:
        return result.get_stage(stage)
    except KeyError:
        return None


def _calculate_method_comparisons(
    *,
    rhri_local: PftRhriLocalResult,
    rhri_sig: PftRhriSigResult,
) -> tuple[RhriMethodComparison, ...]:

    comparisons: list[RhriMethodComparison] = []

    for stage in (
        PftStage.P1,
        PftStage.P2,
    ):
        local = _try_local(
            rhri_local,
            stage,
        )

        sig = _try_sig(
            rhri_sig,
            stage,
        )

        if local is None or sig is None:
            continue

        if sig.value_bpm_per_s <= 0.0:
            continue

        difference = (
            local.value_bpm_per_s
            - sig.value_bpm_per_s
        )

        comparisons.append(
            RhriMethodComparison(
                stage=stage,
                local_bpm_per_s=(
                    local.value_bpm_per_s
                ),
                sig_bpm_per_s=(
                    sig.value_bpm_per_s
                ),
                absolute_difference_bpm_per_s=(
                    difference
                ),
                relative_difference_pct=(
                    difference
                    / sig.value_bpm_per_s
                    * 100.0
                ),
                local_to_sig_ratio=(
                    local.value_bpm_per_s
                    / sig.value_bpm_per_s
                ),
                local_peak_elapsed_s=(
                    local.peak_elapsed_s
                ),
                sig_midpoint_elapsed_s=(
                    sig.midpoint_elapsed_s
                ),
                sig_peak_elapsed_s=sig.peak_elapsed_s,
                peak_timing_difference_s=(
                    local.peak_elapsed_s - sig.peak_elapsed_s
                ),
                timing_difference_s=(
                    local.peak_elapsed_s
                    - sig.midpoint_elapsed_s
                ),
                sig_r_squared=(
                    sig.r_squared
                ),
                sig_mse_bpm2=(
                    sig.mse_bpm2
                ),
            )
        )

    return tuple(comparisons)


def _calculate_window_sensitivity(
    *,
    session: ImportedSession,
    transitions: PftTransitionDetectionResult,
    base_local_rules: RhriLocalRules,
    diagnostics_rules: RhriDiagnosticsRules,
) -> tuple[RhriWindowSensitivity, ...]:

    results_by_window: dict[
        int,
        PftRhriLocalResult,
    ] = {}

    for window_length in (
        diagnostics_rules.local_sensitivity_windows
    ):
        local_rules = replace(
            base_local_rules,
            window_length=window_length,
        )

        results_by_window[
            window_length
        ] = calculate_rhri_local(
            session=session,
            transitions=transitions,
            rules=local_rules,
        )

    sensitivities: list[
        RhriWindowSensitivity
    ] = []

    for stage in (
        PftStage.P1,
        PftStage.P2,
    ):
        points: list[RhriWindowPoint] = []

        for window_length, result in (
            results_by_window.items()
        ):
            value = _try_local(
                result,
                stage,
            )

            if value is None:
                continue

            points.append(
                RhriWindowPoint(
                    window_length=window_length,
                    value_bpm_per_s=(
                        value.value_bpm_per_s
                    ),
                )
            )

        if not points:
            continue

        values = [
            point.value_bpm_per_s
            for point in points
        ]

        mean_value = fmean(values)

        if len(values) >= 2:
            sd_value = pstdev(values)
        else:
            sd_value = 0.0

        if mean_value == 0.0:
            cv_pct = None
        else:
            cv_pct = (
                sd_value
                / abs(mean_value)
                * 100.0
            )

        minimum = min(values)
        maximum = max(values)

        sensitivities.append(
            RhriWindowSensitivity(
                stage=stage,
                points=tuple(points),
                minimum_bpm_per_s=minimum,
                maximum_bpm_per_s=maximum,
                range_bpm_per_s=(
                    maximum - minimum
                ),
                mean_bpm_per_s=mean_value,
                cv_pct=cv_pct,
            )
        )

    return tuple(sensitivities)


def _stage_delta(
    *,
    comparisons: tuple[
        RhriMethodComparison, ...
    ],
    method: str,
) -> float | None:

    by_stage = {
        comparison.stage: comparison
        for comparison in comparisons
    }

    if (
        PftStage.P1 not in by_stage
        or PftStage.P2 not in by_stage
    ):
        return None

    p1 = by_stage[PftStage.P1]
    p2 = by_stage[PftStage.P2]

    if method == "local":
        return (
            p2.local_bpm_per_s
            - p1.local_bpm_per_s
        )

    if method == "sig":
        return (
            p2.sig_bpm_per_s
            - p1.sig_bpm_per_s
        )

    raise ValueError(
        f"Unknown RHRI method: {method}"
    )


def _direction_agreement(
    local_delta: float | None,
    sig_delta: float | None,
) -> bool | None:

    if (
        local_delta is None
        or sig_delta is None
    ):
        return None

    if (
        local_delta == 0.0
        and sig_delta == 0.0
    ):
        return True

    return (
        local_delta * sig_delta
        > 0.0
    )


def _ratio_spread(
    comparisons: tuple[
        RhriMethodComparison, ...
    ],
) -> float | None:

    ratios = [
        comparison.local_to_sig_ratio
        for comparison in comparisons
    ]

    if len(ratios) < 2:
        return None

    return max(ratios) - min(ratios)


def calculate_rhri_diagnostics(
    *,
    session: ImportedSession,
    transitions: PftTransitionDetectionResult,
    rhri_local: PftRhriLocalResult,
    rhri_sig: PftRhriSigResult,
    local_rules: RhriLocalRules,
    rules: RhriDiagnosticsRules = (
        DEFAULT_RHRI_DIAGNOSTICS_RULES
    ),
) -> PftRhriDiagnosticsResult:

    comparisons = (
        _calculate_method_comparisons(
            rhri_local=rhri_local,
            rhri_sig=rhri_sig,
        )
    )

    window_sensitivity = (
        _calculate_window_sensitivity(
            session=session,
            transitions=transitions,
            base_local_rules=local_rules,
            diagnostics_rules=rules,
        )
    )

    local_delta = _stage_delta(
        comparisons=comparisons,
        method="local",
    )

    sig_delta = _stage_delta(
        comparisons=comparisons,
        method="sig",
    )

    return PftRhriDiagnosticsResult(
        rules_version=rules.version,
        local_rules_version=(
            rhri_local.rules_version
        ),
        sig_rules_version=(
            rhri_sig.rules_version
        ),
        comparisons=comparisons,
        window_sensitivity=window_sensitivity,
        local_p2_minus_p1_bpm_per_s=(
            local_delta
        ),
        sig_p2_minus_p1_bpm_per_s=(
            sig_delta
        ),
        p1_p2_direction_agreement=(
            _direction_agreement(
                local_delta,
                sig_delta,
            )
        ),
        local_to_sig_ratio_spread=(
            _ratio_spread(
                comparisons
            )
        ),
    )
