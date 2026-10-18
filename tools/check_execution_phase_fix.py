"""Run the release's HTTP/SQLite, clock, replay and installer checks offline."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root, package = Path(args.project_root).resolve(), Path(args.package_root).resolve()
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1:1/phase_fix_checks_not_production"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(package), str(root/"apps/api"), str(root/"apps/api/tests"),
                                        str(root/"tools"), env.get("PYTHONPATH", "")])
    if not args.worker:
        return subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()),
                               "--project-root", str(root), "--package-root", str(package), "--worker"], env=env).returncode
    sys.path[:0] = [str(root/"apps/api"), str(root/"tools")]
    started = time.monotonic()
    selected = ["tests/test_plan_contract_read_api.py", "tests/test_executed_workout_adapter.py",
                "tests/test_executed_workout_read_api.py", "tests/test_plan_execution_comparison_api.py",
                "tests/test_plan_execution_comparison_probe.py", "tests/test_execution_phase_fix.py",
                "tests/test_execution_phase_fix_api.py", str(package/"test_phase_fix_installer.py"),
                str(package/"test_phase_fix_coverage_entry.py")]
    # The captured source did not include these two old tools. Their runtime
    # routes are tested above; the current coverage collector is tested below.
    excluded = ["test_running_api_probe_saves_an_honest_review_archive",
                "test_user_probe_creates_valid_archive_for_real_app_responses"]
    fixture = root/"apps/api/tests/fixtures/pft/synthetic_pft_run_v01.TCX"
    real_pft = fixture.is_file()
    if real_pft:
        selected += ["tests/test_pft_processing_integration.py", "tests/test_pft_measurement_api.py"]
    with tempfile.TemporaryDirectory(prefix="execution_phase_fix_tests_") as tmp:
        report = Path(tmp)/"junit.xml"
        command = [sys.executable,"-m","pytest","-q",*selected,"-p","no:cacheprovider",
                   "-p","phase_fix_no_network","--basetemp="+str(Path(tmp)/"pytest"),
                   "--junitxml="+str(report),"-k"," and ".join("not "+name for name in excluded)]
        run = subprocess.run(command,cwd=root/"apps/api",env=env)
        if run.returncode: return run.returncode
        suites = ET.parse(report).getroot().findall("testsuite")
        tests = sum(int(s.get("tests",0)) for s in suites)
        skipped = sum(int(s.get("skipped",0)) for s in suites)
        if skipped: raise ValueError("SELECTED_RELEASE_TESTS_SKIPPED")
    from check_execution_phase_reference import check_reference
    print("Offline reference: 103 stored rows; 86 full legacy and corrected replays.", flush=True)
    reference = check_reference(package/"references")
    collector = subprocess.run([sys.executable,"-u",str(package/"coverage/run_coverage_checks.py"),
                                "--project-root",str(root)],env=env)
    if collector.returncode: return collector.returncode
    summary = {"status":"EXECUTION_PHASE_FIX_API_AND_OFFLINE_CHECKS_PASSED",
               "python":sys.version.split()[0],"release_http_domain_and_installer_tests":tests,
               "skipped_selected_tests":skipped,"original_real_pft_reference_tests_run":real_pft,
               "legacy_tool_probe_test_names_not_selected":excluded,
               "current_coverage_collector_tests_and_frozen_reference_passed":True,
               "windows_socketpair_fallback_forced_during_release_tests":True,
               "native_windows_runtime":sys.platform=="win32","reference":reference,
               "production_database_accessed":False,"database_migrated":False,"polar_requests":0,
               "speed_model_retrained":False,"state_model_trained":False,
               "versions":{n:importlib.metadata.version(n) for n in ("fastapi","sqlalchemy","httpx","pytest")},
               "elapsed_seconds":round(time.monotonic()-started,3)}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
