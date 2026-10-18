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


class TransitionDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"


class TransitionSignal(StrEnum):
    POWER = "power"


class RecoveryAnchorSource(StrEnum):
    POWER_STOP = "power_stop"
    NOMINAL = "nominal"


@dataclass(frozen=True)
class TransitionDetectionRules:
    version: str = "transition_detection_v0.1"

    # Reference load immediately before the nominal transition.
    pre_reference_window_s: float = 30.0

    # Wait before estimating the new load level, so the
    # acceleration/ramp itself is not part of the reference.
    post_reference_delay_s: float = 30.0
    post_reference_window_s: float = 60.0

    # How long after the nominal transition we search.
    search_window_s: float = 60.0

    # Ignore tiny load changes that are likely just noise.
    minimum_power_change_w: float = 20.0

    # Fractions between pre and post load used to describe
    # the observed ramp.
    ramp_start_fraction: float = 0.10
    midpoint_fraction: float = 0.50
    steady_fraction: float = 0.90

    # Steady threshold must hold for this many samples.
    steady_confirmation_samples: int = 3

    # Recovery stop detection.
    recovery_stop_power_threshold_w: float = 10.0
    recovery_stop_confirmation_samples: int = 5


DEFAULT_TRANSITION_RULES = TransitionDetectionRules()


@dataclass(frozen=True)
class DetectedLoadTransition:
    from_stage: PftStage
    to_stage: PftStage

    signal: TransitionSignal
    direction: TransitionDirection

    nominal_transition_s: float

    pre_load_w: float
    post_load_w: float
    delta_load_w: float

    ramp_start_s: float
    midpoint_s: float
    steady_start_s: float

    @property
    def ramp_duration_s(self) -> float:
        return self.steady_start_s - self.ramp_start_s

    @property
    def nominal_to_midpoint_delay_s(self) -> float:
        return self.midpoint_s - self.nominal_transition_s


@dataclass(frozen=True)
class RecoveryAnchor:
    nominal_s: float
    observed_s: float
    source: RecoveryAnchorSource


@dataclass(frozen=True)
class PftTransitionDetectionResult:
    rules_version: str

    load_transitions: tuple[DetectedLoadTransition, ...]
    recovery_anchor: RecoveryAnchor

    def get_transition_to(
        self,
        stage: PftStage,
    ) -> DetectedLoadTransition:
        for transition in self.load_transitions:
            if transition.to_stage == stage:
                return transition

        raise KeyError(
            f"Transition to stage not found: {stage}"
        )


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


def _power_values(
    samples: tuple[RawSample, ...],
    start_s: float,
    end_s: float,
) -> list[float]:
    return [
        float(sample.power_w)
        for sample in samples
        if (
            start_s <= sample.elapsed_s < end_s
            and sample.power_w is not None
        )
    ]


def _median_power(
    samples: tuple[RawSample, ...],
    start_s: float,
    end_s: float,
) -> float | None:
    values = _power_values(
        samples,
        start_s,
        end_s,
    )

    if not values:
        return None

    return float(median(values))


def _threshold(
    pre_load: float,
    post_load: float,
    fraction: float,
) -> float:
    return (
        pre_load
        + (post_load - pre_load) * fraction
    )


def _is_crossed(
    value: float,
    threshold: float,
    direction: TransitionDirection,
) -> bool:
    if direction == TransitionDirection.INCREASE:
        return value >= threshold

    return value <= threshold


def _first_threshold_crossing(
    samples: tuple[RawSample, ...],
    *,
    start_s: float,
    end_s: float,
    threshold: float,
    direction: TransitionDirection,
) -> float | None:
    for sample in samples:
        if sample.elapsed_s < start_s:
            continue

        if sample.elapsed_s > end_s:
            break

        if sample.power_w is None:
            continue

        if _is_crossed(
            float(sample.power_w),
            threshold,
            direction,
        ):
            return sample.elapsed_s

    return None


def _first_confirmed_threshold_crossing(
    samples: tuple[RawSample, ...],
    *,
    start_s: float,
    end_s: float,
    threshold: float,
    direction: TransitionDirection,
    confirmation_samples: int,
) -> float | None:
    candidates = [
        sample
        for sample in samples
        if start_s <= sample.elapsed_s <= end_s
    ]

    for index in range(
        0,
        len(candidates) - confirmation_samples + 1,
    ):
        window = candidates[
            index:
            index + confirmation_samples
        ]

        if any(
            sample.power_w is None
            for sample in window
        ):
            continue

        if all(
            _is_crossed(
                float(sample.power_w),
                threshold,
                direction,
            )
            for sample in window
        ):
            return window[0].elapsed_s

    return None


