import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.planning.application.audited_plan_mutation import (
    AuditedPlanMutationInstructionError,
    AuditedPlanMutationInstructionNotFound,
    load_audited_plan_mutation_instruction,
)
from app.planning.domain.common.serialization import (
    canonical_json,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
)
from app.planning.domain.plan_revision.models import (
    OccurrenceIdentityPolicy,
    PlanMutationOperation,
    create_workout_plan_contract_artifact,
    finalize_plan_mutation_instruction,
)


UTC = timezone.utc


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 19, hour, tzinfo=UTC)


def instruction():
    artifact = create_workout_plan_contract_artifact(
        plan_id="planned-workout:w1",
        revision_id="artifact-r2",
        contract_schema_version="0.1",
        contract_json='{"blocks":[],"plan":"updated"}',
        stable_occurrence_ids=(
            "pt-occ:o1",
            "pt-occ:o3",
        ),
    )

    return finalize_plan_mutation_instruction(
        instruction_id="instruction-r2",
        operation=PlanMutationOperation.MODIFY,
        decision_hash="d" * 64,
        rationale_hash="e" * 64,
        context_hash="f" * 64,
        selected_action_id="action-1",
        plan_id="planned-workout:w1",
        expected_current_revision_id=(
            "pt-plan-rev:r1"
        ),
        new_plan_artifact=artifact,
        occurrence_identity_policy=(
            OccurrenceIdentityPolicy.PRESERVE_UNCHANGED
        ),
        effective_from=dt(11),
        created_at=dt(10),
    )


def record(item, *, athlete_id):
    return AuditArtifactRecord(
        artifact_kind=(
            AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
        ),
        artifact_id=item.instruction_id,
        athlete_id=athlete_id,
        schema_version="plan_mutation_instruction_v0.1",
        created_at=item.created_at,
        content_hash_algorithm=(
            item.content_hash_algorithm
        ),
        content_hash=item.content_hash,
        contract_json=canonical_json(item),
    )


class StaticAuditRepository:
    def __init__(self, item):
        self.item = item

    async def get(
        self,
        *,
        artifact_kind,
        artifact_id,
    ):
        assert (
            artifact_kind
            == AuditArtifactKind.PLAN_MUTATION_INSTRUCTION
        )
        if (
            self.item is not None
            and self.item.artifact_id == artifact_id
        ):
            return self.item
        return None


@pytest.mark.asyncio
async def test_load_round_trips_audited_instruction():
    athlete_id = str(uuid4())
    item = instruction()

    loaded = await load_audited_plan_mutation_instruction(
        instruction_id=item.instruction_id,
        expected_athlete_id=athlete_id,
        expected_plan_id=item.plan_id,
        audit_repository=StaticAuditRepository(
            record(item, athlete_id=athlete_id)
        ),
    )

    assert loaded == item
    assert loaded.verify_content_hash()


@pytest.mark.asyncio
async def test_missing_instruction_fails_closed():
    with pytest.raises(
        AuditedPlanMutationInstructionNotFound,
    ):
        await load_audited_plan_mutation_instruction(
            instruction_id="missing",
            expected_athlete_id=str(uuid4()),
            expected_plan_id="planned-workout:w1",
            audit_repository=StaticAuditRepository(None),
        )


@pytest.mark.asyncio
async def test_other_athlete_instruction_is_not_disclosed():
    item = instruction()

    with pytest.raises(
        AuditedPlanMutationInstructionNotFound,
    ):
        await load_audited_plan_mutation_instruction(
            instruction_id=item.instruction_id,
            expected_athlete_id=str(uuid4()),
            expected_plan_id=item.plan_id,
            audit_repository=StaticAuditRepository(
                record(
                    item,
                    athlete_id=str(uuid4()),
                )
            ),
        )


@pytest.mark.asyncio
async def test_instruction_for_other_plan_fails_closed():
    athlete_id = str(uuid4())
    item = instruction()

    with pytest.raises(
        AuditedPlanMutationInstructionError,
        match="different logical plan",
    ):
        await load_audited_plan_mutation_instruction(
            instruction_id=item.instruction_id,
            expected_athlete_id=athlete_id,
            expected_plan_id="planned-workout:other",
            audit_repository=StaticAuditRepository(
                record(item, athlete_id=athlete_id)
            ),
        )


@pytest.mark.asyncio
async def test_tampered_audit_contract_fails_hash_verification():
    athlete_id = str(uuid4())
    item = instruction()
    stored = record(item, athlete_id=athlete_id)

    raw = json.loads(stored.contract_json)
    raw["decision_hash"] = "0" * 64

    tampered = AuditArtifactRecord(
        artifact_kind=stored.artifact_kind,
        artifact_id=stored.artifact_id,
        athlete_id=stored.athlete_id,
        schema_version=stored.schema_version,
        created_at=stored.created_at,
        content_hash_algorithm=(
            stored.content_hash_algorithm
        ),
        content_hash=stored.content_hash,
        contract_json=json.dumps(
            raw,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )

    with pytest.raises(
        AuditedPlanMutationInstructionError,
    ):
        await load_audited_plan_mutation_instruction(
            instruction_id=item.instruction_id,
            expected_athlete_id=athlete_id,
            expected_plan_id=item.plan_id,
            audit_repository=StaticAuditRepository(
                tampered
            ),
        )
