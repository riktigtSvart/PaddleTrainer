from dataclasses import dataclass
from statistics import median

from scipy.signal import savgol_filter

from app.pft_engine.contracts.input import (
    ImportedSession,
)
from app.pft_engine.pft.protocol import (
    PftStage,
)
from app.pft_engine.pft.transition_detection import (
    DetectedLoadTransition,
    PftTransitionDetectionResult,
)


@dataclass(frozen=True)
class RhriLocalRules:
    version: str = "rhri_local_v0.1"

    window_length: int = 11
    polyorder: int = 2

    # Search for maximal HR acceleration from the
    # observed ramp start until this many seconds
    # after the transition midpoint.
    response_window_s: float = 90.0

    # Savitzky-Golay assumes regularly sampled data.
    max_sampling_jitter_s: float = 0.05


DEFAULT_RHRI_LOCAL_RULES = RhriLocalRules()


@dataclass(frozen=True)
class RhriLocalValue:
    stage: PftStage

    value_bpm_per_s: float
    peak_elapsed_s: float

    search_start_s: float
    search_end_s: float

    sampling_interval_s: float

    window_length: int
    polyorder: int


@dataclass(frozen=True)
class PftRhriLocalResult:
    rules_version: str

    values: tuple[RhriLocalValue, ...]

    def get_stage(
        self,
        stage: PftStage,
    ) -> RhriLocalValue:
        for value in self.values:
            if value.stage == stage:
                return value

        raise KeyError(
            f"RHRI_LOCAL not found for stage: {stage}"
        )


def _validate_rules(
    rules: RhriLocalRules,
) -> None:
    if rules.window_length < 3:
        raise ValueError(
            "window_length must be at least 3."
        )

    if rules.window_length % 2 == 0:
        raise ValueError(
            "window_length must be odd."
        )

    if rules.polyorder >= rules.window_length:
        raise ValueError(
            "polyorder must be smaller than "
            "window_length."
        )

    if rules.polyorder < 1:
        raise ValueError(
            "polyorder must be at least 1."
        )


def _calculate_transition_rhri(
    session: ImportedSession,
    transition: DetectedLoadTransition,
    rules: RhriLocalRules,
) -> RhriLocalValue | None:

    search_start_s = transition.ramp_start_s

    search_end_s = (
        transition.midpoint_s
        + rules.response_window_s
    )

    samples = [
        sample
        for sample in session.samples
        if (
            search_start_s
            <= sample.elapsed_s
            <= search_end_s
        )
    ]

    if len(samples) < rules.window_length:
        return None

    # For v0.1 we deliberately require complete HR
    # coverage rather than interpolating missing HR.
    if any(
        sample.hr_bpm is None
        for sample in samples
    ):
        return None

    elapsed = [
        sample.elapsed_s
        for sample in samples
    ]

    heart_rate = [
        float(sample.hr_bpm)
        for sample in samples
        if sample.hr_bpm is not None
    ]

    sampling_deltas = [
        current - previous
        for previous, current in zip(
            elapsed,
            elapsed[1:],
        )
    ]

    if not sampling_deltas:
        return None

    sampling_interval_s = float(
        median(sampling_deltas)
    )

    if sampling_interval_s <= 0.0:
        return None

    if any(
        abs(delta - sampling_interval_s)
        > rules.max_sampling_jitter_s
        for delta in sampling_deltas
    ):
        return None

    derivative = savgol_filter(
        heart_rate,
        window_length=rules.window_length,
        polyorder=rules.polyorder,
        deriv=1,
        delta=sampling_interval_s,
        mode="interp",
    )

    # Do not use the Savitzky-Golay edge region for
    # maximum detection because it relies on boundary
    # interpolation rather than a centred window.
    half_window = (
        rules.window_length // 2
    )

    first_valid = half_window
    last_valid = (
        len(derivative) - half_window
    )

    if last_valid <= first_valid:
        return None

    valid_indexes = range(
        first_valid,
        last_valid,
    )

    peak_index = max(
        valid_indexes,
        key=lambda index: derivative[index],
    )

    peak_value = float(
        derivative[peak_index]
    )

    if peak_value <= 0.0:
        return None

    return RhriLocalValue(
        stage=transition.to_stage,
        value_bpm_per_s=peak_value,
        peak_elapsed_s=elapsed[peak_index],
        search_start_s=search_start_s,
        search_end_s=search_end_s,
        sampling_interval_s=sampling_interval_s,
        window_length=rules.window_length,
        polyorder=rules.polyorder,
    )


def calculate_rhri_local(
    *,
    session: ImportedSession,
    transitions: PftTransitionDetectionResult,
    rules: RhriLocalRules = (
        DEFAULT_RHRI_LOCAL_RULES
    ),
) -> PftRhriLocalResult:

    _validate_rules(rules)

    values: list[RhriLocalValue] = []

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

        result = _calculate_transition_rhri(
            session,
            transition,
            rules,
        )

        if result is not None:
            values.append(result)

    return PftRhriLocalResult(
        rules_version=rules.version,
        values=tuple(values),
    )