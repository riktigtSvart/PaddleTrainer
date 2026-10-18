from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[2]


def test_main_api_router_wires_adoption_without_dropping_existing_phase_routes():
    source = (API_ROOT / "app/api/router.py").read_text(encoding="utf-8")
    for module_name in (
        "planning_adoption",
        "phase_reconciliations",
        "phase_clarification_storage",
    ):
        assert module_name in source
        assert f"api_router.include_router({module_name}.router)" in source


def test_adoption_api_requires_explicit_current_state_acknowledgement_and_hash():
    source = (API_ROOT / "app/api/routes/planning_adoption.py").read_text(
        encoding="utf-8"
    )
    assert "expected_source_content_sha256" in source
    assert "acknowledge_current_state_baseline_only: Literal[True]" in source
    assert '@router.get("/workouts/{workout_id}/plan-adoption-preview")' in source
    assert '@router.post("/workouts/{workout_id}/plan-adoption", status_code=201)' in source
    assert '@router.get("/workouts/{workout_id}/authoritative-plan")' in source
    assert "source_workout_mutated\": False" in source
