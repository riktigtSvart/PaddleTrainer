import json

import pytest

from app.planning.domain.plan_revision.models import (
    create_workout_plan_contract_artifact,
)


def test_workout_plan_artifact_canonicalizes_json() -> None:
    first = create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-1",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"b":2,"a":1}',
        stable_occurrence_ids=("occ-1",),
    )
    second = create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-1",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"a":1, "b":2}',
        stable_occurrence_ids=("occ-1",),
    )

    assert first.ref.integration_content_hash == second.ref.integration_content_hash
    assert first.canonical_contract_json == second.canonical_contract_json
    assert first.verify_integration_hash()


def test_occurrence_ids_must_be_unique() -> None:
    with pytest.raises(ValueError, match="unique"):
        create_workout_plan_contract_artifact(
            plan_id="plan-1",
            revision_id="rev-1",
            contract_schema_version="workout_plan_contract_v0.1",
            contract_json='{"session":{}}',
            stable_occurrence_ids=("occ-1", "occ-1"),
        )


def test_revision_id_changes_integration_hash() -> None:
    first = create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-1",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"session":{}}',
        stable_occurrence_ids=("occ-1",),
    )
    second = create_workout_plan_contract_artifact(
        plan_id="plan-1",
        revision_id="rev-2",
        contract_schema_version="workout_plan_contract_v0.1",
        contract_json='{"session":{}}',
        stable_occurrence_ids=("occ-1",),
    )

    assert first.ref.integration_content_hash != second.ref.integration_content_hash
