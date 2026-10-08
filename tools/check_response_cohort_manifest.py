"""Offline structural checker. Successful validation does not verify source evidence."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.schemas.response_cohort import ResponseCohortManifest

MAX_MANIFEST_FILE_BYTES = 1024 * 1024


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON object key")
        result[name] = value
    return result


def _reject_nonfinite(value):
    raise ValueError("Non-finite JSON number")


def check(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_MANIFEST_FILE_BYTES:
        raise ValueError("Manifest file exceeds 1 MiB")
    data = json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_reject_nonfinite
    )
    manifest = ResponseCohortManifest.model_validate(data)
    return {
        "status": "STRUCTURALLY_VALID_MANIFEST",
        "schema_version": manifest.schema_version,
        "task": manifest.task,
        "member_count": len(manifest.members),
        "requested_assignment_count": len(manifest.split_manifest.assignments)
        if manifest.split_manifest
        else 0,
        "request_manifest_hash": manifest.request_manifest_hash(),
        "claim_scope": "REQUEST_STRUCTURE_AND_COMMITMENT_ONLY",
        "source_evidence_verified": False,
        "chronological_cohort_order_verified": False,
        "split_assignment_persisted": False,
        "training_authorized": False,
        "numeric_output_authorized": False,
        "environmental_provider_calls": 0,
        "storage_writes": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        result = check(args.manifest)
    except ValidationError as exc:
        result = {
            "status": "REJECTED",
            "errors": [
                {"loc": error["loc"], "type": error["type"], "message": error["msg"]}
                for error in exc.errors(include_input=False, include_url=False)
            ],
        }
    except (OSError, ValueError, UnicodeError) as exc:
        result = {"status": "REJECTED", "reason": str(exc)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["status"] == "REJECTED" else 0


if __name__ == "__main__":
    sys.exit(main())
