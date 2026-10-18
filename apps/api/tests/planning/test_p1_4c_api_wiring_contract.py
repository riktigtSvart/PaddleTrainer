from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]


def test_p1_4c_wires_atomic_audit_persistence_into_polar_adoption():
    route = (API_ROOT / "app/api/routes/planning_adoption.py").read_text(encoding="utf-8")
    app = (API_ROOT / "app/planning/application/plan_adoption.py").read_text(encoding="utf-8")
    migration = (API_ROOT / "alembic/versions/f14c7b2e9d01_add_planning_polar_reconciliation_audits.py").read_text(encoding="utf-8")

    assert "build_production_plan_reconciliation_audit_repository" in route
    assert "reconciliation_audit_repository=audit_repository" in route
    assert "POLAR_RECONCILIATION_AUDIT_STORAGE_UNAVAILABLE" in route
    assert "persist_polar_audit" in app
    assert "await session.commit()" in app
    assert "planning_plan_revision_reconciliation_audits" in migration
    assert "planning_reject_immutable_plan_history_mutation" in migration
    assert "down_revision" in migration and "da7e4c92b610" in migration
