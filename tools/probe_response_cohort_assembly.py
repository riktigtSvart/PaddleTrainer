"""One bounded loopback assembly probe; saves successful and non-200 JSON responses."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))

from app.schemas.response_cohort import ResponseCohortManifest  # noqa: E402
from app.services.environment_replay_snapshot import canonical_hash  # noqa: E402
from app.services.response_cohort_assembly import (  # noqa: E402
    _assembly_seconds,
    verify_cohort_index_integrity,
)
from app.services.response_dataset_split import resolve_dataset_split  # noqa: E402

API_URL = (
    "http://127.0.0.1:8000/api/v1/integrations/polar/"
    "response-cohorts/assemble?include_index=true"
)
REQUEST_TIMEOUT_SECONDS = 420
MAX_REQUEST_BYTES = 128 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
PIN_FIELDS = {
    "provider": "provider",
    "athlete_id": "athlete_id",
    "session_external_id": "session_external_id",
    "replay_snapshot_id": "replay_snapshot_id",
    "snapshot_hash": "expected_snapshot_hash",
    "evidence_set_id": "expected_evidence_set_id",
    "evidence_hash": "expected_evidence_hash",
    "unassigned_replay_package_hash": "expected_unassigned_replay_package_hash",
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "COHORT_PROBE_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def nonfinite(value):
    raise ValueError("COHORT_PROBE_NONFINITE_JSON")


def finite_float(value):
    number = float(value)
    require(math.isfinite(number), "COHORT_PROBE_NONFINITE_JSON")
    return number


def decode(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=nonfinite, parse_float=finite_float)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def write_new(path, raw):
    with path.open("xb") as destination:
        destination.write(raw)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def fetch_response(opener, body, response_path):
    request = Request(API_URL, data=body, headers={"Content-Type": "application/json"},
                      method="POST")
    started = monotonic()
    try:
        response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(raw) <= MAX_RESPONSE_BYTES, "COHORT_PROBE_RESPONSE_SIZE_LIMIT")
        # Save error bytes before parsing; a non-200 response is never promoted.
        write_new(response_path, raw)
        elapsed = monotonic() - started
        require(elapsed < REQUEST_TIMEOUT_SECONDS, "COHORT_PROBE_CLIENT_TIME_LIMIT")
        value = decode(raw)
        require(isinstance(value, dict), "COHORT_PROBE_RESPONSE_OBJECT_REQUIRED")
        return response.code, value, elapsed


def check_success(value, manifest):
    require(value.get("representation") == "FULL_INDEX", "COHORT_PROBE_FULL_INDEX_REQUIRED")
    index = value.get("cohort_index")
    require(isinstance(index, dict) and verify_cohort_index_integrity(index),
            "COHORT_PROBE_INDEX_INTEGRITY_FAILED")
    request = manifest.canonical_payload()
    require(index["request_manifest_hash"] == manifest.request_manifest_hash()
            and index["source_evidence_verified"] is True
            and index["verified_member_count"] == len(manifest.members),
            "COHORT_PROBE_REQUEST_BINDING_FAILED")
    require(index["execution_limits"]["max_assembly_seconds"]
            == _assembly_seconds(len(manifest.members)), "COHORT_PROBE_SERVER_BUDGET_MISMATCH")
    for name in ("training_authorized", "numeric_output_authorized",
                 "pre_exercise_prediction_authorized", "causal_prediction_authorized",
                 "split_assignment_persisted"):
        require(index[name] is False, "COHORT_PROBE_UNEXPECTED_AUTHORIZATION")
    for name in ("environmental_provider_calls", "science_storage_writes"):
        require(type(index[name]) is int and index[name] == 0,
                "COHORT_PROBE_UNEXPECTED_EXECUTION")
    for pin, member in zip(request["members"], index["members"]):
        require(all(member[name] == pin[expected] for name, expected in PIN_FIELDS.items()),
                "COHORT_PROBE_MEMBER_PIN_MISMATCH")
        split = resolve_dataset_split(request["split_manifest"], athlete_id=pin["athlete_id"],
                                      session_external_id=pin["session_external_id"])
        require(canonical_hash(split) == canonical_hash(member["requested_split"]),
                "COHORT_PROBE_SPLIT_BINDING_FAILED")
    return index


def run(request_path, output):
    with request_path.open("rb") as source:
        raw = source.read(MAX_REQUEST_BYTES + 1)
    require(len(raw) <= MAX_REQUEST_BYTES, "COHORT_PROBE_REQUEST_SIZE_LIMIT")
    source_hash = hashlib.sha256(raw).hexdigest()
    manifest = ResponseCohortManifest.model_validate(decode(raw))
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "cohort_request_input.json", raw)
    body = encode(manifest.canonical_payload())
    write_new(output / "cohort_request.json", body)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    status, value, elapsed = fetch_response(opener, body, output / "cohort_assemble_response.json")
    require(hashlib.sha256(request_path.read_bytes()).hexdigest() == source_hash,
            "COHORT_PROBE_INPUT_CHANGED")
    if status != 200:
        summary = {
            "HttpStatus": status, "Status": "WITHHELD", "ElapsedSeconds": round(elapsed, 3),
            "BlockingReasons": value.get("blocking_reasons"),
            "UpstreamReason": value.get("upstream_reason"),
            "FailedMemberCanonicalIndex": value.get("failed_member_canonical_index"),
            "SourceEvidenceVerified": False, "VerifiedMemberCount": 0,
            "ResponseFile": str(output / "cohort_assemble_response.json"),
        }
        write_new(output / "cohort_probe_summary.json", encode(summary))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2
    index = check_success(value, manifest)
    summary = {
        "HttpStatus": status, "Status": index["status"],
        "ElapsedSeconds": round(elapsed, 3),
        "ServerAssemblySeconds": index["execution_limits"]["max_assembly_seconds"],
        "VerifiedMemberCount": index["verified_member_count"],
        "SourceObservationCount": index["totals"]["observation_count"],
        "PreparationCandidateCount": index["totals"]["preparation_candidate_count"],
        "RequestedSplitCounts": index["requested_split_counts"],
        "ChronologicalOrderVerified": index["chronological_cohort_order_verified"],
        "ChronologicalSplitVerified": index["chronological_split_verified"],
        "TrainingBlockingReasons": index["training_blocking_reasons"],
        "SourceEvidenceVerified": True,
        "TrainingAuthorized": index["training_authorized"],
        "NumericOutputAuthorized": index["numeric_output_authorized"],
        "ScienceStorageWrites": index["science_storage_writes"],
        "CohortIndexHash": index["cohort_index_hash"],
        "ResponseFile": str(output / "cohort_assemble_response.json"),
    }
    write_new(output / "cohort_probe_summary.json", encode(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.request, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, URLError):
        print("A próba megállt; a már elkészült fájlok megmaradnak: " + str(args.output_dir))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
