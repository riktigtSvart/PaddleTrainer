from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawSample:
    timestamp: datetime
    elapsed_s: float

    hr_bpm: float | None = None
    power_w: float | None = None
    distance_m: float | None = None
    cadence_rpm: float | None = None

    latitude_deg: float | None = None
    longitude_deg: float | None = None
    altitude_m: float | None = None


@dataclass(frozen=True)
class ImportedSession:
    started_at: datetime
    samples: tuple[RawSample, ...]

    @property
    def duration_s(self) -> float:
        if not self.samples:
            return 0.0
        return self.samples[-1].elapsed_s