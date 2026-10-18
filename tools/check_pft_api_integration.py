"""Run on the user's installed API environment; temporary databases only."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

API = Path(__file__).resolve().parents[1]/"apps/api"
TESTS = [
    "tests/test_pft_processing_integration.py",
    "tests/test_pft_measurement_api.py",
    "tests/test_pft_measurement_migration.py",
    "tests/test_response_cohort_migration.py",
    "tests/test_environment_replay_migration.py",
    "tests/test_hr_acquisition_migration.py",
    "tests/test_hr_timebase_migration.py",
]


def main():
    modules = ["fastapi", "sqlalchemy", "alembic", "httpx", "pydantic_settings",
               "asyncpg", "numpy", "scipy", "pytest"]
    missing = []
    versions = {}
    for name in modules:
        try:
            module = importlib.import_module(name)
            versions[name] = getattr(module, "__version__", "available")
        except ImportError:
            missing.append(name)
    if missing:
        print(json.dumps({"status": "DEPENDENCIES_MISSING", "missing": missing,
                          "install": 'python -m pip install -e ".[dev]"'}, indent=2))
        return 2
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *TESTS], cwd=API)
    if result.returncode:
        return result.returncode
    sys.path.insert(0, str(API))
    from app.main import app
    paths = app.openapi()["paths"]
    for path in ("/api/v1/pft/measurements", "/api/v1/pft/measurements/tcx",
                 "/api/v1/integrations/polar/sessions/{session_external_id}/response-dataset/replay"):
        if path not in paths:
            raise RuntimeError("API_ROUTE_REGISTRATION_MISSING: "+path)
    print(json.dumps({
        "status": "PFT_API_TESTS_AND_ROUTER_CHECK_PASSED",
        "python": sys.version.split()[0], "versions": versions,
        "production_database_migrated": False, "polar_requests": 0,
        "state_model_trained": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
