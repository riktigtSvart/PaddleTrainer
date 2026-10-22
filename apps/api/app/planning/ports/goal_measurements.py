"""Session-bound census of existing scalar measurements, without caller selection."""

from datetime import datetime
from typing import Protocol

from ..domain.goals.assessment import CapturedGoalMeasurement


class GoalMeasurementSource(Protocol):
    @property
    def session(self): ...

    async def capture(
        self,
        *,
        athlete_id: str,
        starts_at: datetime,
        ends_at: datetime,
        recorded_before: datetime,
    ) -> tuple[CapturedGoalMeasurement, ...]: ...
