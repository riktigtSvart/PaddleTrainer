from ...domain.plan_revision.models import (
    PlanMutationInstruction,
    PlanMutationOperation,
    PlanRevisionApplyResult,
    PlanRevisionApplyStatus,
    PlanRevisionConflictError,
    WorkoutPlanContractArtifact,
)


class InMemoryWorkoutPlanRevisionGateway:
    """Executable reference semantics for immutable plan revisions.

    It never edits an existing artifact. A successful mutation appends a new
    immutable revision and advances only the current-revision pointer.
    """

    def __init__(self) -> None:
        self._by_plan: dict[str, list[WorkoutPlanContractArtifact]] = {}
        self._applied_instruction_hashes: dict[
            str, PlanRevisionApplyResult
        ] = {}

    @property
    def gateway_version(self) -> str:
        return "in_memory_workout_plan_revision_gateway_v0.1"

    def get_current(
        self,
        *,
        plan_id: str,
    ) -> WorkoutPlanContractArtifact | None:
        revisions = self._by_plan.get(plan_id, ())
        return revisions[-1] if revisions else None

    def get_revision(
        self,
        *,
        plan_id: str,
        revision_id: str,
    ) -> WorkoutPlanContractArtifact | None:
        for artifact in self._by_plan.get(plan_id, ()):
            if artifact.ref.revision_id == revision_id:
                return artifact
        return None

    def apply(
        self,
        instruction: PlanMutationInstruction,
    ) -> PlanRevisionApplyResult:
        if not instruction.verify_content_hash():
            raise ValueError("PlanMutationInstruction hash does not verify.")

        prior_result = self._applied_instruction_hashes.get(
            instruction.content_hash
        )
        if prior_result is not None:
            return prior_result

        current = self.get_current(plan_id=instruction.plan_id)
        current_revision_id = (
            current.ref.revision_id if current is not None else None
        )

        if current_revision_id != instruction.expected_current_revision_id:
            raise PlanRevisionConflictError(
                "Current plan revision changed since planner decision."
            )

        if instruction.operation == PlanMutationOperation.NO_CHANGE:
            result = PlanRevisionApplyResult(
                status=PlanRevisionApplyStatus.NO_CHANGE,
                artifact=current,
                previous_revision_id=current_revision_id,
            )
            self._applied_instruction_hashes[instruction.content_hash] = result
            return result

        if instruction.operation == PlanMutationOperation.REMOVE:
            # P0.10 records the mutation boundary but does not introduce a
            # tombstone WorkoutPlanContract representation. Production removal
            # semantics remain adapter-specific and are therefore not enabled.
            raise NotImplementedError(
                "REMOVE persistence semantics are not enabled in P0.10."
            )

        artifact = instruction.new_plan_artifact
        if artifact is None:
            raise ValueError("Mutation requires new_plan_artifact.")
        if not artifact.verify_integration_hash():
            raise ValueError("WorkoutPlanContractArtifact hash does not verify.")

        if self.get_revision(
            plan_id=artifact.ref.plan_id,
            revision_id=artifact.ref.revision_id,
        ) is not None:
            raise PlanRevisionConflictError(
                "Workout plan revision ID already exists."
            )

        self._by_plan.setdefault(instruction.plan_id, []).append(artifact)
        result = PlanRevisionApplyResult(
            status=PlanRevisionApplyStatus.CREATED,
            artifact=artifact,
            previous_revision_id=current_revision_id,
        )
        self._applied_instruction_hashes[instruction.content_hash] = result
        return result
