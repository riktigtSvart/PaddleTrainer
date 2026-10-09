"""Local live E/3 control: preflight, capture/repeat, archive read and revalidation.

Run with project PYTHONPATH. Only archive rows are created; scientific tables
are read for preservation checks. No deletion, pin update or source fallback.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.schemas.response_cohort import ResponseCohortManifest
from app.services.response_cohort_assembly import verify_cohort_index_integrity
from app.services.response_cohort_storage_contract import (
    build_cohort_record_payload,
    check_cohort_record_payload,
)

# Running this file directly puts tools/, rather than its parent, on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.check_response_cohort_storage import (  # noqa: E402
    _constant,
    _float,
    _object,
    from_api_response,
    read_json,
)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SCIENCE_TABLES = (
    "workout_sessions",
    "heart_rate_timebase_snapshots",
    "hr_acquisition_declarations",
    "route_environment_evidence_sets",
    "route_environment_routes",
    "route_environment_segments",
    "route_environment_weather_samples",
    "route_environment_hydrology_measurements",
    "route_environment_replay_snapshots",
    "route_water_environment_identity_snapshots",
    "route_hydrology_source_resolution_snapshots",
    "route_hydrology_trust_decision_snapshots",
    "route_hydrology_relation_decision_snapshots",
    "route_trusted_environment_context_snapshots",
)


class CaptureControlError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise CaptureControlError(code)


def write_new(path, raw):
    with Path(path).open("xb") as destination:
        destination.write(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, payload=None, *, method="POST"):
    body = json.dumps(payload, allow_nan=False).encode() if method == "POST" else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=165)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(raw) <= MAX_RESPONSE_BYTES, "API_RESPONSE_SIZE_LIMIT")
        # Reuse the strict local decoder without accepting duplicate/nonfinite values.
        value = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=_object,
            parse_constant=_constant,
            parse_float=_float,
        )
        require(isinstance(value, dict), "API_RESPONSE_OBJECT_REQUIRED")
        return response.code, raw, value


async def _storage_state():
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with asyncio.timeout(30), engine.connect() as db:
            heads = (
                (await db.execute(text("SELECT version_num FROM alembic_version")))
                .scalars()
                .all()
            )
            require(heads == ["e4f7a92c1836"], "E2_DATABASE_HEAD_REQUIRED")
            counts = {
                name: (
                    await db.execute(text("SELECT count(*) FROM " + name))
                ).scalar_one()
                for name in (
                    *SCIENCE_TABLES,
                    "response_cohort_records",
                    "response_cohort_members",
                )
            }
            hr = {}
            for name in (
                "heart_rate_timebase_snapshots",
                "hr_acquisition_declarations",
            ):
                rows = (
                    (
                        await db.execute(
                            text("SELECT * FROM " + name + " ORDER BY id LIMIT 10001")
                        )
                    )
                    .mappings()
                    .all()
                )
                require(len(rows) <= 10000, "HR_PROOF_CONTROL_ROW_LIMIT")
                raw = json.dumps(
                    [dict(row) for row in rows],
                    sort_keys=True,
                    default=str,
                    allow_nan=False,
                ).encode()
                require(len(raw) <= 64 * 1024 * 1024, "HR_PROOF_CONTROL_BYTE_LIMIT")
                hr[name] = hashlib.sha256(raw).hexdigest()
            return {"counts": counts, "hr_proof_row_hashes": hr}
    finally:
        await engine.dispose()


def storage_state():
    return asyncio.run(_storage_state())


def _index(value):
    return (
        from_api_response(value)
        if value.get("representation") == "FULL_INDEX"
        else value
    )


def run(request_path, reference_path, output, base_url):
    url = urllib.parse.urlsplit(base_url)
    require(
        url.scheme == "http"
        and url.hostname in {"127.0.0.1", "localhost", "::1"}
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment,
        "LOCAL_LOOPBACK_API_URL_REQUIRED",
    )

    def input_bytes(path):
        with Path(path).open("rb") as source:
            return source.read(MAX_RESPONSE_BYTES + 1)

    original = {
        "request": input_bytes(request_path),
        "reference": input_bytes(reference_path),
    }
    require(
        all(len(raw) <= MAX_RESPONSE_BYTES for raw in original.values()),
        "LOCAL_INPUT_SIZE_LIMIT",
    )
    manifest = ResponseCohortManifest.model_validate(read_json(request_path))
    require(len(manifest.members) <= 20, "COHORT_MEMBER_EXECUTION_LIMIT")
    request = manifest.canonical_payload()
    reference = _index(read_json(reference_path))
    require(
        verify_cohort_index_integrity(reference)
        and reference.get("assembly_version") == "0.2.0",
        "FULL_C_OR_D_INDEX_REQUIRED",
    )
    expected = build_cohort_record_payload(
        manifest, reference, owner_id=manifest.members[0].athlete_id
    )
    check_cohort_record_payload(expected)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_new(
        output / "cohort_request.json",
        (json.dumps(request, indent=2, allow_nan=False) + "\n").encode(),
    )
    base = base_url.rstrip("/") + "/response-cohorts"

    def call(name, path, payload=None, method="POST"):
        status, raw, value = request_json(base + path, payload, method=method)
        write_new(output / (name + ".json"), raw)
        return status, raw, value

    def positive(name, path, payload=None, method="POST"):
        status, raw, value = call(name, path, payload, method)
        require(status == 200, name.upper() + "_HTTP_" + str(status))
        return raw, value

    def negative(name, path, payload, status, code, method="POST"):
        actual, _, value = call(name, path, payload, method)
        require(
            actual == status and value.get("blocking_reasons") == [code],
            name.upper() + "_REJECTION_FAILED",
        )
        require(
            value.get("record_id") is None
            and value.get("record_hash") is None
            and value.get("record_payload") is None
            and value.get("cohort_index") is None
            and value.get("current_source_evidence_verified") is False
            and value.get("storage_attempted") is False,
            name.upper() + "_PUBLISHED_PROOF_OR_WRITE",
        )
        return value

    before = storage_state()
    _, current = positive(
        "preflight_current_index", "/assemble?include_index=true", request
    )
    require(
        current.get("cohort_index") == reference,
        "CURRENT_C_INDEX_DIFFERS_NO_CAPTURE_PERFORMED",
    )
    # The local expected payload is a comparison target, never uploaded proof.
    _, first = positive("capture_first", "/capture", request)
    _, repeat = positive("capture_repeat", "/capture", request)
    require(
        first.get("status") in {"CREATED", "ALREADY_PRESENT"}
        and repeat.get("status") == "ALREADY_PRESENT",
        "CAPTURE_REPEAT_STATUS_FAILED",
    )
    require(
        first.get("record_hash")
        == repeat.get("record_hash")
        == expected["record_hash"],
        "E1_RECORD_HASH_CHANGED",
    )
    require(
        first.get("record_id") == repeat.get("record_id")
        and first.get("created_at") == repeat.get("created_at"),
        "REPEAT_ID_OR_TIME_CHANGED",
    )
    record_id = str(UUID(first["record_id"]))
    for value in (first, repeat):
        require(
            value.get("cohort_index_hash") == expected["cohort_index_hash"]
            and value.get("request_manifest_hash") == expected["request_manifest_hash"]
            and value.get("stored_member_count") == len(request["members"]),
            "CAPTURE_COMMITMENTS_OR_MEMBER_COUNT_FAILED",
        )
        require(
            all(
                value.get(key) is True
                for key in (
                    "round_trip_verified",
                    "commit_acknowledged",
                    "current_source_evidence_verified",
                    "source_evidence_verified",
                    "database_record_persisted",
                    "owner_authorization_verified",
                )
            ),
            "CAPTURE_PROOF_MISSING",
        )
        require(
            value.get("training_authorized") is False
            and value.get("numeric_output_authorized") is False,
            "CAPTURE_AUTHORITY_PROMOTED",
        )
        require(
            value.get("environmental_provider_calls") == 0
            and value.get("scientific_evidence_writes") == 0
            and value.get("dataset_split_assignment_persisted") is False
            and value.get("fixed_hr_shift_applied") is False
            and value.get("physiological_lag_ms") is None,
            "CAPTURE_SCIENTIFIC_BOUNDARY_CHANGED",
        )
    n = len(request["members"])
    require(
        first.get("cohort_storage_rows_written")
        == (n + 1 if first["status"] == "CREATED" else 0)
        and repeat.get("cohort_storage_rows_written") == 0,
        "CAPTURE_ROW_COUNT_FAILED",
    )
    record_uri = "/records/" + record_id
    _, summary = positive("archive_summary", record_uri, method="GET")
    full_raw, full = positive(
        "archive_full_1", record_uri + "?include_record=true", method="GET"
    )
    repeated_raw, repeated = positive(
        "archive_full_2", record_uri + "?include_record=true", method="GET"
    )
    require(
        summary.get("representation") == "SUMMARY"
        and summary.get("record_payload") is None,
        "DEFAULT_ARCHIVE_NOT_SUMMARY",
    )
    require(
        full.get("record_payload") == expected
        and full_raw == repeated_raw
        and full == repeated,
        "ARCHIVE_PAYLOAD_OR_BYTES_CHANGED",
    )
    require(
        full.get("record_id") == record_id
        and full.get("record_hash") == expected["record_hash"],
        "ARCHIVE_HEADER_BINDING_FAILED",
    )
    check_cohort_record_payload(full["record_payload"])
    require(
        full.get("current_source_evidence_verified") is False
        and full.get("source_evidence_verified") is False
        and full.get("storage_writes") == 0,
        "ARCHIVE_READ_PROMOTED_CURRENT_PROOF",
    )
    _, revalidation_summary = positive(
        "revalidation_summary", record_uri + "/revalidate", {}
    )
    _, live = positive(
        "revalidation_full", record_uri + "/revalidate?include_index=true", {}
    )
    require(
        live.get("current_source_evidence_verified") is True
        and live.get("current_index_matches_archived_record") is True
        and live.get("cohort_index") == reference,
        "CURRENT_REVALIDATION_FAILED",
    )
    require(
        live.get("storage_writes")
        == live.get("scientific_evidence_writes")
        == live.get("environmental_provider_calls")
        == 0
        and live.get("training_authorized") is False
        and live.get("numeric_output_authorized") is False
        and live.get("split_assignment_persisted") is False
        and live.get("fixed_hr_shift_applied") is False
        and live.get("physiological_lag_ms") is None,
        "REVALIDATION_SCIENTIFIC_BOUNDARY_CHANGED",
    )
    require(
        revalidation_summary.get("cohort_index") is None
        and revalidation_summary.get("summary") == live.get("summary"),
        "REVALIDATION_SUMMARY_MISMATCH",
    )
    after_positive = storage_state()
    wrong = deepcopy(request)
    old = wrong["members"][0]["expected_snapshot_hash"]
    wrong["members"][0]["expected_snapshot_hash"] = (
        "0" if old[0] != "0" else "1"
    ) + old[1:]
    bad_pin = negative(
        "wrong_pin", "/capture", wrong, 409, "COHORT_CURRENT_SOURCE_CHECK_FAILED"
    )
    require(
        bad_pin.get("upstream_reason") == "COHORT_SNAPSHOT_PIN_MISMATCH",
        "WRONG_PIN_REASON_FAILED",
    )
    negative(
        "forbidden_authority",
        "/capture",
        {**request, "training_authorized": True},
        422,
        "COHORT_REQUEST_INVALID",
    )
    negative(
        "local_candidate_as_input", "/capture", expected, 422, "COHORT_REQUEST_INVALID"
    )
    wrong_owner = deepcopy(request)
    wrong_owner["split_manifest"] = None
    foreign = str(uuid4())
    for member in wrong_owner["members"]:
        member["athlete_id"] = foreign
    negative(
        "wrong_owner_pin",
        "/capture",
        wrong_owner,
        403,
        "COHORT_CURRENT_SOURCE_CHECK_FAILED",
    )
    missing = "/records/" + str(uuid4())
    missing_read = negative(
        "missing_record_read",
        missing,
        None,
        404,
        "COHORT_RECORD_NOT_FOUND_OR_NOT_OWNED",
        "GET",
    )
    missing_revalidation = negative(
        "missing_record_revalidation",
        missing + "/revalidate",
        {},
        404,
        "COHORT_RECORD_NOT_FOUND_OR_NOT_OWNED",
    )
    require(missing_read == missing_revalidation, "MISSING_RECORD_RESPONSE_DIFFERS")
    negative(
        "forbidden_revalidation_authority",
        record_uri + "/revalidate",
        {"source_evidence_verified": True},
        422,
        "COHORT_REQUEST_INVALID",
    )
    final_raw, final = positive(
        "archive_after_negative_controls",
        record_uri + "?include_record=true",
        method="GET",
    )
    require(final_raw == full_raw and final == full, "PRIOR_ARCHIVE_CHANGED")
    after_negative = storage_state()
    require(after_negative == after_positive, "NEGATIVE_CONTROL_CHANGED_STORAGE")
    require(
        all(
            before["counts"][name] == after_positive["counts"][name]
            for name in SCIENCE_TABLES
        ),
        "PRIOR_SCIENCE_COUNTS_CHANGED",
    )
    require(
        before["hr_proof_row_hashes"] == after_positive["hr_proof_row_hashes"],
        "PRIOR_HR_PROOF_ROWS_CHANGED",
    )
    delta = 1 if first["status"] == "CREATED" else 0
    require(
        after_positive["counts"]["response_cohort_records"]
        - before["counts"]["response_cohort_records"]
        == delta
        and after_positive["counts"]["response_cohort_members"]
        - before["counts"]["response_cohort_members"]
        == delta * n,
        "ARCHIVE_TABLE_COUNT_DELTA_FAILED",
    )
    require(
        Path(request_path).read_bytes() == original["request"]
        and Path(reference_path).read_bytes() == original["reference"],
        "ORIGINAL_LOCAL_INPUT_BYTES_CHANGED",
    )
    result = {
        "Status": "COHORT_API_CAPTURE_AND_READBACK_VERIFIED",
        "FirstSave": first["status"],
        "RepeatSave": repeat["status"],
        "RecordId": record_id,
        "RecordHash": first["record_hash"],
        "CIndexHashPreserved": first["cohort_index_hash"],
        "SameRecordId": True,
        "SameCreationTime": True,
        "E1RecordHashPreserved": True,
        "CommitAcknowledged": True,
        "RoundTripVerified": True,
        "StoredMembers": n,
        "OriginalFullIndexPreserved": True,
        "RepeatedArchiveBytesIdentical": True,
        "ArchivedReadCurrentSourceProof": False,
        "ExplicitRevalidationCurrentSourceProof": True,
        "CurrentIndexMatchesArchivedRecord": True,
        "RecordCountsBefore": before["counts"]["response_cohort_records"],
        "RecordCountsAfter": after_positive["counts"]["response_cohort_records"],
        "MemberCountsBefore": before["counts"]["response_cohort_members"],
        "MemberCountsAfter": after_positive["counts"]["response_cohort_members"],
        "NegativeControlsPreservedStorage": True,
        "PriorScienceTableCountsPreserved": True,
        "PriorHRProofRowsPreserved": True,
        "WrongPinHttpStatus": 409,
        "WrongOwnerPinHttpStatus": 403,
        "ForbiddenAuthorityHttpStatus": 422,
        "LocalCandidateHttpStatus": 422,
        "MissingRecordHttpStatus": 404,
        "LiveForeignRecordOwnershipTestPerformed": False,
        "OriginalInputBytesPreserved": True,
        "ObservationCount": reference["totals"]["observation_count"],
        "HRSlots": reference["totals"]["hr_slot_count"],
        "PreparationCandidates": reference["totals"]["preparation_candidate_count"],
        "TemporalAuditStatus": reference["temporal_audit"]["status"],
        "ChronologicalOrderVerified": reference["chronological_cohort_order_verified"],
        "ChronologicalSplitVerified": reference["chronological_split_verified"],
        "EnvironmentalProviderCalls": 0,
        "ScientificEvidenceWrites": 0,
        "SplitAssignmentPersisted": False,
        "FixedHRShiftApplied": False,
        "PhysiologicalLagMs": None,
        "TrainingAuthorized": False,
        "NumericOutputAuthorized": False,
        "OutputFolder": str(output),
        "ClaimScope": "ACTUAL_API_CAPTURE_REVALIDATION_AND_LOCAL_STORAGE_PRESERVATION_CONTROL",
    }
    write_new(
        output / "live_summary.json", (json.dumps(result, indent=2) + "\n").encode()
    )
    write_new(
        output / "storage_preservation.json",
        (
            json.dumps(
                {
                    "before": before,
                    "after_positive": after_positive,
                    "after_negative": after_negative,
                },
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument(
        "--c-index",
        type=Path,
        required=True,
        help="Full C index or full D API response",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000/api/v1/integrations/polar"
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.request, args.c_index, args.output_dir, args.base_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except CaptureControlError as exc:
        print(
            json.dumps(
                {
                    "Status": "CONTROL_STOPPED",
                    "Reason": str(exc),
                    "OutputFolder": str(args.output_dir),
                    "AutomaticArchiveRemovalPerformed": False,
                }
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        # Never print credentials, database URLs, provider errors or private JSON.
        print(
            json.dumps(
                {
                    "Status": "CONTROL_STOPPED",
                    "Reason": "DEPENDENCY_OR_INPUT_FAILURE",
                    "OutputFolder": str(args.output_dir),
                    "AutomaticArchiveRemovalPerformed": False,
                }
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
