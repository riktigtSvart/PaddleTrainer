"""Prepare/check a local storage candidate; never write DB or verify live sources."""

import argparse
import json
import math
from pathlib import Path

from app.schemas.response_cohort import ResponseCohortManifest
from app.services.response_cohort_storage_contract import (
    MAX_RECORD_BYTES,
    build_cohort_record_payload,
    check_cohort_record_payload,
)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON constant")


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def read_json(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_RECORD_BYTES + 1)
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError("Local file size limit")
    return json.loads(
        raw.decode("utf-8-sig"),
        object_pairs_hook=_object,
        parse_constant=_constant,
        parse_float=_float,
    )


def from_api_response(response):
    # Explicit full response input only; no summary-to-index fallback.
    if (
        not isinstance(response, dict)
        or set(response)
        != {
            "schema_version",
            "representation",
            "cohort_index_hash_scope",
            "summary",
            "cohort_index",
        }
        or response["schema_version"] != "0.1"
        or response["representation"] != "FULL_INDEX"
        or response["cohort_index_hash_scope"]
        != "COMPLETE_INDEX_EXCLUDING_OWN_HASH_NOT_API_SUMMARY"
        or not isinstance(response["cohort_index"], dict)
        or not isinstance(response["summary"], dict)
        or response["summary"].get("cohort_index_hash")
        != response["cohort_index"].get("cohort_index_hash")
    ):
        raise ValueError("Full C/D API response required")
    return response["cohort_index"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Make a local candidate, not a database record")
    prepare.add_argument("--manifest", type=Path, required=True)
    inputs = prepare.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--index", type=Path)
    inputs.add_argument("--api-response", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("check", help="Verify local hashes/bindings only")
    check.add_argument("payload", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            manifest = ResponseCohortManifest.model_validate(read_json(args.manifest))
            index = (
                read_json(args.index)
                if args.index
                else from_api_response(read_json(args.api_response))
            )
            # This is an expected local owner pin, never a server identity proof.
            payload = build_cohort_record_payload(
                manifest, index, owner_id=manifest.members[0].athlete_id
            )
            result = check_cohort_record_payload(payload)
            with args.output.open("x", encoding="utf-8", newline="\n") as destination:
                destination.write(json.dumps(payload, indent=2, allow_nan=False) + "\n")
            result["status"] = "LOCAL_COHORT_STORAGE_CANDIDATE_PREPARED"
            result["local_candidate_written"] = True
        else:
            result = check_cohort_record_payload(read_json(args.payload))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        # Malformed files and local validation messages may contain private data.
        result = {
            "status": "REJECTED",
            "reason": "COHORT_RECORD_LOCAL_INPUT_OR_OUTPUT_INVALID",
            "claim_scope": "NO_STORAGE_OR_SOURCE_PROOF_ISSUED",
            "source_evidence_verified": False,
            "current_source_evidence_verified": False,
            "owner_authorization_verified": False,
            "database_record_persisted": False,
            "training_authorized": False,
            "numeric_output_authorized": False,
            "storage_writes": 0,
        }
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["status"] == "REJECTED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
