"""Inspect the running local execution API and save replayable read-only evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = Path(__file__).resolve().parents[1] / "apps/api"
sys.path.insert(0, str(API))
from app.planning_contracts.execution_adapter import ADAPTER_VERSION, verify_execution_read


def get_json(base, path):
    request = urllib.request.Request(base.rstrip("/") + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("EXECUTION_PROBE_RESPONSE_SIZE_LIMIT")
        return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True, help="NEW output directory")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    code = 0
    try:
        capabilities = get_json(args.base_url, "/api/v1/planning/contracts/capabilities")
        (args.output / "capabilities.json").write_text(json.dumps(capabilities, indent=2), encoding="utf-8")
        if (not capabilities.get("read_only") or not capabilities.get("executed_workout_adapter_available")
                or capabilities.get("executed_workout_adapter_version") != ADAPTER_VERSION):
            raise ValueError("EXECUTION_API_CAPABILITY_VERSION_DIFFERS; restart the API after installing the execution adapter")
        page = get_json(args.base_url, "/api/v1/planning/executed-workouts?limit=2")
        (args.output / "page.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
        successful = [v for v in page["items"] if v["status"] != "WITHHELD"]
        for value in successful:
            verify_execution_read(value)
        stable = None
        if successful:
            detail = get_json(args.base_url, "/api/v1/sessions/" + urllib.parse.quote(successful[0]["session_id"], safe="") + "/executed-workout")
            verify_execution_read(detail)
            (args.output / "detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
            stable = successful[0]["source_content_sha256"] == detail["source_content_sha256"]
        executions = [v["adapter_result"]["executed"] for v in successful]
        summary = {"status": "EXECUTED_WORKOUT_API_READ_PROBE_PASSED" if successful else "EXECUTED_WORKOUT_API_REACHABLE_WITHOUT_CONVERTED_SAMPLE",
                   "stored_sessions_on_probe_page": len(page["items"]), "converted_sample_count": len(successful),
                   "withheld_sample_count": page["withheld_count"], "has_more_stored_sessions": page["has_more"],
                   "sample_contract_round_trip_verified": bool(successful), "same_stored_source_on_detail_read": stable,
                   "empty_stored_session_list": not page["items"],
                   "linked_plan_count_on_probe_page": sum(e["plan_ref"] is not None for e in executions),
                   "candidate_phase_count_on_probe_page": sum(b["execution_role"] == "PLAN_PHASE_CANDIDATE" for e in executions for b in e["blocks"]),
                   "native_grid_status_counts": dict(Counter(v["adapter_result"]["native_grid_audit"]["status"] for v in successful)),
                   "withheld_reasons": dict(Counter(v["blocking_reason"] for v in page["items"] if v["status"] == "WITHHELD")),
                   "database_writes": 0, "polar_requests": 0, "numeric_output_authorized": False,
                   "speed_model_retrained": False, "state_model_trained": False,
                   "historical_plan_content_verified": False, "actual_phase_alignment_verified": False,
                   "new_independent_test": False}
    except (urllib.error.URLError, ValueError, KeyError, TypeError) as exc:
        summary = {"status": "EXECUTED_WORKOUT_API_READ_PROBE_STOPPED", "error_type": type(exc).__name__, "reason": str(exc),
                   "next": "Send this archive; if the new routes return 404, restart the API after installation.",
                   "database_writes": 0, "polar_requests": 0}
        code = 1
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = args.output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(args.output.iterdir()):
            if path.is_file():
                z.write(path, path.name)
    print(json.dumps({**summary, "output_folder": str(args.output.resolve()), "result_zip": str(archive.resolve())}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
