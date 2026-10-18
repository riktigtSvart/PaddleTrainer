"""Check execution adapters, both read APIs and available PFT reference tests."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps/api"


def main():
    sys.path.insert(0, str(API))
    path = ROOT / "tools/check_plan_contract_api_integration.py"
    spec = importlib.util.spec_from_file_location("plan_check_reference", path)
    plan_check = importlib.util.module_from_spec(spec); spec.loader.exec_module(plan_check)
    full_reference = plan_check.REFERENCE_FIXTURE.is_file()
    tests = ["tests/test_executed_workout_adapter.py", "tests/test_executed_workout_read_api.py"] + plan_check.BASE_TESTS
    tests += plan_check.REFERENCE_TESTS if full_reference else plan_check.CONTEXT_TESTS
    env = dict(os.environ)
    env["PYTHONPATH"] = str(API) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=API, env=env)
    if result.returncode:
        return result.returncode
    from app.main import app
    from app.planning_contracts.execution_adapter import ADAPTER_VERSION
    from app.planning_contracts.contract_checks import check_schema_subset
    check_schema_subset()
    paths = app.openapi()["paths"]
    for route in ("/api/v1/sessions/{session_id}/executed-workout", "/api/v1/planning/executed-workouts",
                  "/api/v1/workouts/{workout_id}/plan-contract", "/api/v1/pft/measurements/tcx"):
        if route not in paths:
            raise RuntimeError("EXECUTION_API_ROUTE_MISSING: " + route)
    print(json.dumps({"status": "EXECUTED_WORKOUT_API_TESTS_AND_ROUTER_CHECK_PASSED",
          "adapter_version": ADAPTER_VERSION, "python": sys.version.split()[0],
          "original_real_pft_fixture_available": full_reference,
          "original_real_pft_reference_tests_run": full_reference,
          "synthetic_pft_http_regression_run": True,
          "limitations": [] if full_reference else ["REAL_PFT_TCX_FIXTURE_NOT_IN_SOURCE_CAPTURE; ORIGINAL_REFERENCE_TESTS_NOT_RUN"],
          "schema_checker_scope": "PINNED_SCHEMA_SUBSET_PLUS_DOMAIN_RULES_NOT_A_GENERAL_JSON_SCHEMA_ENGINE",
          "production_database_accessed": False, "database_migrated": False, "polar_requests": 0,
          "speed_model_retrained": False, "state_model_trained": False, "new_independent_test": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
