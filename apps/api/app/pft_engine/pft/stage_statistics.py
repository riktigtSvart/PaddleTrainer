from dataclasses import dataclass
from statistics import fmean, median, pstdev
from typing import Iterable

from app.pft_engine.contracts.input import RawSample
from app.pft_engine.pft.protocol import PftStage
from app.pft_engine.pft.segmentation import (
    PftSegmentationResult,
    StageSegment,
)


@dataclass(frozen=True)
class MetricStatistics:
    count: int
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    sd: float | None
    cv_pct: float | None


@dataclass(frozen=True)
class StageStatistics:
    stage: PftStage

    sample_count: int
    observed_span_s: float

    hr: MetricStatistics
    power: MetricStatistics
    cadence: MetricStatistics
    speed: MetricStatistics

    distance_delta_m: float | None


@dataclass(frozen=True)
class PftStageStatisticsResult:
    stages: tuple[StageStatistics, ...]

    def get_stage(self, stage: PftStage) -> StageStatistics:
        for item in self.stages:
            if item.stage == stage:
                return item

        raise KeyError(f"Stage statistics not found: {stage}")


def _summarize(
    values: Iterable[float | None],
) -> MetricStatistics:
    clean = [
        float(value)
        for value in values
        if value is not None
    ]

    if not clean:
        return MetricStatistics(
            count=0,
            mean=None,
            median=None,
            minimum=None,
            maximum=None,
            sd=None,
            cv_pct=None,
        )

    mean_value = fmean(clean)

    if len(clean) >= 2:
        sd_value = pstdev(clean)
    else:
        sd_value = 0.0

    if mean_value == 0.0:
        cv_pct = None
    else:
        cv_pct = sd_value / abs(mean_value) * 100.0

    return MetricStatistics(
        count=len(clean),
        mean=mean_value,
        median=float(median(clean)),
        minimum=min(clean),
        maximum=max(clean),
        sd=sd_value,
        cv_pct=cv_pct,
    )


def _speed_samples(
    samples: tuple[RawSample, ...],
) -> list[float]:
    speeds: list[float] = []

    for previous, current in zip(samples, samples[1:]):
        if (
            previous.distance_m is None
            or current.distance_m is None
        ):
            continue

        dt = current.elapsed_s - previous.elapsed_s

        if dt <= 0.0:
            continue

        distance_delta = (
            current.distance_m
            - previous.distance_m
        )

        # TCX cumulative distance should normally be monotonic.
        # Negative deltas are treated as unusable input here,
        # not silently converted into positive speed.
        if distance_delta < 0.0:
            continue

        speeds.append(distance_delta / dt)

    return speeds


def _distance_delta(
    samples: tuple[RawSample, ...],
) -> float | None:
    distances = [
        sample.distance_m
        for sample in samples
        if sample.distance_m is not None
    ]

    if len(distances) < 2:
        return None

    delta = distances[-1] - distances[0]

    if delta < 0.0:
        return None

    return delta


def calculate_stage_statistics(
    segment: StageSegment,
) -> StageStatistics:
    samples = segment.samples

    return StageStatistics(
        stage=segment.stage,
        sample_count=len(samples),
        observed_span_s=segment.duration_s,
        hr=_summarize(
            sample.hr_bpm
            for sample in samples
        ),
        power=_summarize(
            sample.power_w
            for sample in samples
        ),
        cadence=_summarize(
            sample.cadence_rpm
            for sample in samples
        ),
        speed=_summarize(
            _speed_samples(samples)
        ),
        distance_delta_m=_distance_delta(samples),
    )


def calculate_all_stage_statistics(
    segmentation: PftSegmentationResult,
) -> PftStageStatisticsResult:
    return PftStageStatisticsResult(
        stages=tuple(
            calculate_stage_statistics(segment)
            for segment in segmentation.segments
        )
    )