def detect_power_transition(
    session: ImportedSession,
    *,
    from_stage: PftStage,
    to_stage: PftStage,
    nominal_transition_s: float,
    rules: TransitionDetectionRules = (
        DEFAULT_TRANSITION_RULES
    ),
) -> DetectedLoadTransition | None:
    pre_load = _median_power(
        session.samples,
        nominal_transition_s
        - rules.pre_reference_window_s,
        nominal_transition_s,
    )

    post_reference_start = (
        nominal_transition_s
        + rules.post_reference_delay_s
    )

    post_load = _median_power(
        session.samples,
        post_reference_start,
        post_reference_start
        + rules.post_reference_window_s,
    )

    if pre_load is None or post_load is None:
        return None

    delta_load = post_load - pre_load

    if (
        abs(delta_load)
        < rules.minimum_power_change_w
    ):
        return None

    if delta_load > 0.0:
        direction = TransitionDirection.INCREASE
    else:
        direction = TransitionDirection.DECREASE

    ramp_start_threshold = _threshold(
        pre_load,
        post_load,
        rules.ramp_start_fraction,
    )

    midpoint_threshold = _threshold(
        pre_load,
        post_load,
        rules.midpoint_fraction,
    )

    steady_threshold = _threshold(
        pre_load,
        post_load,
        rules.steady_fraction,
    )

    search_end_s = (
        nominal_transition_s
        + rules.search_window_s
    )

    ramp_start_s = _first_threshold_crossing(
        session.samples,
        start_s=nominal_transition_s,
        end_s=search_end_s,
        threshold=ramp_start_threshold,
        direction=direction,
    )

    midpoint_s = _first_threshold_crossing(
        session.samples,
        start_s=nominal_transition_s,
        end_s=search_end_s,
        threshold=midpoint_threshold,
        direction=direction,
    )

    steady_start_s = (
        _first_confirmed_threshold_crossing(
            session.samples,
            start_s=nominal_transition_s,
            end_s=search_end_s,
            threshold=steady_threshold,
            direction=direction,
            confirmation_samples=(
                rules.steady_confirmation_samples
            ),
        )
    )

    if (
        ramp_start_s is None
        or midpoint_s is None
        or steady_start_s is None
    ):
        return None

    if not (
        ramp_start_s
        <= midpoint_s
        <= steady_start_s
    ):
        return None

    return DetectedLoadTransition(
        from_stage=from_stage,
        to_stage=to_stage,
        signal=TransitionSignal.POWER,
        direction=direction,
        nominal_transition_s=nominal_transition_s,
        pre_load_w=pre_load,
        post_load_w=post_load,
        delta_load_w=delta_load,
        ramp_start_s=ramp_start_s,
        midpoint_s=midpoint_s,
        steady_start_s=steady_start_s,
    )


def detect_recovery_anchor(
    session: ImportedSession,
    *,
    nominal_recovery_start_s: float,
    rules: TransitionDetectionRules = (
        DEFAULT_TRANSITION_RULES
    ),
) -> RecoveryAnchor:
    samples = session.samples

    for index, sample in enumerate(samples):
        if sample.elapsed_s < nominal_recovery_start_s:
            continue

        if sample.power_w is None:
            continue

        if (
            sample.power_w
            > rules.recovery_stop_power_threshold_w
        ):
            continue

        confirmation = samples[
            index:
            index
            + rules.recovery_stop_confirmation_samples
        ]

        if (
            len(confirmation)
            < rules.recovery_stop_confirmation_samples
        ):
            continue

        if all(
            item.power_w is not None
            and item.power_w
            <= rules.recovery_stop_power_threshold_w
            for item in confirmation
        ):
            return RecoveryAnchor(
                nominal_s=nominal_recovery_start_s,
                observed_s=sample.elapsed_s,
                source=RecoveryAnchorSource.POWER_STOP,
            )

    return RecoveryAnchor(
        nominal_s=nominal_recovery_start_s,
        observed_s=nominal_recovery_start_s,
        source=RecoveryAnchorSource.NOMINAL,
    )


def detect_pft_transitions(
    session: ImportedSession,
    protocol: PftProtocol,
    rules: TransitionDetectionRules = (
        DEFAULT_TRANSITION_RULES
    ),
) -> PftTransitionDetectionResult:
    transitions: list[DetectedLoadTransition] = []

    for from_stage, to_stage in (
        (PftStage.P0, PftStage.P1),
        (PftStage.P1, PftStage.P2),
    ):
        nominal_s = _protocol_window(
            protocol,
            to_stage,
        ).start_s

        transition = detect_power_transition(
            session,
            from_stage=from_stage,
            to_stage=to_stage,
            nominal_transition_s=nominal_s,
            rules=rules,
        )

        if transition is not None:
            transitions.append(transition)

    nominal_recovery_s = _protocol_window(
        protocol,
        PftStage.RECOVERY,
    ).start_s

    recovery_anchor = detect_recovery_anchor(
        session,
        nominal_recovery_start_s=(
            nominal_recovery_s
        ),
        rules=rules,
    )

    return PftTransitionDetectionResult(
        rules_version=rules.version,
        load_transitions=tuple(transitions),
        recovery_anchor=recovery_anchor,
    )