from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[2]


def test_polar_reconciliation_is_read_only_and_reuses_existing_adoption_router():
    source = (API_ROOT / "app/api/routes/planning_adoption.py").read_text(
        encoding="utf-8"
    )
    assert '@router.get("/workouts/{workout_id}/polar-source-reconciliation")' in source
    assert "build_polar_source_reconciliation" in source
    assert '"database_writes": 0' in source
    assert '"provider_calls": 0' in source
    assert '"source_workout_mutated": False' in source
    assert "select(User.timezone)" in source
    assert "athlete_timezone=athlete_timezone" in source
    assert '"timezone_context_name"' in source
    assert '"timezone_context_source"' in source


def test_p1_4b_integrates_reconciliation_into_preview_gate_but_keeps_polar_write_fail_closed():
    reconciliation = (
        API_ROOT
        / "app/planning/domain/integration/polar_reconciliation.py"
    ).read_text(encoding="utf-8")
    adoption = (
        API_ROOT / "app/planning/application/plan_adoption.py"
    ).read_text(encoding="utf-8")
    route = (API_ROOT / "app/api/routes/planning_adoption.py").read_text(encoding="utf-8")

    assert "adoption_gate_integrated=False" in reconciliation
    assert "_evaluate_polar_reconciliation_gate" in adoption
    assert "POLAR_RECONCILIATION_AUDIT_PERSISTENCE_REQUIRED" in adoption
    assert "polar_reconciliation_gate_satisfied" in route
    assert '"actual_execution_timing_in_scope": False' in route
    assert "polar_reconciliation=polar_reconciliation" in route
