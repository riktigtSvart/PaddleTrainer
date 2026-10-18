from dataclasses import dataclass

from app.pft_engine.contracts.input import (
    ImportedSession,
    RawSample,
)
from app.pft_engine.pft.protocol import (
    PftProtocol,
    PftStage,
)


@dataclass(frozen=True)
class StageSegment:
    stage: PftStage
    samples: tuple[RawSample, ...]

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def duration_s(self) -> float:
        if len(self.samples) < 2:
            return 0.0

        return (
            self.samples[-1].elapsed_s
            - self.samples[0].elapsed_s
        )


@dataclass(frozen=True)
class PftSegmentationResult:
    protocol: PftProtocol
    segments: tuple[StageSegment, ...]
    unassigned_samples: tuple[RawSample, ...]

    def get_stage(self, stage: PftStage) -> StageSegment:
        for segment in self.segments:
            if segment.stage == stage:
                return segment

        raise KeyError(f"Stage not found: {stage}")


def stage_for_elapsed(
    elapsed_s: float,
    protocol: PftProtocol,
) -> PftStage | None:
    for window in protocol.stages:
        if window.contains(elapsed_s):
            return window.stage

    return None


def segment_session(
    session: ImportedSession,
    protocol: PftProtocol,
) -> PftSegmentationResult:

    samples_by_stage: dict[PftStage, list[RawSample]] = {
        window.stage: []
        for window in protocol.stages
    }

    unassigned: list[RawSample] = []

    for sample in session.samples:
        stage = stage_for_elapsed(
            sample.elapsed_s,
            protocol,
        )

        if stage is None:
            unassigned.append(sample)
            continue

        samples_by_stage[stage].append(sample)

    segments = tuple(
        StageSegment(
            stage=window.stage,
            samples=tuple(samples_by_stage[window.stage]),
        )
        for window in protocol.stages
    )

    return PftSegmentationResult(
        protocol=protocol,
        segments=segments,
        unassigned_samples=tuple(unassigned),
    )