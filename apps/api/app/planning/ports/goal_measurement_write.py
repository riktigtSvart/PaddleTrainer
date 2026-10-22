from typing import Protocol

from ..domain.goals.measurement_registration import GoalMeasurementRegistration


class GoalMeasurementWriteConflict(RuntimeError):
    pass


class GoalMeasurementWriter(Protocol):
    @property
    def session(self): ...

    async def save(self, registration: GoalMeasurementRegistration) -> None: ...

    async def verify(self, registration: GoalMeasurementRegistration) -> None: ...
