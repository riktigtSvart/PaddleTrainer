from typing import Protocol

from ..domain.plan_revision.models import (
    PlanMutationInstruction,
    PlanRevisionApplyResult,
    WorkoutPlanContractArtifact,
)


class WorkoutPlanRevisionGateway(Protocol):
    @property
    def gateway_version(self) -> str:
        ...

    def get_current(
        self,
        *,
        plan_id: str,
    ) -> WorkoutPlanContractArtifact | None:
        ...

    def apply(
        self,
        instruction: PlanMutationInstruction,
    ) -> PlanRevisionApplyResult:
        ...
