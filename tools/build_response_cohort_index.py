"""Prepare pinned requests locally; verify via the existing configured owner's DB."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.response_cohort import ResponseCohortManifest
from app.services.response_cohort_assembly import assemble_response_cohort
from app.services.response_dataset_integrity import (
    MAX_DATASET_BYTES,
    check_response_dataset_integrity,
)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Non-finite JSON number")


def read_json(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input file size limit exceeded")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=_nonfinite)


def write_new_json(path, value):
    # No overwrite of a previous request, index or unrelated file.
    with Path(path).open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def prepare_manifest(members, manifest_id):
    """Files supply expected pins only. No DB, ownership or current-source proof."""
    selected = []
    for day, path in members:
        dataset = read_json(path, MAX_DATASET_BYTES)
        check_response_dataset_integrity(dataset)
        if dataset["split_assignment"]["status"] != "UNASSIGNED":
            raise ValueError("Prepare requires an UNASSIGNED full replay payload")
        replay = dataset["replay_evidence"]
        selected.append(
            {
                "provider": "POLAR",
                "athlete_id": dataset["athlete_id"],
                "session_external_id": dataset["session_external_id"],
                "route_date": day,
                "replay_snapshot_id": replay["snapshot_id"],
                "expected_snapshot_hash": replay["snapshot_hash"],
                "expected_evidence_set_id": replay["evidence_set_id"],
                "expected_evidence_hash": replay["evidence_hash"],
                "expected_unassigned_replay_package_hash": dataset["package_hash"],
                "expected_dataset_version": dataset["dataset_version"],
                "expected_snapshot_schema_version": "0.1",
            }
        )
    return ResponseCohortManifest.model_validate(
        {
            "schema_version": "0.1",
            "manifest_id": manifest_id,
            "members": selected,
        }
    )


async def verify_configured_owner(manifest):
    # Lazy imports keep prepare and malformed-input checks completely offline.
    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models.entities import User

    try:
        async with SessionLocal() as db:
            user = (
                await db.execute(select(User).where(User.email == get_settings().demo_user_email))
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("Configured existing demo user not found")
            return await assemble_response_cohort(db, manifest, user_id=user.id)
    finally:
        await engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Extract expected pins; no source verification")
    prepare.add_argument(
        "--member", action="append", nargs=2, metavar=("ROUTE_DATE", "FULL_REPLAY"), required=True
    )
    prepare.add_argument("--manifest-id", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Check selected real DB and current Polar sources")
    verify.add_argument("manifest", type=Path)
    verify.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            manifest = prepare_manifest(args.member, args.manifest_id)
            write_new_json(args.output, manifest.canonical_payload())
            result = {
                "status": "PINNED_REQUEST_PREPARED",
                "member_count": len(manifest.members),
                "request_manifest_hash": manifest.request_manifest_hash(),
                "claim_scope": "EXPECTED_PINS_FROM_LOCAL_FILES_ONLY",
                "source_evidence_verified": False,
                "training_authorized": False,
            }
        else:
            if args.output is not None and args.output.exists():
                raise ValueError("Output already exists; use a new output path")
            manifest = ResponseCohortManifest.model_validate(read_json(args.manifest, 1024 * 1024))
            result = asyncio.run(verify_configured_owner(manifest))
            if args.output is not None and result["source_evidence_verified"] is True:
                write_new_json(args.output, result)
                result = {
                    key: result[key]
                    for key in (
                        "status",
                        "requested_member_count",
                        "verified_member_count",
                        "request_manifest_hash",
                        "cohort_index_hash",
                        "source_evidence_verified",
                        "chronological_cohort_order_verified",
                        "totals",
                        "requested_split_counts",
                        "environmental_provider_calls",
                        "science_storage_writes",
                        "training_authorized",
                        "numeric_output_authorized",
                    )
                }
    except ValidationError as exc:
        result = {
            "status": "REJECTED",
            "errors": [
                {"loc": e["loc"], "type": e["type"], "message": e["msg"]}
                for e in exc.errors(include_input=False, include_url=False)
            ],
        }
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        result = {"status": "REJECTED", "reason": "COHORT_FILE_OR_LOCAL_CONFIGURATION_INVALID"}
    except (SQLAlchemyError, RuntimeError):
        result = {
            "status": "WITHHELD",
            "reason": "COHORT_LOCAL_DEPENDENCY_FAILURE",
            "source_evidence_verified": False,
            "training_authorized": False,
        }
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["status"] in {"REJECTED", "WITHHELD"} else 0


if __name__ == "__main__":
    sys.exit(main())
