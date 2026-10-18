from datetime import datetime, timezone

import pytest

from app.planning.domain.plan_revision.models import (
    OccurrenceIdentityPolicy,
    PlanMutationOperation,
    PlanRevisionApplyStatus,
    PlanRevisionConflictError,
    create_workout_plan_contract_artifact,
    finalize_plan_mutation_instruction,
)
from app.planning.infrastructure.workout_plan.in_memory import (
    InMemoryWorkoutPlanRevisionGateway,
)


def _dt(hour: int = 10):
    return datetime(2026, 10, 17, hour, tzinfo=timezone.utc)


def _artifact(revision_id: str):
    return create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id=revision_id,
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json=(
            '{"plan_id":"plan-1","revision_id":"'
            + revision_id
            + '","blocks":[]}'
        ),
        stable_occurrence_ids=(),
    )


def _instruction(
    *,
    instruction_id: str,
    operation: PlanMutationOperation,
    expected: str | None,
    artifact=None,
):
    return finalize_plan_mutation_instruction(
        instruction_id=instruction_id,
        operation=operation,
        decision_hash="d" * 64,
        rationale_hash="r" * 64,
        context_hash="c" * 64,
        selected_action_id="action-1",
        plan_id="plan-1",
        expected_current_revision_id=expected,
        new_plan_artifact=artifact,
        occurrence_identity_policy=(
            OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
        ),
        effective_from=_dt(),
        created_at=_dt(),
    )


def test_add_creates_first_immutable_revision() -> None:
    gateway = InMemoryWorkoutPlanRevisionGateway()
    artifact = _artifact("rev-1")
    result = gateway.apply(
        _instruction(
            instruction_id="i-1",
            operation=PlanMutationOperation.ADD,
            expected=None,
            artifact=artifact,
        )
    )

    assert result.status == PlanRevisionApplyStatus.CREATED
    assert gateway.get_current(plan_id="plan-1") == artifact


def test_replace_appends_revision_and_preserves_old_revision() -> None:
    gateway = InMemoryWorkoutPlanRevisionGateway()
    first = _artifact("rev-1")
    second = _artifact("rev-2")
    gateway.apply(
        _instruction(
            instruction_id="i-1",
            operation=PlanMutationOperation.ADD,
            expected=None,
            artifact=first,
        )
    )
    gateway.apply(
        _instruction(
            instruction_id="i-2",
            operation=PlanMutationOperation.REPLACE,
            expected="rev-1",
            artifact=second,
        )
    )

    assert gateway.get_current(plan_id="plan-1") == second
    assert gateway.get_revision(
        plan_id="plan-1",
        revision_id="rev-1",
    ) == first


def test_stale_expected_revision_is_rejected() -> None:
    gateway = InMemoryWorkoutPlanRevisionGateway()
    first = _artifact("rev-1")
    gateway.apply(
        _instruction(
            instruction_id="i-1",
            operation=PlanMutationOperation.ADD,
            expected=None,
            artifact=first,
        )
    )

    with pytest.raises(PlanRevisionConflictError, match="changed"):
        gateway.apply(
            _instruction(
                instruction_id="i-2",
                operation=PlanMutationOperation.REPLACE,
                expected="wrong-revision",
                artifact=_artifact("rev-2"),
            )
        )


def test_same_instruction_is_idempotent() -> None:
    gateway = InMemoryWorkoutPlanRevisionGateway()
    instruction = _instruction(
        instruction_id="i-1",
        operation=PlanMutationOperation.ADD,
        expected=None,
        artifact=_artifact("rev-1"),
    )

    first = gateway.apply(instruction)
    second = gateway.apply(instruction)

    assert first == second


def test_revision_id_cannot_be_reused() -> None:
    gateway = InMemoryWorkoutPlanRevisionGateway()
    gateway.apply(
        _instruction(
            instruction_id="i-1",
            operation=PlanMutationOperation.ADD,
            expected=None,
            artifact=_artifact("rev-1"),
        )
    )

    with pytest.raises(PlanRevisionConflictError, match="already exists"):
        gateway.apply(
            _instruction(
                instruction_id="i-2",
                operation=PlanMutationOperation.REPLACE,
                expected="rev-1",
                artifact=_artifact("rev-1"),
            )
        )
