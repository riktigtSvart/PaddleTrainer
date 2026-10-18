"""Inspect the running local read-only API and save reviewable responses."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = Path(__file__).resolve().parents[1] / "apps/api"
sys.path.insert(0, str(API))
from app.planning_contracts.contract_checks import validate_contract
from app.planning_contracts.legacy_plan_adapter import digest, verify_result


def get_json(base, path):
    request = urllib.request.Request(base.rstrip("/") + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("API_PROBE_RESPONSE_SIZE_LIMIT")
        return json.loads(raw)


def verify_read(value):
    if value["numeric_output_authorized"] or value["database_writes"] or value["provider_calls"]:
        raise ValueError("API_READ_SCOPE_DIFFERS")
    if digest(value["source_snapshot"]) != value["source_content_sha256"]:
        raise ValueError("API_SOURCE_CONTENT_HASH_DIFFERS")
    verify_result(value["adapter_result"])
    validate_contract(value["adapter_result"]["plan"])
    for decision in value["applicability_decisions"]:
        validate_contract(decision)
        if decision["numeric_result_allowed"]:
            raise ValueError("API_PLAN_ROUTING_UNEXPECTEDLY_AUTHORIZES_NUMBERS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True, help="NEW output directory")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        capabilities = get_json(args.base_url, "/api/v1/planning/contracts/capabilities")
        (args.output / "capabilities.json").write_text(json.dumps(capabilities, indent=2), encoding="utf-8")
        if capabilities.get("api_rules_version") != "plan-contract-read-api-0.1-draft1" or not capabilities.get("read_only"):
            raise ValueError("PLAN_CONTRACT_API_CAPABILITY_VERSION_DIFFERS")
        page = get_json(args.base_url, "/api/v1/planning/plan-contracts?limit=2")
        (args.output / "page.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
        successful = [i for i in page["items"] if i["status"] != "WITHHELD"]
        for item in successful:
            verify_read(item)
        if successful:
            detail = get_json(args.base_url, "/api/v1/workouts/" + urllib.parse.quote(successful[0]["workout_id"], safe="") + "/plan-contract")
            verify_read(detail)
            (args.output / "detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {"status": "PLAN_CONTRACT_API_READ_PROBE_PASSED" if successful else "PLAN_CONTRACT_API_REACHABLE_WITHOUT_CONVERTED_SAMPLE",
                   "stored_plans_on_probe_page": len(page["items"]), "converted_sample_count": len(successful),
                   "withheld_sample_count": page["withheld_count"], "has_more_stored_plans": page["has_more"],
                   "sample_contract_round_trip_verified": bool(successful),
                   "empty_stored_plan_list": not page["items"], "database_writes": 0, "polar_requests": 0,
                   "numeric_output_authorized": False, "speed_model_retrained": False,
                   "historical_plan_content_verified": False, "actual_phase_alignment_verified": False}
        code = 0
    except (urllib.error.URLError, ValueError, KeyError, TypeError) as exc:
        summary = {"status": "PLAN_CONTRACT_API_READ_PROBE_STOPPED", "error_type": type(exc).__name__,
                   "reason": str(exc), "next": "If new routes return 404, restart the API process; source installation alone does not reload a running server.",
                   "database_writes": 0, "polar_requests": 0}
        code = 1
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = args.output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                zip_file.write(path, path.name)
    print(json.dumps({**summary, "output_folder": str(args.output.resolve()), "result_zip": str(archive.resolve())}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
