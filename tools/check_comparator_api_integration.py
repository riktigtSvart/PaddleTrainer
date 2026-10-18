"""HTTP/SQLite and frozen-reference checks without the production database."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

POST_SHA = "3b3b7f25c1828bcdaa535a1ec197257456bf6d39bef9fa3acca803e341948870"
EVIDENCE_SHA = "564253345e21c9147daa0fd1b84aa1d11c6ed0bd0cf826c651034fa95603a6be"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def archive(path, sha):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == sha, "REFERENCE_ZIP_HASH_DIFFERS")
    z = zipfile.ZipFile(path)
    require(z.testzip() is None, "REFERENCE_ZIP_CRC_ERROR")
    for name, entry in json.loads(z.read("OUTPUT_MANIFEST.json"))["files"].items():
        raw = z.read(name)
        require(len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["sha256"], "REFERENCE_MEMBER_HASH_DIFFERS")
    return z


def reference_check(reference_root):
    from app.planning_contracts.comparison_evidence import compare_execution_read, ComparisonError
    from app.planning_contracts.contract_checks import validate_contract
    from app.services.plan_execution_comparison_read import build_comparison_read, verify_comparison_read, ComparisonReadError
    with archive(reference_root / "post_import_read_reference.zip", POST_SHA) as z:
        captures = [json.loads(s) for s in gzip.decompress(z.read("unprotected_execution_captures.jsonl.gz")).splitlines()]
        inventory = json.loads(z.read("storage_before.json"))["sessions"]
    with archive(reference_root / "comparison_evidence_reference.zip", EVIDENCE_SHA) as z:
        original = {c["session_id"]: c for c in map(json.loads, gzip.decompress(z.read("comparisons.jsonl.gz")).splitlines())}
    counts = Counter()
    dev = {r["session_id"] for r in inventory if r["is_development"]}
    for read in captures:
        try:
            evidence = compare_execution_read(read)
        except ComparisonError as exc:
            require(str(exc) == "PLAN_EXECUTION_SPORT_MISMATCH", "UNEXPECTED_REFERENCE_WITHHOLD")
            counts["sport_withheld"] += 1
            continue
        require(evidence == original[read["session_id"]], "FROZEN_DESCRIPTIVE_COMPARISON_CHANGED")
        counts["unchanged_descriptive_comparison_count"] += 1
        try:
            value = build_comparison_read(read, include_bundle=True, include_source=True)
        except ComparisonReadError as exc:
            require(exc.code == "COMPARISON_NO_USABLE_OWNED_PLAN", "UNEXPECTED_COMPARISON_WITHHOLD")
            counts["no_plan"] += 1
            continue
        require(verify_comparison_read(value), "REFERENCE_API_RESPONSE_REPLAY_FAILED")
        validate_contract(value["comparison"]); validate_contract(value["integration_bundle"])
        counts["canonical_comparison_count"] += 1
        counts["candidate_row_count"] += sum(r["alignment_status"] == "MATCHED_CANDIDATE" for r in value["comparison"]["rows"])
        if read["session_id"] in dev:
            counts["development_canonical_comparison_count"] += 1
            counts["development_candidate_row_count"] += sum(r["alignment_status"] == "MATCHED_CANDIDATE" for r in value["comparison"]["rows"])
    require(len(captures) == 99 and len(inventory) == 103, "REFERENCE_COVERAGE_DIFFERS")
    require(counts["canonical_comparison_count"] == 86 and counts["no_plan"] == 8 and counts["sport_withheld"] == 5,
            "REFERENCE_ROUTING_COUNTS_DIFFERS")
    require(counts["unchanged_descriptive_comparison_count"] == 94 and counts["development_candidate_row_count"] == 147,
            "REFERENCE_DESCRIPTIVE_OR_DEVELOPMENT_COUNTS_DIFFERS")
    counts["protected_metadata_only_count"] = sum(r["protected_metadata_and_hash_only"] for r in inventory)
    return dict(counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--reference-root", required=True)
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve(); reference = Path(args.reference_root).resolve()
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root / "apps/api"), str(root / "apps/api/tests")]
    selected = ["tests/test_plan_contract_read_api.py", "tests/test_executed_workout_adapter.py",
                "tests/test_executed_workout_read_api.py", "tests/test_plan_execution_comparison_api.py",
                "tests/test_plan_execution_comparison_probe.py"]
    excluded, limitations = [], []
    for tool, name in (("probe_plan_contract_api.py", "test_running_api_probe_saves_an_honest_review_archive"),
                       ("probe_executed_workout_api.py", "test_user_probe_creates_valid_archive_for_real_app_responses")):
        if not (root / "tools" / tool).is_file():
            excluded.append(name)
    fixture = root / "apps/api/tests/fixtures/pft/synthetic_pft_run_v01.TCX"
    real_pft = fixture.is_file()
    if real_pft:
        selected += ["tests/test_pft_processing_integration.py", "tests/test_pft_measurement_api.py"]
    else:
        limitations.append("ORIGINAL_REAL_PFT_FIXTURE_UNAVAILABLE_REAL_REFERENCE_TESTS_NOT_RUN")
    if excluded:
        limitations.append("PRIOR_PROBE_TOOL_SOURCE_NOT_AVAILABLE_SOME_OLD_TOOL_PROBE_TESTS_NOT_RUN")
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1:1/comparison_checks_not_production"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(root / "apps/api"), str(root / "apps/api/tests"), env.get("PYTHONPATH", "")])
    with tempfile.TemporaryDirectory(prefix="comparator_api_tests_") as temp:
        report = Path(temp) / "report.xml"
        command = [sys.executable, "-m", "pytest", "-q", *selected, "--junitxml=" + str(report)]
        if excluded:
            command += ["-k", " and ".join("not " + name for name in excluded)]
        completed = subprocess.run(command, cwd=root / "apps/api", env=env)
        if completed.returncode:
            return completed.returncode
        suites = ET.parse(report).getroot().findall("testsuite")
        tests = sum(int(s.get("tests", 0)) for s in suites)
        skipped = sum(int(s.get("skipped", 0)) for s in suites)
        require(skipped == 0, "SELECTED_TESTS_WERE_SKIPPED")
    counts = reference_check(reference)
    versions = {name: importlib.metadata.version(name) for name in (
        "fastapi", "sqlalchemy", "pydantic-settings", "httpx", "asyncpg", "numpy", "scipy", "pytest")}
    summary = {"status": "COMPARISON_API_TESTS_AND_REFERENCE_CHECK_PASSED" if not limitations else
                         "COMPARISON_API_TESTS_AND_REFERENCE_CHECK_PASSED_WITH_LIMITATIONS",
               "python": sys.version.split()[0], "versions": versions,
               "http_and_domain_tests": tests, "skipped_selected_tests": skipped,
               "original_real_pft_reference_tests_run": real_pft,
               "synthetic_pft_http_regression_run": True, "old_tool_probe_tests_omitted": excluded,
               "reference": counts, "limitations": limitations,
               "production_database_accessed": False, "production_database_migrated": False,
               "http_test_database": "SQLITE_IN_MEMORY", "polar_requests": 0,
               "speed_model_retrained": False, "state_model_trained": False,
               "new_independent_test": False,
               "schema_checker_scope": "PINNED_SCHEMA_SUBSET_PLUS_DOMAIN_RULES_NOT_A_GENERAL_JSON_SCHEMA_ENGINE"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
