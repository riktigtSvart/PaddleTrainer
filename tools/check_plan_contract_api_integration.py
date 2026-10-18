"""Run temporary-database API checks and available PFT regression tests."""
from pathlib import Path
import importlib
import json
import os
import subprocess
import sys

API = Path(__file__).resolve().parents[1] / "apps/api"
BASE_TESTS = ["tests/test_plan_contract_read_api.py", "tests/test_pft_measurement_migration.py",
              "tests/test_response_cohort_migration.py", "tests/test_environment_replay_migration.py",
              "tests/test_hr_acquisition_migration.py", "tests/test_hr_timebase_migration.py"]
REFERENCE_TESTS = ["tests/test_pft_processing_integration.py", "tests/test_pft_measurement_api.py"]
REFERENCE_FIXTURE = API / "tests/fixtures/pft/synthetic_pft_run_v01.TCX"
CONTEXT_TESTS = ["tests/test_pft_processing_integration.py::test_client_cannot_supply_owner_or_authority",
                 "tests/test_pft_processing_integration.py::test_invalid_target_is_rejected",
                 "tests/test_pft_processing_integration.py::test_power_target_order_must_match_the_step_protocol",
                 "tests/test_pft_measurement_api.py::test_openapi_and_router_contract_expose_measured_data_without_readiness"]


def main():
    sys.path.insert(0, str(API))
    modules = ["fastapi", "sqlalchemy", "alembic", "httpx", "pydantic_settings", "asyncpg", "numpy", "scipy", "pytest"]
    versions, missing = {}, []
    for name in modules:
        try:
            module = importlib.import_module(name)
            versions[name] = getattr(module, "__version__", "available")
        except ImportError:
            missing.append(name)
    if missing:
        print(json.dumps({"status": "PLAN_CONTRACT_API_DEPENDENCIES_MISSING", "missing": missing}, indent=2))
        return 2
    full_reference = REFERENCE_FIXTURE.is_file()
    tests = BASE_TESTS + (REFERENCE_TESTS if full_reference else CONTEXT_TESTS)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(API) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # Tests use their own temporary SQLite databases. Production settings may be
    # imported for route registration; none of these tests opens that engine.
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=API, env=env)
    if result.returncode:
        return result.returncode
    from app.main import app
    from app.planning_contracts.contract_checks import check_schema_subset
    check_schema_subset()
    paths = app.openapi()["paths"]
    required = ["/api/v1/workouts/{workout_id}/plan-contract", "/api/v1/planning/plan-contracts",
                "/api/v1/planning/contracts/capabilities", "/api/v1/planning/contracts/schemas/{contract_type}",
                "/api/v1/pft/measurements", "/api/v1/pft/measurements/tcx",
                "/api/v1/integrations/polar/sessions/{session_external_id}/response-dataset/replay"]
    for path in required:
        if path not in paths:
            raise RuntimeError("API_ROUTE_REGISTRATION_MISSING: " + path)
    print(json.dumps({"status": "PLAN_CONTRACT_API_TESTS_AND_ROUTER_CHECK_PASSED",
          "python": sys.version.split()[0], "versions": versions,
          "original_real_pft_fixture_available": full_reference,
          "original_real_pft_reference_tests_run": full_reference,
          "synthetic_pft_http_regression_run": True,
          "limitations": [] if full_reference else ["REAL_PFT_TCX_FIXTURE_NOT_IN_SOURCE_CAPTURE; ORIGINAL_REFERENCE_TESTS_NOT_RUN"],
          "schema_checker_scope": "PINNED_SCHEMA_SUBSET_PLUS_DOMAIN_RULES_NOT_A_GENERAL_JSON_SCHEMA_ENGINE",
          "production_database_accessed": False, "production_database_migrated": False,
          "polar_requests": 0, "speed_model_retrained": False, "state_model_trained": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
