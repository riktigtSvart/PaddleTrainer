"""GET-only loopback probe; verifies one full comparator response replay."""
import argparse
from collections import Counter
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from app.planning_contracts.contract_checks import validate_contract
from app.services.plan_execution_comparison_read import API_RULES_VERSION, verify_comparison_read

MAX_RESPONSE_BYTES = 12 * 1024 * 1024
TOTAL_BYTES_LIMIT = 96 * 1024 * 1024
TRANSCRIPT = []
TOTAL_BYTES = 0


def require(condition, code):
    if not condition:
        raise ValueError(code)


def loopback_base(value):
    parsed = urllib.parse.urlsplit(value)
    require(parsed.scheme in {"http", "https"} and not parsed.username and not parsed.password and
            not parsed.query and not parsed.fragment and parsed.path in {"", "/"}, "LOOPBACK_BASE_URL_REQUIRED")
    host = parsed.hostname
    try:
        allowed = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        allowed = False
    require(allowed, "LOOPBACK_BASE_URL_REQUIRED")
    return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError("API_REDIRECT_NOT_ALLOWED")


def get_json(base, path):
    global TOTAL_BYTES
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(base + path, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            require(len(raw) <= MAX_RESPONSE_BYTES, "HTTP_RESPONSE_BYTE_LIMIT")
            TOTAL_BYTES += len(raw)
            require(TOTAL_BYTES <= TOTAL_BYTES_LIMIT, "HTTP_TOTAL_BYTE_LIMIT")
            TRANSCRIPT.append({"method": "GET", "path": path, "http_status": response.status,
                               "response_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        TRANSCRIPT.append({"method": "GET", "path": path, "http_status": exc.code})
        raise ValueError("API_HTTP_" + str(exc.code)) from None


def write_json(path, value):
    path.write_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")


def main(argv=None):
    global TOTAL_BYTES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args(argv)
    base = loopback_base(args.api_base_url)
    require(1 <= args.max_pages <= 100, "INVALID_PAGE_LIMIT")
    output = Path(args.output).resolve()
    archive_path = output.with_name(output.name + ".zip")
    require(not output.exists() and not archive_path.exists(), "OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True)
    TRANSCRIPT.clear(); TOTAL_BYTES = 0
    started = time.monotonic()
    summary = {"status": "COMPARISON_API_PROBE_NOT_COMPLETED", "sample_contract_round_trip_verified": False,
               "complete_history_coverage_claimed": False, "database_writes": 0, "polar_requests": 0,
               "numeric_output_authorized": False, "speed_model_retrained": False, "state_model_trained": False,
               "actual_phase_alignment_verified": False, "historical_plan_content_verified": False,
               "new_independent_test": False}
    code = 1
    try:
        caps = get_json(base, "/api/v1/planning/contracts/capabilities")
        require(caps.get("plan_execution_comparison_available") is True and
                caps.get("plan_execution_comparison_api_version") == API_RULES_VERSION,
                "COMPARISON_CAPABILITY_MISSING_RESTART_API_AFTER_INSTALL")
        write_json(output / "capabilities.json", caps)
        paths = get_json(base, "/openapi.json")["paths"]
        require("/api/v1/sessions/{session_id}/plan-execution-comparison" in paths and
                "/api/v1/planning/plan-execution-comparisons" in paths, "COMPARISON_ROUTES_NOT_REGISTERED")
        get_json(base, "/api/v1/pft/capabilities")
        offset, sample, reasons, pages, scanned = 0, None, Counter(), [], 0
        for _ in range(args.max_pages):
            require(time.monotonic() - started < 240, "PROBE_EXECUTION_TIME_LIMIT")
            page = get_json(base, "/api/v1/planning/plan-execution-comparisons?limit=5&offset=" + str(offset))
            require(page.get("api_rules_version") == API_RULES_VERSION and page.get("database_writes") == 0 and
                    page.get("provider_calls") == 0 and page.get("numeric_output_authorized") is False,
                    "PAGE_VERSION_OR_AUTHORITY_MISMATCH")
            items = page["items"]
            require(page["returned_count"] == len(items), "PAGE_RETURNED_COUNT_DIFFERS")
            pages.append(page); scanned += len(items)
            for item in items:
                if item["status"] == "WITHHELD":
                    require(item.get("comparison") is None, "WITHHELD_HAS_COMPARISON")
                    reasons[item["blocking_reason"]] += 1
                else:
                    validate_contract(item["comparison"])
                    if sample is None:
                        sample = item
            if sample is not None or not page["has_more"]:
                break
            next_offset = page.get("next_offset")
            require(type(next_offset) is int and next_offset == offset + len(items) and next_offset > offset,
                    "PAGINATION_DID_NOT_ADVANCE")
            offset = next_offset
        write_json(output / "pages.json", pages)
        if sample is not None:
            path = "/api/v1/sessions/" + sample["session_id"] + "/plan-execution-comparison?include_bundle=true&include_source=true"
            detail = get_json(base, path)
            require(detail["session_id"] == sample["session_id"] and
                    detail["source_content_sha256"] == sample["source_content_sha256"] and
                    detail["plan_source_content_sha256"] == sample["plan_source_content_sha256"],
                    "SOURCE_CHANGED_BETWEEN_LIST_AND_DETAIL")
            require(verify_comparison_read(detail) is not False, "FULL_COMPARISON_REPLAY_FAILED")
            validate_contract(detail["integration_bundle"])
            write_json(output / "detail.json", detail)
            summary.update(status="COMPARISON_API_READ_PROBE_PASSED", sample_contract_round_trip_verified=True,
                sample_session_id=detail["session_id"], sample_comparison_id=detail["comparison"]["comparison_id"],
                comparison_row_count=len(detail["comparison"]["rows"]))
        else:
            summary["status"] = "COMPARISON_API_REACHABLE_WITHOUT_ELIGIBLE_SAMPLE"
        summary.update(scanned_page_count=len(pages), scanned_session_count=scanned,
                       withheld_reasons=dict(reasons), old_pft_capability_available=True,
                       has_more_after_scanned_pages=bool(pages[-1]["has_more"]) if pages else False)
        code = 0
    except Exception as exc:
        summary.update(status="COMPARISON_API_READ_PROBE_FAILED", error_type=type(exc).__name__, reason=str(exc))
    summary.update(elapsed_seconds=round(time.monotonic() - started, 3), http_get_count=len(TRANSCRIPT))
    write_json(output / "summary.json", summary)
    write_json(output / "http_transcript.json", TRANSCRIPT)
    files = {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in output.iterdir() if p.is_file()}
    write_json(output / "OUTPUT_MANIFEST.json", {"files": files})
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            archive.write(path, path.name)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Visszaküldendő ZIP: " + str(archive_path))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
