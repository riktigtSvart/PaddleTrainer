from typing import Protocol

from ..domain.goals.protocol import TrainingGoalSourceSnapshot
from .audit import PlanningAuditSession


class SessionBoundTrainingGoalSource(Protocol):
    @property
    def session(self) -> PlanningAuditSession: ...

    async def capture(
        self,
        *,
        athlete_id: str,
        macrocycle_period_id: str,
    ) -> TrainingGoalSourceSnapshot: ...
