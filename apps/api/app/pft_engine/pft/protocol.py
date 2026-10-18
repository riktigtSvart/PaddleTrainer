from dataclasses import dataclass
from enum import StrEnum


class PftStage(StrEnum):
    PRE = "pre"
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class StageWindow:
    stage: PftStage
    start_s: float
    end_s: float

    def contains(self, elapsed_s: float) -> bool:
        return self.start_s <= elapsed_s < self.end_s

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class PftProtocol:
    name: str
    version: str
    stages: tuple[StageWindow, ...]

    @property
    def duration_s(self) -> float:
        if not self.stages:
            return 0.0
        return max(stage.end_s for stage in self.stages)


def pft_run_v01() -> PftProtocol:
    return PftProtocol(
        name="PFT-RUN",
        version="0.1",
        stages=(
            StageWindow(
                stage=PftStage.PRE,
                start_s=0.0,
                end_s=120.0,
            ),
            StageWindow(
                stage=PftStage.P0,
                start_s=120.0,
                end_s=300.0,
            ),
            StageWindow(
                stage=PftStage.P1,
                start_s=300.0,
                end_s=480.0,
            ),
            StageWindow(
                stage=PftStage.P2,
                start_s=480.0,
                end_s=660.0,
            ),
            StageWindow(
                stage=PftStage.RECOVERY,
                start_s=660.0,
                end_s=780.0,
            ),
        ),
    )