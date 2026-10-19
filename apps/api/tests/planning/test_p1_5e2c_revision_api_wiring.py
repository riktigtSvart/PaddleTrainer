from pathlib import Path


API_ROOT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "routes"
    / "planning_adoption.py"
)


def test_p1_5_revision_post_uses_server_side_audited_instruction():
    source = API_ROOT.read_text(encoding="utf-8")

    assert (
        '@router.post(\n'
        '    "/workouts/{workout_id}/authoritative-plan/revisions",'
        in source
    )
    assert (
        "load_audited_plan_mutation_instruction"
        in source
    )
    assert (
        "build_production_planning_audit_repository"
        in source
    )
    assert (
        "apply_authoritative_plan_revision_with_repository"
        in source
    )
    assert "payload.instruction_id" in source

    # Trust boundary: the request model must not accept lineage hashes.
    request_section = source.split(
        "class AuthoritativePlanRevisionRequest",
        1,
    )[1].split(
        "async def _existing_owner_id",
        1,
    )[0]

    assert "instruction_id" in request_section
    assert "decision_hash" not in request_section
    assert "rationale_hash" not in request_section
    assert "context_hash" not in request_section
    assert "expected_current_revision_id" not in request_section
